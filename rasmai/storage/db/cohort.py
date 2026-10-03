from typing import Dict, Iterator, Tuple

from rasmai.storage.db.connection import _load_json_column, get_database_connection


def cohort_accounts() -> Iterator[Tuple[str, int, Dict[str, float]]]:
    """Each linked account that has not opted out, as ``(user id, rating, best achievement per chart key)``, one at a time.

    The best is the highest achievement stored for the chart, the same number ``best_recorded_scores`` gives
    for one account. Accounts without a rating, and accounts whose settings say ``"cohort": false``, are
    left out; nobody who has unlinked is here, because the scores are read through ``connected_accounts``.

    :rtype: Iterator[Tuple[str, int, Dict[str, float]]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT a.user_id, a.official_profile, s.settings FROM connected_accounts a "
            "LEFT JOIN user_settings s ON s.user_id = a.user_id").fetchall()
        ratings: Dict[str, int] = {}
        for row in rows:
            if (_load_json_column(row["settings"]) or {}).get("cohort") is False:
                continue
            try:
                rating = int((_load_json_column(row["official_profile"]) or {}).get("rating") or 0)
            except (TypeError, ValueError):
                rating = 0
            if rating > 0:
                ratings[str(row["user_id"])] = rating
        # ordered by account, so one pass is enough and only one account's scores are held at a time
        cursor = connection.execute(
            "SELECT user_id, chart_key, MAX(achievement) AS best FROM chart_scores GROUP BY user_id, chart_key ORDER BY user_id")
        current, bests = "", {}
        for user_id, chart_key, best in cursor:
            if user_id != current:
                if current in ratings and bests:
                    yield current, ratings[current], bests
                current, bests = user_id, {}
            bests[str(chart_key)] = float(best)
        if current in ratings and bests:
            yield current, ratings[current], bests
    finally:
        connection.close()
