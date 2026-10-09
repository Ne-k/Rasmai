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
                               "seen_at TEXT",                             # last time the person used the bot or the site
                               "avatar BLOB",                              # the profile picture's PNG, kept out of official_profile's JSON
                               "deletion_warned TEXT NOT NULL DEFAULT ''"):  # when the DM saying it will be deleted went out
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
                    CREATE TABLE IF NOT EXISTS news_subscriptions (   -- a channel following a source; the webhook URL is sealed, bound to its channel
                        channel_id TEXT NOT NULL,
                        source     TEXT NOT NULL,
                        guild_id   TEXT NOT NULL,
                        webhook    TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (channel_id, source)
                    )
                    """
                )
                try:
                    # whether the channel gets only the account's posts about maimai
                    setup.execute("ALTER TABLE news_subscriptions ADD COLUMN maimai_only INTEGER NOT NULL DEFAULT 0")
                    # until a channel could choose, Preformai's filter was the account's own and always on, so its channels keep it
                    setup.execute("UPDATE news_subscriptions SET maimai_only = 1 WHERE source = 'preformai'")
                except sqlite3.OperationalError:
                    pass          # already there
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_sources (   -- a public Bluesky or X account a server added to follow: nobody's private data
                        key        TEXT PRIMARY KEY,
                        platform   TEXT NOT NULL,
                        handle     TEXT NOT NULL,
                        did        TEXT NOT NULL DEFAULT '',
                        label      TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_seen (   -- posts already handled, so a restart sends nothing twice: nobody's data
                        source  TEXT NOT NULL,
                        post_id TEXT NOT NULL,
                        seen_at TEXT NOT NULL,
                        PRIMARY KEY (source, post_id)
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS status_samples (   -- the bot's own heartbeat, for the status page: nobody's data
                        at         TEXT PRIMARY KEY,
                        states     TEXT NOT NULL,
                        gateway_ms INTEGER NOT NULL DEFAULT 0,
                        waiting    INTEGER NOT NULL DEFAULT 0
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
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS people (   -- an account made on the site: who accepted which terms, and when
                        user_id           TEXT PRIMARY KEY,
                        created_at        TEXT NOT NULL,
                        terms_version     TEXT NOT NULL,
                        terms_accepted_at TEXT NOT NULL
                    )
                    """
                )
                setup.execute(
                    """
                    CREATE TABLE IF NOT EXISTS identities (   -- the sign-ins (Discord, Google) that open one account
                        provider   TEXT NOT NULL,
                        subject    TEXT NOT NULL,
                        user_id    TEXT NOT NULL,
                        email_hash TEXT NOT NULL DEFAULT '',   -- keyed hash of a verified email, never the email itself
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (provider, subject)
                    )
                    """
                )
                setup.execute("CREATE INDEX IF NOT EXISTS identities_email ON identities(email_hash)")
                setup.execute("CREATE INDEX IF NOT EXISTS identities_user ON identities(user_id)")
                _upgrade_stored_tokens(setup)
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
        # per connection, so set here rather than with the journal mode. NORMAL under WAL can lose the last
        # write to a power cut but never corrupts, and skips an fsync per commit; the mapping lets threads share pages
        connection.execute("PRAGMA synchronous=NORMAL")
        # a sign-in that is replaced or deleted is overwritten with zeroes, not left in a free page
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("PRAGMA mmap_size=268435456")
        connection.execute("PRAGMA temp_store=MEMORY")
        _kept.held = (path, connection)
    # set on every hand-out, so one caller changing it cannot change what the next caller reads
    connection.row_factory = sqlite3.Row
    return connection


def _upgrade_stored_tokens(setup: sqlite3.Connection) -> None:
    """Re-encrypt every stored sign-in not yet under the current encryption and key (see `rasmai.security`).

    Runs once, when the database is first opened. The old values are overwritten with zeroes as they
    are replaced, and the write-ahead log is checkpointed and emptied, so no copy under the old
    encryption is left in either file. A value that cannot be opened is left as it is, to be found
    and relinked the way an expired session is.

    :param setup: The connection the database is being set up on.
    :type setup: sqlite3.Connection
    """
    from rasmai.security import upgrade_token
    rows = setup.execute("SELECT user_id, token FROM connected_accounts").fetchall()
    changed = [(sealed, user_id) for user_id, token in rows
               if (sealed := upgrade_token(str(token or ""), str(user_id)))]
    if not changed:
        return
    setup.execute("PRAGMA secure_delete=ON")
    setup.executemany("UPDATE connected_accounts SET token = ? WHERE user_id = ?", changed)
    upgraded = len(changed)
    setup.commit()
    setup.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    logger.info("Re-encrypted %d stored sign-in(s) with AES-256-GCM", upgraded)


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
