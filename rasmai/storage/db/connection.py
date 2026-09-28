from typing import Dict, Optional, Any
import json
import sqlite3
import threading
import logging
import zlib

from rasmai.config import DATABASE_PATH
from rasmai.util import _json_safe

logger = logging.getLogger(__name__)


_database_ready = False


_database_lock = threading.Lock()

# the connection each thread keeps, as (path it was opened on, connection)
_kept = threading.local()


class _KeptConnection(sqlite3.Connection):
    """A connection its thread holds on to and hands out again, instead of opening one per call.

    Opening one is not free: on the dashboard's overview, nine opens were twenty of its twenty-two
    milliseconds, and opens contend with each other, so eight threads served fewer requests a second
    than one. Every caller still closes what it opened, and close still throws away whatever that
    caller left uncommitted, which is all a real close ever did to their work. The handle itself is
    kept for the next caller on the same thread, and goes when the thread does.
    """

    def close(self) -> None:
        if self.in_transaction:
            self.rollback()

    def really_close(self) -> None:
        super().close()


def get_database_connection() -> sqlite3.Connection:
    """Open the local account database, creating it on first use.

    :rtype: sqlite3.Connection
    """
    global _database_ready
    with _database_lock:
        if not _database_ready:
            DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(DATABASE_PATH) as setup:
                setup.execute("PRAGMA journal_mode=WAL")
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS connected_accounts (
                        user_id          TEXT PRIMARY KEY,
                        region           TEXT NOT NULL,
                        token            TEXT NOT NULL,
                        official_profile TEXT,
                        latest_snapshot  TEXT,
                        created_at       TEXT NOT NULL,
                        updated_at       TEXT NOT NULL
                    )
                    """
                )
                for column in ("session_expired TEXT NOT NULL DEFAULT ''",
                               "share_slug TEXT",                          # the public profile link, unset until asked for
                               "seen_at TEXT"):                            # last time the person used the bot or the site
                    try:
                        setup.execute(f"ALTER TABLE connected_accounts ADD COLUMN {column}")
                    except sqlite3.OperationalError:
                        pass      # already there
                setup.execute("CREATE UNIQUE INDEX IF NOT EXISTS connected_accounts_share ON connected_accounts(share_slug)")
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS login_codes (
                        code_hash  TEXT PRIMARY KEY,
                        user_id    TEXT NOT NULL,
                        region     TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        used_at    TEXT
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id    TEXT PRIMARY KEY,
                        settings   TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rating_history (
                        user_id     TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        rating      INTEGER NOT NULL,
                        best50      INTEGER NOT NULL,
                        new_total   INTEGER NOT NULL,
                        old_total   INTEGER NOT NULL,
                        charts      INTEGER NOT NULL,
                        plays       INTEGER NOT NULL,
                        PRIMARY KEY (user_id, recorded_at)
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS area_progress (
                        user_id     TEXT NOT NULL,
                        kind        TEXT NOT NULL,
                        name        TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        distance    INTEGER NOT NULL,
                        next_reward INTEGER,
                        state       TEXT NOT NULL,
                        plays       INTEGER NOT NULL DEFAULT 0,
                        period_start TEXT,
                        period_end   TEXT,
                        PRIMARY KEY (user_id, kind, name, recorded_at)
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chart_play_counts (
                        user_id    TEXT NOT NULL,
                        chart_key  TEXT NOT NULL,
                        plays      INTEGER NOT NULL,
                        fetched_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, chart_key)
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_state (   -- crawl state per source (etag, payload, last check); the name predates the sources module
                        source        TEXT PRIMARY KEY,
                        etag          TEXT NOT NULL DEFAULT '',
                        last_modified TEXT NOT NULL DEFAULT '',
                        payload       TEXT NOT NULL DEFAULT '',
                        checked_at    TEXT NOT NULL
                    )
                    """
                )
                try:
                    setup.execute("ALTER TABLE login_codes ADD COLUMN verified_at TEXT")
                except sqlite3.OperationalError:
                    pass          # already there
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id   TEXT PRIMARY KEY,
                        settings   TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notify_state (
                        user_id     TEXT PRIMARY KEY,
                        rating      INTEGER NOT NULL DEFAULT 0,
                        notified_at TEXT NOT NULL
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quiet_reads (
                        user_id     TEXT PRIMARY KEY,
                        read_at     TEXT NOT NULL,
                        plays_added INTEGER NOT NULL DEFAULT 0,
                        error       TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS simai_sheets (
                        chart_key  TEXT PRIMARY KEY,
                        chart_id   TEXT NOT NULL DEFAULT '',
                        sheet      TEXT NOT NULL,
                        fetched_at TEXT NOT NULL
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chart_videos (
                        song       TEXT PRIMARY KEY,
                        page       TEXT NOT NULL DEFAULT '',
                        videos     TEXT NOT NULL DEFAULT '{}',
                        fetched_at TEXT NOT NULL
                    )
                    """
                )
                try:
                    setup.execute("ALTER TABLE chart_videos ADD COLUMN unlock TEXT")    # NULL until the page was read for it
                except sqlite3.OperationalError:
                    pass          # already there
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chart_scores (
                        user_id     TEXT NOT NULL,
                        chart_key   TEXT NOT NULL,
                        played_at   TEXT NOT NULL,
                        achievement REAL NOT NULL,
                        dx_score    INTEGER NOT NULL DEFAULT 0,
                        fc          TEXT NOT NULL DEFAULT '',
                        fs          TEXT NOT NULL DEFAULT '',
                        source      TEXT NOT NULL DEFAULT 'play',
                        PRIMARY KEY (user_id, chart_key, played_at)
                    )
                    """
                )
                for column in ("max_dx INTEGER NOT NULL DEFAULT 0", "track INTEGER NOT NULL DEFAULT 0",
                               "judgement TEXT NOT NULL DEFAULT ''"):
                    try:
                        setup.execute(f"ALTER TABLE chart_scores ADD COLUMN {column}")
                    except sqlite3.OperationalError:
                        pass      # already there
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS play_judgements (   -- one play's judgement page: counts per note type, timing split
                        user_id     TEXT NOT NULL,
                        idx         TEXT NOT NULL,
                        chart_key   TEXT NOT NULL,
                        played_at   TEXT NOT NULL,
                        achievement REAL NOT NULL,
                        fast        INTEGER NOT NULL DEFAULT 0,
                        late        INTEGER NOT NULL DEFAULT 0,
                        notes       TEXT NOT NULL,
                        PRIMARY KEY (user_id, idx)
                    )
                    """
                )
                for column in ("combo INTEGER NOT NULL DEFAULT 0", "max_combo INTEGER NOT NULL DEFAULT 0",
                               "sync INTEGER NOT NULL DEFAULT 0", "max_sync INTEGER NOT NULL DEFAULT 0"):
                    try:
                        setup.execute(f"ALTER TABLE play_judgements ADD COLUMN {column}")
                    except sqlite3.OperationalError:
                        pass      # already there
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS beta_feedback (   -- what one player made of one beta feature
                        user_id  TEXT NOT NULL,
                        feature  TEXT NOT NULL,
                        verdict  TEXT NOT NULL,
                        said     TEXT NOT NULL DEFAULT '',
                        said_at  TEXT NOT NULL,
                        PRIMARY KEY (user_id, feature)   -- the latest word, not a log: saying it twice replaces it
                    )
                    """
                )
            _database_ready = True

    # Keyed by the path as well as the thread: the sweep points DATABASE_PATH at a scratch file and
    # back, and a connection kept from before the swap would carry its writes into the real one.
    path = str(DATABASE_PATH)
    held = getattr(_kept, "held", None)
    if held is not None and held[0] == path:
        connection = held[1]
    else:
        if held is not None:
            held[1].really_close()
        connection = sqlite3.connect(DATABASE_PATH, timeout=10, factory=_KeptConnection)
        _kept.held = (path, connection)
    # set on every hand-out, so one caller changing it cannot change what the next caller reads
    connection.row_factory = sqlite3.Row
    return connection


def _dump_json_column(value: Optional[Dict[str, Any]], packed: bool = False) -> Optional[Any]:
    """JSON for a column; ``packed`` stores it deflated, which the stored score snapshot is, at about a fifth of its size.

    A packed value is a BLOB in a TEXT column, which SQLite keeps as it is given, and
    ``_load_json_column`` reads either. SQL's own JSON functions cannot see into one, so
    only a column nothing queries that way is packed.
    """
    if value is None:
        return None
    try:
        text = json.dumps(_json_safe(value), ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        logger.warning(f"Failed to serialise account column: {error}")
        return None
    return zlib.compress(text.encode("utf-8"), 6) if packed else text


def _load_json_column(value: Any) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        return json.loads(zlib.decompress(value) if isinstance(value, bytes) else value)
    except (TypeError, ValueError, zlib.error):
        return None
