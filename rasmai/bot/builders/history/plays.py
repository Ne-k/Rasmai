from datetime import datetime
from typing import Any, Dict, List, Tuple
import logging


from rasmai.engine.analysis import calculate_rating, rank_for
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.builders.charts import songs_by_key

logger = logging.getLogger(__name__)


def recent_key(analyzer: Any, record: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        analyzer._normalize_official_song_name(str(record.get("songName", ""))).casefold(),
        str(record.get("musicType") or "std").lower(),
        str(record.get("difficulty") or "").lower(),
    )


def recent_plays(cached: CachedAnalysis) -> List[Dict[str, Any]]:
    """The recent-plays list with scores, ranks and best-50 context filled in, newest first.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :rtype: List[Dict[str, Any]]
    """
    a = cached.analyzer
    by_key = songs_by_key(cached)
    plays: List[Dict[str, Any]] = []
    for position, record in enumerate(a.recent_songs or []):
        key = recent_key(a, record)
        song = by_key.get(key)
        ref = a.chart_index.get(key)
        raw = float(record.get("achievement") or 0) / 10000.0
        achievement = raw if 0 < raw <= 101.0 else None
        constant = float(song.difficulty or 0) if song else (ref.constant if ref else 0.0)
        chart_rating = calculate_rating(constant, achievement) if achievement and constant > 0 else 0
        is_new = bool(song.is_new) if song else bool(ref and a.current_version and ref.version == a.current_version)
        in_b50 = bool(a.best50) and key in a.best50.pool_for(is_new).in_pool
        pb = bool(song and achievement is not None and abs(float(song.accuracy or 0) - achievement) < 0.00005)
        max_dx = int(record.get("maxDxScore") or 0)
        dx = int(record.get("dxScore") or 0)
        played_at = str(record.get("playedAt", ""))
        try:
            when = datetime.fromisoformat(played_at)
        except ValueError:
            when = None
        plays.append({
            "position": position + 1, "idx": record.get("idx", ""), "key": key,
            "title": song.name if song else (ref.title if ref else str(record.get("songName", ""))),
            "difficulty": key[2], "chart_type": key[1], "level": str(record.get("level") or (song.level if song else "")),
            "constant": round(constant, 1),
            "achievement": achievement, "rank": rank_for(achievement) if achievement is not None else "",
            "dx": dx, "max_dx": max_dx, "dx_pct": (100.0 * dx / max_dx) if max_dx else 0.0,
            "fc": record.get("fc", ""), "fs": record.get("fs", ""),
            "track": f"T{int(record.get('track') or 0)}", "time": played_at[11:16], "day": played_at[:10],
            "when": when,
            "chart_rating": chart_rating, "pb": pb, "in_b50": in_b50,
            "cover": (song.cover_url if song else "") or (ref.cover if ref else ""),
        })
    return plays


def _short_day(label: str) -> str:
    """A day label without its year, for field names where the year is noise."""
    head, _, tail = label.rpartition(" ")
    return head if head and tail.isdigit() and len(tail) == 4 else label


def _day_label(day: str) -> str:
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%a %d %b %Y")
    except ValueError:
        return day or "unknown day"
