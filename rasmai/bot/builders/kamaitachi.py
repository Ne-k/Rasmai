from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import json

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.state.snapshots import chart_key, play_rows
from rasmai.storage.db import load_play_history

SERVICE = "Rasmai"
DIFFICULTY = {"basic": "Basic", "advanced": "Advanced", "expert": "Expert", "master": "Master", "remaster": "Re:Master"}
# worst to best; a lamp is only ever moved down this ladder
LAMPS = ("FAILED", "CLEAR", "FULL COMBO", "FULL COMBO+", "ALL PERFECT", "ALL PERFECT+")
LAMP_FOR = {"AP+": "ALL PERFECT+", "AP": "ALL PERFECT", "FC+": "FULL COMBO+", "FC": "FULL COMBO"}
JUDGEMENTS = ("pcrit", "perfect", "great", "good", "miss")
STORED_AS = {"pcrit": "critical"}        # what the stored plays call a judgement that Tachi names differently
EARLIEST = datetime(2012, 1, 1)          # Tachi reads a time before this as a mistake, and maimai DX is younger than that


def tachi_lamp(fc: Any, percent: float) -> str:
    """The lamp Tachi calls a Rasmai fc status; sync marks have no place there, and no combo is a clear from 80%."""
    return LAMP_FOR.get(str(fc or "").strip().upper()) or ("CLEAR" if percent >= 80 else "FAILED")


def broken_rule(percent: float, lamp: str, judgements: Optional[Dict[str, int]]) -> Optional[str]:
    """Why Tachi would refuse this score, or None: its maimai DX validators, ported.

    The third of Tachi's validators, that max combo equals the sum of the judgements, never fires
    here because max combo is not sent.
    """
    if not 0 < percent <= 101:
        return "percent outside 0 to 101"
    if lamp == "ALL PERFECT+" and percent != 101:
        return "ALL PERFECT+ without 101%"
    if lamp != "ALL PERFECT+" and percent == 101:
        return "101% without ALL PERFECT+"
    if lamp == "ALL PERFECT" and percent < 100.5:
        return "ALL PERFECT below 100.5%"
    if lamp == "CLEAR" and percent < 80:
        return "CLEAR below 80%"
    if lamp == "FAILED" and percent >= 80:
        return "FAILED from 80%"
    if judgements:
        great, good, miss = judgements["great"], judgements["good"], judgements["miss"]
        if lamp.startswith("ALL PERFECT") and great + good + miss > 0:
            return "ALL PERFECT with non-perfect judgements"
        if lamp == "FULL COMBO+" and good + miss > 0:
            return "FULL COMBO+ with goods or misses"
        if lamp == "FULL COMBO" and miss > 0:
            return "FULL COMBO with misses"
    return None


def mend(percent: float, lamp: str, judgements: Optional[Dict[str, int]]) -> Optional[str]:
    """A lamp that agrees with the percent and the judgements, or None when no honest one exists.

    A lamp that overclaims is moved down the ladder until it holds. 101% can only be an all perfect plus,
    so a lamp short of it moves up, and if the judgements deny that too the score is not trusted at all.
    """
    if not 0 < percent <= 101:
        return None
    floor = "CLEAR" if percent >= 80 else "FAILED"
    ladder = ["ALL PERFECT+"] if percent == 101 else list(reversed(LAMPS[2:LAMPS.index(lamp) + 1])) + [floor]
    return next((candidate for candidate in ladder if broken_rule(percent, candidate, judgements) is None), None)


def _judgements(detail: Any, notes: int) -> Tuple[Optional[Dict[str, int]], Optional[Dict[str, int]]]:
    """Judgement counts and fast/late from one stored play, summed over the note types; (None, None) unless they account for every note."""
    if not isinstance(detail, dict) or not isinstance(detail.get("notes"), dict):
        return None, None
    total = dict.fromkeys(JUDGEMENTS, 0)
    try:
        for kind in detail["notes"].values():
            for key in total:
                total[key] += max(0, int(kind.get(STORED_AS.get(key, key)) or 0))
        fast, slow = max(0, int(detail.get("fast") or 0)), max(0, int(detail.get("late") or 0))
    except (AttributeError, TypeError, ValueError):
        return None, None
    count = sum(total.values())
    if count <= 0 or (notes and count != notes):
        return None, None
    return total, {"fast": fast, "slow": slow}


def _millis(text: Any) -> Optional[int]:
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return int(moment.timestamp() * 1000) if moment.replace(tzinfo=None) >= EARLIEST else None


def build_document(analyzer: Any, history: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """The player's scores as a Tachi BATCH-MANUAL document, and what was done to get there.

    One score for the stored best of every chart, and one for every stored play with its time and, where
    the judgement page was read, its judgements. A best is left out when a timed play already says the
    same thing. Titles are the chart database's, because Tachi matches by title and Rasmai keeps the name
    maimai DX NET printed. A score that contradicts itself is mended where there is one honest reading and
    left out where there is not, so the file never holds one Tachi would reject.

    :param analyzer: The scraper and the analysis it holds.
    :type analyzer: Any
    :param history: The stored play history, as ``load_play_history`` returns it.
    :type history: List[Dict[str, Any]]
    :returns: The document, and counts of ``charts`` (bests), ``plays``, ``skipped`` (every score left out)
        with the reasons ``utage``, ``unmatched`` and ``invalid``, and ``repaired``.
    :rtype: Tuple[Dict[str, Any], Dict[str, int]]
    """
    index = analyzer.chart_index
    pages = {(str(page.get("chart_key")), str(page.get("played_at"))): page for page in analyzer.judgements or []}
    counts = {"charts": 0, "plays": 0, "skipped": 0, "utage": 0, "unmatched": 0, "invalid": 0, "repaired": 0}

    def left_out(reason: str) -> None:
        counts["skipped"] += 1
        counts[reason] += 1

    def score(key: str, level: str, percent: float, fc: Any, moment: Optional[str], detail: Any) -> Optional[Dict[str, Any]]:
        name, chart_type, tier = key.rsplit("|", 2)
        if tier == "utage":
            left_out("utage")
            return None
        ref = index.get((name, chart_type, tier), level or None)
        if ref is None or tier not in DIFFICULTY or not ref.title.strip():
            left_out("unmatched")
            return None
        stamp = _millis(moment) if moment else None
        if moment and stamp is None:
            left_out("invalid")
            return None
        judged, timing = _judgements(detail, ref.notes)
        lamp = tachi_lamp(fc, percent)
        mended = mend(percent, lamp, judged)
        if mended is None:
            left_out("invalid")
            return None
        counts["repaired"] += mended != lamp
        out: Dict[str, Any] = {"percent": percent, "lamp": mended, "matchType": "songTitle", "identifier": ref.title,
                               "difficulty": ("DX " if chart_type == "dx" else "") + DIFFICULTY[tier]}
        if stamp is not None:
            out["timeAchieved"] = stamp
        if judged and timing:
            out["judgements"], out["optional"] = judged, timing
        return out

    plays: List[Dict[str, Any]] = []
    reached: Dict[str, List[Tuple[float, int]]] = {}       # per chart, each timed play's percent and lamp rank, to tell a best that adds nothing
    seen = set()
    # the recent list goes first: a play on both lists is kept once, and the recent one still carries its judgement page
    rows = [(row[0], row[1], float(row[2]), row[4], row[9] if len(row) > 9 else None) for row in play_rows(analyzer, analyzer.recent_songs or [])]
    rows += [(p["key"], p["played_at"], float(p["achievement"]), p["fc"], p.get("judgement")) for p in history]
    for key, moment, percent, fc, detail in rows:
        if (key, moment) in seen or len(key.rsplit("|", 2)) != 3:
            continue
        seen.add((key, moment))
        built = score(key, "", round(percent, 4), fc, moment, pages.get((key, moment)) or detail)
        if built:
            plays.append(built)
            reached.setdefault(key, []).append((built["percent"], LAMPS.index(built["lamp"])))
    counts["plays"] = len(plays)

    bests: List[Dict[str, Any]] = []
    for song in analyzer.songs:
        percent = round(float(song.accuracy or 0), 4)
        if percent <= 0:
            continue
        key = "|".join(chart_key(song))
        built = score(key, str(song.level or ""), percent, song.fc_status, None, None)
        if built and not any(p == percent and rank >= LAMPS.index(built["lamp"]) for p, rank in reached.get(key, [])):
            bests.append(built)
    counts["charts"] = len(bests)
    plays.sort(key=lambda row: row["timeAchieved"])
    return {"meta": {"game": "maimaidx", "playtype": "Single", "service": SERVICE}, "scores": bests + plays}, counts


def kamaitachi_file(cached: CachedAnalysis) -> Tuple[bytes, str, Dict[str, int]]:
    """The document for a signed-in player as bytes, the file name to offer it under, and the counts.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :rtype: Tuple[bytes, str, Dict[str, int]]
    """
    document, counts = build_document(cached.analyzer, load_play_history(cached.user_id))
    body = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return body, f"rasmai-kamaitachi-{datetime.now().strftime('%Y%m%d-%H%M')}.json", counts
