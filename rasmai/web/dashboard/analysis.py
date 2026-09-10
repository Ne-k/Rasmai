from typing import Dict, Optional, Tuple, Any

from rasmai.bot.state.cache import CachedAnalysis, cache_get, cache_put
from rasmai.bot.state.snapshots import analyzer_from_snapshot
from rasmai.bot.tasks.chart_db import resolve_unknown_later


def analysis_for_user(user_id: str, account: Dict[str, Any]) -> Optional[CachedAnalysis]:
    """The bot's live analysis when it has one, else one rebuilt from the stored snapshot.

    :param user_id: The Discord user id.
    :type user_id: str
    :param account: The linked account, as stored.
    :type account: Dict[str, Any]
    :rtype: Optional[CachedAnalysis]
    """
    live = cache_get(user_id)
    if live is not None:
        return live
    analyzer = analyzer_from_snapshot(user_id, account)
    if analyzer is None:
        return None
    recommendations, value_charts = analyzer.generate_recommendations()
    cached = CachedAnalysis(user_id=user_id, region=analyzer.region, analyzer=analyzer,
                            recommendations=recommendations, value_charts=value_charts)
    cache_put(cached)      # the bot's own store, so a command that follows finds the same analysis
    resolve_unknown_later(cached)
    return cached


def _chart_key(song: Any) -> Tuple[str, str, str]:
    return (str(song.name).casefold(), (song.chart_type or "std").lower(), (song.difficulty_type or "").lower())
