from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import base64
import re
import secrets
import sqlite3

from rasmai.config import EXPIRED_ACCOUNT_DAYS, EXPIRED_ACCOUNT_WARN_DAYS
from rasmai.security import LOGIN_CODE_TTL, _hash_code, decrypt_token, encrypt_token
from rasmai.storage.db.connection import _dump_json_column, _load_json_column, get_database_connection
from rasmai.util import _json_safe


def issue_login_code(user_id: str, region: str) -> str:
    """Random, single-use, short-lived code bound to one Discord user.

    :param user_id: The Discord user id.
    :type user_id: str
    :param region: intl, jp or cn.
    :type region: str
    :rtype: str
    """
    code = secrets.token_urlsafe(24)
    now = datetime.now()
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "DELETE FROM login_codes WHERE created_at < ?", ((now - timedelta(days=1)).isoformat(),)
            )
            connection.execute(
                "INSERT INTO login_codes (code_hash, user_id, region, created_at) VALUES (?, ?, ?, ?)",
                (_hash_code(code), user_id, region, now.isoformat()),
            )
    finally:
        connection.close()
    return code


def _lookup_login_code(code: str, consume: bool) -> Optional[Tuple[str, str]]:
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", code):
        return None
    connection = get_database_connection()
    try:
        row = connection.execute(
            "SELECT user_id, region, created_at, used_at FROM login_codes WHERE code_hash = ?", (_hash_code(code),)
        ).fetchone()
        if row is None or row["used_at"]:
            return None
        try:
            if datetime.now() - datetime.fromisoformat(row["created_at"]) > LOGIN_CODE_TTL:
                return None
        except ValueError:
            return None
        if consume:
            with connection:
                updated = connection.execute(
                    "UPDATE login_codes SET used_at = ? WHERE code_hash = ? AND used_at IS NULL",
                    (datetime.now().isoformat(), _hash_code(code)),
                ).rowcount
            if not updated:
                return None
        return str(row["user_id"]), str(row["region"]), str(row["created_at"])
    finally:
        connection.close()


def login_code_issued_at(code: str) -> Optional[datetime]:
    """When a login code was issued, whether or not it has been used since.

    :param code: The login code.
    :type code: str
    :rtype: Optional[datetime]
    """
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", code):
        return None
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT created_at FROM login_codes WHERE code_hash = ?", (_hash_code(code),)).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    try:
        return datetime.fromisoformat(row["created_at"])
    except ValueError:
        return None


def peek_login_code(code: str) -> Optional[Tuple[str, str, str]]:
    return _lookup_login_code(code, consume=False)


def mark_login_code_verified(code: str) -> bool:
    """Record that the person holding this code passed the human check.

    :param code: The login code.
    :type code: str
    :rtype: bool
    """
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", code):
        return False
    connection = get_database_connection()
    try:
        with connection:
            return bool(connection.execute(
                "UPDATE login_codes SET verified_at = ? WHERE code_hash = ? AND used_at IS NULL",
                (datetime.now().isoformat(), _hash_code(code)),
            ).rowcount)
    finally:
        connection.close()


def login_code_verified(code: str) -> bool:
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", code):
        return False
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT verified_at FROM login_codes WHERE code_hash = ?", (_hash_code(code),)).fetchone()
    finally:
        connection.close()
    return bool(row and row["verified_at"])


def consume_login_code(code: str) -> Optional[Tuple[str, str, str]]:
    return _lookup_login_code(code, consume=True)


def login_code_expiry(created: Optional[datetime] = None) -> datetime:
    return (created or datetime.now()) + LOGIN_CODE_TTL


# the minute each account was last noted as active, so a run of commands writes once
_SEEN: Dict[str, str] = {}


def _split_avatar(profile: Any) -> Tuple[Any, Optional[bytes]]:
    """Take the avatar out of a profile, as the PNG's own bytes, for the ``avatar`` column.

    As base64 inside the profile's JSON it was about 8 KB an account, a third more than the
    picture itself. The profile stays plain JSON text, because the dashboard reads its name and
    rating with SQL. An avatar that would not come back as the same text is left where it is.

    :param profile: The profile as the caller passed it, or ``None``.
    :type profile: Any
    :returns: The profile without the avatar, and the avatar, or ``None`` when it had none.
    :rtype: Tuple[Any, Optional[bytes]]
    """
    if profile is None:
        return None, None
    profile = _json_safe(profile)     # a copy, so the caller's own dict keeps its avatar
    if not isinstance(profile, dict):
        return profile, None
    encoded = profile.pop("avatar_base64", None)
    if encoded:
        try:
            avatar = base64.b64decode(encoded, validate=True)
            if base64.b64encode(avatar).decode("ascii") == encoded:
                return profile, avatar
        except (TypeError, ValueError):
            pass
        profile["avatar_base64"] = encoded
    return profile, None


def upsert_connected_account(user_id: str, region: str, token: str, official_profile: Optional[Dict[str, Any]] = None, snapshot: Optional[Dict[str, Any]] = None) -> None:
    now = datetime.now().isoformat()
    official_profile, avatar = _split_avatar(official_profile)
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO connected_accounts
                    (user_id, region, token, official_profile, avatar, latest_snapshot, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    region           = excluded.region,
                    token            = excluded.token,
                    official_profile = COALESCE(excluded.official_profile, connected_accounts.official_profile),
                    avatar           = COALESCE(excluded.avatar, connected_accounts.avatar),
                    latest_snapshot  = COALESCE(excluded.latest_snapshot, connected_accounts.latest_snapshot),
                    updated_at       = excluded.updated_at,
                    session_expired  = '',
                    deletion_warned  = ''
                """,
                (
                    user_id,
                    region,
                    encrypt_token(token),
                    _dump_json_column(official_profile),
                    avatar,
                    _dump_json_column(snapshot, packed=True),
                    now,
                    now,
                ),
            )
    finally:
        connection.close()


def get_connected_account(user_id: str, with_snapshot: bool = True) -> Optional[Dict[str, Any]]:
    """The linked account, with its profile and, unless asked not to, its stored scores.

    :param user_id: The Discord user id.
    :type user_id: str
    :param with_snapshot: False skips reading the stored scores, which are most of an account's
        size and take unpacking; the result then has no ``latestSnapshot`` key at all, so
        ``account.get("latestSnapshot")`` is ``None``. Only for callers that never look at it.
    :type with_snapshot: bool
    :rtype: Optional[Dict[str, Any]]
    """
    columns = ("user_id, region, token, official_profile, avatar, created_at, updated_at, session_expired, "
               "share_slug, seen_at" + (", latest_snapshot" if with_snapshot else ""))
    connection = get_database_connection()
    try:
        row = connection.execute(
            f"SELECT {columns} FROM connected_accounts WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None
    profile = _load_json_column(row["official_profile"])
    # a profile stored before the avatar had its own column still carries it, and so does one whose
    # avatar would not have read back the same; either is at least as new as the column
    if profile is not None and row["avatar"] and not profile.get("avatar_base64"):
        profile["avatar_base64"] = base64.b64encode(row["avatar"]).decode("ascii")
    account = {
        "userId": row["user_id"],
        "region": row["region"],
        "token": decrypt_token(str(row["token"] or "")),
        "officialProfile": profile,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "sessionExpired": row["session_expired"] or "",
        "shareSlug": row["share_slug"] or "",
        "seenAt": row["seen_at"] or "",
    }
    if with_snapshot:
        account["latestSnapshot"] = _load_json_column(row["latest_snapshot"])
    return account


def touch_account(user_id: str) -> None:
    """Note that the person used the bot or the site just now, to the minute.

    Written at most once a minute per account so a burst of commands is one write, not dozens.

    :param user_id: The Discord user id.
    :type user_id: str
    """
    stamp = datetime.now().replace(second=0, microsecond=0).isoformat()
    if _SEEN.get(user_id) == stamp:
        return
    _SEEN[user_id] = stamp
    connection = get_database_connection()
    try:
        with connection:
            connection.execute("UPDATE connected_accounts SET seen_at = ? WHERE user_id = ?", (stamp, user_id))
    finally:
        connection.close()


def set_share_slug(user_id: str, slug: Optional[str]) -> Optional[str]:
    """Give the account a public profile address, or take it away with ``None``.

    A new slug replaces the old one, so a link that has been passed around stops working the
    moment the person asks for a fresh one.

    :param user_id: The Discord user id.
    :type user_id: str
    :param slug: The new slug, or ``None`` to remove the public profile.
    :type slug: Optional[str]
    :returns: The slug now in force, or ``None``.
    :rtype: Optional[str]
    """
    connection = get_database_connection()
    try:
        with connection:
            connection.execute("UPDATE connected_accounts SET share_slug = ? WHERE user_id = ?", (slug, user_id))
    finally:
        connection.close()
    return slug


def account_by_share_slug(slug: str) -> Optional[Dict[str, Any]]:
    """The account a public profile link points at, or ``None`` when nothing matches.

    :param slug: The slug from the address.
    :type slug: str
    :rtype: Optional[Dict[str, Any]]
    """
    if not slug or not re.fullmatch(r"[A-Za-z0-9_-]{10,64}", slug):
        return None
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT user_id FROM connected_accounts WHERE share_slug = ?", (slug,)).fetchone()
    finally:
        connection.close()
    return get_connected_account(str(row["user_id"])) if row else None


def mark_session_expired(user_id: str, when: str = "") -> None:
    """Record that maimai DX NET refused the saved sign-in, so the site can say so before the next read.

    The next successful ``/login`` clears it, because the upsert writes the column back to empty.

    :param user_id: The Discord user id.
    :type user_id: str
    :param when: When it was refused, ISO 8601; now by default.
    :type when: str
    """
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "UPDATE connected_accounts SET session_expired = ? WHERE user_id = ? AND session_expired = ''",
                (when or datetime.now().isoformat(timespec="seconds"), user_id),
            )
    finally:
        connection.close()


def _account_tables(connection: Any) -> List[str]:
    """Every table with a ``user_id`` column: all of it is one person's, and all of it goes with them.

    Read from the schema rather than listed by hand, so a table added later is never left behind.
    """
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return [name for name in tables
            if any(column[1] == "user_id" for column in connection.execute(f'PRAGMA table_info("{name}")'))]


def _delete_account_rows(connection: Any, user_id: str) -> bool:
    """Delete the account and every row stored against it, inside the caller's transaction."""
    tables = _account_tables(connection)
    cursor = connection.execute("DELETE FROM connected_accounts WHERE user_id = ?", (user_id,))
    for table in tables:
        if table != "connected_accounts":
            connection.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (user_id,))
    return cursor.rowcount > 0


def _erase(connection: Any, user_id: str, keep_if: Optional[Any] = None) -> bool:
    """Delete one account so its data cannot be read back out of the file.

    SQLite marks deleted rows free and leaves their bytes on disk until something else happens to
    overwrite them, and a copy of each changed page waits in the write-ahead log beside the file.
    ``secure_delete`` zeroes the freed space as the rows go, and the checkpoint afterwards writes the
    log back and empties it. A reader holding the log open can stop that emptying; the zeroed pages
    are then copied in by the next checkpoint instead, and the old frames overwritten as the log is reused.

    `keep_if` is asked inside the delete's own transaction, so a check it makes cannot go stale first.
    """
    connection.execute("PRAGMA secure_delete = ON")
    with connection:
        if keep_if is not None and keep_if(connection):
            return False
        deleted = _delete_account_rows(connection, user_id)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    _erase_from_backup(user_id)
    _erase_debug_exports(user_id)
    return deleted


def _erase_debug_exports(user_id: str) -> None:
    """Debug exports that name this account, when the operator has them switched on: they hold its whole read."""
    from rasmai.config import DEBUG_EXPORT_DIR
    try:
        exports = list(Path(DEBUG_EXPORT_DIR).glob("maimai-export-*.json"))
    except OSError:
        return
    mark = f'"userId": "{user_id}"'
    for path in exports:
        try:
            if mark in path.read_text(encoding="utf-8", errors="replace"):
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _erase_from_backup(user_id: str) -> None:
    """The same delete in the copy the one-off pack keeps beside the database, when there is one."""
    from rasmai.storage.db import connection as store     # the path is read at call time, as the checks swap it
    backup = Path(str(store.DATABASE_PATH) + ".before-pack")
    if not backup.exists():
        return
    copy = sqlite3.connect(str(backup))
    try:
        copy.execute("PRAGMA secure_delete = ON")
        with copy:
            _delete_account_rows(copy, user_id)
        copy.execute("VACUUM")      # a file nothing else writes to: rebuilt without the freed pages at all
    except sqlite3.Error:
        pass
    finally:
        copy.close()


def delete_connected_account(user_id: str) -> bool:
    connection = get_database_connection()
    try:
        return _erase(connection, user_id)
    finally:
        connection.close()


def _expired_moment(text: Any) -> Optional[datetime]:
    """The moment written in ``session_expired``, as local time; ``None`` when it is empty or unreadable."""
    try:
        when = datetime.fromisoformat(str(text or "").strip())
    except ValueError:
        return None
    if when.tzinfo is not None:
        when = when.astimezone().replace(tzinfo=None)      # the column is written in the server's local time
    return when


def session_deletes_at(expired_since: str) -> str:
    """When an account whose sign-in was refused at `expired_since` is deleted unless it is linked again.

    :param expired_since: The account's ``sessionExpired``.
    :type expired_since: str
    :returns: ISO 8601, or empty when it is not expired or expired accounts are kept.
    :rtype: str
    """
    when = _expired_moment(expired_since)
    if when is None or EXPIRED_ACCOUNT_DAYS <= 0:
        return ""
    return (when + timedelta(days=EXPIRED_ACCOUNT_DAYS)).isoformat(timespec="seconds")


def expired_accounts_due(now: Optional[datetime] = None, days: Optional[int] = None) -> List[Dict[str, str]]:
    """Accounts whose sign-in has been refused for `days` or longer, oldest first. Reads only.

    :param now: The moment to measure from.
    :type now: Optional[datetime]
    :param days: How long an account may stay expired; the configured allowance by default.
    :type days: Optional[int]
    :returns: ``{"userId", "since"}`` for each account due.
    :rtype: List[Dict[str, str]]
    """
    days = EXPIRED_ACCOUNT_DAYS if days is None else days
    if days <= 0:
        return []
    cutoff = (now or datetime.now()) - timedelta(days=days)
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT user_id, session_expired FROM connected_accounts WHERE session_expired <> ''").fetchall()
    finally:
        connection.close()
    due = []
    for row in rows:
        when = _expired_moment(row["session_expired"])
        if when is not None and when <= cutoff:
            due.append((when, {"userId": str(row["user_id"]), "since": str(row["session_expired"])}))
    return [entry for _when, entry in sorted(due, key=lambda pair: pair[0])]


def purge_expired_accounts(now: Optional[datetime] = None, days: Optional[int] = None) -> List[str]:
    """Delete every account whose sign-in has been refused for `days` or longer, as ``/delete-account`` would.

    Each account is looked at again inside its own delete, so one linked again between the listing
    and the delete is kept: a fresh ``/login`` clears ``session_expired``.

    :param now: The moment to measure from.
    :type now: Optional[datetime]
    :param days: How long an account may stay expired; the configured allowance by default.
    :type days: Optional[int]
    :returns: The Discord ids of the accounts deleted.
    :rtype: List[str]
    """
    days = EXPIRED_ACCOUNT_DAYS if days is None else days
    if days <= 0:
        return []
    cutoff = (now or datetime.now()) - timedelta(days=days)
    deleted: List[str] = []
    for entry in expired_accounts_due(now, days):
        def relinked(connection: Any, user_id: str = entry["userId"]) -> bool:
            row = connection.execute("SELECT session_expired FROM connected_accounts WHERE user_id = ?",
                                     (user_id,)).fetchone()
            when = _expired_moment(row["session_expired"]) if row else None
            return when is None or when > cutoff      # linked again since the listing: kept

        connection = get_database_connection()
        try:
            if _erase(connection, entry["userId"], keep_if=relinked):
                deleted.append(entry["userId"])
        finally:
            connection.close()
    return deleted


def accounts_to_warn(now: Optional[datetime] = None, days: Optional[int] = None,
                     warn_days: Optional[int] = None) -> List[Dict[str, str]]:
    """Accounts to be deleted within `warn_days` whose owner has not been warned yet. Reads only.

    :param now: The moment to measure from.
    :type now: Optional[datetime]
    :param days: How long an account may stay expired; the configured allowance by default.
    :type days: Optional[int]
    :param warn_days: How far ahead of the deletion to warn; the configured lead by default.
    :type warn_days: Optional[int]
    :returns: ``{"userId", "region", "since", "deletesAt"}`` for each account, soonest first.
    :rtype: List[Dict[str, str]]
    """
    days = EXPIRED_ACCOUNT_DAYS if days is None else days
    warn_days = EXPIRED_ACCOUNT_WARN_DAYS if warn_days is None else warn_days
    if days <= 0 or warn_days <= 0:
        return []
    now = now or datetime.now()
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT user_id, region, session_expired FROM connected_accounts "
            "WHERE session_expired <> '' AND deletion_warned = ''").fetchall()
    finally:
        connection.close()
    due = []
    for row in rows:
        since = _expired_moment(row["session_expired"])
        if since is None:
            continue
        deletes = since + timedelta(days=days)
        if deletes - timedelta(days=warn_days) <= now < deletes:
            due.append((deletes, {"userId": str(row["user_id"]), "region": str(row["region"] or "intl"),
                                  "since": str(row["session_expired"]),
                                  "deletesAt": deletes.isoformat(timespec="seconds")}))
    return [entry for _when, entry in sorted(due, key=lambda pair: pair[0])]


def mark_deletion_warned(user_id: str, when: str = "") -> None:
    """Record that the owner was sent the deletion warning, or that one was tried, so it goes once.

    :param user_id: The Discord user id.
    :type user_id: str
    :param when: When, ISO 8601; now by default.
    :type when: str
    """
    connection = get_database_connection()
    try:
        with connection:
            connection.execute("UPDATE connected_accounts SET deletion_warned = ? WHERE user_id = ?",
                               (when or datetime.now().isoformat(timespec="seconds"), user_id))
    finally:
        connection.close()


def update_account_snapshot(user_id: str, official_profile: Optional[Dict[str, Any]], snapshot: Optional[Dict[str, Any]]) -> None:
    """Refresh the stored profile and compact score snapshot after an analysis.

    :param user_id: The Discord user id.
    :type user_id: str
    :param snapshot: The stored copy of the player's scores.
    :type snapshot: Optional[Dict[str, Any]]
    """
    official_profile, avatar = _split_avatar(official_profile)
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                """
                UPDATE connected_accounts
                SET official_profile = COALESCE(?, official_profile),
                    -- a profile read without its picture keeps the one already held
                    avatar           = COALESCE(?, avatar),
                    latest_snapshot  = COALESCE(?, latest_snapshot),
                    updated_at       = ?,
                    -- a read that landed proves the session works, whatever an earlier one thought
                    session_expired  = '',
                    deletion_warned  = ''
                WHERE user_id = ?
                """,
                (_dump_json_column(official_profile), avatar, _dump_json_column(snapshot, packed=True),
                 datetime.now().isoformat(), user_id),
            )
    finally:
        connection.close()
