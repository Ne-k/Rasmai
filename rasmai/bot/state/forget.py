from typing import Callable, List
import logging

logger = logging.getLogger(__name__)


def forget_user(user_id: str) -> None:
    """Drop everything this process holds in memory about one person, once their stored data is deleted.

    The database delete takes what is on disk; these are the copies held while the bot runs: the
    analysis and its pictures, a dashboard build waiting or just finished, a score read in progress,
    the map data of the last light check, the minute they were last seen, and their Discord name
    and avatar on the developer page. Each is dropped on its own, so one that is missing (a module
    never loaded in this process) does not keep the rest.

    :param user_id: The Discord user id.
    :type user_id: str
    """
    uid = str(user_id)

    def analysis() -> None:
        from rasmai.bot.state.cache import forget_analysis
        forget_analysis(uid)

    def dashboard_builds() -> None:
        from rasmai.web.dashboard import analysis as builds
        with builds._pending_guard:
            builds._pending.pop(uid, None)
            builds._finished.pop(uid, None)

    def score_read() -> None:
        from rasmai.web.dashboard.refresh import refresh_jobs
        with refresh_jobs._lock:
            refresh_jobs._jobs.pop(uid, None)

    def read_slot() -> None:
        from rasmai.bot.state import reads
        reads.release(uid)

    def light_check() -> None:
        from rasmai.bot.builders.results import stored
        stored._fresh_areas.pop(uid, None)

    def last_seen() -> None:
        from rasmai.storage.db import accounts
        accounts._SEEN.pop(uid, None)

    def developer_page() -> None:
        from rasmai.web.dashboard import admin
        admin._PEOPLE.pop(uid, None)

    steps: List[Callable[[], None]] = [analysis, dashboard_builds, score_read, read_slot, light_check,
                                       last_seen, developer_page]
    for step in steps:
        try:
            step()
        except Exception as error:
            # a step that fails leaves a deleted account's data in memory: worth knowing about, not a shrug
            logger.exception("forgetting %s: %s failed (%s)", uid, step.__name__, error)
