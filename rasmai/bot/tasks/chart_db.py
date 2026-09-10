from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import asyncio
import logging
import threading

from rasmai.engine import analysis
from rasmai.bot.builders.charts.index import refresh_shared_index

logger = logging.getLogger(__name__)

# a song the fetched database still lacks is not asked about again for this long; a fetch that failed is retried sooner
REFRESH_AFTER_MISS = timedelta(hours=12)
RETRY_AFTER_FAILURE = timedelta(hours=1)
_tried: Dict[str, datetime] = {}      # title -> when the database was last fetched for it
_lock = threading.Lock()


def unknown_titles(analyzer: Any) -> List[str]:
    """The titles among the player's scored charts that the chart database has no entry for.

    :param analyzer: The analysis, after ``generate_recommendations`` has enriched its songs.
    :type analyzer: Any
    :rtype: List[str]
    """
    return sorted({str(s.name) for s in getattr(analyzer, "songs", []) or [] if getattr(s, "constant_estimated", False)})


def _due(titles: List[str]) -> List[str]:
    now = datetime.now()
    with _lock:
        due = [t for t in titles if t not in _tried or now - _tried[t] >= REFRESH_AFTER_MISS]
        for title in due:
            _tried[title] = now        # claimed: a second analysis arriving now does not fetch too
    return due


def resolve_unknown(analyzer: Any, tell: Optional[Callable[..., None]] = None) -> bool:
    """Fetch the chart database again when the analysis met charts it does not know, and point the analysis at the new copy.

    New songs reach otoge-db within days of release, and the weekly refresh would leave them
    guessed at for up to a week: no jacket, a constant taken from the level, nothing to look
    up. The fetch runs here, in the calling thread, so the read that met the song finishes
    with its constants. A title the fresh database still lacks is left alone for twelve hours.

    :param analyzer: The analysis, after ``generate_recommendations`` has run once.
    :type analyzer: Any
    :param tell: The read's progress callback, told what is happening.
    :type tell: Optional[Callable[..., None]]
    :returns: True when the database changed under the analysis, which must then be generated again.
    :rtype: bool
    """
    titles = unknown_titles(analyzer)
    due = _due(titles) if titles else []
    if not due:
        return False
    logger.info("%d song(s) unknown to the chart database (%s): fetching it again",
                len(due), ", ".join(due[:3]) + (" ..." if len(due) > 3 else ""))
    if tell:
        tell("analysis", 0, 1, detail=f"Updating the chart database for {due[0]}" + (f" and {len(due) - 1} more" if len(due) > 1 else ""))
    try:
        fetched = bool(analyzer.otoge_db.refresh_now())
    except Exception:
        logger.exception("fetching the chart database for unknown songs failed")
        fetched = False
    if not fetched:
        with _lock:
            for title in due:
                _tried[title] = datetime.now() - REFRESH_AFTER_MISS + RETRY_AFTER_FAILURE
        logger.warning("the chart database could not be fetched; %s keep a constant taken from the level", ", ".join(due[:3]))
        return False
    # both indexes are built to the side and swapped in, so a command answered meanwhile reads a whole one
    analyzer._chart_index = analysis.build_chart_index(analyzer.otoge_db.songs_data, region=getattr(analyzer, "region", None))
    refresh_shared_index()
    index = analyzer.chart_index
    found = [t for t in titles if any(index.get((s.name, s.chart_type, s.difficulty_type), s.level) is not None
                                      for s in analyzer.songs if str(s.name) == t)]
    still = [t for t in titles if t not in found]
    with _lock:
        for title in found:
            _tried.pop(title, None)
    if found:
        logger.info("chart database fetched: %s now known", ", ".join(found[:5]))
    if still:
        logger.info("chart database fetched: %s not listed there yet, constants stay estimated from the level", ", ".join(still[:5]))
    return True


def rebuild(cached: Any, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Generate the analysis again over the database as it now is and drop everything derived from the old one.

    The generating is done here, on whichever thread calls; only the swap is handed to ``loop`` when
    given, so the bot's cache changes on its own thread without that thread doing the work.

    :param cached: The player's analysis, held in memory.
    :type cached: Any
    :param loop: The bot's event loop, or None to swap the results in from this thread.
    :type loop: Optional[asyncio.AbstractEventLoop]
    """
    recommendations, value_charts = cached.analyzer.generate_recommendations()

    def install() -> None:
        cached.recommendations, cached.value_charts = recommendations, value_charts
        cached.analyses.clear()
        cached.plans.clear()
        cached.images.clear()

    if loop is not None:
        loop.call_soon_threadsafe(install)
    else:
        install()


def resolve_unknown_later(cached: Any, loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
    """Run ``resolve_unknown`` behind an analysis that has already answered, then rebuild it in place.

    For the stored-copy paths, which answer in a moment and should not wait on a clone.
    The rebuilt results are swapped in on ``loop`` when given, so the bot's cache changes on its own thread.

    :param cached: The player's analysis, held in memory.
    :type cached: Any
    :param loop: The bot's event loop, or None to rebuild on the worker thread.
    :type loop: Optional[asyncio.AbstractEventLoop]
    :returns: True when a fetch was started.
    :rtype: bool
    """
    titles = unknown_titles(cached.analyzer)
    now = datetime.now()
    with _lock:
        if not any(t not in _tried or now - _tried[t] >= REFRESH_AFTER_MISS for t in titles):
            return False

    def work() -> None:
        try:
            if resolve_unknown(cached.analyzer):
                rebuild(cached, loop)
        except Exception:
            logger.exception("rebuilding an analysis after a chart database fetch failed")

    threading.Thread(target=work, name="chart-db-refresh", daemon=True).start()
    return True
