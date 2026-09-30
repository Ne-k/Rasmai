from typing import Dict, Tuple

WEIGHTS = {"tap": 1, "hold": 2, "slide": 3, "touch": 1, "break": 5}      # shares of the 100% each note is worth


def note_losses(notes: Dict[str, Dict[str, int]], achievement: float,
                bonus_apart: bool = False) -> Dict[str, float]:
    """Percent of achievement lost per note type, summing to what was missing from 101%.

    The arithmetic follows maimai-score-details by SpiritsUnite (Apache-2.0, see THIRD_PARTY_NOTICES.md).
    A break is worth five shares plus an equal slice of the 1% bonus; a great keeps 80% of a note, a good
    50%, a break good 40% and a break miss nothing.

    A break great and a break perfect each come in grades the page does not show: a great keeps 80%,
    60% or 50% of the break, and a perfect half or three quarters of its slice of the bonus (only a
    critical keeps all of it). The achievement says which mix it was, so the mix that comes closest
    to it is the one charged. Over 457 recorded plays, every record fits exactly except three whose
    counts cannot give their achievement at all, and on all but 8 of the 263 with a break great,
    every mix that fits puts the same cost on the greats.

    The bonus a perfect gives up is lost by anyone not hunting criticals, on a run with nothing else
    wrong with it, so `bonus_apart` puts the bonus under "bonus" rather than letting it read as a break
    gone wrong. What a break great costs of the break itself stays on breaks.

    :param notes: Judgement counts per note type, as the play detail page lists them.
    :type notes: Dict[str, Dict[str, int]]
    :param achievement: The play's achievement.
    :type achievement: float
    :param bonus_apart: Whether the break bonus is reported on its own rather than charged to breaks.
    :type bonus_apart: bool
    :rtype: Dict[str, float]
    """
    counts = {kind: notes.get(kind) or {} for kind in WEIGHTS}
    total = sum(WEIGHTS[kind] * sum(int(v) for v in row.values()) for kind, row in counts.items())
    if total <= 0:
        return {}
    base = 100.0 / total
    breaks = sum(int(v) for v in counts["break"].values())
    lost: Dict[str, float] = {}
    for kind, row in counts.items():
        if not row:
            continue
        great, good, miss = int(row.get("great", 0)), int(row.get("good", 0)), int(row.get("miss", 0))
        if kind == "break":
            lost[kind] = good * 3 * base + miss * 5 * base
        else:
            lost[kind] = WEIGHTS[kind] * base * (great / 5 + good / 2 + miss)
    bonus = 0.0
    if breaks:
        row = counts["break"]
        perfect, great = int(row.get("perfect", 0)), int(row.get("great", 0))
        # the slice of the 1% each break gives up where the judgement alone settles it
        bonus = (great * 0.6 + int(row.get("good", 0)) * 0.7 + int(row.get("miss", 0))) / breaks
        missing = 101.0 - achievement - sum(lost.values()) - bonus
        great_lost, perfect_lost = _break_grades(perfect, great, base, breaks, missing)
        lost["break"] += great_lost
        bonus += perfect_lost
        # what even the closest mix leaves over rides with the bonus: on a sound record it
        # is the last digit the achievement cuts off, and on one whose counts cannot give its
        # achievement it is not a break's to carry
        bonus += max(0.0, 101.0 - sum(lost.values()) - bonus - achievement)
    if bonus_apart:
        if bonus:
            lost["bonus"] = bonus
    elif "break" in lost:
        lost["break"] += bonus
    return lost


def _break_grades(perfect: int, great: int, base: float, breaks: int, missing: float) -> Tuple[float, float]:
    """What the break greats cost of the break and the break perfects of the bonus, in the mix of
    grades that comes closest to `missing`.

    A great keeps 80%, 60% or 50% of the break, so it costs 1, 2 or 2.5 shares. A perfect costs a
    quarter or half of its slice of the bonus. For each split of the greats, the number of
    three-quarter perfects follows from what is left, so only the greats are searched. maimai cuts
    the achievement off at four places rather than rounding it, so the real loss sits up to 0.0001
    below the one shown, and the mix is aimed at the middle of that.

    :param perfect: Break perfects.
    :type perfect: int
    :param great: Break greats.
    :type great: int
    :param base: What one share is worth, in percent.
    :type base: float
    :param breaks: Breaks in the chart.
    :type breaks: int
    :param missing: What the rest of the play does not account for, in percent.
    :type missing: float
    :rtype: Tuple[float, float]
    """
    slice_ = 1.0 / breaks
    missing -= 0.00005
    closest = None
    for high in range(great + 1):
        for middle in range(great - high + 1):
            great_lost = base * (high + 2 * middle + 2.5 * (great - high - middle))
            # every perfect at a half slice, less a quarter back for each one that kept three quarters
            better = round((perfect * 0.5 * slice_ + great_lost - missing) / (0.25 * slice_))
            better = min(perfect, max(0, better))
            perfect_lost = (perfect * 0.5 - better * 0.25) * slice_
            off = abs(great_lost + perfect_lost - missing)
            if closest is None or off < closest[0]:
                closest = (off, great_lost, perfect_lost)
    return closest[1], closest[2]


def counts_fit(notes: Dict[str, Dict[str, int]], achievement: float) -> bool:
    """Whether a judgement page could have given this achievement.

    Now and then a stored play's judgement page and achievement do not belong together: a 26% run
    with a handful of misses, or twenty break misses on a 97. Such a page's losses say nothing about
    the player, and one of them outweighs a hundred sound plays, so
    what reads note types across many plays leaves it out. The test is loose on purpose: the loss
    has to fall between what the counts cost at best and at worst, grades unseen included.

    :param notes: Judgement counts per note type, as the play detail page lists them.
    :type notes: Dict[str, Dict[str, int]]
    :param achievement: The play's achievement.
    :type achievement: float
    :rtype: bool
    """
    counts = {kind: notes.get(kind) or {} for kind in WEIGHTS}
    total = sum(WEIGHTS[kind] * sum(int(v) for v in row.values()) for kind, row in counts.items())
    if total <= 0:
        return False
    base = 100.0 / total
    least = 0.0
    for kind, row in counts.items():
        great, good, miss = int(row.get("great", 0)), int(row.get("good", 0)), int(row.get("miss", 0))
        if kind == "break":
            least += good * 3 * base + miss * 5 * base
        else:
            least += WEIGHTS[kind] * base * (great / 5 + good / 2 + miss)
    most = least
    row = counts["break"]
    breaks = sum(int(v) for v in row.values())
    if breaks:
        great, perfect = int(row.get("great", 0)), int(row.get("perfect", 0))
        settled = (great * 0.6 + int(row.get("good", 0)) * 0.7 + int(row.get("miss", 0))) / breaks
        least += great * base + settled + perfect * 0.25 / breaks
        most += great * 2.5 * base + settled + perfect * 0.5 / breaks
    missing = 101.0 - achievement
    # the achievement is cut off at four places, so the loss can sit up to 0.0001 under the one shown
    return least - 0.0001 <= missing <= most + 0.0001
