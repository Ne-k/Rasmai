from typing import Any, Dict, List, Optional, Sequence, Tuple

from rasmai.engine.analysis.rating import ACHIEVEMENT_CAP, RANK_TARGETS, _normal_cdf, calculate_rating, rank_for
from rasmai.engine.analysis.charts import ChartIndex
from rasmai.engine.analysis.profile import PlayProfile
from rasmai.engine.analysis.pools import Best50
from rasmai.engine.analysis.planning.model import LADDER_ROWS


# A first pass on an unfamiliar chart lands below the player's curve, and scatters more
# than their repeat plays do: on the held-out plays of the June->September backtest the
# first-pass residuals spread 1.8x the played-chart sigma, so the odds are quoted on a
# wider spread than the repeat-play model uses.
FIRST_PASS_DROP = 0.35


FIRST_PASS_SPREAD = 1.5


def first_pass_expectation(profile: PlayProfile, key: Tuple[str, str, str], constant: float) -> Tuple[float, float]:
    """Expected score and spread for a chart the player has never tried.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: Tuple[str, str, str]
    :param constant: The chart's internal difficulty constant.
    :type constant: float
    :returns: ``(expected achievement, spread)``.
    :rtype: Tuple[float, float]
    """
    sigma = max(0.3, profile.sigma_at(constant))
    expected = profile.expected_for(constant, key[2]) - FIRST_PASS_DROP - 0.4 * sigma
    return expected, sigma * FIRST_PASS_SPREAD


def chart_prediction(profile: Optional[PlayProfile], key: Tuple[str, str, str], constant: float,
                     accuracy: float, played: bool = True) -> Optional[Dict[str, Any]]:
    """What the model expects on this chart: the score a good run lands, its spread, the chance of a new best.

    :param profile: How the player plays, as measured from their scores.
    :type profile: Optional[PlayProfile]
    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: Tuple[str, str, str]
    :param constant: The chart's internal difficulty constant.
    :type constant: float
    :param accuracy: Achievement on the chart, as a percentage.
    :type accuracy: float
    :param played: Whether the player has a score on the chart.
    :type played: bool
    :returns: The prediction, or ``None`` without a profile.
    :rtype: Optional[Dict[str, Any]]
    """
    if profile is None or constant <= 0 or not profile.sample_size:
        return None
    if played:
        expected, sigma = profile.chart_expectation(key, constant, accuracy)
    else:
        expected, sigma = first_pass_expectation(profile, key, constant)
    sigma = max(0.3, sigma)
    return {
        "expected": min(ACHIEVEMENT_CAP, expected),
        "sigma": sigma,
        "rank": rank_for(min(ACHIEVEMENT_CAP, expected)),
        "low": max(0.0, expected - sigma),
        "high": min(ACHIEVEMENT_CAP, expected + sigma),
        "new_best": _normal_cdf((expected - accuracy) / sigma) if played and accuracy > 0 else None,
        "plays": profile.plays_for(key),
        "tier_offset": profile.difficulty_offset.get(key[2], 0.0),
    }


def rank_ladder(profile: Optional[PlayProfile], best50: Optional[Best50], key: Tuple[str, str, str],
                constant: float, accuracy: float, is_new: bool, played: bool = True) -> List[Dict[str, Any]]:
    """What each rank above the current score is worth on one chart, and the odds of it.

    The table other trackers print stops at the rating: this one adds what the rank
    would add to the best-50 and how often this player lands a score like it.

    :param profile: How the player plays, as measured from their scores.
    :type profile: Optional[PlayProfile]
    :param best50: The player's two rating pools.
    :type best50: Optional[Best50]
    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: Tuple[str, str, str]
    :param constant: The chart's internal difficulty constant.
    :type constant: float
    :param accuracy: Achievement on the chart, as a percentage.
    :type accuracy: float
    :param is_new: Whether the chart counts toward the current-version pool.
    :type is_new: bool
    :param played: Whether the player has a score on the chart.
    :type played: bool
    :returns: One row per rank above the current score.
    :rtype: List[Dict[str, Any]]
    """
    if constant <= 0:
        return []
    if profile is None:
        expected, sigma = 0.0, 0.0
    elif played:
        expected, sigma = profile.chart_expectation(key, constant, accuracy)
    else:
        expected, sigma = first_pass_expectation(profile, key, constant)
    rows: List[Dict[str, Any]] = []
    for name, threshold in sorted(RANK_TARGETS, key=lambda pair: pair[1]):
        if threshold <= accuracy + 1e-9:
            continue
        rating = calculate_rating(constant, threshold)
        rows.append({
            "rank": name,
            "need": threshold,
            "rating": rating,
            "gain": best50.gain_if(key, is_new, rating) if best50 else 0,
            "odds": _normal_cdf((expected - threshold) / sigma) if sigma > 0 else 0.0,
        })
        if len(rows) >= LADDER_ROWS:
            break
    return rows


def played_keys(songs: Sequence[Any], chart_index: ChartIndex) -> set:
    """Every chart the player has a score on, under both the scraped and database spelling.

    :param songs: The player's scored charts.
    :type songs: Sequence[Any]
    :param chart_index: The chart database to look constants and metadata up in.
    :type chart_index: ChartIndex
    :returns: Every key the player's scores answer to.
    :rtype: set
    """
    played: set = set()
    for song in songs:
        key = (
            str(getattr(song, "name", "")).casefold(),
            str(getattr(song, "chart_type", "")).lower() or "std",
            str(getattr(song, "difficulty_type", "")).lower(),
        )
        played.add(key)
        chart = chart_index.get(key)
        if chart is not None:
            played.add(chart.key)
    return played


def target_tiers(profile: PlayProfile, accuracy: float, expected: float, sigma: float, constant: float,
                 stretch_sigmas: float, slack: float, played: bool = True):
    """Rank targets worth chasing on one chart: above the current score, inside reach.

    The eight-point cap keeps a played chart's target near what it already scores;
    an unplayed chart has no score to sit near, so the cap does not apply to it. A
    best that was itself a dropped run is treated as unplayed, and its estimate is a
    guess from the curve alone, so the stretch above it is held to half a spread.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param accuracy: Achievement on the chart, as a percentage.
    :type accuracy: float
    :param expected: The achievement a good run is predicted to land.
    :type expected: float
    :param sigma: The spread of the player's scores at this level.
    :type sigma: float
    :param constant: The chart's internal difficulty constant.
    :type constant: float
    :param stretch_sigmas: How many spreads above the expected score a target may sit.
    :type stretch_sigmas: float
    :param slack: How far past the player's best nearby score a target may reach.
    :type slack: float
    :param played: Whether the player has a score on the chart.
    :type played: bool
    :returns: The ranks worth chasing, with what each needs.
    """
    ceiling = min(ACHIEVEMENT_CAP, expected + stretch_sigmas * sigma)
    if played:
        ceiling = min(ceiling, accuracy + 8.0)
    elif accuracy > 0:
        ceiling = min(ceiling, expected + 0.5 * sigma)
    proof = profile.rank_ceiling(constant, slack=slack)
    for name, threshold in RANK_TARGETS:
        if threshold <= accuracy + 1e-9 or threshold > ceiling + 1e-9:
            continue
        if threshold >= 97.0 and threshold > proof + 1e-9:
            continue
        yield name, threshold
