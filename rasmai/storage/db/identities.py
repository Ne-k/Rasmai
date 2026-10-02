from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional
import hashlib
import hmac
import re
import secrets
import sqlite3

from rasmai.security import decrypt_token, encrypt_token, get_master_secret
from rasmai.storage.db.accounts import _account_tables, _erase_debug_exports, _erase_from_backup
from rasmai.storage.db.connection import _load_json_column, get_database_connection

PROVIDERS = ("discord", "google")
_DISCORD_ID = re.compile(r"\d{5,25}")
_WEB_ID = re.compile(r"w[0-9a-f]{20}")
_TERMS_VERSION = re.compile(r"\d{4}-\d{2}-\d{2}")
_SUBJECT = re.compile(r"[A-Za-z0-9_.:-]{1,255}")
_NOT_DATA = ("identities", "people")      # the rows that name the account rather than belong to its data


def is_discord_id(user_id: Any) -> bool:
    return bool(_DISCORD_ID.fullmatch(str(user_id or "")))


def is_web_id(user_id: Any) -> bool:
    """An account made on the site with no Discord behind it: ``w`` and 20 hex digits. It is never a snowflake and never an admin."""
    return bool(_WEB_ID.fullmatch(str(user_id or "")))


def email_hash(email: Any) -> str:
    """Keyed hash of an email address, lowercased and trimmed, so the same person is recognised without keeping the address.

    :rtype: str
    """
    text = str(email or "").strip().lower()
    if not text:
        return ""
    return hmac.new(get_master_secret().encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def clean_identity(raw: Any) -> Dict[str, Any]:
    """One sign-in as the site reports it, checked: provider, subject, email and whether the provider vouched for it.

    :raises ValueError: for anything the site could not have sent.
    :rtype: Dict[str, Any]
    """
    if not isinstance(raw, dict):
        raise ValueError("identity must be an object")
    provider = str(raw.get("provider") or "")
    subject = str(raw.get("subject") or "")
    email = str(raw.get("email") or "").strip()
    if provider not in PROVIDERS:
        raise ValueError("unknown provider")
    if not _SUBJECT.fullmatch(subject) or (provider == "discord" and not is_discord_id(subject)):
        raise ValueError("bad subject")
    if len(email) > 254 or any(ord(char) < 32 or ord(char) == 127 for char in email):
        raise ValueError("bad email")
    return {"provider": provider, "subject": subject, "email": email, "emailVerified": raw.get("emailVerified") is True}


@contextmanager
def _transaction() -> Iterator[sqlite3.Connection]:
    """A write transaction that takes the lock first, so the lookups inside it cannot go stale before the writes."""
    connection = get_database_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        connection.commit()
    finally:
        connection.close()


def _exists(connection: sqlite3.Connection, user_id: str) -> bool:
    return bool(connection.execute(
        "SELECT 1 FROM connected_accounts WHERE user_id = ? UNION SELECT 1 FROM people WHERE user_id = ?",
        (user_id, user_id)).fetchone())


def account_exists(user_id: str) -> bool:
    """Whether a linked maimai account or a person made on the site is stored under this id.

    :rtype: bool
    """
    connection = get_database_connection()
    try:
        return _exists(connection, str(user_id))
    finally:
        connection.close()


def _summary(connection: sqlite3.Connection, user_id: str) -> Optional[Dict[str, Any]]:
    row = connection.execute("SELECT region, official_profile FROM connected_accounts WHERE user_id = ?",
                             (user_id,)).fetchone()
    if row is None:
        return None
    profile = _load_json_column(row["official_profile"]) or {}
    try:
        rating: Optional[int] = int(profile.get("rating"))
    except (TypeError, ValueError):
        rating = None
    return {"player": str(profile.get("name") or ""), "rating": rating, "region": str(row["region"] or "")}


def summaries(*user_ids: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """Who the linked maimai account of each id is, for asking which one to keep; ``None`` for an id with none.

    :rtype: Dict[str, Optional[Dict[str, Any]]]
    """
    connection = get_database_connection()
    try:
        return {user_id: _summary(connection, user_id) for user_id in user_ids}
    finally:
        connection.close()


def sign_in_providers(user_id: str) -> List[str]:
    """Which sign-ins open this account, in the order the site lists them.

    :rtype: List[str]
    """
    connection = get_database_connection()
    try:
        providers = {row[0] for row in connection.execute("SELECT provider FROM identities WHERE user_id = ?", (user_id,))}
    finally:
        connection.close()
    if is_discord_id(user_id):
        providers.add("discord")        # an account from before sign-ins were recorded is still reached by its Discord id
    return [name for name in PROVIDERS if name in providers]


def _signed_in(user_id: str, merged: Optional[str] = None) -> Dict[str, Any]:
    # `merged` names the site account that was folded into this one on the way, so the caller can drop what it holds in memory for it
    return {"status": "signed_in", "userId": user_id, **({"merged": merged} if merged else {})}


def _taken() -> Dict[str, Any]:
    return {"status": "error", "error": "identity_taken"}


def _attach(connection: sqlite3.Connection, provider: str, subject: str, user_id: str, hashed: str) -> None:
    connection.execute("INSERT OR IGNORE INTO identities (provider, subject, user_id, email_hash, created_at) "
                       "VALUES (?, ?, ?, ?, ?)", (provider, subject, user_id, hashed, datetime.now().isoformat()))
    if hashed:
        connection.execute("UPDATE identities SET email_hash = ? WHERE provider = ? AND subject = ? AND user_id = ?",
                           (hashed, provider, subject, user_id))


def _clear_data(connection: sqlite3.Connection, user_id: str) -> None:
    """Delete an account's data but not the rows naming it, which go on to the account that stays."""
    for table in _account_tables(connection):
        if table not in _NOT_DATA:
            connection.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (user_id,))


def _merge(connection: sqlite3.Connection, source: str, target: str, keep: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fold the site account `source` into the Discord account `target`, in the caller's transaction.

    :returns: ``None`` when it was done, or the question to ask when both sides have a linked maimai account and `keep` is not set.
    """
    has_source = connection.execute("SELECT 1 FROM connected_accounts WHERE user_id = ?", (source,)).fetchone()
    has_target = connection.execute("SELECT 1 FROM connected_accounts WHERE user_id = ?", (target,)).fetchone()
    if has_source and has_target:
        if keep not in ("from", "to"):
            return {"status": "needs_choice", "from": source, "to": target,
                    "fromSummary": _summary(connection, source), "toSummary": _summary(connection, target)}
        _clear_data(connection, target if keep == "from" else source)
    held = connection.execute("SELECT token FROM connected_accounts WHERE user_id = ?", (source,)).fetchone()
    opened = decrypt_token(str(held["token"] or ""), source) if held else ""
    for table in _account_tables(connection):
        if table not in _NOT_DATA:
            connection.execute(f'UPDATE OR IGNORE "{table}" SET user_id = ? WHERE user_id = ?', (target, source))
            connection.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (source,))
    if held:
        # sealed against its owner's id, so a row moved to another id would no longer open
        connection.execute("UPDATE connected_accounts SET token = ? WHERE user_id = ?", (encrypt_token(opened, target), target))
    mine = connection.execute("SELECT * FROM people WHERE user_id = ?", (source,)).fetchone()
    theirs = connection.execute("SELECT * FROM people WHERE user_id = ?", (target,)).fetchone()
    if mine and (not theirs or mine["created_at"] < theirs["created_at"]):
        connection.execute("DELETE FROM people WHERE user_id = ?", (target,))
        connection.execute("UPDATE people SET user_id = ? WHERE user_id = ?", (target, source))
    else:
        connection.execute("DELETE FROM people WHERE user_id = ?", (source,))
    connection.execute("UPDATE identities SET user_id = ? WHERE user_id = ?", (target, source))
    return None


def _resolve(connection: sqlite3.Connection, provider: str, subject: str, email: str, verified: bool,
             session: Optional[str], may_merge: bool = True) -> Dict[str, Any]:
    hashed = email_hash(email) if verified else ""
    if session and not _exists(connection, session):
        session = None          # a session for an account that has since been deleted proves nothing
    row = connection.execute("SELECT user_id FROM identities WHERE provider = ? AND subject = ?", (provider, subject)).fetchone()
    merged = None
    if row:
        user = row["user_id"]
        if session and session != user:
            if not (is_web_id(session) and is_discord_id(user)):
                return _taken()
            question = _merge(connection, session, user, None)
            if question:
                return question
            merged = session
        if hashed:
            _attach(connection, provider, subject, user, hashed)
        return _signed_in(user, merged)
    if session:
        target = session
        if provider == "discord":
            if is_discord_id(session) and session != subject:
                return _taken()         # a second Discord account cannot join an account that already has one
            if is_web_id(session):
                question = _merge(connection, session, subject, None)
                if question:
                    return question
                target, merged = subject, session
        _attach(connection, provider, subject, target, hashed)
        return _signed_in(target, merged)
    if hashed:
        matches = [r["user_id"] for r in connection.execute(
            "SELECT user_id FROM identities WHERE email_hash = ? ORDER BY created_at", (hashed,))]
        for user in matches:
            if provider == "discord" and is_discord_id(user) and user != subject:
                continue                # two Discord accounts that share an address are still two accounts
            if provider == "discord" and is_web_id(user):
                if not may_merge:
                    continue
                question = _merge(connection, user, subject, None)      # its data moves to the Discord id the bot reads by
                if question:
                    return question
                user, merged = subject, user
            _attach(connection, provider, subject, user, hashed)
            return _signed_in(user, merged)
    if provider == "discord" and _exists(connection, subject):
        _attach(connection, provider, subject, subject, hashed)       # an account from before sign-ins were recorded
        return _signed_in(subject)
    return {"status": "needs_terms"}


def resolve_identity(provider: str, subject: str, email: str = "", email_verified: bool = False,
                     session_user_id: Optional[str] = None) -> Dict[str, Any]:
    """Whose account a sign-in opens. Creates nothing but a link: a person who has to accept the terms first is told so.

    :returns: ``{"status": "signed_in", "userId"}``, ``{"status": "needs_terms"}``, ``{"status": "needs_choice", "from", "to",
        "fromSummary", "toSummary"}`` or ``{"status": "error", "error": "identity_taken"}``.
    :rtype: Dict[str, Any]
    """
    one = clean_identity({"provider": provider, "subject": subject, "email": email, "emailVerified": email_verified})
    with _transaction() as connection:
        return _resolve(connection, one["provider"], one["subject"], one["email"], one["emailVerified"],
                        str(session_user_id) if session_user_id else None)


def create_person(identities: List[Dict[str, Any]], terms_version: str) -> Dict[str, Any]:
    """Make the account once the person has accepted the terms; the Discord id when one of the sign-ins is Discord, else a new site id.

    Whatever the sign-ins already open is looked for again first, inside the same transaction, in case it appeared since.

    :raises ValueError: for a terms version that is not a date, or no sign-ins, or more than one Discord.
    :returns: ``{"status": "signed_in", "userId"}``.
    :rtype: Dict[str, Any]
    """
    if not _TERMS_VERSION.fullmatch(str(terms_version or "")):
        raise ValueError("bad terms version")
    cleaned = [clean_identity(one) for one in (identities or [])]
    if not 1 <= len(cleaned) <= 4 or sum(one["provider"] == "discord" for one in cleaned) > 1:
        raise ValueError("bad identities")
    with _transaction() as connection:
        for one in cleaned:
            found = _resolve(connection, one["provider"], one["subject"], one["email"], one["emailVerified"], None, may_merge=False)
            if found["status"] == "signed_in":
                # ponytail: every pending sign-in joins whichever account the first one opens, without a merge; route a Discord id
                # that lands on a site account through _merge if the sign-ins in one pending set can ever disagree
                for other in cleaned:
                    _attach(connection, other["provider"], other["subject"], found["userId"],
                            email_hash(other["email"]) if other["emailVerified"] else "")
                return found
        discord = next((one["subject"] for one in cleaned if one["provider"] == "discord"), None)
        user_id = discord or "w" + secrets.token_hex(10)
        now = datetime.now().isoformat()
        connection.execute("INSERT INTO people (user_id, created_at, terms_version, terms_accepted_at) VALUES (?, ?, ?, ?)",
                           (user_id, now, terms_version, now))
        for one in cleaned:
            _attach(connection, one["provider"], one["subject"], user_id, email_hash(one["email"]) if one["emailVerified"] else "")
        return _signed_in(user_id)


def merge_accounts(from_web_id: str, to_discord_id: str, keep: Optional[str] = None,
                   identity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Move a site account's data to a Discord id, and attach `identity` to it afterwards.

    When both have a linked maimai account nothing is deleted until `keep` says which: "from" keeps the site
    account's and discards the Discord id's, "to" the other way round.

    :raises ValueError: for ids of the wrong kind, or a `keep` that is neither "from" nor "to".
    :returns: ``{"status": "merged", "userId"}``, ``{"status": "needs_choice", ...}`` or ``{"status": "error", "error": ...}``.
    :rtype: Dict[str, Any]
    """
    if not is_web_id(from_web_id) or not is_discord_id(to_discord_id):
        raise ValueError("only a site account can be merged into a Discord id")
    if keep not in (None, "from", "to"):
        raise ValueError("bad keep")
    one = clean_identity(identity) if identity else None
    with _transaction() as connection:
        if not _exists(connection, from_web_id):
            return {"status": "error", "error": "not_found"}
        question = _merge(connection, from_web_id, to_discord_id, keep)
        if question:
            return question
        if one:
            owner = connection.execute("SELECT user_id FROM identities WHERE provider = ? AND subject = ?",
                                       (one["provider"], one["subject"])).fetchone()
            if owner and owner["user_id"] != to_discord_id:
                connection.rollback()
                return _taken()
            _attach(connection, one["provider"], one["subject"], to_discord_id,
                    email_hash(one["email"]) if one["emailVerified"] else "")
    if keep:
        # what was discarded may also sit in the pack backup and in debug exports, which a delete reaches
        loser = to_discord_id if keep == "from" else from_web_id
        _erase_from_backup(loser)
        _erase_debug_exports(loser)
    return {"status": "merged", "userId": to_discord_id, "from": from_web_id}
