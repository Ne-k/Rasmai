from typing import Any, Dict
import logging

from rasmai.config import MAX_CONCURRENT_SCRAPES
from rasmai.storage.db import get_database_connection

logger = logging.getLogger(__name__)

# Statuspage's own words for a component, worst last
OPERATIONAL, MAINTENANCE, DEGRADED, PARTIAL, MAJOR = (
    "operational", "under_maintenance", "degraded_performance", "partial_outage", "major_outage")
_ORDER = (OPERATIONAL, MAINTENANCE, DEGRADED, PARTIAL, MAJOR)

SLOW_GATEWAY_MS = 1500     # Discord answering slower than this is a bot people notice
LONG_LINE = 10             # people waiting on a build, warm-ups not counted, before the dashboard is called slow


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
        live = _bot()
        components["bot"] = live["discord"]
        components["maimai"] = live["maimai"]
        metrics["gatewayMs"] = live["gatewayMs"]
        metrics["scrapesInFlight"] = live["scrapesInFlight"]
    except Exception:
        logger.exception("the status check could not read the bot")
        components["bot"] = MAJOR
    try:
        held = _analysis()
        components["analysis"] = held["state"]
        metrics["analysisWaiting"] = held["waiting"]
        metrics["analysesCached"] = held["cached"]
    except Exception:
        logger.exception("the status check could not read the analysis queue")
        components["analysis"] = MAJOR
    return {"ok": True, "status": worst(components.values()), "components": components, "metrics": metrics}
