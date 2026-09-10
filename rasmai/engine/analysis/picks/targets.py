from typing import Optional, Tuple

from rasmai.engine.analysis.rating import ACHIEVEMENT_CAP, CHALLENGES, Challenge, RANK_TARGETS, _normal_cdf, calculate_rating
from rasmai.engine.analysis.profile import PlayProfile
from rasmai.engine.analysis.picks.model import DROPPED_BEST_STRETCH


def _freshness(profile: PlayProfile, key: Tuple[str, str, str]) -> float:
    """Recently ground charts are worth less: the easy points are already taken.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: Tuple[str, str, str]
    :returns: A multiplier below 1.0 for charts the player has been grinding.
    :rtype: float
    """
    index = profile.recent_keys.get(key)
    if index is None:
        return 1.0
    grind = profile.recent_grind.get(key, 1)
    if grind >= 3:
        return 0.45
    if index < 5:
        return 0.75 if grind == 1 else 0.6
    if index < 15:
        return 0.95
    return 1.0


def _target_for(
    profile: PlayProfile, key: Tuple[str, str, str], constant: float, accuracy: float,
    challenge: Challenge = CHALLENGES["balanced"],
) -> Optional[Tuple[str, float]]:
    """The rank worth chasing here: the best expected rating gain, not simply the next rank.

    A target of S or better also needs proof - a score near it on a chart about this
    hard - so a player who has never seen 97% on a 12.5 is not told to S a 13, while a
    player with SS+ on 14s still gets pushed. The challenge level sets how far above
    the player's usual score the ceiling sits and how much proof is required.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: Tuple[str, str, str]
    :param constant: The chart's internal difficulty constant.
    :type constant: float
    :param accuracy: Achievement on the chart, as a percentage.
    :type accuracy: float
    :param challenge: How bold the targets are: ``"easy"``, ``"balanced"``, ``"hard"`` or ``"extreme"``.
    :type challenge: Challenge
    :returns: The rank and the achievement it needs, or ``None`` when nothing is worth chasing.
    :rtype: Optional[Tuple[str, float]]
    """
    expected, sigma = profile.chart_expectation(key, constant, accuracy)
    # how far the chart could take them is a question about practice, and charts differ; whether one
    # run lands it is a question about that run alone. The first sets what may be aimed at, the
    # second prices it, so a chart with real headroom is still offered and still priced honestly.
    reach = max(sigma, profile.sigma_at(constant))
    ceiling = min(ACHIEVEMENT_CAP, expected + challenge.sigmas * reach)
    if profile.dropped_best(key, constant, accuracy):
        # a best that was itself a dropped run is no anchor: the target is what a first pass would land.
        # The estimate is a guess from the curve alone, so no level stretches far past it
        ceiling = min(ceiling, expected + DROPPED_BEST_STRETCH * sigma)
    else:
        # a score they are working up from: the target stays within a few points of it
        plays = profile.plays_for(key)
        familiarity = plays / (plays + 3.0)
        recovery = max(0.0, expected - accuracy) * (1.0 - familiarity)
        ceiling = min(ceiling, accuracy + min(6.0, 1.5 + recovery + challenge.sigmas))
    proof = profile.rank_ceiling(constant, slack=challenge.slack)
    current_rating = calculate_rating(constant, accuracy)

    best: Optional[Tuple[str, float]] = None
    best_value = 0.0
    for name, threshold in RANK_TARGETS:
        if threshold <= accuracy + 1e-9 or threshold > ceiling + 1e-9:
            continue
        if threshold >= 97.0 and threshold > proof + 1e-9:
            continue
        feasibility = _normal_cdf((expected - threshold) / sigma)
        if feasibility < challenge.min_feasibility:
            continue
        gain = calculate_rating(constant, threshold) - current_rating
        if gain <= 0:
            continue
        if challenge.pick == "likely":
            value = feasibility + gain / 10000.0
        elif challenge.pick == "gain":
            value = gain + feasibility
        else:
            value = gain * feasibility
        if value > best_value:
            best, best_value = (name, threshold), value
    return best
