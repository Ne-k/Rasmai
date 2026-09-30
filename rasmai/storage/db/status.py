from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import json

from rasmai.storage.db.connection import get_database_connection

SAMPLE_MINUTES = 5       # how often the bot writes one; a slot with no sample is a slot the bot was not running
KEPT_DAYS = 90
RECENT_HOURS = 24
# a component counts as up in any of these: a slow one is still answering and maintenance is announced
_UP = ("operational", "degraded_performance", "under_maintenance")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_status_sample(payload: Dict[str, Any], now: Optional[datetime] = None) -> None:
    """Keep one reading of the components, and drop what is past the 90 days the page shows.

    :param payload: What :func:`rasmai.web.statuspage.status_payload` returned.
    :type payload: Dict[str, Any]
    """
    now = now or _now()
    metrics = payload.get("metrics") or {}
    connection = get_database_connection()
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO status_samples (at, states, gateway_ms, waiting) VALUES (?, ?, ?, ?)",
                (now.isoformat(timespec="seconds"), json.dumps(payload.get("components") or {}),
                 int(metrics.get("gatewayMs") or 0), int(metrics.get("analysisWaiting") or 0)),
            )
            connection.execute("DELETE FROM status_samples WHERE at < ?",
                               ((now - timedelta(days=KEPT_DAYS + 1)).isoformat(timespec="seconds"),))
    finally:
        connection.close()


def status_history(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Uptime per component per day for the last 90 days, and the last day's readings.

    Uptime is measured against the slots there should have been since the first sample, so a stretch
    with no sample counts as down: it is a stretch in which the bot was not running to write one.

    :rtype: Dict[str, Any]
    """
    now = now or _now()
    start = now - timedelta(days=KEPT_DAYS)
    connection = get_database_connection()
    try:
        rows = connection.execute("SELECT at, states, gateway_ms, waiting FROM status_samples WHERE at >= ? ORDER BY at",
                                  (start.isoformat(timespec="seconds"),)).fetchall()
    finally:
        connection.close()
    if not rows:
        return {"ok": True, "sampleMinutes": SAMPLE_MINUTES, "since": None, "days": [], "recent": []}
    first = datetime.fromisoformat(rows[0]["at"])
    slot = timedelta(minutes=SAMPLE_MINUTES)
    days: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        moment = datetime.fromisoformat(row["at"])
        day = days.setdefault(moment.strftime("%Y-%m-%d"), {"samples": 0, "components": {}})
        day["samples"] += 1
        for name, state in json.loads(row["states"]).items():
            counts = day["components"].setdefault(name, {"up": 0, "degraded": 0})
            counts["up"] += state in _UP
            counts["degraded"] += state == "degraded_performance"
    out: List[Dict[str, Any]] = []
    for offset in range(KEPT_DAYS, -1, -1):
        midnight = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        # the slots of this day that fall between the first sample and now
        lo, hi = max(midnight, first), min(midnight + timedelta(days=1), now)
        expected = max(0, int((hi - lo) / slot))
        if not expected:
            continue
        held = days.get(midnight.strftime("%Y-%m-%d"), {"samples": 0, "components": {}})
        out.append({"day": midnight.strftime("%Y-%m-%d"), "expected": expected, "samples": held["samples"],
                    "components": held["components"]})
    since = (now - timedelta(hours=RECENT_HOURS)).isoformat(timespec="seconds")
    recent = [{"at": r["at"], "gatewayMs": r["gateway_ms"], "waiting": r["waiting"]} for r in rows if r["at"] >= since]
    return {"ok": True, "sampleMinutes": SAMPLE_MINUTES, "since": rows[0]["at"], "days": out, "recent": recent}
