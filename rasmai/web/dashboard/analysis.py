from typing import Dict, Optional, Tuple, Any
import threading

from rasmai.bot.state.cache import CachedAnalysis, cache_get, cache_put
from rasmai.bot.state.snapshots import analyzer_from_snapshot
from rasmai.bot.tasks.chart_db import resolve_unknown_later
from rasmai.config import ANALYSIS_BUILDS

# A dashboard asks for six things as it opens, and every one of them needs the analysis. With
# nothing cached, all six used to build it at once: k6 counted six analyses for one visit, and a
# burst of fifty new visitors queued three hundred of them, which held the whole server - cached
# users and the health check included - for minutes. One lock per person makes the other five wait
# for the first and take its result.
# ponytail: one lock per person ever seen, kept for the life of the process; a few dozen bytes each,
# so it only matters past tens of thousands of accounts, and then wants evicting with the cache.
_building: Dict[str, threading.Lock] = {}
_building_guard = threading.Lock()

# and only so many builds at once, whoever they are for: past that they queue rather than thrash
# the one interpreter lock between them, and a cached request never waits here at all
_builds = threading.BoundedSemaphore(ANALYSIS_BUILDS)


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
    with _building_guard:
        mine = _building.setdefault(user_id, threading.Lock())
    with mine:
        live = cache_get(user_id)          # somebody else's request for this person got here first
        if live is not None:
            return live
        with _builds:
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
