from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
import logging
import threading
import time

from rasmai.engine import cohort as model
from rasmai.engine.cohort import Cohort, Difficulty, Key

logger = logging.getLogger(__name__)

# The cohort is rebuilt inside the request that finds the held copy old, so that request stalls for the
# build: a fraction of a second now, about 3 s at 5,000 players, once an hour. If that ever hurts, the fix
# is to move the build to a background thread.
REBUILD_AFTER = 3600.0
RETRY_AFTER = 300.0      # a build that failed is not tried again for this long, and the last good copy keeps answering


@dataclass
class _Built:
    cohort: Cohort
    found: Difficulty
    at: float


_lock = threading.Lock()
_built: Optional[_Built] = None
_failed_at: Optional[float] = None


def _resolver() -> Tuple[Callable[[Dict[str, float]], Dict[Key, float]], Dict[Key, float]]:
    """How an account's stored bests become scores under the chart database's keys, and the listed constant of each chart."""
    from rasmai.bot.builders.charts import shared_index
    index = shared_index()
    refs = index.values()
    seen: Dict[Key, int] = {}
    for ref in refs:
        seen[ref.key] = seen.get(ref.key, 0) + 1
    # two songs can share a title ("Link") and a stored key carries no level to tell them by, so such a title is left out
    constants = {ref.key: float(ref.constant) for ref in refs if seen[ref.key] == 1 and ref.constant > 0}
    memo: Dict[str, Optional[Key]] = {}

    def best(raw: Dict[str, float]) -> Dict[Key, float]:
        scores: Dict[Key, float] = {}
        for stored, value in raw.items():
            if stored not in memo:
                parts = stored.rsplit("|", 2)
                ref = index.get((parts[0], parts[1], parts[2])) if len(parts) == 3 else None
                memo[stored] = ref.key if ref is not None and ref.key in constants else None
            key = memo[stored]
            if key is not None and value > scores.get(key, 0.0):
                scores[key] = value
        return scores
    return best, constants


def _build() -> _Built:
    from rasmai.storage.db.cohort import cohort_accounts
    started = time.monotonic()
    best, constants = _resolver()
    # an account's tag is its id: it only leaves a viewer out of their own neighbours and takes an opted-out
    # row out, stays in this process's memory, and is never returned or logged
    cohort = model.build_cohort(((str(user_id).encode(), rating, best(raw)) for user_id, rating, raw in cohort_accounts()), constants)
    found = model.fit_difficulty(cohort)
    logger.info("cohort built: %d players, %d charts with enough players, %.1fs", cohort.players, len(found.charts), time.monotonic() - started)
    return _Built(cohort, found, time.monotonic())


def _due() -> bool:
    now = time.monotonic()
    return (_built is None or now - _built.at >= REBUILD_AFTER) and (_failed_at is None or now - _failed_at >= RETRY_AFTER)


def _held() -> Optional[_Built]:
    # with a copy held, a request that finds a build running serves the copy; with none, it waits for the build
    global _built, _failed_at
    if _due() and _lock.acquire(blocking=_built is None):
        try:
            if _due():
                try:
                    _built, _failed_at = _build(), None
                except Exception:
                    logger.exception("cohort build failed; keeping the last one")
                    _failed_at = time.monotonic()
        finally:
            _lock.release()
    return _built


def _row(built: _Built, key: Key) -> Dict[str, Any]:
    rate, expected, players, offset, error = built.found.charts[key]
    return {"rate": round(rate, 3), "expected": round(expected, 3), "players": players, "lean": model.lean(rate, expected, offset, error)}


def players() -> int:
    built = _held()
    return built.cohort.players if built is not None else 0


def difficulty(key: Key) -> Optional[Dict[str, Any]]:
    """What the cohort says about one chart, ``{"rate", "expected", "players", "lean"}``, or ``None`` when too few play it."""
    built = _held()
    if built is None or built.cohort.players < model.MIN_COHORT or key not in built.found.charts:
        return None
    return _row(built, key)


def observed_line(key: Key) -> str:
    """The sentence a chart gets in the bot, or ``""`` when too few players have played it.

    The site draws the same numbers in its own words, with the same caution beside them.
    """
    row = difficulty(key)
    if row is None:
        return ""
    where = {"harder": "harder than its level", "easier": "easier than its level"}.get(row["lean"], "about its level")
    return (f"SS or better by {row['rate']:.0%} of {row['players']} players, {row['expected']:.0%} expected for its level · {where}"
            " · rough guide, not hard data")


def drop(user_id: str) -> None:
    """Take one account's row out of what is held, and the difficulty fitted with it; the next call rebuilds."""
    global _built, _failed_at
    tag = str(user_id).encode()
    with _lock:      # a build that is reading right now finishes first, so the row is taken out of its result
        if _built is not None and tag in _built.cohort.tags:
            _built, _failed_at = _Built(_built.cohort.without(tag), Difficulty({}), float("-inf")), None


def reset() -> None:
    global _built, _failed_at
    with _lock:
        _built, _failed_at = None, None
