from datetime import datetime
from typing import Any, Dict, List, Optional

from rasmai.storage.db.connection import get_database_connection

# What a tester can say about a beta. Three answers rather than a free-for-all, because the point
# is to compare one feature against no feature, and a sentence nobody can count says less than that.
VERDICTS = ("better", "same", "worse")

SAID_LIMIT = 500      # a note, not an essay: anything longer is cut rather than refused


def set_beta_feedback(user_id: str, feature: str, verdict: str, said: str = "") -> Optional[Dict[str, Any]]:
    """Record what one player made of one beta feature, replacing whatever they said before.

    :param user_id: The Discord user id.
    :type user_id: str
    :param feature: The feature's key, which the caller has already checked is a real one.
    :type feature: str
    :param verdict: One of :data:`VERDICTS`.
    :type verdict: str
    :param said: An optional note, cut to :data:`SAID_LIMIT`.
    :type said: str
    :returns: The stored row, or ``None`` if the verdict was not one of the three.
    :rtype: Optional[Dict[str, Any]]
    """
    if verdict not in VERDICTS:
        return None
    note = " ".join(str(said or "").split())[:SAID_LIMIT]
    now = datetime.now().isoformat(timespec="seconds")
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO beta_feedback (user_id, feature, verdict, said, said_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, feature) DO UPDATE SET
                    verdict = excluded.verdict, said = excluded.said, said_at = excluded.said_at
                """,
                (user_id, feature, verdict, note, now),
            )
    finally:
        connection.close()
    return {"feature": feature, "verdict": verdict, "said": note, "saidAt": now}


def beta_feedback_for(user_id: str) -> Dict[str, Dict[str, Any]]:
    """What this player has already said, keyed by feature, so the page can show it back to them.

    :rtype: Dict[str, Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT feature, verdict, said, said_at FROM beta_feedback WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        connection.close()
    return {row["feature"]: {"verdict": row["verdict"], "said": row["said"], "saidAt": row["said_at"]}
            for row in rows}


def beta_feedback(limit: int = 200) -> List[Dict[str, Any]]:
    """Everything anybody has said, newest first, for the developer page.

    :param limit: Most rows to return.
    :type limit: int
    :rtype: List[Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            """
            SELECT f.user_id, f.feature, f.verdict, f.said, f.said_at, a.official_profile
            FROM beta_feedback f LEFT JOIN connected_accounts a ON a.user_id = f.user_id
            ORDER BY f.said_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        connection.close()
    from rasmai.storage.db.connection import _load_json_column
    out = []
    for row in rows:
        profile = _load_json_column(row["official_profile"]) or {}
        out.append({"userId": row["user_id"], "feature": row["feature"], "verdict": row["verdict"],
                    "said": row["said"], "saidAt": row["said_at"],
                    "player": str(profile.get("name") or "")})
    return out


def beta_feedback_tally() -> Dict[str, Dict[str, int]]:
    """How many said what, per feature, so the page leads with the count rather than the prose.

    :rtype: Dict[str, Dict[str, int]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT feature, verdict, COUNT(*) AS n FROM beta_feedback GROUP BY feature, verdict"
        ).fetchall()
    finally:
        connection.close()
    tally: Dict[str, Dict[str, int]] = {}
    for row in rows:
        tally.setdefault(row["feature"], {v: 0 for v in VERDICTS})[row["verdict"]] = row["n"]
    return tally
