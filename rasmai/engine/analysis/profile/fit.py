import math
import statistics
from typing import Dict, List, Sequence, Tuple


def _bias_map(counts: Dict[str, int], strength: float = 0.35) -> Dict[str, float]:
    """Turn play counts into multipliers centred on 1.0.

    :param counts: How often each value was played.
    :type counts: Dict[str, int]
    :param strength: How far the multipliers may stray from 1.0.
    :type strength: float
    :returns: A multiplier per value, centred on 1.0.
    :rtype: Dict[str, float]
    """
    total = sum(counts.values())
    if total <= 0 or len(counts) < 2:
        return {}
    average = total / len(counts)
    bias: Dict[str, float] = {}
    for key, count in counts.items():
        ratio = count / average
        bias[key] = 1.0 + strength * math.tanh(ratio - 1.0)
    return bias


def _fit_skill_curve(points: Sequence[Tuple[float, float]]):
    """Achievement-vs-constant fit on what the player scores when a run goes well.

    Returns (intercept, slope, sigma, bucket_stats, dense_ceiling).

    :param points: ``(constant, achievement)`` pairs to fit.
    :type points: Sequence[Tuple[float, float]]
    :returns: ``(intercept, slope, sigma, bucket stats, dense ceiling)``.
    """
    buckets: Dict[float, List[float]] = {}
    for constant, accuracy in points:
        buckets.setdefault(round(constant * 2) / 2, []).append(accuracy)

    stats: Dict[float, Tuple[float, int, float]] = {}
    samples: List[Tuple[float, float, float]] = []  # constant, representative, weight
    for constant, values in buckets.items():
        values.sort()
        # a well-populated level shows what the player does when they try (upper quartile);
        # a thin one only supports a more cautious read
        quantile = 0.75 if len(values) >= 6 else 0.65
        representative = values[min(len(values) - 1, int(round(quantile * (len(values) - 1))))]
        stats[constant] = (representative, len(values), values[-1])
        samples.append((constant, representative, float(min(len(values), 10))))

    dense = [c for c, (_r, n, _b) in stats.items() if n >= 3]
    dense_ceiling = max(dense) if dense else (max(stats) - 0.5 if stats else 0.0)

    if len(points) < 8 or len(samples) < 3:
        return 101.0, -0.3, 0.9, stats, dense_ceiling

    weight_total = sum(w for _c, _a, w in samples)
    mean_x = sum(c * w for c, _a, w in samples) / weight_total
    mean_y = sum(a * w for _c, a, w in samples) / weight_total
    covariance = sum(w * (c - mean_x) * (a - mean_y) for c, a, w in samples)
    variance = sum(w * (c - mean_x) ** 2 for c, _a, w in samples)
    slope = covariance / variance if variance > 1e-9 else -0.3
    slope = max(-2.5, min(-0.2, slope))
    intercept = mean_y - slope * mean_x

    # spread of the good runs around each level's typical score, over the levels the
    # player actually works at (easy charts are played carelessly and would inflate it)
    top = max(stats)
    residuals: List[float] = []
    for constant, values in buckets.items():
        if constant < top - 4.0 or len(values) < 3:
            continue
        representative = stats[constant][0]
        residuals.extend(value - representative for value in values[len(values) // 2:])
    sigma = statistics.pstdev(residuals) if len(residuals) > 4 else 0.9
    return intercept, slope, max(0.4, min(2.0, sigma)), stats, dense_ceiling
