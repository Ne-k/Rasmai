from typing import Any, Dict, List, Optional, Sequence, Tuple
import math
import statistics

from rasmai.engine.analysis import ChartIndex, PlayProfile, _normal_cdf


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


DEFAULT_RUN_SPREAD = 0.5     # how far one run falls from the next until the player's own repeats say otherwise


RUN_SPREAD_BOUNDS = (0.3, 1.5)


RUN_SPREAD_PAIRS = 12        # pairs of plays on one chart before the measurement is trusted over the default


DROPPED_RUN = 5.0            # a play this far under the player's own best on that chart was abandoned


def run_spread(plays: Sequence[Dict[str, Any]]) -> Optional[float]:
    """How far one run on a chart falls from the next: the spread of a single score, in achievement points.

    The difference between two plays of the same chart cancels the chart's own difficulty and the
    player's standing on it, so what is left is run-to-run variation. Two independent runs differ by
    root two spreads, and the median absolute difference is used in place of a standard deviation so
    an abandoned run does not widen it. Returns None until there are enough pairs to say anything.

    This is not the same number as the scatter of a player's scores across different charts, which is
    mostly the charts differing from each other. Using that one for a chart the player already holds a
    score on is what made every rank target look reachable.

    :param plays: Stored plays, each with a chart key and an achievement.
    :type plays: Sequence[Dict[str, Any]]
    :returns: The spread of a single run, or None when the player has too few repeats.
    :rtype: Optional[float]
    """
    by_chart: Dict[str, List[Tuple[str, float]]] = {}
    for play in plays or []:
        key = str(play.get("key") or "")
        achievement = float(play.get("achievement") or 0)
        if not key or not (0 < achievement <= 101.0):
            continue
        by_chart.setdefault(key, []).append((str(play.get("played_at") or ""), achievement))
    gaps: List[float] = []
    for runs in by_chart.values():
        if len(runs) < 2:
            continue
        runs.sort()
        # a run that fell far short of what the player manages on the chart was dropped, not attempted
        floor = max(value for _when, value in runs) - DROPPED_RUN
        kept = [(when, value) for when, value in runs if value >= floor]
        gaps.extend(abs(second - first) for (_t1, first), (_t2, second) in zip(kept, kept[1:]))
    if len(gaps) < RUN_SPREAD_PAIRS:
        return None
    measured = 1.4826 * statistics.median(gaps) / math.sqrt(2.0)
    # thin evidence leans on the default; a player with a long history is measured on their own runs
    weight = len(gaps) / (len(gaps) + 15.0)
    blended = DEFAULT_RUN_SPREAD + (measured - DEFAULT_RUN_SPREAD) * weight
    return _clamp(blended, *RUN_SPREAD_BOUNDS)


def calibrate(profile: PlayProfile, plays: Sequence[Dict[str, Any]], chart_index: ChartIndex) -> Dict[str, Any]:
    """Score the model's predictions against the player's recorded plays and derive corrections.

    Each play is predicted from the best the player held before it; a play with no earlier
    recorded score is left out, since the best it was measured against is unknown. The model's centre is
    'a good run', so the upper third of residuals should sit on zero; the spread should
    make one standardised residual cover about two thirds of plays. Where enough plays say
    otherwise, the spread is rescaled and the centre shifted, shrunk toward no change.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param plays: How many times the chart has been played.
    :type plays: Sequence[Dict[str, Any]]
    :param chart_index: The chart database to look constants and metadata up in.
    :type chart_index: ChartIndex
    :rtype: Dict[str, Any]
    """
    zs: List[float] = []
    residuals: List[float] = []
    per_tier: Dict[str, List[float]] = {}
    predicted_new_best: List[float] = []
    actual_new_best: List[float] = []
    inside = 0
    for play in plays:
        raw_key = play.get("key")
        key = tuple(str(raw_key).split("|", 2)) if isinstance(raw_key, str) else tuple(raw_key or ())
        if len(key) != 3:
            continue
        chart = chart_index.get(key)   # type: ignore[arg-type]
        if chart is None or chart.constant <= 0:
            continue
        achievement = float(play.get("achievement") or 0)
        best_before = float(play.get("best_before") or 0)
        if achievement <= 0 or best_before <= 0:
            continue          # only a play with a recorded score before it is a fair test of a prediction
        mu, sigma = profile.chart_expectation(chart.key, chart.constant, best_before)
        sigma = max(0.3, sigma)
        z = (achievement - mu) / sigma
        if z < -4:
            continue          # a run that was dropped, not an attempt at the chart
        zs.append(z)
        residuals.append(achievement - mu)
        per_tier.setdefault(chart.difficulty, []).append(achievement - mu)
        if abs(z) <= 1:
            inside += 1
        predicted_new_best.append(_normal_cdf((mu - best_before) / sigma))
        actual_new_best.append(1.0 if achievement >= best_before - 1e-4 else 0.0)

    n = len(zs)
    result: Dict[str, Any] = {"plays": n}
    if n < 15:
        return result
    centre = statistics.median(zs)
    robust = 1.4826 * statistics.median(abs(z - centre) for z in zs)
    scale = 1.0 + (_clamp(robust, 0.6, 1.8) - 1.0) * n / (n + 30.0)
    upper_third = _quantile(residuals, 0.65)
    shift = _clamp(upper_third * n / (n + 30.0), -2.0, 2.0)
    tier_shifts: Dict[str, float] = {}
    for tier, values in per_tier.items():
        if len(values) >= 8:
            tier_shifts[tier] = round(_clamp((_quantile(values, 0.65) - upper_third) * len(values) / (len(values) + 20.0), -2.0, 2.0), 2)
    result.update({
        "sigmaScale": round(scale, 2),
        "shift": round(shift, 2),
        "tierShifts": tier_shifts,
        "coverage": round(inside / n, 2),
        "newBestPredicted": round(statistics.fmean(predicted_new_best), 2) if predicted_new_best else None,
        "newBestActual": round(statistics.fmean(actual_new_best), 2) if actual_new_best else None,
    })
    return result


def apply_calibration(profile: PlayProfile, result: Dict[str, Any]) -> None:
    profile.calibration = dict(result)
    if result.get("plays", 0) < 15:
        return
    profile.sigma_scale = float(result.get("sigmaScale", 1.0))
    profile.calibration_shift = float(result.get("shift", 0.0))
    profile.tier_shift = {tier: float(value) for tier, value in (result.get("tierShifts") or {}).items()}
