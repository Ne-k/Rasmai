from concurrent.futures import Future, TimeoutError as NotYet
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import itertools
import logging
import math
import queue
import threading
import time

from rasmai.bot.state.cache import CachedAnalysis, cache_get, cache_put
from rasmai.bot.state.snapshots import analyzer_from_snapshot
from rasmai.bot.tasks.chart_db import resolve_unknown_later
from rasmai.config import ANALYSIS_BUILDS, ANALYSIS_CACHE_MAX, ANALYSIS_WAIT
from rasmai.storage.db import get_connected_account

logger = logging.getLogger(__name__)


class StillBuilding(Exception):
    """The analysis is queued behind other people's: where it stands, about how long, and when to ask again."""

    def __init__(self, position: int, eta: int, seconds: int) -> None:
        super().__init__(f"building: number {position} in line, about {eta}s, ask again in {seconds}s")
        self.position = position
        self.eta = eta
        self.seconds = seconds


# Builds run on a few threads of their own, one job per person however many of their requests ask.
# A request used to build, or wait on somebody else's build, for as long as it took: k6 opened the
# dashboard for a thousand new people at once, the builds queued at two or three a second, and every
# request behind them held a thread and a parsed account while it waited - 7,700 threads, 8 GB, and
# five thousand connections refused before the first minute was out.
#
# Somebody waiting goes before a warm-up: after a restart everyone recently active is queued to be
# built before they ask, and one of them opening the page moves their own build to the front.
NOW, LATER = 0, 1
_jobs: "queue.PriorityQueue[Tuple[int, int, str, Future]]" = queue.PriorityQueue()
_pending: Dict[str, Future] = {}
_pending_guard = threading.Lock()
_places = {NOW: itertools.count(1), LATER: itertools.count(1)}   # each job's place in its line
_taken = {NOW: 0, LATER: 0}      # the place of the last job a worker took up, per line
_build_seconds = 1.0             # how long a build takes, as it has lately; the wait a queued page is told

# Jobs that ended without an analysis to cache - no stored scores, or a build that failed - kept a
# minute, so the page asking again is answered the same rather than sent to the back of the line.
FINISHED_KEPT = 60.0
_finished: Dict[str, Tuple[float, Future]] = {}

WARM_WITHIN = timedelta(days=1)


def _build(user_id: str) -> Optional[CachedAnalysis]:
    live = cache_get(user_id)     # a read of the player's own while the job queued: nothing left to do
    if live is not None:
        return live
    analyzer = analyzer_from_snapshot(user_id, get_connected_account(user_id) or {})
    if analyzer is None:
        return None
    recommendations, value_charts = analyzer.generate_recommendations()
    cached = CachedAnalysis(user_id=user_id, region=analyzer.region, analyzer=analyzer,
                            recommendations=recommendations, value_charts=value_charts)
    cache_put(cached)      # the bot's own store, so a command that follows finds the same analysis
    resolve_unknown_later(cached)
    return cached


def _worker() -> None:
    global _build_seconds
    while True:
        priority, place, user_id, job = _jobs.get()
        with _pending_guard:
            _taken[priority] = max(_taken[priority], place)
            if job.taken:
                continue       # moved to the front already: this is the entry it left behind
            job.taken = True
        started = time.monotonic()
        try:
            job.set_result(_build(user_id))
        except BaseException as error:
            job.set_exception(error)
        finally:
            with _pending_guard:
                _build_seconds = 0.8 * _build_seconds + 0.2 * (time.monotonic() - started)
                _pending.pop(user_id, None)
                now = time.monotonic()
                for gone in [k for k, (at, _) in _finished.items() if now - at > FINISHED_KEPT]:
                    del _finished[gone]
                if job.exception() is not None or job.result() is None:
                    _finished[user_id] = (now, job)


# daemon threads rather than an executor, whose exit would first work through the whole queue
for _ in range(ANALYSIS_BUILDS):
    threading.Thread(target=_worker, name="analysis", daemon=True).start()


def _enqueue(user_id: str, job: Future, priority: int) -> None:
    job.priority, job.place = priority, next(_places[priority])
    _jobs.put((priority, job.place, user_id, job))


def analysis_for_user(user_id: str, patient: bool = False) -> Optional[CachedAnalysis]:
    """The bot's live analysis when it has one, else one rebuilt from the stored snapshot.

    Waits up to ``ANALYSIS_WAIT`` seconds when the build is under way or next in line, and not at
    all when there is a queue ahead of it: a waiting request is a thread held, and the page shows
    its place in line and asks again. ``patient`` waits regardless, for a download the browser
    cannot ask for twice.

    :param user_id: The Discord user id.
    :type user_id: str
    :param patient: Wait out the queue, up to a minute and a half.
    :type patient: bool
    :raises StillBuilding: When the analysis is not ready yet.
    :rtype: Optional[CachedAnalysis]
    """
    live = cache_get(user_id)
    if live is not None:
        return live
    with _pending_guard:
        live = cache_get(user_id)          # finished between the look above and this lock
        if live is not None:
            return live
        ended = _finished.get(user_id)
        if ended is not None and time.monotonic() - ended[0] <= FINISHED_KEPT:
            return ended[1].result()       # the same None, or the same error, as a moment ago
        job = _pending.get(user_id)
        if job is None:
            job = _pending[user_id] = Future()
            job.taken = False
            _enqueue(user_id, job, NOW)
        elif job.priority == LATER and not job.taken:
            _enqueue(user_id, job, NOW)    # a warm-up the person has now asked for: to the front
        ahead = 0 if job.taken else max(0, job.place - _taken[NOW] - 1)
        per_build = _build_seconds
    try:
        return job.result(timeout=90.0 if patient else ANALYSIS_WAIT if ahead < ANALYSIS_BUILDS else 0)
    except NotYet:
        eta = math.ceil((ahead // ANALYSIS_BUILDS + 1) * per_build)
        # asked again often enough that the place shown moves, and rarely enough that a long line is not all asking
        raise StillBuilding(ahead + 1, eta, min(10, max(2, eta // 5))) from None


def warm(user_ids: List[str]) -> int:
    """Queue analyses to be built before anyone asks, behind every build somebody is waiting for.

    :param user_ids: Whose analyses to build.
    :type user_ids: List[str]
    :returns: How many were queued.
    :rtype: int
    """
    queued = 0
    with _pending_guard:
        for user_id in user_ids:
            if user_id in _pending or cache_get(user_id) is not None:
                continue
            job = _pending[user_id] = Future()
            job.taken = False
            _enqueue(user_id, job, LATER)
            queued += 1
    return queued


def warm_recent() -> None:
    """After a restart every analysis is gone; build those of the people active in the last day, most recent first."""
    from rasmai.storage.db.history import recently_seen
    try:
        queued = warm(recently_seen(datetime.now() - WARM_WITHIN, ANALYSIS_CACHE_MAX))
        if queued:
            logger.info("warming %d analyses of people active in the last day", queued)
    except Exception:
        logger.exception("warming analyses after the restart failed")


def _chart_key(song: Any) -> Tuple[str, str, str]:
    return (str(song.name).casefold(), (song.chart_type or "std").lower(), (song.difficulty_type or "").lower())
