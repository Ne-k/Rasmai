from typing import Any, Dict, List, Optional, Sequence

from rasmai.engine.analysis.rating import ACHIEVEMENT_CAP, accuracy_for_rating, calculate_rating, challenge_for, rank_for
from rasmai.engine.analysis.charts import ChartIndex, constant_span
from rasmai.engine.analysis.profile import PlayProfile
from rasmai.engine.analysis.pools import Best50
from rasmai.engine.analysis.picks.candidates import _unplayed_candidates
from rasmai.engine.analysis.picks.first_runs import _charts_to_try
from rasmai.engine.analysis.picks.model import MAX_UNPLAYED_PICKS, MIN_PICKS, ScoredCandidate
from rasmai.engine.analysis.picks.targets import _freshness, _target_for


def generate_recommendations(
    songs: Sequence[Any],
    profile: PlayProfile,
    best50: Best50,
    chart_index: ChartIndex,
    current_version: int,
    limit: int = 60,
    include_unplayed: bool = True,
    challenge: str = "balanced",
    level: Optional[str] = None,
) -> List[ScoredCandidate]:
    mode = challenge_for(challenge)
    span = constant_span(level) if level else None     # a level, a constant or a range the player asked to see alone
    candidates: List[ScoredCandidate] = []
    played_keys: set = set()

    for song in songs:
        difficulty_type = str(getattr(song, "difficulty_type", "")).lower()
        if difficulty_type == "utage":
            continue
        constant = float(getattr(song, "difficulty", 0) or 0)
        accuracy = float(getattr(song, "accuracy", 0) or 0)
        if constant <= 0 or accuracy <= 0:
            continue

        chart_type = str(getattr(song, "chart_type", "")).lower() or "std"
        key = (str(song.name).casefold(), chart_type, difficulty_type)
        played_keys.add(key)
        matched = chart_index.get(key)
        if matched is not None:
            played_keys.add(matched.key)   # the database's spelling, so unplayed searches skip it too
        if span and not (span[0] <= constant <= span[1]):
            continue

        target = _target_for(profile, key, constant, accuracy, mode)
        if not target:
            continue
        target_rank, target_accuracy = target
        expected_here, _sigma_here = profile.chart_expectation(key, constant, accuracy)

        current_rating = int(getattr(song, "rating", 0) or 0)
        target_rating = calculate_rating(constant, target_accuracy)
        chart_gain = target_rating - current_rating
        if chart_gain <= 0:
            continue

        is_new = bool(getattr(song, "is_new", False))
        rating_gain = best50.gain_if(key, is_new, target_rating)

        feasibility = profile.chart_feasibility(key, constant, accuracy, target_accuracy)
        chart = chart_index.get(key)
        genre = chart.genre if chart else str(getattr(song, "genre", ""))
        affinity = profile.affinity(chart_type, genre, difficulty_type)
        freshness = _freshness(profile, key)

        pool = best50.pool_for(is_new)
        required_accuracy = 0.0
        reach_gap = 0.0
        if rating_gain > 0:
            category = "rating"
            reason = f"+{rating_gain} rating at {target_rank}"
            if profile.dropped_best(key, constant, accuracy):
                reason += f" · one run, well under the ~{expected_here:.1f}% you score at this level"
            score = rating_gain * feasibility * affinity * freshness
        else:
            needed = accuracy_for_rating(constant, pool.cutoff + 1)
            if needed is None or needed <= accuracy:
                continue
            if needed >= ACHIEVEMENT_CAP - 1e-9 and accuracy < 100.0:
                continue      # "reach SSS+ and it counts" is not a near miss
            required_accuracy = needed
            reach_gap = needed - expected_here
            if reach_gap > 2.0 * max(0.5, profile.consistency):
                continue
            category = "near"
            reason = f"needs {needed:.2f}% to enter your best-50"
            # Ranked below every real gain, closest first.
            score = affinity * freshness / (1.0 + max(0.0, reach_gap))

        candidates.append(ScoredCandidate(
            title=song.name,
            chart_type=chart_type,
            difficulty_type=difficulty_type,
            level=str(getattr(song, "level", "") or (chart.level if chart else "")),
            constant=constant,
            genre=genre,
            artist=str(getattr(song, "artist", "")),
            cover=str(getattr(song, "cover_url", "")),
            is_new=is_new,
            is_unplayed=False,
            current_accuracy=accuracy,
            current_rating=current_rating,
            target_accuracy=target_accuracy,
            target_rating=target_rating,
            target_rank=target_rank,
            current_rank=rank_for(accuracy),
            chart_gain=chart_gain,
            rating_gain=rating_gain,
            feasibility=feasibility,
            affinity=affinity,
            score=score,
            fc_status=str(getattr(song, "fc_status", "") or "NONE"),
            category=category,
            reason=reason,
            required_accuracy=required_accuracy,
            reach_gap=reach_gap,
            plays=profile.plays_for(key),
            expected=expected_here,
        ))

    if include_unplayed:
        candidates.extend(_unplayed_candidates(
            profile, best50, chart_index, played_keys, current_version, span=span,
        ))

    movers = [c for c in candidates if c.rating_gain > 0]
    near = [c for c in candidates if c.rating_gain <= 0]
    if mode.pick == "likely":
        # first-pass estimates on unplayed charts are less certain than a score you already hold
        movers.sort(key=lambda c: (c.rating_gain * c.feasibility * (0.6 if c.is_unplayed else 1.0), c.feasibility), reverse=True)
    else:
        movers.sort(key=lambda c: (c.rating_gain, c.feasibility), reverse=True)
    # a new player's list would otherwise be twenty-five unplayed 12.1s all reading "~S for +12": a few make the
    # point, the New charts view has the rest, and the charts they already hold a score on stay visible
    kept, unplayed_shown = [], 0
    for c in movers:
        if c.is_unplayed:
            if unplayed_shown >= MAX_UNPLAYED_PICKS:
                continue
            unplayed_shown += 1
        kept.append(c)
    movers = kept
    near.sort(key=lambda c: c.score, reverse=True)
    tries: List[ScoredCandidate] = []
    if include_unplayed and len(movers) < MIN_PICKS:
        taken = {(c.title.casefold(), c.chart_type, c.difficulty_type) for c in candidates}
        tries = _charts_to_try(songs, profile, best50, chart_index, current_version, mode,
                               MIN_PICKS - len(movers), level, taken)
    return (movers + tries + near)[:limit]


def summarise(
    candidates: Sequence[ScoredCandidate],
    profile: PlayProfile,
    best50: Best50,
) -> Dict[str, Any]:
    rating_moves = [c for c in candidates if c.rating_gain > 0]
    # gains are measured against today's best-50; once a few land the cutoffs rise,
    # so the reachable total is what the best-50 actually becomes when every move lands
    simulated = Best50(best50.new_pool.clone(), best50.old_pool.clone())
    reachable = 0
    for c in sorted(rating_moves, key=lambda c: -c.rating_gain):
        key = (c.title.casefold(), c.chart_type, c.difficulty_type)
        reachable += simulated.pool_for(c.is_new).apply(key, c.target_rating)
    quick_wins = [c for c in rating_moves if c.feasibility >= 0.5][:10]
    stretch = [c for c in rating_moves if c.feasibility < 0.5][:10]
    unplayed = [c for c in candidates if c.category == "unplayed"][:10]
    near_misses = [c for c in candidates if c.category == "near"][:10]
    return {
        "profile": profile.summary(),
        "best50": {
            "total": best50.total,
            "newTotal": best50.new_pool.total,
            "oldTotal": best50.old_pool.total,
            "newCutoff": best50.new_pool.cutoff,
            "oldCutoff": best50.old_pool.cutoff,
            "newSlotsOpen": best50.new_pool.headroom(),
            "oldSlotsOpen": best50.old_pool.headroom(),
        },
        "reachableGain": reachable,
        "naiveGain": sum(c.rating_gain for c in rating_moves),
        "ratingMoves": len(rating_moves),
        "playCountsKnown": sum(1 for v in profile.play_counts.values() if v >= 0),
        "nearMisses": [
            {"title": c.title, "needs": round(c.required_accuracy, 2), "level": c.level}
            for c in near_misses
        ],
        "quickWins": [c.title for c in quick_wins],
        "stretchGoals": [c.title for c in stretch],
        "newChartsToTry": [c.title for c in unplayed],
    }
