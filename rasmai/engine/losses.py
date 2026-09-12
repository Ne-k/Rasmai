from typing import Dict

# How much achievement each note type cost on one play. The arithmetic follows maimai-score-details
# by SpiritsUnite (github.com/SpiritsUnite/maimai-score-details, Apache-2.0); see THIRD_PARTY_NOTICES.md.
# Every tap, hold, slide and touch is worth a share of 100% weighted 1:2:3:1, and a break is worth five
# shares plus an equal slice of the 1% bonus. A great keeps 80% of a note, a good 50%; a break good keeps
# 40% and a break miss nothing. Breaks also lose bonus on perfects and greats, which the site does not
# split out, so whatever the totals do not explain is charged to breaks.
WEIGHTS = {"tap": 1, "hold": 2, "slide": 3, "touch": 1, "break": 5}


def note_losses(notes: Dict[str, Dict[str, int]], achievement: float) -> Dict[str, float]:
    """Percent of achievement lost per note type, summing to what was missing from 101%.

    :param notes: Judgement counts per note type, as the play detail page lists them.
    :type notes: Dict[str, Dict[str, int]]
    :param achievement: The play's achievement.
    :type achievement: float
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
            lost[kind] = good * (3 * base + 0.7 / breaks) + miss * (5 * base + 1.0 / breaks)
        else:
            lost[kind] = WEIGHTS[kind] * base * (great / 5 + good / 2 + miss)
    if "break" in lost:
        lost["break"] += max(0.0, 101.0 - sum(lost.values()) - achievement)
    return lost
