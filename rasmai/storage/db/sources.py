from datetime import datetime
from typing import List, Dict, Optional, Any
import hashlib
import json
import re
import zlib

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
    if row is None:
        return None
    state = dict(row)
    if isinstance(state.get("payload"), bytes):
        state["payload"] = zlib.decompress(state["payload"]).decode("utf-8")
    return state


def source_state_set(source: str, etag: Optional[str] = None, last_modified: Optional[str] = None,
                   payload: Optional[str] = None) -> None:
    """Update the fields given and leave the others as they were.

    A payload is stored deflated past a few kilobytes: the chart tables held here were 3.9 MB as
    text and are 0.6 MB packed. One left out is not touched, where it used to be read back and
    written again whole on every check that found nothing new.

    :param source: Which crawled source the stored state belongs to.
    :type source: str
    :param etag: The tag the site gave the copy already held.
    :type etag: Optional[str]
    :param payload: The crawled copy to keep, or None to leave the stored one.
    :type payload: Optional[str]
    """
    stored: Any = payload
    if payload is not None and len(payload) > 4096:
        stored = zlib.compress(payload.encode("utf-8"), 6)
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO news_state (source, etag, last_modified, payload, checked_at)
                VALUES (:source, COALESCE(:etag, ''), COALESCE(:modified, ''), COALESCE(:payload, ''), :now)
                ON CONFLICT(source) DO UPDATE SET
                    etag          = COALESCE(:etag, etag),
                    last_modified = COALESCE(:modified, last_modified),
                    payload       = COALESCE(:payload, payload),
                    checked_at    = :now
                """,
                {"source": source, "etag": etag, "modified": last_modified, "payload": stored,
                 "now": datetime.now().isoformat(timespec="seconds")},
            )
    finally:
        connection.close()


# one row in the shared source table holds whatever band the site should be showing
_NOTICE = "site-notice"

TONES = ("info", "notice", "warning")


MAX_NOTICE = 300

# the invisible ones: zero-width joiners and spaces, the bidi overrides that can display a link
# backwards, and the byte-order mark. A banner is read by strangers, so none of them survive.
_TRICKS = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]"
)


def _clean(notice: Dict[str, Any]) -> Dict[str, Any]:
    """Force a stored notice back into what a banner may contain, however it got into the table.

    Applied on the way in and on the way out, so a row written by anything other than the command
    still cannot put a script link or a wall of text in front of every visitor.

    :param notice: The notice as stored.
    :type notice: Dict[str, Any]
    :rtype: Dict[str, Any]
    """
    text = " ".join(_TRICKS.sub("", str(notice.get("text", "") or "")).split())[:MAX_NOTICE]
    link = str(notice.get("link", "") or "").strip()
    tone = str(notice.get("tone", "") or "")
    return {
        **notice,
        "text": text,
        "tone": tone if tone in TONES else "notice",
        # only ever a plain https address: anything else, javascript: most of all, is dropped rather than shown
        "link": link if re.fullmatch(r"https://[^\s<>'\"]{1,300}", link) else "",
        "id": str(notice.get("id", "") or "") if text else "",
    }


_FLAGS = "dev-flags"
_flags: Optional[Dict[str, Any]] = None       # read once: the one bot process is the only writer, and the gate asks on every command


def dev_flags_get() -> Dict[str, Any]:
    """The developer's switches: ``maintenance`` pauses every command for everyone but the developer, ``disabled`` names the commands
    switched off, and ``deletions`` off holds the hourly deletion of expired accounts.

    :rtype: Dict[str, Any]
    """
    global _flags
    if _flags is None:
        row = source_state_get(_FLAGS)
        try:
            stored = json.loads((row or {}).get("payload") or "{}")
        except json.JSONDecodeError:
            stored = {}
        _flags = {"maintenance": bool(stored.get("maintenance")), "disabled": sorted(str(name) for name in stored.get("disabled") or []),
                  "deletions": bool(stored.get("deletions", True))}
    return dict(_flags)


def dev_flags_set(**changes: Any) -> Dict[str, Any]:
    """Store the switches named, keeping the rest, so they hold across a restart.

    :param changes: ``maintenance`` and ``deletions`` as bools, ``disabled`` as the command names.
    :rtype: Dict[str, Any]
    """
    global _flags
    merged = {**dev_flags_get(), **changes}
    _flags = {"maintenance": bool(merged["maintenance"]), "disabled": sorted(set(merged["disabled"])), "deletions": bool(merged["deletions"])}
    source_state_set(_FLAGS, payload=json.dumps({**_flags, "setAt": datetime.now().isoformat(timespec="seconds")}))
    return dict(_flags)


_BOTS = "link-bots"


def link_bots_get() -> Dict[str, str]:
    """The bots the developer listed as verified for the Aime sign-in helper, as origin to name.

    :rtype: Dict[str, str]
    """
    row = source_state_get(_BOTS)
    try:
        stored = json.loads((row or {}).get("payload") or "{}")
    except json.JSONDecodeError:
        stored = {}
    return {str(origin): str(name) for origin, name in stored.items()} if isinstance(stored, dict) else {}


def link_bots_set(bots: Dict[str, str]) -> None:
    """Replace the list of verified bots.

    :param bots: Origin to name.
    :type bots: Dict[str, str]
    """
    source_state_set(_BOTS, payload=json.dumps(bots))


def site_notice_get() -> Optional[Dict[str, Any]]:
    """The banner the site should be showing, or ``None`` when one has never been set.

    An empty ``text`` is a banner that was deliberately taken down, which is not the same as
    never having set one: the site falls back to its built-in notice only in the second case.

    :rtype: Optional[Dict[str, Any]]
    """
    row = source_state_get(_NOTICE)
    if not row:
        return None
    try:
        stored = json.loads(row.get("payload") or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(stored, dict):
        return None
    return _clean(stored)


def site_notice_set(text: str, tone: str = "notice", link: str = "", by: str = "") -> Dict[str, Any]:
    """Put a banner up, or take it down by passing empty text.

    :param text: What the band should say; empty takes it down.
    :type text: str
    :param tone: One of ``info``, ``notice`` or ``warning``.
    :type tone: str
    :param link: An address to offer alongside the words, if any.
    :type link: str
    :param by: The Discord user id that set it, for the record.
    :type by: str
    :returns: The notice as stored.
    :rtype: Dict[str, Any]
    """
    notice = _clean({"text": text, "tone": tone, "link": link})
    # the words decide the id, so editing a notice shows it again to everyone who dismissed the last one
    notice["id"] = hashlib.sha256(notice["text"].encode("utf-8")).hexdigest()[:12] if notice["text"] else ""
    notice["setAt"] = datetime.now().isoformat(timespec="seconds")
    notice["setBy"] = str(by or "")
    source_state_set(_NOTICE, payload=json.dumps(notice, ensure_ascii=False))
    return notice
