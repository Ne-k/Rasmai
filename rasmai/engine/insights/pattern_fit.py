from typing import Any, Dict, Sequence, Tuple
import logging
import math

logger = logging.getLogger(__name__)

Key = Tuple[str, str, str]

# How far a chart's patterns may move it, fitted in tools/laya_eval.py against 105 plays eight
# accounts made after the snapshot the ranking was built from.
#
# Unlike the decision model this one is worth listening to, and its best setting is not zero.
# Inside the shortlist the arithmetic alone places a played chart at 0.565, where 0.5 is a coin
# toss; at 0.10 that becomes 0.588 with six of the eight accounts improving. Higher is worse
# (0.25 -> 0.586, 0.5 -> 0.578) and the wrong way round is much worse (-0.25 -> 0.489), so the
# sign means something: a player goes back to the patterns they already score well on.
#
# Small sample, though. Held out a player at a time, six of eight still improve, but the two that
# do not lose more than the six gain, and a sign test on that is p=0.15. Read it as promising
# rather than proven, which is why it is a beta and off until someone asks for it.
WEIGHT = 0.10

# a chart nothing was measured on lands on exactly 1.0, and no chart is ever multiplied out of a
# list the arithmetic says is worth playing
FLOOR = 0.25
CEILING = 2.0


def offsets(profile: Any, charts: Sequence[Dict[str, Any]]) -> Dict[Key, float]:
    """Each chart's patterns added up against how this player scores on charts carrying them.

    Positive where the chart is made of the things they beat their own curve on, negative where it
    is made of what costs them. Every measured axis counts, not only the few that cleared the bar
    to be *named* as a trait: half of the accounts measured have no named trait at all, and reading
    only those leaves the whole thing saying nothing for them.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param charts: The shortlist, each carrying a ``key`` and a ``ref`` chart.
    :type charts: Sequence[Dict[str, Any]]
    :rtype: Dict[Key, float]
    """
    try:
        from rasmai.engine.insights.tags import chart_traits
    except Exception:
        return {}
    axes = {(axis.get("dimension"), axis.get("label")): float(axis.get("offset", 0.0))
            for axis in (getattr(profile, "trait_axes", None) or [])}
    if not axes:
        return {}
    out: Dict[Key, float] = {}
    for chart in charts:
        ref = chart.get("ref")
        if ref is None:
            continue
        try:
            out[chart["key"]] = sum(axes.get(trait, 0.0) for trait in chart_traits(ref))
        except Exception as error:
            logger.debug(f"pattern fit could not read {chart.get('key')}: {error}")
    return out


def taste(profile: Any, charts: Sequence[Dict[str, Any]], weight: float = WEIGHT) -> Dict[Key, float]:
    """The pattern verdict as the multiplier the ranking already understands.

    The verdict is in achievement points either side of the player's own curve, so it is used as
    it stands rather than ranked: a chart carrying nothing measured is worth 0.0 and lands on
    exactly 1.0, which is how it stays out of the way instead of being sorted arbitrarily among
    every other chart nothing was measured on.

    :param weight: 0.0 leaves the ranking exactly as it was, and larger is more said.
    :type weight: float
    :rtype: Dict[Key, float]
    """
    if weight <= 0:
        return {}
    return {key: min(CEILING, max(FLOOR, math.exp(weight * value)))
            for key, value in offsets(profile, charts).items()}
