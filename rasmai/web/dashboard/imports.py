from datetime import datetime
from typing import Any, Dict, List, Tuple

from rasmai.bot.state.snapshots import play_rows, snapshot_charts
from rasmai.storage.db import best_recorded_scores, import_rating_points, load_play_counts, record_chart_scores, save_play_counts

MAX_ROWS = 20000


def import_payload(user_id: str, data: Dict[str, Any], analyzer: Any) -> Dict[str, int]:
    """Merge an export the bot wrote back into the stored history; what is already there is left alone.

    Bests are dated to the export and only kept when they beat what is recorded, the plays on its
    recent list and its stored play history are added as plays, rating points keep their own dates,
    and a play count only ever goes up.

    :param user_id: The Discord user id.
    :type user_id: str
    :param data: The parsed export file.
    :type data: Dict[str, Any]
    :param analyzer: A scraper, for the title normalisation the recent list is keyed by.
    :type analyzer: Any
    :returns: How many bests, plays, rating points and play counts were new.
    :rtype: Dict[str, int]
    """
    if not isinstance(data, dict) or not isinstance(data.get("charts"), list) or not data.get("fields"):
        raise ValueError("That is not a Rasmai export: it has no chart table.")
    recorded_at = str(data.get("recordedAt") or "")
    try:
        datetime.fromisoformat(recorded_at)
    except ValueError:
        raise ValueError("That export carries no readable date.")

    known = best_recorded_scores(user_id)
    bests: List[Tuple[Any, ...]] = []
    for chart in snapshot_charts(data)[:MAX_ROWS]:
        name = str(chart.get("name") or "")
        tier = str(chart.get("difficulty_type") or "").lower()
        accuracy = round(float(chart.get("accuracy") or 0), 4)
        if not name or tier == "utage" or not 0 < accuracy <= 101:
            continue
        key = "|".join((name.casefold(), str(chart.get("chart_type") or "std").lower(), tier))
        if key not in known or accuracy > known[key] + 0.00005:
            bests.append((key, recorded_at, accuracy, int(chart.get("dx_score") or 0),
                          str(chart.get("fc_status") or ""), str(chart.get("fs_status") or ""), "best"))
            known[key] = accuracy

    plays = play_rows(analyzer, [r for r in data.get("recentPlays") or [] if isinstance(r, dict)][:200])
    for play in (data.get("playHistory") or [])[:MAX_ROWS]:
        if not isinstance(play, dict) or not play.get("key") or not play.get("played_at"):
            continue
        accuracy = round(float(play.get("achievement") or 0), 4)
        if 0 < accuracy <= 101:
            plays.append((str(play["key"]), str(play["played_at"]), accuracy, int(play.get("dx_score") or 0),
                          str(play.get("fc") or ""), str(play.get("fs") or ""), "play",
                          int(play.get("max_dx") or 0), int(play.get("track") or 0)))

    points = [(recorded_at, int(data.get("rating") or 0), int(data.get("best50") or 0), int(data.get("newTotal") or 0),
               int(data.get("oldTotal") or 0), len(data["charts"]), int(data.get("totalPlayCount") or 0))]
    for row in (data.get("ratingHistory") or [])[:MAX_ROWS]:
        if isinstance(row, dict) and row.get("recorded_at"):
            points.append((str(row["recorded_at"]), int(row.get("rating") or 0), int(row.get("best50") or 0), int(row.get("new_total") or 0),
                           int(row.get("old_total") or 0), int(row.get("charts") or 0), int(row.get("plays") or 0)))

    held = load_play_counts(user_id)
    counts: Dict[Tuple[str, str, str], int] = {}
    for key, value in (data.get("playCounts") or {}).items():
        parts = str(key).rsplit("|", 2)
        if len(parts) == 3 and int(value or 0) > held.get(tuple(parts), 0):
            counts[(parts[0], parts[1], parts[2])] = int(value)
    if counts:
        save_play_counts(user_id, counts)

    return {
        "bests": record_chart_scores(user_id, bests),
        "plays": record_chart_scores(user_id, plays),
        "ratingPoints": import_rating_points(user_id, points),
        "playCounts": len(counts),
    }
