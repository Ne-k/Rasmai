from typing import Any, Dict, List, Optional

from rasmai.engine.losses import WEIGHTS, note_losses

KINDS = tuple(WEIGHTS)
MIN_PLAYS = 3            # one play says little; three is enough to name the note type that costs most
TILT = 1.5               # a type carrying this many times its share of the loss is called out


def judgement_profile(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Loss and timing across every stored play, per note type; None until there are a few plays.

    :param rows: The stored judgement pages.
    :type rows: List[Dict[str, Any]]
    :rtype: Optional[Dict[str, Any]]
    """
    if len(rows) < MIN_PLAYS:
        return None
    notes = {k: 0 for k in KINDS}
    clean = {k: 0 for k in KINDS}
    lost = {k: 0.0 for k in KINDS}
    fast = late = 0
    for row in rows:
        counts = row.get("notes") or {}
        for kind, judged in counts.items():
            if kind in notes:
                notes[kind] += sum(int(v) for v in judged.values())
                clean[kind] += int(judged.get("critical", 0)) + int(judged.get("perfect", 0))
        for kind, value in note_losses(counts, float(row.get("achievement") or 0)).items():
            lost[kind] += value
        fast += int(row.get("fast") or 0)
        late += int(row.get("late") or 0)
    all_notes = sum(notes.values())
    all_lost = sum(lost.values())
    if not all_notes:
        return None
    types = []
    for kind in KINDS:
        if not notes[kind]:
            continue
        share = notes[kind] / all_notes
        loss_share = lost[kind] / all_lost if all_lost else 0.0
        types.append({
            "kind": kind, "notes": notes[kind], "share": round(share, 4), "lossShare": round(loss_share, 4),
            "per100": round(100 * lost[kind] / notes[kind], 3),           # points lost per hundred notes of this type
            "clean": round(clean[kind] / notes[kind], 4),                  # critical or perfect
            "tilt": round(loss_share / share, 2) if share else 0.0,        # 1.0 = costs what its share of the notes would
        })
    weak = max((t for t in types if t["tilt"] >= TILT and t["lossShare"] >= 0.15), key=lambda t: t["tilt"], default=None)
    hits = fast + late
    return {
        "plays": len(rows), "types": types, "weak": weak["kind"] if weak else None,
        "fast": fast, "late": late, "lateShare": round(late / hits, 3) if hits else None,
        "lostPerPlay": round(all_lost / len(rows), 3),
    }
