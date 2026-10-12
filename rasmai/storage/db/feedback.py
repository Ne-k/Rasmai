from datetime import datetime
from typing import Any, Dict, List, Optional

from rasmai.storage.db.connection import get_database_connection

# What a tester can say about a beta. Three answers rather than a free-for-all, because the point
# is to compare one feature against no feature, and a sentence nobody can count says less than that.
VERDICTS = ("better", "same", "worse")

SAID_LIMIT = 500      # a note, not an essay: anything longer is cut rather than refused

FORM_TEXT_LIMIT = 1000     # each answer on the site's feedback form
FORM_CONTACT_LIMIT = 200
FORM_MAX_ROWS = 5000       # the form is open to anybody, so it stops taking answers rather than fill the disk


def _form_text(value: Any, limit: int) -> str:
    """An answer cleaned for keeping: no control characters, lines kept, ends trimmed, cut to the limit."""
    text = "".join(ch for ch in str(value or "") if ch == "\n" or ch >= " ")
    return text.strip()[:limit]


def add_form_feedback(rating: Any, liked: Any = "", annoyed: Any = "", wish: Any = "", contact: Any = "") -> Optional[int]:
    """Keep one response to the feedback form.

    :param rating: How they are enjoying Rasmai, 1 to 5.
    :type rating: Any
    :param liked: What they like most.
    :type liked: Any
    :param annoyed: Anything that turns them off.
    :type annoyed: Any
    :param wish: What they would like added or changed.
    :type wish: Any
    :param contact: How to reach them, if they want a reply.
    :type contact: Any
    :returns: The new row's id; ``None`` when the rating is not a whole number from 1 to 5 or the form already holds as many as it takes.
    :rtype: Optional[int]
    """
    try:
        stars = int(rating)
    except (TypeError, ValueError):
        return None
    if not 1 <= stars <= 5:
        return None
    connection = get_database_connection()
    try:
        with connection:
            if connection.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] >= FORM_MAX_ROWS:
                return None
            cursor = connection.execute(
                "INSERT INTO feedback (created_at, rating, liked, annoyed, wish, contact) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), stars, _form_text(liked, FORM_TEXT_LIMIT),
                 _form_text(annoyed, FORM_TEXT_LIMIT), _form_text(wish, FORM_TEXT_LIMIT), _form_text(contact, FORM_CONTACT_LIMIT)),
            )
            return int(cursor.lastrowid)
    finally:
        connection.close()


def delete_form_feedback(feedback_id: Any) -> bool:
    """Take one response to the feedback form out, for a fake or bogus one. It is gone for good, and frees its place under the cap.

    :param feedback_id: The id the developer page lists the response under.
    :type feedback_id: Any
    :returns: ``True`` when there was a response with that id to remove.
    :rtype: bool
    """
    try:
        row_id = int(feedback_id)
    except (TypeError, ValueError):
        return False
    connection = get_database_connection()
    try:
        with connection:
            return connection.execute("DELETE FROM feedback WHERE id = ?", (row_id,)).rowcount > 0
    finally:
        connection.close()


def form_feedback(limit: int = 100) -> List[Dict[str, Any]]:
    """The newest responses to the feedback form, for the developer page.

    :param limit: Most rows to return.
    :type limit: int
    :rtype: List[Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT id, created_at, rating, liked, annoyed, wish, contact FROM feedback ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    finally:
        connection.close()
    return [{"id": row["id"], "at": row["created_at"], "rating": row["rating"], "liked": row["liked"],
             "annoyed": row["annoyed"], "wish": row["wish"], "contact": row["contact"]} for row in rows]


def form_feedback_summary() -> Dict[str, Any]:
    """How many have answered, the average rating, and how many gave each rating from 1 to 5.

    :rtype: Dict[str, Any]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute("SELECT rating, COUNT(*) AS n FROM feedback GROUP BY rating").fetchall()
    finally:
        connection.close()
    stars = {str(n): 0 for n in range(1, 6)}
    for row in rows:
        stars[str(row["rating"])] = int(row["n"])
    total = sum(stars.values())
    average = round(sum(int(k) * v for k, v in stars.items()) / total, 2) if total else 0.0
    return {"total": total, "average": average, "stars": stars}


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
