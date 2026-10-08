from datetime import datetime
from typing import Any, Dict, Optional
import asyncio
import logging
import os
import shutil
import time

from rasmai.config import DATABASE_PATH, MAX_CONCURRENT_SCRAPES
from rasmai.storage.db import get_database_connection

logger = logging.getLogger(__name__)

# Statuspage's own words for a component, worst last
OPERATIONAL, MAINTENANCE, DEGRADED, PARTIAL, MAJOR = (
    "operational", "under_maintenance", "degraded_performance", "partial_outage", "major_outage")
_ORDER = (OPERATIONAL, MAINTENANCE, DEGRADED, PARTIAL, MAJOR)

SLOW_GATEWAY_MS = 1500     # Discord answering slower than this is a bot people notice
LONG_LINE = 10             # people waiting on a build, warm-ups not counted, before the dashboard is called slow
SLOW_LOOP_MS = 1000        # the bot taking longer than this to get to a waiting task is a bot that answers late
STUCK_LOOP_S = 5           # and not getting to it at all in this long is a bot that has stopped answering
LOW_DISK_MB = 1024         # free space under this and the database, the score reads and the logs are close to failing to write
RENDER_FAILS = 3           # renders failing in a row before the images count as broken; one bad page is not that
CHART_STAMP = os.path.join("otoge_cache", "last_update.txt")      # when the chart database was last fetched


def worst(states: Any) -> str:
    """The worst of several component states.

    :rtype: str
    """
    return max(states, key=_ORDER.index, default=OPERATIONAL)


def _bot() -> Dict[str, Any]:
    from rasmai.bot.core import SCRAPE_SEMAPHORE, bot, watch
    from rasmai.bot.tasks.presence import maintenance_at
    latency = round((bot.latency or 0) * 1000) if bot.is_ready() else 0
    if not bot.is_ready():
        discord_state = MAJOR
    else:
        discord_state = DEGRADED if latency > SLOW_GATEWAY_MS else OPERATIONAL
    if maintenance_at().active:
        maimai_state = MAINTENANCE
    else:
        maimai_state = OPERATIONAL if watch.reachable else MAJOR
    return {"discord": discord_state, "maimai": maimai_state, "gatewayMs": latency,
            "scrapesInFlight": MAX_CONCURRENT_SCRAPES - SCRAPE_SEMAPHORE._value}


def loop_lag_ms() -> Optional[int]:
    """How long the bot took to get to a task handed to it, in ms; None when it is not running.

    Discord can be reachable while the bot itself is stuck on something, and then every command times out.
    Called from outside the bot's own thread, as the web server and the heartbeat both do.
    """
    from rasmai.bot.core import bot
    loop = bot.loop
    if not isinstance(loop, asyncio.AbstractEventLoop) or not loop.is_running():
        return None
    started = time.monotonic()
    try:
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop).result(timeout=STUCK_LOOP_S)
    except Exception:
        return STUCK_LOOP_S * 1000
    return round((time.monotonic() - started) * 1000)


def _jobs() -> Dict[str, bool]:
    """Whether each of the bot's background jobs is still running; one that died stops what it does without a word."""
    from rasmai.bot import core
    return {
        "server watch": core.watch._task is not None and not core.watch._task.done(),
        "score history": core.history_watch._task is not None and not core.history_watch._task.done(),
        "status heartbeat": core._status_heartbeat.is_running(),
        "chart upkeep": core._chart_db_daily.is_running(),
        "expired accounts": core._expired_account_sweep.is_running(),
    }


def _memory_mb() -> Optional[int]:
    try:        # Linux, which the container is; nothing elsewhere
        with open("/proc/self/statm") as f:
            return round(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024)
    except (OSError, ValueError, AttributeError):
        return None


def _charts() -> Dict[str, Any]:
    """How old the chart database is: a refresh that keeps failing leaves new songs unknown and constants out of date."""
    from rasmai.scraping.otoge.db import REFRESH_AFTER
    try:
        with open(CHART_STAMP) as f:
            age = datetime.now() - datetime.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return {"state": DEGRADED, "ageHours": None}
    # a refresh is due every REFRESH_AFTER and tried daily, so twice that is a few refreshes failed in a row
    return {"state": DEGRADED if age > 2 * REFRESH_AFTER else OPERATIONAL, "ageHours": round(age.total_seconds() / 3600)}


def _analysis() -> Dict[str, Any]:
    from rasmai.bot.state.cache import _analysis_cache
    from rasmai.web.dashboard import analysis
    with analysis._pending_guard:
        waiting = sum(1 for job in analysis._pending.values() if job.priority == analysis.NOW and not job.taken)
    return {"state": DEGRADED if waiting > LONG_LINE else OPERATIONAL,
            "waiting": waiting, "cached": len(_analysis_cache)}


def status_payload() -> Dict[str, Any]:
    """Component states and metrics as Statuspage's own vocabulary names them, for the script that pushes them there.

    Each part is read on its own, so one that cannot be read is reported as an outage of that part
    and does not take the rest down with it.

    :rtype: Dict[str, Any]
    """
    components: Dict[str, str] = {}
    metrics: Dict[str, float] = {}
    try:
        connection = get_database_connection()
        try:
            metrics["accounts"] = connection.execute("SELECT COUNT(*) FROM connected_accounts").fetchone()[0]
        finally:
            connection.close()
        components["database"] = OPERATIONAL
    except Exception as error:
        logger.error("the status check could not open the database: %s", error)
        components["database"] = MAJOR
    try:
        free = shutil.disk_usage(DATABASE_PATH.parent).free // (1024 * 1024)
        metrics["diskFreeMb"] = free
        metrics["databaseMb"] = round(DATABASE_PATH.stat().st_size / 1024 / 1024, 1)
        if free < LOW_DISK_MB and components["database"] == OPERATIONAL:
            components["database"] = DEGRADED
    except OSError:
        pass
    try:
        live = _bot()
        components["bot"] = live["discord"]
        components["maimai"] = live["maimai"]
        metrics["gatewayMs"] = live["gatewayMs"]
        metrics["scrapesInFlight"] = live["scrapesInFlight"]
        lag = loop_lag_ms()
        if lag is not None:
            metrics["loopLagMs"] = lag
            if lag >= STUCK_LOOP_S * 1000:
                components["bot"] = MAJOR
            elif lag > SLOW_LOOP_MS:
                components["bot"] = worst([components["bot"], DEGRADED])
        from rasmai.bot.core import RENDER_HEALTH, STARTED, bot
        metrics["uptimeSeconds"] = round(time.monotonic() - STARTED)
        metrics["renderFailuresInARow"] = RENDER_HEALTH["failing"]
        # a render that fails still answers in text, so images going is part of the bot down, not all of it
        components["images"] = PARTIAL if RENDER_HEALTH["failing"] >= RENDER_FAILS else OPERATIONAL
        if bot.is_ready():
            down = [name for name, running in _jobs().items() if not running]
            metrics["jobsDown"] = len(down)
            components["jobs"] = PARTIAL if down else OPERATIONAL
            if down:
                logger.warning("the status check found background jobs not running: %s", ", ".join(down))
    except Exception:
        logger.exception("the status check could not read the bot")
        components["bot"] = MAJOR
    try:
        charts = _charts()
        components["charts"] = charts["state"]
        if charts["ageHours"] is not None:
            metrics["chartDataAgeHours"] = charts["ageHours"]
    except Exception:
        logger.exception("the status check could not read the chart database's age")
    memory = _memory_mb()
    if memory is not None:
        metrics["memoryMb"] = memory
    try:
        held = _analysis()
        components["analysis"] = held["state"]
        metrics["analysisWaiting"] = held["waiting"]
        metrics["analysesCached"] = held["cached"]
    except Exception:
        logger.exception("the status check could not read the analysis queue")
        components["analysis"] = MAJOR
    return {"ok": True, "status": worst(components.values()), "components": components, "metrics": metrics}
