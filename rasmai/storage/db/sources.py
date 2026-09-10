from datetime import datetime
from typing import List, Dict, Optional, Any
import json

from rasmai.storage.db.connection import get_database_connection


def chart_videos_get(song: str) -> Optional[Dict[str, Any]]:
    """What the wiki said about a song: its page, chart videos and unlock notes; `unlock` is None if the page was read before notes were kept.

    :param song: The player's score on the chart.
    :type song: str
    :rtype: Optional[Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT page, videos, unlock, fetched_at FROM chart_videos WHERE song = ?", (song,)).fetchone()
    finally:
        connection.close()
    if not row:
        return None
    try:
        videos = json.loads(row["videos"] or "{}")
    except json.JSONDecodeError:
        videos = {}
    unlock: Optional[List[str]] = None
    if row["unlock"] is not None:
        try:
            unlock = [str(line) for line in json.loads(row["unlock"])]
        except (json.JSONDecodeError, TypeError):
            unlock = []
    return {"page": row["page"], "videos": videos, "unlock": unlock, "fetched_at": row["fetched_at"]}


def chart_videos_set(song: str, page: str, videos: Dict[str, str], unlock: Optional[List[str]] = None) -> None:
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO chart_videos (song, page, videos, unlock, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (song, page, json.dumps(videos, ensure_ascii=False), json.dumps(list(unlock or []), ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds")),
            )
    finally:
        connection.close()


def source_state_get(source: str) -> Optional[Dict[str, Any]]:
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT * FROM news_state WHERE source = ?", (source,)).fetchone()
    finally:
        connection.close()
    return dict(row) if row else None


def source_state_set(source: str, etag: Optional[str] = None, last_modified: Optional[str] = None,
                   payload: Optional[str] = None) -> None:
    """Update the fields given and leave the others as they were.

    :param source: Which crawled source the stored state belongs to.
    :type source: str
    :param etag: The tag the site gave the copy already held.
    :type etag: Optional[str]
    :param payload: The data to store or send.
    :type payload: Optional[str]
    """
    current = source_state_get(source) or {}
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO news_state (source, etag, last_modified, payload, checked_at) VALUES (?, ?, ?, ?, ?)",
                (source,
                 current.get("etag", "") if etag is None else etag,
                 current.get("last_modified", "") if last_modified is None else last_modified,
                 current.get("payload", "") if payload is None else payload,
                 datetime.now().isoformat(timespec="seconds")),
            )
    finally:
        connection.close()
