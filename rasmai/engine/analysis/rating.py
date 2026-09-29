import math
import re
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# (minimum achievement, rank name, rating coefficient) - the official DX table
RANK_TABLE: List[Tuple[float, str, float]] = [
    (100.5, "SSS+", 22.4),
    (100.0, "SSS", 21.6),
    (99.5, "SS+", 21.1),
    (99.0, "SS", 20.8),
    (98.0, "S+", 20.3),
    (97.0, "S", 20.0),
    (94.0, "AAA", 16.8),
    (90.0, "AA", 15.2),
    (80.0, "A", 13.6),
    (75.0, "BBB", 12.8),
    (70.0, "BB", 12.4),
    (60.0, "B", 12.0),
    (50.0, "C", 10.4),
    (0.0, "D", 9.5),
]

# Scores exactly one unit under a rank boundary use their own coefficient.
BORDERLINE_COEFFICIENTS: Dict[float, float] = {
    100.4999: 22.2, 99.9999: 21.4, 99.4999: 21.0, 98.9999: 20.6, 96.9999: 17.6, 59.9999: 11.2,
}

ACHIEVEMENT_CAP = 100.5

# How far above their own best the model lets a good run sit, in sigmas. Zero: the centre of a
# prediction never sits above a score the player has already proved, because assuming improvement
# without evidence is what made targets look cheap. A run above the best is still perfectly
# possible, it just costs the spread; and a chart whose history shows real improvement is lifted
# afterwards by that history rather than by an assumption. Measured over 246 recorded runs, moving
# this from 0.3 to 0 called the exact rank right 64% of the time instead of 61% on runs that beat
# the player's best, and 42% instead of 39% on runs that did not.
BEST_HEADROOM = 0.0

# Targets worth aiming for, best first.
RANK_TARGETS: List[Tuple[str, float]] = [
    ("SSS+", 100.5),
    ("SSS", 100.0),
    ("SS+", 99.5),
    ("SS", 99.0),
    ("S+", 98.0),
    ("S", 97.0),
    ("AAA", 94.0),
    ("AA", 90.0),
]

@dataclass(frozen=True)
class Challenge:
    """How far above a player's usual scores the targets sit."""
    key: str
    label: str
    sigmas: float            # target ceiling: expected + sigmas * spread (0 = 50% odds, 0.67 = 25%, 1.3 = 10%, 2.2 = 1.5%)
    min_feasibility: float   # drop targets with lower odds
    slack: float             # how far past the best nearby score an S+ target may sit
    plan_min_feasibility: float
    plan_sigmas: float
    new_floor: float         # /new: lowest acceptable first-pass estimate
    new_reach: float         # /new: how far past the hardest cleared constant to look
    pick: str = "value"      # which rank to chase: "likely" (best odds), "value" (gain x odds) or "gain"

CHALLENGES: Dict[str, Challenge] = {
    "easy": Challenge("easy", "Easier", 0.35, 0.3, 0.5, 0.35, 0.4, 97.0, -0.7, pick="likely"),
    "balanced": Challenge("balanced", "Balanced", 1.0, 0.16, 1.0, 0.2, 1.0, 94.0, 0.3, pick="value"),
    "hard": Challenge("hard", "Challenging", 1.3, 0.08, 2.0, 0.1, 1.8, 92.0, 0.8, pick="gain"),
    "extreme": Challenge("extreme", "Long shots", 2.2, 0.03, 3.0, 0.04, 2.6, 90.0, 1.3, pick="gain"),
}

def challenge_for(key: Optional[str]) -> Challenge:
    return CHALLENGES.get(str(key or "balanced"), CHALLENGES["balanced"])

def rank_for(accuracy: float) -> str:
    for minimum, name, _coefficient in RANK_TABLE:
        if accuracy >= minimum:
            return name
    return "D"

def rating_coefficient(accuracy: float) -> float:
    for borderline, coefficient in BORDERLINE_COEFFICIENTS.items():
        if abs(accuracy - borderline) < 5e-5:
            return coefficient
    for minimum, _name, coefficient in RANK_TABLE:
        if accuracy >= minimum:
            return coefficient
    return RANK_TABLE[-1][2]

def calculate_rating(constant: float, accuracy: float) -> int:
    if not (math.isfinite(constant) and math.isfinite(accuracy)):
        return 0      # a score that never parsed is worth nothing, not a crash
    if constant <= 0 or accuracy <= 0:
        return 0
    capped = min(accuracy, ACHIEVEMENT_CAP)
    return int(math.floor(constant * (capped / 100.0) * rating_coefficient(capped)))

def accuracy_for_rating(constant: float, wanted_rating: int) -> Optional[float]:
    """Lowest achievement that scores at least `wanted_rating` on this chart.

    :param constant: The chart's internal difficulty constant.
    :type constant: float
    :param wanted_rating: The rating the achievement has to reach.
    :type wanted_rating: int
    :returns: The achievement needed, or ``None`` when the rating is out of reach.
    :rtype: Optional[float]
    """
    if constant <= 0:
        return None
    bands = list(reversed(RANK_TABLE))  # lowest rank first
    for index, (minimum, _name, coefficient) in enumerate(bands):
        band_top = bands[index + 1][0] if index + 1 < len(bands) else ACHIEVEMENT_CAP
        needed = wanted_rating * 100.0 / (constant * coefficient)
        if needed < minimum:
            needed = minimum
        if needed <= band_top + 1e-9 and needed <= ACHIEVEMENT_CAP + 1e-9:
            # Guard against floor() rounding leaving us one point short.
            candidate = min(ACHIEVEMENT_CAP, round(needed, 4))
            while candidate <= ACHIEVEMENT_CAP and calculate_rating(constant, candidate) < wanted_rating:
                candidate = round(candidate + 0.0001, 4)
            if candidate <= ACHIEVEMENT_CAP and calculate_rating(constant, candidate) >= wanted_rating:
                return candidate
    return None

_normal_cdf = statistics.NormalDist().cdf

# The rating colour bands, from SilentBlue RemyWiki's "maimai DX:Rating". The game also cuts gold,
# platinum and rainbow into 250-point steps (JiETNG lists 14250, 14750, 15250...); those are frame
# variants inside one colour, so the table keeps the colours and rating_step the steps. The fills follow the game's
# frames: white to purple a flat colour with deeper sides, bronze dark to light left to right, silver an icy blue
# sheen, gold and platinum (a pale champagne) a diagonal glint, rainbow pastel bands corner to corner, kiwami
# (16000+, CiRCLE PLUS) the same bands saturated. Bronze and kiwami are lifted a little so ink type still reads.
# web/components/dash/band.ts carries the same table.
RATING_BANDS: List[Tuple[int, str, str]] = [
    (16000, "kiwami", "linear-gradient(120deg, #c070f4, #ff6cc8 18%, #ffd23a 36%, #62e070 54%, #3cc8f5 72%, #9a7cff)"),
    (15000, "rainbow", "linear-gradient(120deg, #ffa0d2, #ffe07a 20%, #c6f27c 38%, #8ee6f2 58%, #aab8ff 78%, #f0a8f0)"),
    (14500, "platinum", "linear-gradient(120deg, #f4de78, #fffbe2 16%, #f9e99a 32%, #fff5c6 60%, #eed266)"),
    (14000, "gold", "linear-gradient(120deg, #ffc81a, #fff4a8 16%, #ffd83a 32%, #f7b02a 62%, #ffcf2a)"),
    (13000, "silver", "linear-gradient(120deg, #b2d2ef, #e9f5fd 18%, #bcd8f2 34%, #d9ecfa 62%, #a2c4e5)"),
    (12000, "bronze", "linear-gradient(90deg, #c0683e, #d47f48 45%, #f0a462)"),
    (10000, "purple", "linear-gradient(90deg, #b070ec, #d8a4f6 22%, #d8a4f6 78%, #b070ec)"),
    (7000, "red", "linear-gradient(90deg, #e8606c, #f59a9a 22%, #f59a9a 78%, #e8606c)"),
    (4000, "yellow", "linear-gradient(90deg, #f0a030, #f9c848 22%, #f9c848 78%, #f0a030)"),
    (2000, "green", "linear-gradient(90deg, #7fd045, #a8e864 22%, #a8e864 78%, #7fd045)"),
    (1000, "blue", "linear-gradient(90deg, #a4dcfa, #78c6f5 22%, #78c6f5 78%, #a4dcfa)"),
    (0, "white", "linear-gradient(90deg, #a9dcf8, #f4fbff 20%, #ffffff 50%, #f4fbff 80%, #a9dcf8)"),
]

def rating_band(rating: Any) -> Tuple[str, str]:
    """The colour band a rating sits in.

    :param rating: The player's rating.
    :type rating: Any
    :returns: The band's name (``"gold"``) and its CSS fill, a gradient.
    :rtype: Tuple[str, str]
    """
    try:
        value = int(rating or 0)
    except (TypeError, ValueError):
        value = 0
    return next((key, fill) for minimum, key, fill in RATING_BANDS if value >= minimum or minimum == 0)

# the bands the game cuts into 250-point steps, marked with stars: 2 in gold and platinum, up to 4 in rainbow and kiwami
STEPPED_BANDS = ("gold", "platinum", "rainbow", "kiwami")


def rating_step(rating: Any) -> int:
    """Which 250-point step of a gold, platinum, rainbow or kiwami band a rating is on, 1 to 4; 0 in the other bands.

    :param rating: The player's rating.
    :type rating: Any
    :rtype: int
    """
    try:
        value = int(rating or 0)
    except (TypeError, ValueError):
        return 0
    minimum, key, _fill = next(band for band in RATING_BANDS if value >= band[0] or band[0] == 0)
    return min(4, 1 + (value - minimum) // 250) if key in STEPPED_BANDS else 0

def parse_constant(raw: Any) -> float:
    if raw is None:
        return 0.0
    text = str(raw).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    match = re.match(r"(\d+)(\+?)", text)
    if not match:
        return 0.0
    base = float(match.group(1))
    return base + (0.6 if match.group(2) else 0.0)

def version_major(raw: Any) -> int:
    text = str(raw or "").strip()
    if len(text) < 2 or not text[:2].isdigit():
        return 0
    return int(text[:2])
