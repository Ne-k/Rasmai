from typing import Any, Dict, List, Optional

from rasmai.bot.state import cohort
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.engine.cohort import MIN_COHORT, Key, compare_judgements
from rasmai.engine.judgements import judgement_profile
from rasmai.storage.db import load_judgements
from rasmai.util import _json_safe

PICKED_TIERS = ("expert", "master", "remaster")


def _index(cached: Optional[CachedAnalysis]) -> Any:
    from rasmai.bot.builders.charts import shared_index
    return cached.analyzer.chart_index if cached else shared_index()


def _chart(index: Any, key: Key, **fields: Any) -> Optional[Dict[str, Any]]:
    ref = index.get(key)
    if ref is None:
        return None
    return {"title": ref.title, "chartType": ref.chart_type, "difficulty": ref.difficulty, "level": ref.level,
            "cover": ref.cover, **fields}


def likeyou_payload(account: Dict[str, Any], cached: Optional[CachedAnalysis]) -> Dict[str, Any]:
    """Charts that players like the signed-in person score well on, from everyone's best scores in aggregate.

    Only counts and typical scores leave here: how many players the cohort holds, how many of them were
    like this person, and how many of those have played each chart.

    :param account: The linked account, as stored.
    :type account: Dict[str, Any]
    :param cached: The player's analysis, held in memory, if there is one.
    :type cached: Optional[CachedAnalysis]
    :rtype: Dict[str, Any]
    """
    index = _index(cached)
    analyzer = cached.analyzer if cached else None
    profile = analyzer.play_profile if analyzer is not None and analyzer.play_profile.sample_size else None
    rating = int((account.get("officialProfile") or {}).get("rating") or (analyzer.player.rating if analyzer is not None else 0) or 0)

    def wanted(key: Key, _constant: float) -> bool:
        ref = index.get(key)
        return ref is not None and ref.difficulty in PICKED_TIERS and not ref.locked and index.playable(ref)

    counted, found = cohort.like_you(
        str(account["userId"]), rating, reach=profile.reach_constant if profile and profile.reach_constant > 0 else None,
        expected=(lambda key, constant: profile.expected_for(constant, key[2])) if profile else None, wanted=wanted)
    if found is None:
        return {"ok": True, "ready": False, "players": counted, "picks": [], "reason": "not_enough_players"}
    picks: List[Dict[str, Any]] = []
    for pick in found.picks:
        chart = _chart(index, pick["key"], constant=pick["constant"], yours=pick["yours"],
                       typical=round(pick["typical"], 2), neighbours=pick["neighbours"], average=cohort.average(pick["key"]))
        if chart is not None:
            picks.append(chart)
    return _json_safe({"ok": True, "ready": counted >= MIN_COHORT, "players": counted, "picks": picks, "reason": found.reason,
                       "judgements": _judgements(str(account["userId"]), found.tags) if not found.reason else None})


def _judgements(user_id: str, neighbours: List[bytes]) -> Optional[Dict[str, Any]]:
    """How this person's judgements compare with those of the players like them.

    The neighbours' tags are only used to read their own stored pages, one profile each; what comes out is
    the middle value across them, never a profile of anyone, and nothing until enough of them have one.
    """
    mine = judgement_profile(load_judgements(user_id))
    if mine is None:
        return None
    theirs = [judgement_profile(load_judgements(tag.decode())) for tag in neighbours]
    return compare_judgements(mine, [profile for profile in theirs if profile is not None])


def difficulty_payload(cached: Optional[CachedAnalysis]) -> Dict[str, Any]:
    """The charts that play furthest harder and furthest easier than their listed constant, among those enough players have played.

    :param cached: The player's analysis, held in memory, if there is one.
    :type cached: Optional[CachedAnalysis]
    :rtype: Dict[str, Any]
    """
    index = _index(cached)
    counted, harder, easier = cohort.outliers()

    def rows(found: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = [_chart(index, row["key"], listed=row["listed"], observed=row["observed"], players=row["players"], average=row["average"]) for row in found]
        return [row for row in out if row is not None]
    return _json_safe({"ok": True, "ready": counted >= MIN_COHORT, "players": counted, "harder": rows(harder), "easier": rows(easier)})

