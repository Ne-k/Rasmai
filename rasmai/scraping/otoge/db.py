from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
import threading
import os
import pickle
import shutil
import subprocess
import logging

from rasmai.scraping.otoge import changes
from rasmai.scraping.otoge.loader import load_songs_from_repo

logger = logging.getLogger(__name__)


_update_lock = threading.Lock()   # one chart-database refresh at a time, however many analyses start together
_forced_at = None                  # when a read last forced a fetch; the analyses that ask soon after take that copy
_forced_ok = False                 # whether that fetch succeeded; a failure is not retried for every title that turns up meanwhile
FORCED_COOLDOWN = timedelta(minutes=10)

# The cache file as last read, handed to every instance: each analysis used to unpickle a copy of its
# own, about five megabytes, and the dashboard keeps five hundred analyses. Nothing writes into these
# tables once read; a refresh builds new ones, saves them, and the next instance reads the new file.
_read: Dict[str, tuple] = {}
_read_lock = threading.Lock()


class CachedOtogeDB:
    def __init__(self, cache_dir: str = "otoge_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.repo_path = self.cache_dir / "repo"
        self.jacket_dir = self.cache_dir / "jackets"
        self.cache_file = self.cache_dir / "songs_cache.pkl"
        self.last_update_file = self.cache_dir / "last_update.txt"
        self.refresh_after = timedelta(days=int(os.getenv("MAIMAI_DB_REFRESH_DAYS", "7")))
        self.songs_data = {}          # as Japan has it: the table the search and the jackets read
        self.songs_data_intl = {}     # as the international game has it, empty until a fetch has made one
        self._load_cache()

    def _load_cache(self):
        try:
            stat = self.cache_file.stat()
        except OSError:
            return
        stamp = (str(self.cache_file.resolve()), stat.st_mtime_ns, stat.st_size)
        with _read_lock:
            held = _read.get("file")
            if held is not None and held[0] == stamp:
                self.songs_data, self.songs_data_intl = held[1], held[2]
                return
            self._read_cache_file()
            if self.songs_data:
                _read["file"] = (stamp, self.songs_data, self.songs_data_intl)

    def _has_covers(self) -> bool:
        return any(song.get('cover') for song in self.songs_data.values())

    def _read_cache_file(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                if isinstance(cached_data, dict) and 'songs' in cached_data:
                    self.songs_data = cached_data['songs']
                    self.songs_data_intl = cached_data.get('songs_intl') or {}
                    logger.debug(f"Loaded {len(self.songs_data)} songs from cache")

                if not self._has_covers():
                    logger.warning("Cache has no cover data - forcing refresh")
                    self.songs_data = {}
                    self.cache_file.unlink(missing_ok=True)

            except Exception as e:
                logger.error(f"Error loading cache: {e}")
                self.songs_data = {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump({'songs': self.songs_data, 'songs_intl': self.songs_data_intl}, f)
            logger.debug(f"Saved {len(self.songs_data)} songs to cache")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def songs_for(self, region: Optional[str]) -> Dict[str, Any]:
        """The song table for a region: Japan's for ``"jp"``, the international game's for anything else.

        Until a fetch has made the international table (a cache from before it existed), Japan's stands in.

        :param region: ``"intl"``, ``"jp"``, ``"cn"`` or ``None``.
        :rtype: Dict[str, Any]
        """
        return self.songs_data if region == "jp" or not self.songs_data_intl else self.songs_data_intl

    def _should_update(self) -> bool:
        if not self._has_covers() or not self.songs_data_intl:
            return True
        if not any(self.jacket_dir.glob("*")):
            return True
        if self.last_update_file.exists():
            try:
                last_update = datetime.fromisoformat(self.last_update_file.read_text().strip())
                if datetime.now() - last_update < self.refresh_after:
                    return False
            except (OSError, ValueError):
                pass
        return True

    def _clone_or_update_repo(self) -> bool:
        """Fresh sparse clone of just the maimai data and jackets; the checkout is discarded once the jackets are moved out.

        :rtype: bool
        """
        self._discard_repo()     # a checkout left by an interrupted run is stale, and a forced fetch wants today's files
        try:
            logger.debug("Fetching otoge-db (maimai data + jackets only)")
            # Both run under _update_lock, so a stalled GitHub would hold up every analysis waiting on
            # the chart database for good; a timeout lands in the except below like any other failure.
            subprocess.run(["git", "clone", "--depth=1", "--filter=blob:none", "--sparse",
                            "https://github.com/zvuc/otoge-db.git", str(self.repo_path)],
                           check=True, capture_output=True, timeout=300)
            subprocess.run(["git", "-C", str(self.repo_path), "sparse-checkout", "set", "maimai/data", "maimai/jacket"],
                           check=True, capture_output=True, timeout=120)
            return True
        except Exception as error:
            logger.error(f"Error fetching otoge-db: {error}")
            return False

    def _keep_jackets(self) -> None:
        """Copy the checked-out jackets into jacket_dir before the checkout goes."""
        # ~65 KB per Discord thumbnail); re-encode through the Chromium Playwright already installs if that ever matters
        source = self.repo_path / "maimai" / "jacket"
        if source.exists():
            shutil.copytree(source, self.jacket_dir, dirs_exist_ok=True)
        # Most jackets come as a .png and a .webp, and everything that opens one tries the .webp
        # first, so the .png beside it is never read: 78 of the folder's 98 MB. A jacket that only
        # comes as a .png stays.
        for png in self.jacket_dir.glob("*.png"):
            if png.with_suffix(".webp").exists():
                png.unlink(missing_ok=True)

    def _discard_repo(self) -> None:
        if self.repo_path.exists():
            shutil.rmtree(self.repo_path, ignore_errors=True)
            if self.repo_path.exists():
                for path in self.repo_path.rglob("*"):
                    try:
                        path.chmod(0o666)
                    except OSError:
                        pass
                shutil.rmtree(self.repo_path, ignore_errors=True)

    def refresh_now(self) -> bool:
        """Fetch the database again whatever its age, because a read met a song it does not know.

        One forced fetch serves every analysis that asks within a few minutes: the later
        ones load the copy the first one wrote instead of cloning again.

        :returns: True when this instance now holds a database fetched just now.
        :rtype: bool
        """
        global _forced_at, _forced_ok
        with _update_lock:
            if _forced_at and datetime.now() - _forced_at < FORCED_COOLDOWN:
                if not _forced_ok:
                    return False
                self._load_cache()
                return bool(self.songs_data)
            _forced_at = datetime.now()
            _forced_ok = self._fetch()
            return _forced_ok

    def update_if_needed(self) -> bool:
        """Fetch the database when the copy held is older than the refresh interval; True when it was fetched.

        :rtype: bool
        """
        with _update_lock:
            if not self._should_update():
                logger.debug("Using cached otoge-db data")
                if self.repo_path.exists():
                    self._discard_repo()
                return False
            return self._fetch()

    def _fetch(self) -> bool:
        """Clone otoge-db, read the songs, keep the jackets, drop the checkout. Runs under ``_update_lock``.

        :returns: True when the songs were read from a fresh checkout.
        :rtype: bool
        """
        logger.debug("Updating otoge-db cache...")
        before = len(self.songs_data)
        if not self._clone_or_update_repo():
            logger.error("Keeping the chart database already held" if before else "No otoge-db data available")
            return False
        # compared with the saved copy, not this instance's own: the bot and the site both fetch, and only the first to see a change should report it
        old_jp, old_intl = changes.held(self.cache_file)
        if not load_songs_from_repo(self):
            self._discard_repo()
            logger.error("The checkout held no song data; keeping the chart database already held")
            return False
        self._keep_jackets()
        self._discard_repo()
        self.last_update_file.write_text(datetime.now().isoformat())
        logger.info("chart database fetched: %d songs, %d before", len(self.songs_data), before)
        changes.announce([("Japan", old_jp, self.songs_data), ("International", old_intl, self.songs_data_intl)])
        return bool(self.songs_data)
