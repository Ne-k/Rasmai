from typing import Any, List, Optional, Sequence, Tuple

from rasmai.engine.analysis.rating import ACHIEVEMENT_CAP, Challenge, accuracy_for_rating, calculate_rating, rank_for
from rasmai.engine.analysis.charts import ChartIndex
from rasmai.engine.analysis.profile import PlayProfile
from rasmai.engine.analysis.pools import Best50
from rasmai.engine.analysis.picks.model import ScoredCandidate


def _weak_trait(profile: PlayProfile, chart: Any) -> Optional[Tuple[str, float]]:
    """The confirmed trait this chart carries that the player scores furthest below their own curve on.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param chart: The chart being judged.
    :type chart: Any
    :returns: ``(label, offset)`` for the worst of them, or None when the chart carries none.
    :rtype: Optional[Tuple[str, float]]
    """
    from rasmai.engine.insights import chart_traits, leaning, notable
    axes = profile.trait_axes or []
    # confirmed traits are rare, so the ones that only lean count here too: the Traits view already
    # shows them, and "this chart is mostly the pattern you drop points on" is worth saying either way
    # only hand patterns: an era or a genre is something a chart is, not something you can go and drill
    offsets = {trait["label"]: float(trait["offset"]) for trait in (notable(axes) + leaning(axes))
               if float(trait["offset"]) < 0 and trait["dimension"] == "pattern"}
    worst: Optional[Tuple[str, float]] = None
    for dimension, label in chart_traits(chart):
        if dimension != "pattern":
            continue
        value = offsets.get(label)
        if value is not None and (worst is None or value < worst[1]):
            worst = (label, value)
    return worst


def _charts_to_try(
    songs: Sequence[Any],
    profile: PlayProfile,
    best50: Best50,
    chart_index: ChartIndex,
    current_version: int,
    mode: Challenge,
    want: int,
    level: Optional[str],
    taken: set,
) -> List[ScoredCandidate]:
    """Unplayed charts worth a run, for when the played picks run short.

    A player whose best-50 is nearly maxed has almost nothing left to grind, and a list of four
    charts reads as the model giving up. Two things still earn a place: a chart where a good first
    pass would already bank rating, and a chart that drills a pattern the player's own scores say
    costs them points. The first is rating, the second is practice, and both beat an empty list.

    :param songs: The player's scored charts.
    :type songs: Sequence[Any]
    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param best50: The player's two rating pools.
    :type best50: Best50
    :param chart_index: The chart database to look constants and metadata up in.
    :type chart_index: ChartIndex
    :param current_version: The game version the player is on.
    :type current_version: int
    :param mode: The challenge level being built.
    :type mode: Challenge
    :param want: How many charts are needed to fill the list out.
    :type want: int
    :param level: A level, constant or range the player asked to be held to.
    :type level: Optional[str]
    :param taken: Keys already on the list, so a chart is never offered twice.
    :type taken: set
    :rtype: List[ScoredCandidate]
    """
    from rasmai.engine.analysis.unplayed import recommend_unplayed
    from rasmai.scraping.mai_notes import english_label
    found: List[ScoredCandidate] = []
    for pick in recommend_unplayed(songs, profile, best50, chart_index, current_version,
                                   limit=max(12, want * 3), challenge=mode.key, level=level):
        key = (pick.title.casefold(), pick.chart_type, pick.difficulty)
        if key in taken:
            continue
        chart = chart_index.get((pick.title, pick.chart_type, pick.difficulty), pick.level)
        weak = _weak_trait(profile, chart) if chart is not None else None
        target_rating = calculate_rating(pick.constant, pick.target_accuracy)
        gain = best50.gain_if(key, pick.is_new, target_rating)
        if gain > 0:
            reason = f"never played · a good first run adds +{gain}"
        elif weak is not None:
            reason = f"never played · practice: {english_label(weak[0])} costs you {weak[1]:+.1f}"
        else:
            cutoff = best50.pool_for(pick.is_new).cutoff
            needed = accuracy_for_rating(pick.constant, cutoff + 1)
            reason = (f"never played · {needed:.2f}% gets it into your best-50"
                      if needed is not None and needed <= ACHIEVEMENT_CAP else
                      f"never played · a first pass banks {pick.expected_rating}")
        found.append(ScoredCandidate(
            title=pick.title, chart_type=pick.chart_type, difficulty_type=pick.difficulty, level=pick.level,
            constant=pick.constant, genre=pick.genre, artist=pick.artist, cover=pick.cover, is_new=pick.is_new,
            is_unplayed=True, current_accuracy=0.0, current_rating=0,
            target_accuracy=pick.target_accuracy, target_rating=target_rating,
            target_rank=rank_for(pick.target_accuracy), current_rank="-",
            chart_gain=gain, rating_gain=gain,
            feasibility=profile.feasibility(pick.constant, pick.target_accuracy, pick.difficulty),
            affinity=pick.affinity, score=pick.score, fc_status="NONE", category="try", reason=reason,
            plays=0, expected=pick.expected_accuracy,
        ))
    # a stable sort on the gain alone, so charts that would pay lead while the rest keep the spread
    # across constants that `recommend_unplayed` already gave them
    found.sort(key=lambda candidate: -candidate.rating_gain)
    return found[:want]
