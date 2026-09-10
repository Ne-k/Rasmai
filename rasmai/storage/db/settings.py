from datetime import datetime
from typing import List, Dict, Any
import json

from rasmai.storage.db.connection import _load_json_column, get_database_connection


def get_user_settings(user_id: str) -> Dict[str, Any]:
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT settings FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    finally:
        connection.close()
    return _load_json_column(row["settings"]) or {} if row else {}


def set_user_settings(user_id: str, settings: Dict[str, Any]) -> None:
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO user_settings (user_id, settings, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET settings = excluded.settings, updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(settings, ensure_ascii=False), datetime.now().isoformat()),
            )
    finally:
        connection.close()


def accounts_with_setting(flag: str) -> List[Dict[str, Any]]:
    """Linked accounts whose settings have `flag` switched on, with their stored profile.

    :rtype: List[Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            """
            SELECT a.user_id, a.region, a.official_profile, a.updated_at, s.settings
            FROM connected_accounts a JOIN user_settings s ON s.user_id = a.user_id
            """
        ).fetchall()
    finally:
        connection.close()
    out: List[Dict[str, Any]] = []
    for row in rows:
        settings = _load_json_column(row["settings"]) or {}
        if settings.get(flag):
            out.append({
                "userId": row["user_id"], "region": row["region"], "updatedAt": row["updated_at"],
                "officialProfile": _load_json_column(row["official_profile"]) or {},
            })
    return out


def get_guild_settings(guild_id: str) -> Dict[str, Any]:
    """Per-server switches set by people with Manage Server; empty when none were set.

    :param guild_id: The Discord server id.
    :type guild_id: str
    :rtype: Dict[str, Any]
    """
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT settings FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    finally:
        connection.close()
    return _load_json_column(row["settings"]) or {} if row else {}


def set_guild_settings(guild_id: str, settings: Dict[str, Any]) -> None:
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO guild_settings (guild_id, settings, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET settings = excluded.settings, updated_at = excluded.updated_at
                """,
                (guild_id, json.dumps(settings, ensure_ascii=False), datetime.now().isoformat()),
            )
    finally:
        connection.close()


def notified_rating(user_id: str) -> int:
    """The rating the person was last told about by the daily read, 0 when never.

    :param user_id: The Discord user id.
    :type user_id: str
    :rtype: int
    """
    connection = get_database_connection()
    try:
        row = connection.execute("SELECT rating FROM notify_state WHERE user_id = ?", (user_id,)).fetchone()
    finally:
        connection.close()
    return int(row["rating"]) if row else 0


def set_notified_rating(user_id: str, rating: int) -> None:
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO notify_state (user_id, rating, notified_at) VALUES (?, ?, ?)",
                (user_id, int(rating), datetime.now().isoformat(timespec="seconds")),
            )
    finally:
        connection.close()
