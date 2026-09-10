from typing import Any, Dict, List, Optional

from rasmai.engine import analysis
from rasmai.engine.analysis import ChartRef, accuracy_for_rating, chart_prediction, rank_ladder
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.state.snapshots import chart_key
from rasmai.bot.builders.charts.index import song_for_chart, songs_by_loose_key


def entry_note(cached: CachedAnalysis, ref: ChartRef, song: Any) -> str:
    """Where the chart stands relative to the best-50.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :param ref: The chart being shown.
    :type ref: ChartRef
    :param song: The player's score on the chart.
    :type song: Any
    :rtype: str
    """
    a = cached.analyzer
    if a.best50 is None:
        return ""
    is_new = bool(a.current_version) and ref.version == a.current_version
    pool = a.best50.pool_for(is_new)
    key = chart_key(song) if song is not None else ref.key
    if key in pool.in_pool:
        return "in your best-50"
    if pool.headroom() > 0:
        return "any score counts (open slot)"
    need = accuracy_for_rating(ref.constant, pool.cutoff + 1)
    if need is None or need > analysis.ACHIEVEMENT_CAP:
        return "cannot reach your best-50"
    if song is not None and float(song.accuracy or 0) >= need:
        return "in your best-50"
    return f"needs {need:.2f}% to enter"


def _level_value(level: str) -> float:
    text = str(level or "").strip()
    if not text:
        return 0.0
    plus = text.endswith("+")
    try:
        return float(text.rstrip("+")) + (0.6 if plus else 0.0)
    except ValueError:
        return 0.0


def _version_label(cached: Optional[CachedAnalysis], ref: Optional[ChartRef]) -> str:
    if ref is None:
        return ""
    label = f"v{ref.version}" if ref.version else "version unknown"
    if cached and cached.analyzer.current_version and ref.version == cached.analyzer.current_version:
        label += " · current version"
    return label


def _cutoffs(cached: Optional[CachedAnalysis]) -> str:
    if not cached or cached.analyzer.best50 is None:
        return "—"
    b = cached.analyzer.best50
    return f"{b.new_pool.cutoff} new / {b.old_pool.cutoff} old"


def chart_ladder(cached: Optional[CachedAnalysis], ref: ChartRef, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The rank ladder for one chart of this song, priced against the player's best-50.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param ref: The chart being shown.
    :type ref: ChartRef
    :param row: One row of the table.
    :type row: Dict[str, Any]
    :rtype: List[Dict[str, Any]]
    """
    if cached is None:
        return []
    a = cached.analyzer
    song = song_for_chart(songs_by_loose_key(cached), ref)
    key = chart_key(song) if song is not None else ref.key
    is_new = bool(song.is_new) if song is not None else bool(a.current_version and ref.version == a.current_version)
    return rank_ladder(a.play_profile, a.best50, key, ref.constant,
                       float(row["accuracy"]) if row.get("played") else 0.0, is_new, played=bool(row.get("played")))


def prediction_for(cached: Optional[CachedAnalysis], ref: ChartRef, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if cached is None:
        return None
    a = cached.analyzer
    song = song_for_chart(songs_by_loose_key(cached), ref)
    key = chart_key(song) if song is not None else ref.key
    return chart_prediction(a.play_profile, key, ref.constant,
                            float(row["accuracy"]) if row.get("played") else 0.0, played=bool(row.get("played")))


def format_prediction(prediction: Dict[str, Any], played: bool) -> str:
    """One line: the score a good run should land, the spread, and the odds of beating the best.

    :param played: Whether the player has a score on the chart.
    :type played: bool
    :rtype: str
    """
    body = f"**{prediction['expected']:.2f}%** {prediction['rank']} on a good run · {prediction['low']:.1f} to {prediction['high']:.1f}"
    if played and prediction.get("new_best") is not None:
        body += f"\n-# **{prediction['new_best'] * 100:.0f}%** chance the next run is a new best"
    else:
        body += "\n-# first pass, judged from how you play this level"
    offset = prediction.get("tier_offset", 0.0)
    if abs(offset) >= 0.5:
        body += f" · your {ref_tier_name(prediction)} runs sit {offset:+.1f} against your curve"
    return body


def ref_tier_name(prediction: Dict[str, Any]) -> str:
    return prediction.get("tier", "")


def format_ladder(ladder: List[Dict[str, Any]]) -> str:
    """The ladder as a monospace block: what each rank needs, pays and costs in odds.

    :rtype: str
    """
    lines = [f"{'RANK':<5} {'NEED':>7}  {'RATING':>6} {'GAIN':>5} {'ODDS':>5}"]
    for step in ladder:
        gain = f"+{step['gain']}" if step["gain"] > 0 else "-"
        lines.append(f"{step['rank']:<5} {step['need']:>6.2f}%  {step['rating']:>6} {gain:>5} {step['odds'] * 100:>4.0f}%")
    return "```\n" + "\n".join(lines) + "\n```"
