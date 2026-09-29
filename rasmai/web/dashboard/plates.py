from typing import Any, Dict, Optional

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.engine.plates import plate_missing, plate_overview
from rasmai.util import _json_safe


def plates_payload(cached: Optional[CachedAnalysis], plate: str = "", goal: str = "") -> Optional[Dict[str, Any]]:
    """Every plate's progress, or with `plate` and `goal` the charts one plate still needs; None for a plate that does not exist.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param plate: The plate's kanji, such as ``"真"``; empty for the overview.
    :type plate: str
    :param goal: The condition, such as ``"極"``.
    :type goal: str
    :rtype: Optional[Dict[str, Any]]
    """
    if cached is None:
        return {"plates": []}
    a = cached.analyzer
    if plate:
        return _json_safe(plate_missing(a.songs, a.chart_index, plate, goal)) if goal else None
    # a plate the player's cabinet has no charts for yet (a version not out in their region) is left off
    return {"plates": [p for p in plate_overview(a.songs, a.chart_index) if p["required"]]}
