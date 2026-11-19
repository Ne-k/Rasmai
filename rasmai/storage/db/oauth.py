from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional
import json
import sqlite3
import time

from rasmai.storage.db.connection import get_database_connection

_APP_COLUMNS = ("owner_name", "name", "description", "website", "privacy", "redirects", "secret_hash", "review", "icon")


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    connection = get_database_connection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _app(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return {**dict(row), "redirects": json.loads(row["redirects"])} if row else None


def oauth_app_add(app_id: str, user_id: str, owner_name: str, name: str, limit: int) -> bool:
    """Make an app for a developer who has fewer than ``limit`` of them; False when they are at the limit."""
    with _database() as connection:
        return bool(connection.execute(
            "INSERT OR IGNORE INTO oauth_apps (id, user_id, owner_name, name, created_at) SELECT ?, ?, ?, ?, ? "
            "WHERE (SELECT COUNT(*) FROM oauth_apps WHERE user_id = ?) < ?",
            (app_id, user_id, owner_name, name, datetime.now().isoformat(timespec="seconds"), user_id, limit)).rowcount)


def oauth_app_get(app_id: str) -> Optional[Dict[str, Any]]:
    with _database() as connection:
        return _app(connection.execute("SELECT * FROM oauth_apps WHERE id = ?", (app_id,)).fetchone())


def oauth_apps(user_id: str = "") -> List[Dict[str, Any]]:
    """One developer's apps, oldest first; every app when no developer is named."""
    with _database() as connection:
        return [_app(row) for row in connection.execute(
            "SELECT * FROM oauth_apps WHERE user_id = ? OR ? = '' ORDER BY rowid", (user_id, user_id))]


def oauth_app_set(app_id: str, **changes: Any) -> None:
    """Change an app's columns by name; ``redirects`` is given as a list."""
    changes = {column: json.dumps(value) if column == "redirects" else value for column, value in changes.items() if column in _APP_COLUMNS}
    if changes:
        with _database() as connection:
            connection.execute(f"UPDATE oauth_apps SET {', '.join(f'{column} = ?' for column in changes)} WHERE id = ?", (*changes.values(), app_id))


def oauth_purge() -> None:
    """Delete every ticket, code and token that has run out or whose app is gone, the sign-ins they held, and a gone app's picture."""
    with _database() as connection:
        connection.execute("DELETE FROM oauth_icons WHERE app_id NOT IN (SELECT id FROM oauth_apps)")
        for table in ("oauth_tickets", "oauth_codes", "oauth_tokens"):
            connection.execute(f"DELETE FROM {table} WHERE expires_at <= ? OR client_id NOT IN (SELECT id FROM oauth_apps)", (int(time.time()),))


def oauth_app_delete(app_id: str) -> None:
    """Delete an app, and its tickets, codes and tokens with it."""
    with _database() as connection:
        connection.execute("DELETE FROM oauth_apps WHERE id = ?", (app_id,))
    oauth_purge()


def oauth_app_block(app_id: str, blocked: bool) -> None:
    """Block or unblock an app. Blocking also deletes its tickets, codes and tokens, and the sign-ins they held."""
    with _database() as connection:
        connection.execute("UPDATE oauth_apps SET blocked = ? WHERE id = ?", (int(blocked), app_id))
        if blocked:
            for table in ("oauth_tickets", "oauth_codes", "oauth_tokens"):
                connection.execute(f"DELETE FROM {table} WHERE client_id = ?", (app_id,))


def oauth_icon_set(app_id: str, png: Optional[bytes]) -> None:
    """Keep an app's picture, or with None drop it."""
    with _database() as connection:
        if png is None:
            connection.execute("DELETE FROM oauth_icons WHERE app_id = ?", (app_id,))
        else:
            connection.execute("INSERT OR REPLACE INTO oauth_icons (app_id, png) VALUES (?, ?)", (app_id, png))


def oauth_icon_get(app_id: str) -> Optional[bytes]:
    with _database() as connection:
        row = connection.execute("SELECT png FROM oauth_icons WHERE app_id = ?", (app_id,)).fetchone()
        return bytes(row["png"]) if row else None


def oauth_ticket_add(ticket_hash: str, client_id: str, redirect_uri: str, scope: str, state: str, challenge: str, expires_at: int) -> None:
    with _database() as connection:
        connection.execute("INSERT INTO oauth_tickets (ticket_hash, client_id, redirect_uri, scope, state, challenge, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (ticket_hash, client_id, redirect_uri, scope, state, challenge, expires_at))


def oauth_ticket_get(ticket_hash: str, spend: bool = False) -> Optional[Dict[str, Any]]:
    """A ticket that has not run out. With ``spend`` it is deleted too, and only the one caller who deleted it gets it."""
    with _database() as connection:
        row = connection.execute("SELECT * FROM oauth_tickets WHERE ticket_hash = ? AND expires_at > ?", (ticket_hash, int(time.time()))).fetchone()
        if row and spend and not connection.execute("DELETE FROM oauth_tickets WHERE ticket_hash = ?", (ticket_hash,)).rowcount:
            return None
        return dict(row) if row else None


def oauth_code_add(code_hash: str, client_id: str, redirect_uri: str, scope: str, challenge: str, clal: str, clal_expires: int, expires_at: int) -> None:
    with _database() as connection:
        connection.execute("INSERT INTO oauth_codes (code_hash, client_id, redirect_uri, scope, challenge, clal, clal_expires, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (code_hash, client_id, redirect_uri, scope, challenge, clal, clal_expires, expires_at))


def oauth_code_get(code_hash: str) -> Optional[Dict[str, Any]]:
    """A code that has not run out, spent or not: ``used`` says which."""
    with _database() as connection:
        row = connection.execute("SELECT * FROM oauth_codes WHERE code_hash = ? AND expires_at > ?", (code_hash, int(time.time()))).fetchone()
        return dict(row) if row else None


def oauth_code_waiting(client_id: str, redirect_uri: str, challenge: str) -> Optional[Dict[str, Any]]:
    """The newest unspent code for a request, found by its PKCE challenge: for an app that is never handed its code."""
    with _database() as connection:
        row = connection.execute("SELECT * FROM oauth_codes WHERE client_id = ? AND redirect_uri = ? AND challenge = ? AND used = 0 AND expires_at > ? "
                                 "ORDER BY rowid DESC LIMIT 1", (client_id, redirect_uri, challenge, int(time.time()))).fetchone()
        return dict(row) if row else None


def oauth_code_spend(code_hash: str, token_hash: str, expires_at: int) -> bool:
    """Turn an unspent code into a token, moving the sign-in it held; False when someone else spent it first.

    The spent code is kept, without the sign-in, for as long as its token: that is how a second use of it is recognised.
    """
    with _database() as connection:
        if not connection.execute("UPDATE oauth_codes SET used = 1, expires_at = ? WHERE code_hash = ? AND used = 0 AND expires_at > ?",
                                  (expires_at, code_hash, int(time.time()))).rowcount:
            return False
        connection.execute("INSERT INTO oauth_tokens (token_hash, code_hash, client_id, scope, clal, clal_expires, expires_at) "
                           "SELECT ?, code_hash, client_id, scope, clal, clal_expires, expires_at FROM oauth_codes WHERE code_hash = ?", (token_hash, code_hash))
        connection.execute("UPDATE oauth_codes SET clal = '' WHERE code_hash = ?", (code_hash,))
        return True


def oauth_token_get(token_hash: str) -> Optional[Dict[str, Any]]:
    with _database() as connection:
        row = connection.execute("SELECT * FROM oauth_tokens WHERE token_hash = ? AND expires_at > ?", (token_hash, int(time.time()))).fetchone()
        return dict(row) if row else None


def oauth_tokens_drop(code_hash: str) -> None:
    """Delete the tokens made from one code."""
    with _database() as connection:
        connection.execute("DELETE FROM oauth_tokens WHERE code_hash = ?", (code_hash,))
