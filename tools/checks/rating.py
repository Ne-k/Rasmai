
from tools.checks import check


@check("the level bands match the game")
def _levels():
    from rasmai.engine.analysis import level_range, level_floor
    problems = []
    expected = {"13": (13.0, 13.5), "13+": (13.6, 13.9), "14": (14.0, 14.5), "14+": (14.6, 14.9),
                "6": (6.0, 6.9), "6+": None, "x": None}
    for level, want in expected.items():
        got = level_range(level)
        if got != want:
            problems.append(f"level_range({level!r}) is {got}, expected {want}")
    if level_floor("13+") != 13.6:
        problems.append(f"level_floor('13+') is {level_floor('13+')}, expected 13.6 to match level_range")
    return problems


@check("the rating maths is unchanged")
def _rating():
    from rasmai.engine.analysis import calculate_rating, rank_for, accuracy_for_rating
    problems = []
    for accuracy, rank in ((100.5, "SSS+"), (100.0, "SSS"), (99.5, "SS+"), (97.0, "S"), (80.0, "A")):
        if rank_for(accuracy) != rank:
            problems.append(f"rank_for({accuracy}) is {rank_for(accuracy)!r}, expected {rank!r}")
    if calculate_rating(13.5, 100.5) != 303:
        problems.append(f"calculate_rating(13.5, 100.5) is {calculate_rating(13.5, 100.5)}, expected 303")
    if accuracy_for_rating(0, 250) is not None:
        problems.append("accuracy_for_rating with no constant should be None")
    return problems


@check("a failed attempt does not raise the ceiling searches reach from")
def _ceiling():
    from rasmai.engine.analysis import ChartIndex, build_play_profile, unplayed_window
    from rasmai.engine.analysis.picks import MAX_UNPLAYED_PICKS
    from rasmai.storage.models import SongInfo
    # a 12,000-ish player: SS territory to 11.5, S to 12.8, then one failed attempt at a 15
    songs = []
    for tenth in range(90, 129):
        constant = tenth / 10.0
        for i in range(3):
            accuracy = 100.2 - (constant - 9.0) * 0.55 - i * 0.4
            songs.append(SongInfo(name=f"c{tenth}-{i}", chart_type="dx", difficulty_type="master", accuracy=round(accuracy, 4),
                                  level="12", difficulty=constant, rating=200))
    songs.append(SongInfo(name="the wall", chart_type="dx", difficulty_type="master", accuracy=68.7, level="15", difficulty=15.0, rating=100))
    profile = build_play_profile(songs, [], ChartIndex(), 26)
    problems = []
    if profile.played_ceiling != 15.0:
        problems.append(f"played_ceiling should still record the attempt, got {profile.played_ceiling}")
    if profile.search_ceiling >= 14.0 or profile.search_ceiling < profile.hardest_s:
        problems.append(f"search_ceiling {profile.search_ceiling} should sit at the hardest S ({profile.hardest_s}), not at the failed 15")
    low, high = unplayed_window(profile, "balanced")
    if high > profile.search_ceiling + 0.3 + 1e-9:
        problems.append(f"balanced /new reaches {high}, past the search ceiling {profile.search_ceiling} + 0.3")
    if profile.reach_constant - profile.comfort_constant > 1.0 + 1e-9:
        problems.append(f"comfort {profile.comfort_constant} sits more than a level under reach {profile.reach_constant}")
    if not 3 <= MAX_UNPLAYED_PICKS <= 10:
        problems.append(f"MAX_UNPLAYED_PICKS is {MAX_UNPLAYED_PICKS}; a handful is the point")
    return problems


@check("the new-chart list spans its window instead of one constant")
def _spread():
    from rasmai.engine.analysis import (ChartIndex, ChartRef, build_best50, build_play_profile, challenge_for,
                                        recommend_unplayed, unplayed_window)
    from rasmai.storage.models import SongInfo
    index = ChartIndex("intl")
    for tenth in range(100, 141):
        constant = tenth / 10.0
        for n in range(6):
            index.add(ChartRef(title=f"unplayed {tenth} {n}", chart_type="dx", difficulty="master", constant=constant,
                               level=str(int(constant)), notes=700, genre="maimai", artist="a", cover="", version=26, intl=True))
    songs = []
    for tenth in range(95, 126):
        constant = tenth / 10.0
        for n in range(3):
            accuracy = round(100.4 - (constant - 9.5) * 0.12 - n * 0.2, 4)     # flat and high, so many constants clear the first-pass floor
            songs.append(SongInfo(name=f"played {tenth} {n}", chart_type="dx", difficulty_type="master", accuracy=accuracy,
                                  level=str(int(constant)), difficulty=constant, rating=250))
    profile = build_play_profile(songs, [], index, 26)
    problems = []
    for tier in ("easy", "balanced", "hard", "extreme"):
        low, high = unplayed_window(profile, tier)
        floor = challenge_for(tier).new_floor
        offered = {round(chart.constant, 1) for chart in index.values()
                   if low <= chart.constant <= high
                   and profile.expected_for(chart.constant, chart.difficulty) - 0.35 - 0.4 * profile.sigma_at(chart.constant) >= floor}
        picks = recommend_unplayed(songs, profile, build_best50(songs), index, 26, limit=12, challenge=tier)
        if not picks or not offered:
            continue
        shown = {round(p.constant, 1) for p in picks}
        # the list should spend the window: as many distinct constants as it has room for, not one repeated
        want = min(len(offered), 12 // max(2, 12 // 6))
        if len(shown) < want:
            problems.append(f"{tier}: 12 picks cover {len(shown)} constant(s) {sorted(shown)} of the {len(offered)} the window offers")
    # the same call twice must give the same order, or the page reshuffles between reads
    first = [p.title for p in recommend_unplayed(songs, profile, build_best50(songs), index, 26, limit=12)]
    again = [p.title for p in recommend_unplayed(songs, profile, build_best50(songs), index, 26, limit=12)]
    if first != again:
        problems.append("two identical calls returned different orders")
    return problems


@check("a short pick list is continued with charts worth a first run")
def _topup():
    from rasmai.engine.analysis import ChartIndex, ChartRef, build_best50, build_play_profile, generate_recommendations
    from rasmai.engine.analysis.picks import MIN_PICKS
    from rasmai.storage.models import SongInfo
    index = ChartIndex("intl")
    for tenth in range(100, 141):
        constant = tenth / 10.0
        for n in range(6):
            index.add(ChartRef(title=f"unplayed {tenth} {n}", chart_type="dx", difficulty="master", constant=constant,
                               level=str(int(constant)), notes=700, genre=f"genre {n % 3}", artist="a", cover="", version=26, intl=True))
    # a player with a handful of scores: almost nothing of theirs can move a best-50 that is not full
    songs = []
    for tenth in range(118, 125):
        constant = tenth / 10.0
        songs.append(SongInfo(name=f"played {tenth}", chart_type="dx", difficulty_type="master", accuracy=99.8,
                              level=str(int(constant)), difficulty=constant, rating=250))
    profile = build_play_profile(songs, [], index, 26)
    best50 = build_best50(songs)
    problems = []
    picks = generate_recommendations(songs, profile, best50, index, 26, challenge="balanced")
    grind = [c for c in picks if c.category not in ("near", "try")]
    tries = [c for c in picks if c.category == "try"]
    if len(grind) < MIN_PICKS and not tries:
        problems.append(f"only {len(grind)} played picks and no charts to try were offered")
    if len(grind) + len(tries) < min(MIN_PICKS, len(grind) + len(tries)):
        problems.append("the top-up did not fill the list")
    for candidate in tries:
        if not candidate.is_unplayed or candidate.current_accuracy:
            problems.append(f"{candidate.title}: offered as a first run but carries a score")
        if not candidate.reason:
            problems.append(f"{candidate.title}: offered with no reason given")
    seen = [(c.title, c.difficulty_type) for c in picks]
    if len(seen) != len(set(seen)):
        problems.append("a chart is listed twice")
    # a full list must not be padded
    many = generate_recommendations(songs * 1, profile, best50, index, 26, challenge="extreme")
    if len([c for c in many if c.category not in ("near", "try")]) >= MIN_PICKS and any(c.category == "try" for c in many):
        problems.append("a list that is already long was padded with charts to try")
    return problems


@check("the target levels stay in order, easier through to long shots")
def _ladder():
    from rasmai.engine.analysis import CHALLENGES
    order = ["easy", "balanced", "hard", "extreme"]
    problems = []
    missing = [key for key in order if key not in CHALLENGES]
    if missing:
        return [f"missing target level(s): {missing}"]
    if list(CHALLENGES) != order:
        problems.append(f"CHALLENGES is ordered {list(CHALLENGES)}; the bolder-level search and the menus read it in order")
    for earlier, later in zip(order, order[1:]):
        a, b = CHALLENGES[earlier], CHALLENGES[later]
        if not b.sigmas > a.sigmas:
            problems.append(f"{later} reaches {b.sigmas} spreads, no further than {earlier} at {a.sigmas}")
        if not b.min_feasibility < a.min_feasibility:
            problems.append(f"{later} floors odds at {b.min_feasibility}, no lower than {earlier} at {a.min_feasibility}")
    # a level must never offer a target it would then refuse to plan
    for key, mode in CHALLENGES.items():
        if mode.plan_min_feasibility < mode.min_feasibility:
            problems.append(f"{key}: the route accepts {mode.plan_min_feasibility} odds, under the {mode.min_feasibility} the picks demand")
    return problems


@check("a best that was one dropped run is offered again at what the player scores at that level")
def _dropped():
    from rasmai.engine.analysis import ChartIndex, build_best50, build_play_profile, calculate_rating, generate_recommendations
    from rasmai.storage.models import SongInfo
    # a player who scores ~99 on everything 11.5 to 13.0, with room left in their best-50 (32 charts, 35 old slots)
    songs = []
    for tenth in range(115, 131):
        constant = tenth / 10.0
        for n in range(2):
            accuracy = round(99.6 - (constant - 11.5) * 0.3 - n * 0.15, 4)
            songs.append(SongInfo(name=f"played {tenth} {n}", chart_type="dx", difficulty_type="master", accuracy=accuracy, is_new=False,
                                  level=str(int(constant)), difficulty=constant, rating=calculate_rating(constant, accuracy)))
    songs.append(SongInfo(name="Dropped", chart_type="dx", difficulty_type="master", accuracy=86.5, level="12", is_new=False,
                          difficulty=12.8, rating=calculate_rating(12.8, 86.5)))
    index = ChartIndex()
    best50 = build_best50(songs)
    problems = []
    # no play counts: the one score is proof of one play, and 86.5 on a 12.8 is a run that was dropped
    profile = build_play_profile(songs, [], index, 26)
    picks = {c.title: c for c in generate_recommendations(songs, profile, best50, index, 26, challenge="balanced")}
    pick = picks.get("Dropped")
    if pick is None:
        problems.append("a 12.8 scored 86.5 once, by a player who scores ~99 on 12.8s, was not offered at all")
    elif pick.target_accuracy < 97.0:
        problems.append(f"the dropped run's target is {pick.target_accuracy}, under the S its level supports")
    elif "one run" not in pick.reason:
        problems.append(f"the pick does not say why: {pick.reason!r}")
    # a dozen plays ending at 86.5 is the chart's difficulty for them, and the target stays near the score
    profile = build_play_profile(songs, [], index, 26, play_counts={("dropped", "dx", "master"): 12})
    picks = {c.title: c for c in generate_recommendations(songs, profile, best50, index, 26, challenge="balanced")}
    pick = picks.get("Dropped")
    if pick is not None and pick.target_accuracy >= 97.0:
        problems.append(f"twelve plays ending at 86.5 were still offered an S ({pick.target_accuracy})")
    # the index folds a key itself, so a title with capitals finds its chart under either spelling
    from rasmai.engine.analysis import ChartRef
    index.add(ChartRef(title="Dropped", chart_type="dx", difficulty="master", constant=12.8, level="12", notes=700,
                       genre="maimai", artist="a", cover="", version=26, intl=True))
    if index.get(("Dropped", "dx", "master")) is None or index.get(("dropped", "dx", "master")) is None:
        problems.append("ChartIndex.get does not fold the title it is given")
    return problems


@check("a prediction never sits above a score the player has already proved")
def _no_free_improvement():
    from rasmai.engine.analysis import rating
    from rasmai.engine.analysis.profile.model import PlayProfile

    problems = []
    if rating.BEST_HEADROOM > 0.0:
        problems.append(f"the centre is allowed {rating.BEST_HEADROOM} sigmas above the player's own best; "
                        f"measured over real runs, assuming improvement without evidence costs accuracy")

    profile = PlayProfile()
    profile.sample_size = 200
    profile.intercept, profile.slope = 101.0, -0.3
    profile.consistency, profile.run_consistency = 0.8, 0.5
    key = ("a song", "dx", "master")
    curve = profile.expected_for(13.0, "master")

    # someone a little under their curve: the model may lean towards the curve, never past the best.
    # Further under than DROPPED_BEST_GAP is a different case, handled as an abandoned run.
    under = curve - 1.0
    low, _sigma = profile.chart_expectation(key, 13.0, under)
    if low > under + 1e-6:
        problems.append(f"predicted {low:.2f} on a chart whose best is {under:.2f}, above what they have proved")

    # and someone whose best is above their curve keeps it, rather than being dragged back down
    high_best = curve + 2.0
    high, _sigma = profile.chart_expectation(key, 13.0, high_best)
    if high > high_best + 1e-6:
        problems.append(f"predicted {high:.2f} above a proved {high_best:.2f}")
    if high < high_best - 1.5:
        problems.append(f"predicted {high:.2f} well under a proved {high_best:.2f}: a good chart should stay good")

    # a chart with a rising history is still allowed to be lifted, because that improvement is evidence
    profile.history = {key: [curve - 2.0, curve - 1.0, curve]}
    lifted, _sigma = profile.chart_expectation(key, 13.0, curve)
    if lifted <= curve:
        problems.append("a chart the player is measurably improving on should still be allowed to rise")
    return problems


@check("the curve never says a harder chart should go better, nor an easier one worse")
def _curve_runs_one_way():
    from rasmai.engine.analysis import ChartIndex, ChartRef, build_play_profile, calculate_rating
    from rasmai.storage.models import SongInfo

    # a player with a dense band of good scores and two lonely ones far outside it, which is what
    # bends the fit: the kernel reaches for whatever bucket is nearest and can turn the curve round
    index, played = ChartIndex(), []
    rows = [(12.0, 99.5)] * 40 + [(12.5, 99.0)] * 20 + [(4.0, 80.0), (15.0, 84.0), (14.6, 70.0)]
    for n, (constant, accuracy) in enumerate(rows):
        title = f"chart {n}"
        index.add(ChartRef(title=title, chart_type="dx", difficulty="master", constant=constant,
                           level="13", notes=700, genre="", artist="", cover="", version=25, bpm=0.0))
        played.append(SongInfo(name=title, chart_type="dx", difficulty_type="master", accuracy=accuracy,
                               is_new=False, level="13", difficulty=constant,
                               rating=calculate_rating(constant, accuracy)))
    profile = build_play_profile(played, [], index, 26)

    problems = []
    points = profile.curve_points()
    if not points:
        problems.append("the curve came out empty for a player with sixty scores")
    rises = [(a, b) for a, b in zip(points, points[1:]) if b["e"] > a["e"] + 1e-6]
    if rises:
        first = rises[0]
        problems.append(f"the curve rises as charts get harder, at {first[0]['c']} -> {first[1]['c']} "
                        f"({first[0]['e']} -> {first[1]['e']}), on {len(rises)} points")
    # and the same rule the other way: a chart easier than where the evidence is may not be worse
    if profile.expected_accuracy(6.0) < profile.expected_accuracy(12.0) - 1e-6:
        problems.append("an easier chart was expected to go worse than a harder one")
    # where the player actually plays, the fit is left alone
    if abs(profile.expected_accuracy(12.0) - profile._raw_expectation(12.0)) > 0.05:
        problems.append("the flattening moved the curve where the player's own scores are densest")
    return problems
