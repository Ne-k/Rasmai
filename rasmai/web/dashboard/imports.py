from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import re

from rasmai.bot.state.snapshots import play_rows
from rasmai.storage.db import best_recorded_scores, import_rating_points, load_play_counts, record_chart_scores, save_play_counts

MAX_ROWS = 6000          # more charts than the game has
NAME_CHARS = 200
EARLIEST = datetime(2019, 7, 1)          # maimai DX opened; nothing in an export predates it
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _text(value: Any, limit: int = NAME_CHARS) -> str:
    """A string cut to `limit` with control characters removed; anything that is not a string is ''."""
    return _CONTROL.sub("", value)[:limit] if isinstance(value, str) else ""


def _int(value: Any, high: int, low: int = 0) -> int:
    """An integer inside [low, high]; anything unreadable or outside is 0."""
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if low <= number <= high else 0


def _accuracy(value: Any) -> float:
    try:
        number = round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0
    return number if 0 < number <= 101 else 0.0      # NaN and infinity fail the comparison and are dropped


def _when(value: Any, now: datetime) -> Optional[str]:
    """An ISO 8601 moment between the game's launch and tomorrow, as given; None otherwise."""
    text = _text(value, 40)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    naive = moment.replace(tzinfo=None)
    return text if EARLIEST <= naive <= now + timedelta(days=1) else None


def _chart_key(name: str, chart_type: Any, tier: str) -> str:
    return "|".join((name.casefold(), "dx" if str(chart_type).lower() == "dx" else "std", tier))


def import_payload(user_id: str, data: Dict[str, Any], analyzer: Any, index: Any) -> Dict[str, int]:
    """Merge an export the bot wrote back into the stored history; what is already there is left alone.

    Bests are dated to the export and only kept when they beat what is recorded, the plays on its
    recent list and its stored play history are added as plays, rating points keep their own dates,
    and a play count only ever goes up. Every value is bounded: the file is the user's to shape,
    so nothing in it is trusted further than a row that fits.

    :param user_id: The Discord user id.
    :type user_id: str
    :param data: The parsed export file.
    :type data: Dict[str, Any]
    :param analyzer: A scraper, for the title normalisation the recent list is keyed by.
    :type analyzer: Any
    :param index: The chart database; a row for a chart it does not know is dropped.
    :type index: Any
    :returns: How many bests, plays, rating points and play counts were new.
    :rtype: Dict[str, int]
    """
    if not isinstance(data, dict) or not isinstance(data.get("charts"), list) or not isinstance(data.get("fields"), list):
        raise ValueError("That is not a Rasmai export: it has no chart table.")
    now = datetime.now()
    recorded_at = _when(data.get("recordedAt"), now)
    if not recorded_at:
        raise ValueError("That export carries no readable date.")
    tiers = ("basic", "advanced", "expert", "master", "remaster")

    def real(key: str) -> bool:
        parts = key.rsplit("|", 2)
        return len(parts) == 3 and index.get((parts[0], parts[1], parts[2])) is not None

    known = best_recorded_scores(user_id)
    bests: List[Tuple[Any, ...]] = []
    fields = [_text(f, 40) for f in data["fields"][:40]]
    for row in data["charts"][:MAX_ROWS]:
        if not isinstance(row, list):
            continue
        chart = dict(zip(fields, row))
        name = _text(chart.get("name"))
        tier = _text(chart.get("difficulty_type"), 12).lower()
        accuracy = _accuracy(chart.get("accuracy"))
        if not name or tier not in tiers or not accuracy:
            continue
        key = _chart_key(name, chart.get("chart_type"), tier)
        if real(key) and (key not in known or accuracy > known[key] + 0.00005):
            bests.append((key, recorded_at, accuracy, _int(chart.get("dx_score"), 10000),
                          _text(chart.get("fc_status"), 8), _text(chart.get("fs_status"), 8), "best"))
            known[key] = accuracy

    recent = []
    for record in (data.get("recentPlays") or [])[:200]:
        if not isinstance(record, dict) or not _when(record.get("playedAt"), now):
            continue
        recent.append({
            "songName": _text(record.get("songName")), "musicType": _text(record.get("musicType"), 4),
            "difficulty": _text(record.get("difficulty"), 12), "achievement": _int(record.get("achievement"), 1010000),
            "dxScore": _int(record.get("dxScore"), 10000), "maxDxScore": _int(record.get("maxDxScore"), 10000),
            "fc": _text(record.get("fc"), 8), "fs": _text(record.get("fs"), 8), "track": _int(record.get("track"), 99),
            "playedAt": _text(record.get("playedAt"), 40),
        })
    plays = [row for row in play_rows(analyzer, recent) if real(row[0])]
    for play in (data.get("playHistory") or [])[:MAX_ROWS]:
        if not isinstance(play, dict):
            continue
        key = _text(play.get("key"), NAME_CHARS + 20)
        played_at = _when(play.get("played_at"), now)
        accuracy = _accuracy(play.get("achievement"))
        parts = key.rsplit("|", 2)
        if len(parts) != 3 or not parts[0] or parts[2] not in tiers or not played_at or not accuracy or not real(key):
            continue
        plays.append((_chart_key(parts[0], parts[1], parts[2]), played_at, accuracy, _int(play.get("dx_score"), 10000),
                      _text(play.get("fc"), 8), _text(play.get("fs"), 8), "play",
                      _int(play.get("max_dx"), 10000), _int(play.get("track"), 99)))

    points = [(recorded_at, _int(data.get("rating"), 20000), _int(data.get("best50"), 20000), _int(data.get("newTotal"), 20000),
               _int(data.get("oldTotal"), 20000), min(len(data["charts"]), MAX_ROWS), _int(data.get("totalPlayCount"), 1000000))]
    for row in (data.get("ratingHistory") or [])[:MAX_ROWS]:
        when = _when(row.get("recorded_at"), now) if isinstance(row, dict) else None
        if when:
            points.append((when, _int(row.get("rating"), 20000), _int(row.get("best50"), 20000), _int(row.get("new_total"), 20000),
                           _int(row.get("old_total"), 20000), _int(row.get("charts"), 100000), _int(row.get("plays"), 1000000)))
    points = [p for p in points if p[1] > 0]

    held = load_play_counts(user_id)
    counts: Dict[Tuple[str, str, str], int] = {}
    raw_counts = data.get("playCounts") if isinstance(data.get("playCounts"), dict) else {}
    for key, value in list(raw_counts.items())[:MAX_ROWS]:
        parts = _text(key, NAME_CHARS + 20).rsplit("|", 2)
        plays_seen = _int(value, 100000)
        if len(parts) == 3 and parts[0] and parts[2] in tiers and real("|".join(parts)) and plays_seen > held.get((parts[0], parts[1], parts[2]), 0):
            counts[(parts[0], parts[1], parts[2])] = plays_seen
    if counts:
        save_play_counts(user_id, counts)

    return {
        "bests": record_chart_scores(user_id, bests),
        "plays": record_chart_scores(user_id, plays),
        "ratingPoints": import_rating_points(user_id, points),
        "playCounts": len(counts),
    }
