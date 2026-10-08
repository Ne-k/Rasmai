from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple
import logging

from rasmai.security import decrypt_token, encrypt_token
from rasmai.storage.db.connection import get_database_connection
from rasmai.storage.db.sources import source_state_get, source_state_set

logger = logging.getLogger(__name__)

SEEN_KEPT = 600      # posts remembered per source; the feeds show a few dozen, so this is plenty
JETSTREAM_STATE = "news:jetstream"


def _owner(channel_id: str) -> str:
    """What a webhook URL is bound to when it is sealed: its channel, so a row moved to another cannot be opened."""
    return f"news:{channel_id}"


def add_news_subscription(guild_id: str, channel_id: str, source: str, webhook_url: str) -> None:
    """Follow a source in a channel. The webhook URL is sealed here and never written any other way.

    :param guild_id: The Discord server id.
    :type guild_id: str
    :param channel_id: The channel the posts go to.
    :type channel_id: str
    :param source: The source key, such as ``"maimai"``.
    :type source: str
    :param webhook_url: The webhook that posts into the channel.
    :type webhook_url: str
    """
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "INSERT INTO news_subscriptions (channel_id, source, guild_id, webhook, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(channel_id, source) DO UPDATE SET webhook = excluded.webhook, guild_id = excluded.guild_id",
                (channel_id, source, guild_id, encrypt_token(webhook_url, _owner(channel_id)), datetime.now().isoformat()),
            )
    finally:
        connection.close()


def replace_channel_webhook(channel_id: str, webhook_url: str) -> None:
    """Point every source followed in a channel at a new webhook, for when the old one is gone."""
    connection = get_database_connection()
    try:
        with connection:
            connection.execute("UPDATE news_subscriptions SET webhook = ? WHERE channel_id = ?",
                               (encrypt_token(webhook_url, _owner(channel_id)), channel_id))
    finally:
        connection.close()


def news_webhook(channel_id: str) -> Optional[str]:
    """The webhook already made for a channel, so a second source reuses it; None when there is none or it cannot be opened."""
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT webhook FROM news_subscriptions WHERE channel_id = ? LIMIT 1", (channel_id,)).fetchone()
    finally:
        connection.close()
    return (decrypt_token(str(row["webhook"]), _owner(channel_id)) or None) if row else None


def news_subscribers(source: str) -> List[Tuple[str, str]]:
    """``(channel id, webhook URL)`` for everyone following a source. A row that cannot be opened (the key changed) is skipped."""
    connection = get_database_connection()
    try:
        rows = connection.execute("SELECT channel_id, webhook FROM news_subscriptions WHERE source = ?", (source,)).fetchall()
    finally:
        connection.close()
    out: List[Tuple[str, str]] = []
    for row in rows:
        url = decrypt_token(str(row["webhook"]), _owner(str(row["channel_id"])))
        if url:
            out.append((str(row["channel_id"]), url))
        else:
            logger.warning("a news webhook could not be opened, so its channel gets no posts")
    return out


def channel_sources(channel_id: str) -> List[str]:
    connection = get_database_connection()
    try:
        rows = connection.execute("SELECT source FROM news_subscriptions WHERE channel_id = ? ORDER BY source", (channel_id,)).fetchall()
    finally:
        connection.close()
    return [str(row["source"]) for row in rows]


def guild_news(guild_id: str) -> Dict[str, List[str]]:
    """Every channel in a server that follows something, with what it follows, in the order they were set up."""
    connection = get_database_connection()
    try:
        rows = connection.execute("SELECT channel_id, source FROM news_subscriptions WHERE guild_id = ? ORDER BY created_at, source", (guild_id,)).fetchall()
    finally:
        connection.close()
    out: Dict[str, List[str]] = {}
    for row in rows:
        out.setdefault(str(row["channel_id"]), []).append(str(row["source"]))
    return out


def news_subscription_count(guild_id: str) -> int:
    connection = get_database_connection()
    try:
        return int(connection.execute("SELECT COUNT(*) FROM news_subscriptions WHERE guild_id = ?", (guild_id,)).fetchone()[0])
    finally:
        connection.close()


def remove_news_subscription(channel_id: str, source: Optional[str] = None) -> int:
    """Stop following one source in a channel, or everything there when ``source`` is None. Returns the rows removed."""
    connection = get_database_connection()
    try:
        with connection:
            if source is None:
                cursor = connection.execute("DELETE FROM news_subscriptions WHERE channel_id = ?", (channel_id,))
            else:
                cursor = connection.execute("DELETE FROM news_subscriptions WHERE channel_id = ? AND source = ?", (channel_id, source))
            return cursor.rowcount
    finally:
        connection.close()


def remove_channel_webhook(channel_id: str, webhook_url: str) -> int:
    """Stop following whatever a channel follows through this webhook, which is gone. Rows already moved to a newer webhook stay."""
    connection = get_database_connection()
    try:
        with connection:
            rows = connection.execute("SELECT source, webhook FROM news_subscriptions WHERE channel_id = ?", (channel_id,)).fetchall()
            gone = [str(row["source"]) for row in rows if decrypt_token(str(row["webhook"]), _owner(channel_id)) == webhook_url]
            connection.executemany("DELETE FROM news_subscriptions WHERE channel_id = ? AND source = ?", [(channel_id, source) for source in gone])
            return len(gone)
    finally:
        connection.close()


def remove_unknown_news_sources(known: Iterable[str]) -> int:
    """Forget subscriptions to sources the bot no longer has, so they stop counting against a server's limit."""
    keys = list(known)
    connection = get_database_connection()
    try:
        with connection:
            return connection.execute(f"DELETE FROM news_subscriptions WHERE source NOT IN ({','.join('?' * len(keys))})", keys).rowcount
    finally:
        connection.close()


def remove_guild_news(guild_id: str) -> int:
    """Forget a server's subscriptions, for when the bot is removed from it."""
    connection = get_database_connection()
    try:
        with connection:
            return connection.execute("DELETE FROM news_subscriptions WHERE guild_id = ?", (guild_id,)).rowcount
    finally:
        connection.close()


def news_seen_any(source: str) -> bool:
    """Whether anything from this source has ever been recorded, which tells a first look from a later one."""
    connection = get_database_connection()
    try:
        return connection.execute("SELECT 1 FROM news_seen WHERE source = ? LIMIT 1", (source,)).fetchone() is not None
    finally:
        connection.close()


def news_unseen(source: str, post_ids: Iterable[str]) -> Set[str]:
    """Those of these posts not recorded yet."""
    ids = [str(i) for i in post_ids if i]
    if not ids:
        return set()
    connection = get_database_connection()
    try:
        marks = ",".join("?" * len(ids))
        known = {row[0] for row in connection.execute(f"SELECT post_id FROM news_seen WHERE source = ? AND post_id IN ({marks})", (source, *ids))}
    finally:
        connection.close()
    return set(ids) - known


def news_mark_seen(source: str, post_ids: Iterable[str]) -> None:
    """Record posts as handled, and drop the oldest records past ``SEEN_KEPT``."""
    ids = [str(i) for i in post_ids if i]
    if not ids:
        return
    now = datetime.now().isoformat()
    connection = get_database_connection()
    try:
        with connection:
            connection.executemany("INSERT OR IGNORE INTO news_seen (source, post_id, seen_at) VALUES (?, ?, ?)", [(source, i, now) for i in ids])
            connection.execute(
                "DELETE FROM news_seen WHERE source = ? AND rowid NOT IN "
                "(SELECT rowid FROM news_seen WHERE source = ? ORDER BY rowid DESC LIMIT ?)", (source, source, SEEN_KEPT))
    finally:
        connection.close()


def jetstream_alive() -> Optional[int]:
    """When the Jetstream connection was last known to be up, in microseconds since 1970, so a reconnect can ask for what it missed."""
    try:
        return int((source_state_get(JETSTREAM_STATE) or {}).get("payload") or "")
    except ValueError:
        return None


def save_jetstream_alive(micros: int) -> None:
    source_state_set(JETSTREAM_STATE, payload=str(micros))
