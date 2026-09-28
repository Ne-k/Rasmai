from concurrent.futures import Future, TimeoutError as NotYet
from typing import Dict, Optional, Tuple, Any
import itertools
import queue
import threading
import time

from rasmai.bot.state.cache import CachedAnalysis, cache_get, cache_put
from rasmai.bot.state.snapshots import analyzer_from_snapshot
from rasmai.bot.tasks.chart_db import resolve_unknown_later
from rasmai.config import ANALYSIS_BUILDS, ANALYSIS_WAIT
from rasmai.storage.db import get_connected_account


class StillBuilding(Exception):
    """The analysis is queued behind other people's; ask again in ``seconds``."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"building, ask again in {seconds}s")
        self.seconds = seconds


# Builds run on a few threads of their own, one job per person however many of their requests ask.
# A request used to build, or wait on somebody else's build, for as long as it took: k6 opened the
# dashboard for a thousand new people at once, the builds queued at two or three a second, and every
# request behind them held a thread and a parsed account while it waited - 7,700 threads, 8 GB, and
# five thousand connections refused before the first minute was out.
_jobs: "queue.SimpleQueue[Tuple[str, Future]]" = queue.SimpleQueue()
_pending: Dict[str, Future] = {}
_pending_guard = threading.Lock()
_queued = itertools.count(1)     # each job's place in the line, in the order they joined it
_started = 0                     # the place of the last job a worker took up

# Jobs that ended without an analysis to cache - no stored scores, or a build that failed - kept a
# minute, so the page asking again is answered the same rather than sent to the back of the line.
FINISHED_KEPT = 60.0
_finished: Dict[str, Tuple[float, Future]] = {}


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
    global _started
    while True:
        user_id, job = _jobs.get()
        _started = job.place
        try:
            job.set_result(_build(user_id))
        except BaseException as error:
            job.set_exception(error)
        finally:
            with _pending_guard:
                _pending.pop(user_id, None)
                now = time.monotonic()
                for gone in [k for k, (at, _) in _finished.items() if now - at > FINISHED_KEPT]:
                    del _finished[gone]
                if job.exception() is not None or job.result() is None:
                    _finished[user_id] = (now, job)


# daemon threads rather than an executor, whose exit would first work through the whole queue
for _ in range(ANALYSIS_BUILDS):
    threading.Thread(target=_worker, name="analysis", daemon=True).start()


def analysis_for_user(user_id: str, patient: bool = False) -> Optional[CachedAnalysis]:
    """The bot's live analysis when it has one, else one rebuilt from the stored snapshot.

    Waits up to ``ANALYSIS_WAIT`` seconds when the build is under way or next in line, and not at
    all when there is a queue ahead of it: a waiting request is a thread held, and the page asks
    again. ``patient`` waits regardless, for a download the browser cannot ask for twice.

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
            job.place = next(_queued)
            _jobs.put((user_id, job))
        ahead = job.place - _started       # 0 or less once a worker has it
    try:
        return job.result(timeout=90.0 if patient else ANALYSIS_WAIT if ahead <= ANALYSIS_BUILDS else 0)
    except NotYet:
        # roughly when this person's turn comes, at about a build a second a worker, capped so a page never sits idle long
        raise StillBuilding(min(30, max(2, ahead // ANALYSIS_BUILDS))) from None


def _chart_key(song: Any) -> Tuple[str, str, str]:
    return (str(song.name).casefold(), (song.chart_type or "std").lower(), (song.difficulty_type or "").lower())
