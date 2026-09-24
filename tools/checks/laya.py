import sys

from tools.checks import ROOT, check


@check("the decision model is a switch, and the picks are unchanged for everyone who never finds it")
def _laya_is_optional():
    import pathlib
    import tempfile

    from rasmai.engine.analysis import ChartIndex, ChartRef, build_best50, build_play_profile, generate_recommendations
    from rasmai.engine.insights import laya
    from rasmai.storage.db import connection as store
    from rasmai.storage.models import SongInfo
    from rasmai.web.dashboard.beta import FEATURES, READINESS, set_beta, wants

    problems = []
    if "laya" not in FEATURES:
        problems.append("the decision model is not in the beta picker, so nobody can switch it on or off")
    if "laya" not in READINESS:
        problems.append("a bot built without the model would offer the switch anyway, and do nothing when it is flipped")

    # the site draws these itself, so a spelling only the bot knows leaves a checkbox with no words on it
    drawn = (ROOT / "web" / "components" / "dash" / "api.ts").read_text(encoding="utf-8")
    shape = drawn.split("export type BetaFeature = {", 1)[-1].split("};", 1)[0]
    required = {line.split(":", 1)[0].strip() for line in shape.splitlines()
                if ":" in line and not line.strip().startswith("//") and "?" not in line.split(":", 1)[0]}
    for key, spec in FEATURES.items():
        missing = (required - {"key"}) - set(spec)
        if missing:
            problems.append(f"the site draws {', '.join(sorted(missing))} for a beta feature, and {key} has none")

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        user = "laya-check-user"
        if wants(user, "laya"):
            problems.append("the decision model is on for somebody who never asked for it")
        if not set_beta(user, {"laya": True})["on"].get("laya"):
            problems.append("switching the decision model on did not stick")
        if not wants(user, "laya"):
            problems.append("the switch reads off straight after being turned on")
        set_beta(user, {"laya": False})
        if wants(user, "laya"):
            problems.append("switching the decision model off did not stick")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False

    # the model is not in the image, so every path through it has to end in the arithmetic
    held = laya.available
    try:
        laya.available = lambda: False
        laya._forget()
        if laya.load() is not None:
            problems.append("a bot without the package still handed back a model")
        if laya.pick_odds(object(), [{"key": ("a", "dx", "master")}]):
            problems.append("a bot without the package still answered with odds")
        if laya.taste(object(), [{"key": ("a", "dx", "master")}]):
            problems.append("a bot without the package still moved the ranking")
        if READINESS["laya"]().get("ready"):
            problems.append("a bot without the package reported the feature ready to use")
    finally:
        laya.available = held
        laya._forget()

    index = ChartIndex()
    index.add(ChartRef(title="Song", chart_type="dx", difficulty="master", constant=13.0, level="13",
                       notes=700, genre="POPS", artist="a", cover="", version=26, bpm=170.0))
    songs = [SongInfo(name="Song", chart_type="dx", difficulty_type="master", accuracy=98.0,
                      rating=250, level="13", difficulty=13.0, is_new=False)]
    profile = build_play_profile(songs, [], index, 26)
    best50 = build_best50(songs)
    key = ("song", "dx", "master")
    plain = generate_recommendations(songs, profile, best50, index, 26)
    # nothing has measured this player's taste, so the three categories are still what answers
    if profile.affinity("dx", "POPS", "master", key) != profile.affinity("dx", "POPS", "master"):
        problems.append("an unmeasured chart was scored differently just for being asked about by key")
    categories = profile.affinity("dx", "POPS", "master")
    profile.taste = {key: 4.0}
    if profile.affinity("dx", "POPS", "master", key) != categories * 4.0:
        problems.append("a measured chart was not weighed on the same scale as an unmeasured one, so "
                        "the two cannot be ranked against each other")
    if profile.affinity("dx", "POPS", "master") != categories:
        problems.append("a reading for one chart leaked into every chart that was asked about without a key")
    moved = generate_recommendations(songs, profile, best50, index, 26)
    if len(moved) != len(plain):
        problems.append("the model changed which charts are recommended, when it may only change their order")

    # the switch is per player, so an analyzer with nobody attached to it must never reach the model
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    analyzer = MaimaiRatingAnalyzer.__new__(MaimaiRatingAnalyzer)
    analyzer.user_id, analyzer._pick_odds = "", {}
    if analyzer._read_taste([], index):
        problems.append("an analysis with no account behind it still asked the model about somebody")

    # And the switch has to be read *before* the model's module is, or every analysis on the bot
    # pays to import it - which on a bot built with the package means importing torch - whether the
    # person turned anything on or not. This is the one ordering that can regress silently.
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    import rasmai.engine.insights as _insights
    module = sys.modules.pop("rasmai.engine.insights.laya", None)
    # the package keeps its own attribute once a submodule has been imported, and an import would
    # find that instead of loading anything, so hiding it too is what makes this test mean something
    attribute = getattr(_insights, "laya", None)
    if attribute is not None:
        delattr(_insights, "laya")
    try:
        analyzer.user_id = "somebody-who-never-found-it"
        chart = ChartRef(title="Song", chart_type="dx", difficulty="master", constant=13.0, level="13",
                         notes=700, genre="POPS", artist="a", cover="", version=26, bpm=170.0)
        index.add(chart)
        if analyzer._read_taste(list(plain), index):
            problems.append("a player who never switched the model on had their picks reordered by it")
        if "rasmai.engine.insights.laya" in sys.modules:
            problems.append("an analysis for somebody without the switch on loaded the model's module "
                            "anyway, so the switch is being read after the import rather than before it")
    finally:
        if module is not None:
            sys.modules["rasmai.engine.insights.laya"] = module
        if attribute is not None:
            setattr(_insights, "laya", attribute)
        store.DATABASE_PATH = was
        store._database_ready = False

    if laya.WEIGHT <= 0:
        problems.append(f"a weight of {laya.WEIGHT} means the feature does nothing when it is switched on")
    # Every weight measured cost the ranking something, more of it the further it went: against 105
    # held-out plays the arithmetic alone placed a played chart at 0.565 and the model took that to
    # 0.538 at 0.25 and 0.513 at 1.0. 0.25 is the least harm anyone has measured, and there is no
    # reading anywhere that supports turning it up.
    MEASURED_TO = 0.25
    if laya.WEIGHT > MEASURED_TO:
        problems.append(f"a weight of {laya.WEIGHT} is past the {MEASURED_TO} that was measured, and "
                        f"every reading past it made the ranking worse; measure it again before raising it")

    # over a gigabyte of it, so it stays out of the image everybody gets
    base = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package in ("laya", "torch", "transformers"):
        if any(line.split("==")[0].strip() == package for line in base.splitlines()):
            problems.append(f"{package} is in requirements.txt, so every deployment now carries the "
                            f"model whether it will ever switch the feature on or not")
    extra = ROOT / "requirements-laya.txt"
    if not extra.exists():
        problems.append("there is nowhere to install the model from, so nobody can turn the feature on")
    elif "laya==" not in extra.read_text(encoding="utf-8"):
        problems.append("requirements-laya.txt does not pin the model it exists to install")
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "requirements-laya.txt" not in docker:
        problems.append("the image cannot be built with the model at all")
    elif "WITH_LAYA" not in docker:
        problems.append("the image installs the model unconditionally, so it is no longer optional")
    return problems


@check("what the decision model says reaches the list, and never outranks what a score is worth")
def _laya_reaches_the_picks():
    from rasmai.engine.analysis import ChartIndex, ChartRef, build_best50, build_play_profile, generate_recommendations
    from rasmai.engine.insights import laya
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import SongInfo

    problems = []
    # a player whose own charts are all worth the same, which is what most of a real list looks like:
    # the gain is a whole number, and nine in ten of the first forty picks share one with something
    index, songs = ChartIndex("intl"), []
    for tenth in range(100, 141):
        constant = tenth / 10.0
        for number in range(6):
            index.add(ChartRef(title=f"unplayed {tenth} {number}", chart_type="dx", difficulty="master",
                               constant=constant, level=str(int(constant)), notes=700,
                               genre=f"genre {number % 3}", artist="a", cover="", version=26, intl=True))
    for number in range(12):
        title = f"played {number:02d}"
        index.add(ChartRef(title=title, chart_type="dx", difficulty="master", constant=12.0, level="12",
                           notes=700, genre="POPS", artist="a", cover="", version=25, intl=True))
        songs.append(SongInfo(name=title, chart_type="dx", difficulty_type="master", accuracy=99.8,
                              level="12", difficulty=12.0, rating=250))
    profile = build_play_profile(songs, [], index, 26)
    best50 = build_best50(songs)
    # the unplayed picks are judged on their own score, so which of them make the cut may change;
    # the charts the player already holds a score on are the tie this is about
    tied = lambda picks: [c for c in picks if c.category == "rating"]
    order = lambda picks: [c.title for c in tied(picks)]
    gains = lambda picks: [c.rating_gain for c in tied(picks)]

    plain = generate_recommendations(songs, profile, best50, index, 26)
    if len(order(plain)) < 6 or len(set(gains(plain))) != 1:
        problems.append(f"the fixture is no longer a tie of a useful size ({len(order(plain))} charts, "
                        f"{len(set(gains(plain)))} distinct gains), so nothing here tests what it says it does")
        return problems

    # nothing measured: every chart has to weigh exactly 1.0, or a list nobody asked to be read moves
    if any(profile.pick_weight((c.title.casefold(), c.chart_type, c.difficulty_type)) != 1.0 for c in plain):
        problems.append("an unmeasured chart carried a weight other than 1.0 into the ordering")

    # the model's opinion, back to front: the list has to follow it
    profile.taste = {(title.casefold(), "dx", "master"): 0.25 + 1.75 * number / (len(order(plain)) - 1)
                     for number, title in enumerate(order(plain))}
    moved = generate_recommendations(songs, profile, best50, index, 26)
    if order(moved) == order(plain):
        problems.append("the model was listened to and the list came back in exactly the same order, "
                        "so nothing it says reaches anybody")
    if order(moved)[0] != order(plain)[-1]:
        problems.append("the chart the model liked most did not come first among charts worth the same")
    if gains(moved) != gains(plain):
        problems.append("taste moved a bigger rating gain below a smaller one, when it may only "
                        "decide between charts already worth the same")
    if set(order(moved)) != set(order(plain)):
        problems.append("the model changed which charts are recommended, when it may only change their order")

    # and it is bounded: a chart the model dislikes is ranked last, never dropped out of the ranking
    keys = [(letter, "dx", "master") for letter in "abc"]
    # answers a few percent apart, which is how far apart the real ones sit across one shortlist
    odds = dict(zip(keys, (0.70, 0.75, 0.80)))
    for how in ("rank", "spread", "mean"):
        weights = laya.weigh(odds, weight=laya.WEIGHT, how=how)
        if not weights:
            problems.append(f"odds the model did give were turned into no opinion at all by {how}")
            continue
        for key, value in weights.items():
            if not laya.FLOOR <= value <= laya.CEILING:
                problems.append(f"{how} weighted {key[0]} at {value}, outside the {laya.FLOOR} to "
                                f"{laya.CEILING} a chart is allowed to be moved by")
        if sorted(weights, key=lambda key: weights[key]) != keys:
            problems.append(f"{how} did not keep the order the model put the charts in")
    if laya.MAPPING not in ("rank", "spread", "mean"):
        problems.append(f"the shipped mapping is {laya.MAPPING}, which nothing was fitted for")
    if laya.weigh(odds, weight=0.0):
        problems.append("a weight of nothing still moved the ranking")
    if laya.weigh({}, weight=laya.WEIGHT):
        problems.append("no odds at all still moved the ranking")
    # zero is a deletion rather than an opinion, and the floor is what stops it being one
    if min(laya.weigh(dict(zip(keys, (0.0, 0.5, 1.0))), weight=3.0).values()) < laya.FLOOR:
        problems.append("a chart the model scored zero was not held at the floor, so it can be "
                        "multiplied out of a list the arithmetic says is worth playing")

    # one read ranks three times over, and the model may only be asked once
    asked = []
    original = laya.pick_odds
    try:
        def counting(profile, charts):
            asked.append([chart["key"] for chart in charts])
            return {chart["key"]: 0.5 + number / 100.0 for number, chart in enumerate(charts)}
        laya.pick_odds = counting
        analyzer = MaimaiRatingAnalyzer.__new__(MaimaiRatingAnalyzer)
        analyzer.user_id, analyzer._pick_odds, analyzer.play_profile = "somebody", {}, profile
        candidates = generate_recommendations(songs, profile, best50, index, 26) or plain
        from rasmai.web.dashboard import beta as _beta
        was_settings = _beta.get_user_settings
        try:
            _beta.get_user_settings = lambda user_id: {"beta": {"laya": True}}
            first = analyzer._read_taste(candidates, index)
            again = analyzer._read_taste(candidates, index)
        finally:
            _beta.get_user_settings = was_settings
        if not first:
            problems.append("a player who switched the model on got nothing back from it")
        if first != again:
            problems.append("asking twice for the same shortlist gave two different answers")
        if len(asked) != 1:
            problems.append(f"the model was asked {len(asked)} times for one read, when the answers "
                            f"from the first time were still sitting there")
    finally:
        laya.pick_odds = original
    return problems
