from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict
import threading
import os
import pickle
import shutil
import subprocess
import logging

from rasmai.scraping.otoge.loader import load_songs_from_repo
from rasmai.scraping.otoge.search import search_song

logger = logging.getLogger(__name__)


_update_lock = threading.Lock()   # one chart-database refresh at a time, however many analyses start together
_forced_at = None                  # when a read last forced a fetch; the analyses that ask soon after take that copy
_forced_ok = False                 # whether that fetch succeeded; a failure is not retried for every title that turns up meanwhile
FORCED_COOLDOWN = timedelta(minutes=10)


class CachedOtogeDB:
    def __init__(self, cache_dir: str = "otoge_cache", debug: bool = False):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.repo_path = self.cache_dir / "repo"
        self.jacket_dir = self.cache_dir / "jackets"
        self.cache_file = self.cache_dir / "songs_cache.pkl"
        self.last_update_file = self.cache_dir / "last_update.txt"
        self.refresh_after = timedelta(days=int(os.getenv("MAIMAI_DB_REFRESH_DAYS", "7")))
        self.songs_data = {}
        self.cover_cache = {}
        self.debug = debug
        self._load_cache()

    def _log(self, message: str, level: str = "info"):
        if self.debug:
            if level == "debug":
                logger.debug(message)
            elif level == "warning":
                logger.warning(message)
            elif level == "error":
                logger.error(message)
            else:
                logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)

    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    if isinstance(cached_data, dict):
                        if 'songs' in cached_data:
                            self.songs_data = cached_data.get('songs', {})
                            self.cover_cache = cached_data.get('covers', {})
                            self._log(
                                f"Loaded {len(self.songs_data)} songs and {len(self.cover_cache)} covers from cache",
                                "info")
                        else:
                            self.songs_data = cached_data
                            self.cover_cache = {}
                            for key, data in cached_data.items():
                                if isinstance(data, dict) and data.get('cover'):
                                    self.cover_cache[key] = data.get('cover')
                            self._log(
                                f"Converted old cache: {len(self.songs_data)} songs, {len(self.cover_cache)} covers",
                                "info")

                if len(self.cover_cache) == 0:
                    self._log("Cache has no cover data - forcing refresh", "warning")
                    self.songs_data = {}
                    self.cover_cache = {}
                    self.cache_file.unlink(missing_ok=True)

            except Exception as e:
                self._log(f"Error loading cache: {e}", "error")
                self.songs_data = {}
                self.cover_cache = {}

    def _save_cache(self):
        try:
            cache_data = {
                'songs': self.songs_data,
                'covers': self.cover_cache
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            self._log(f"Saved {len(self.songs_data)} songs and {len(self.cover_cache)} covers to cache", "info")
        except Exception as e:
            self._log(f"Error saving cache: {e}", "error")

    def _should_update(self) -> bool:
        if not self.songs_data or not self.cover_cache:
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
            self._log("Fetching otoge-db (maimai data + jackets only)", "info")
            subprocess.run(["git", "clone", "--depth=1", "--filter=blob:none", "--sparse",
                            "https://github.com/zvuc/otoge-db.git", str(self.repo_path)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(self.repo_path), "sparse-checkout", "set", "maimai/data", "maimai/jacket"],
                           check=True, capture_output=True)
            return True
        except Exception as error:
            self._log(f"Error fetching otoge-db: {error}", "error")
            return False

    def _keep_jackets(self) -> None:
        """Copy the checked-out jackets into jacket_dir before the checkout goes."""
        # ~65 KB per Discord thumbnail); re-encode through the Chromium Playwright already installs if that ever matters
        source = self.repo_path / "maimai" / "jacket"
        if source.exists():
            shutil.copytree(source, self.jacket_dir, dirs_exist_ok=True)

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

    def _load_songs_from_repo(self) -> bool:
        return load_songs_from_repo(self)

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

    def update_if_needed(self):
        with _update_lock:
            if not self._should_update():
                self._log("Using cached otoge-db data", "info")
                if self.repo_path.exists():
                    self._discard_repo()
                return
            self._fetch()

    def _fetch(self) -> bool:
        """Clone otoge-db, read the songs, keep the jackets, drop the checkout. Runs under ``_update_lock``.

        :returns: True when the songs were read from a fresh checkout.
        :rtype: bool
        """
        self._log("Updating otoge-db cache...", "info")
        before = len(self.songs_data)
        if not self._clone_or_update_repo():
            self._log("Keeping the chart database already held" if before else "No otoge-db data available", "error")
            return False
        if not self._load_songs_from_repo():
            self._discard_repo()
            self._log("The checkout held no song data; keeping the chart database already held", "error")
            return False
        self._keep_jackets()
        self._discard_repo()
        self.last_update_file.write_text(datetime.now().isoformat())
        logger.info("chart database fetched: %d songs, %d before", len(self.songs_data), before)
        return bool(self.songs_data)

    def search_song(self, song_name: str) -> Dict:
        return search_song(self, song_name)
