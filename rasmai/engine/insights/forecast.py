from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
import statistics

from rasmai.engine.analysis import next_milestone


def rating_forecast(history: Sequence[Dict[str, Any]], now: Optional[datetime] = None,
                    window_days: int = 120) -> Optional[Dict[str, Any]]:
    """Rating per day from the recorded readings (median pairwise slope), and the dates the next milestones land.

    :param history: The stored points, oldest first.
    :type history: Sequence[Dict[str, Any]]
    :param now: The moment to measure from.
    :type now: Optional[datetime]
    :param window_days: How many days back to look.
    :type window_days: int
    :rtype: Optional[Dict[str, Any]]
    """
    now = now or datetime.now()
    points: List[Tuple[float, int]] = []
    for row in history:
        try:
            when = datetime.fromisoformat(str(row.get("recorded_at") or row.get("recordedAt")))
        except (TypeError, ValueError):
            continue
        if when.tzinfo is not None:
            when = when.astimezone().replace(tzinfo=None)
        age = (now - when).total_seconds() / 86400.0
        if age <= window_days:
            points.append((-age, int(row.get("rating") or 0)))
    points.sort()
    if len(points) < 3:
        return None
    span = points[-1][0] - points[0][0]
    if span < 10:
        return None
    slopes = [(r2 - r1) / (t2 - t1) for i, (t1, r1) in enumerate(points) for (t2, r2) in points[i + 1:] if t2 - t1 >= 1.0]
    if not slopes:
        return None
    per_day = statistics.median(slopes)
    current = points[-1][1]
    out: Dict[str, Any] = {
        "perDay": round(per_day, 2), "perWeek": round(per_day * 7, 1), "perMonth": round(per_day * 30, 0),
        "spanDays": int(round(span)), "readings": len(points), "targets": [], "flat": per_day < 0.15,
    }
    if per_day >= 0.15:
        goal = next_milestone(current)
        for _ in range(2):
            days = (goal - current) / per_day
            if days > 730:
                break
            out["targets"].append({"rating": goal, "days": int(round(days)), "date": (now + timedelta(days=days)).date().isoformat()})
            goal += 1000
    return out
