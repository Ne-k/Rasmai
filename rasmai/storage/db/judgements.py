from typing import Any, Dict, List
import json

from rasmai.storage.db.connection import get_database_connection


def save_judgement(user_id: str, idx: str, chart_key: str, played_at: str, detail: Dict[str, Any]) -> None:
    """Keep one play's judgement page: the counts per note type, the timing split and the achievement.

    :param user_id: The Discord user id.
    :type user_id: str
    :param idx: The site's own id for the play.
    :type idx: str
    :param chart_key: The chart, as ``"title|type|difficulty"``.
    :type chart_key: str
    :param played_at: When the play happened, ISO 8601.
    :type played_at: str
    :param detail: The play's judgement page.
    :type detail: Dict[str, Any]
    """
    if not detail.get("notes"):
        return
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO play_judgements (user_id, idx, chart_key, played_at, achievement, fast, late, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, idx, chart_key, played_at, float(detail.get("achievement") or 0), int(detail.get("fast") or 0),
                 int(detail.get("late") or 0), json.dumps(detail["notes"], separators=(",", ":"))),
            )
    finally:
        connection.close()


def load_judgements(user_id: str) -> List[Dict[str, Any]]:
    """Every stored judgement page for a player, oldest first.

    :param user_id: The Discord user id.
    :type user_id: str
    :rtype: List[Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT idx, chart_key, played_at, achievement, fast, late, notes FROM play_judgements WHERE user_id = ? ORDER BY played_at",
            (user_id,),
        ).fetchall()
    finally:
        connection.close()
    out = []
    for row in rows:
        try:
            notes = json.loads(row["notes"])
        except ValueError:
            continue
        out.append({"idx": row["idx"], "chart_key": row["chart_key"], "played_at": row["played_at"],
                    "achievement": float(row["achievement"]), "fast": int(row["fast"]), "late": int(row["late"]), "notes": notes})
    return out


def judged_ids(user_id: str) -> set:
    """The play ids whose judgement page is already stored.

    :param user_id: The Discord user id.
    :type user_id: str
    :rtype: set
    """
    connection = get_database_connection()
    try:
        return {row["idx"] for row in connection.execute("SELECT idx FROM play_judgements WHERE user_id = ?", (user_id,))}
    finally:
        connection.close()


def delete_judgements(user_id: str) -> None:
    connection = get_database_connection()
    try:
        with connection:
            connection.execute("DELETE FROM play_judgements WHERE user_id = ?", (user_id,))
    finally:
        connection.close()
