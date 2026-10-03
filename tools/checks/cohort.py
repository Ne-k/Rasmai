from contextlib import contextmanager
import json
import logging

import numpy as np

from tools.checks import check

# A world with structure planted in it: every chart has a true offset from its listed constant, every
# player an ability set by their rating, and the scores are drawn from that. What the models find has
# to line up with what was planted, and nothing that identifies anybody may come out.
CHARTS = 220
PLAYERS = 90
BAR = 0.6        # rank correlation between how much harder the charts played than expected and the planted offsets the check demands
NAMES = [f"Song {i}" for i in range(CHARTS)]


def _id(n):
    return f"2000000000000{n:05d}"


@contextmanager
def _scratch():
    import pathlib
    import tempfile

    from rasmai.bot.state import cohort
    from rasmai.storage.db import connection as store
    was = store.DATABASE_PATH
    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "cohort.sqlite3", False
    cohort.reset()
    try:
        yield store
    finally:
        cohort.reset()
        store.DATABASE_PATH, store._database_ready = was, False


@contextmanager
def _charts(constants):
    """The chart database is these charts and nothing else, wherever the bot would fetch one."""
    import rasmai.bot.builders.charts as charts_package
    from rasmai.engine.analysis import build_chart_index
    from rasmai.scraping import dxdata

    songs = {name: {"title": name, "artist": "Somebody", "cover": f"{name.replace(' ', '')}.png", "dx_lev_mas_i": f"{c:.1f}",
                    "dx_lev_mas": str(int(c)), "dx_lev_mas_notes": "500"} for name, c in constants.items()}
    kept_cached, kept_shared = dxdata.cached, charts_package.shared_index
    dxdata.cached = lambda: {}
    try:
        index = build_chart_index(songs, region="intl")
    finally:
        dxdata.cached = kept_cached
    charts_package.shared_index = lambda: index
    try:
        yield index
    finally:
        charts_package.shared_index = kept_shared


def _stored(name):
    """The key the bot stores a chart under: spaces gone, as maimai DX NET names it."""
    return f"{name.replace(' ', '').casefold()}|dx|master"


def _key(stored):
    return (stored.rsplit("|", 2)[0], "dx", "master")


def _world(seed=11, players=PLAYERS):
    """Planted constants, offsets and each player's rating and best scores, as {id: (rating, {stored key: best})}."""
    rng = np.random.default_rng(seed)
    const = np.round(np.clip(rng.triangular(10.0, 12.6, 14.8, CHARTS), 10.0, 14.8), 1)
    delta = rng.normal(0, 0.5, CHARTS)                  # + means harder than listed
    pop = np.exp(rng.normal(0, 0.6, CHARTS))
    load = rng.normal(0, 1, (CHARTS, 3))
    accounts = {}
    for n in range(players):
        rating = float(np.clip(rng.normal(12600, 1300, 1)[0], 8000, 16000))
        skill = 11.2 + 1.5 * (rating - 13600) / 1000.0
        sharp = float(np.clip(rng.lognormal(np.log(1.5), 0.3), 0.8, 3.0))
        traits = rng.normal(0, 0.4, 3)
        weights = pop * np.exp(-0.5 * ((const - (skill - 0.6)) / 1.4) ** 2)
        picked = rng.choice(CHARTS, size=140, replace=False, p=weights / weights.sum())
        z = sharp * (skill - const[picked] - delta[picked] + load[picked] @ traits) + rng.logistic(0, 1, len(picked))
        achievement = np.clip(np.where(z > 0, 99 + 2 * (1 - np.exp(-0.9 * z)), 99 + 1.6 * z), 20, 101.0)
        accounts[_id(n)] = (round(rating), {_stored(NAMES[i]): round(float(a), 4) for i, a in zip(picked, achievement)})
    return const, delta, accounts, rng


def _store(accounts, optout=()):
    from rasmai.storage.db import get_user_settings, record_chart_scores, set_user_settings, upsert_connected_account
    for user, (rating, scores) in accounts.items():
        upsert_connected_account(user, "intl", "cookie://" + "a" * 64, {"name": "Player", "rating": rating})
        record_chart_scores(user, [(key, "2026-09-27T06:27:00+09:00", best, 0, "", "", "best") for key, best in scores.items()])
        if user in optout:
            settings = get_user_settings(user)
            settings["cohort"] = False
            set_user_settings(user, settings)


def _median_rating(accounts, exclude=""):
    """The account whose rating is in the middle, who has players like them on both sides."""
    ordered = sorted((user for user in accounts if user != exclude), key=lambda user: accounts[user][0])
    return ordered[len(ordered) // 2]


def _constants(const):
    return {name: float(c) for name, c in zip(NAMES, const)}


def _model_input(const, accounts):
    """The world as the engine takes it: constants by chart key, and (tag, rating, scores) per account in id order."""
    constants = {_key(_stored(n)): float(c) for n, c in zip(NAMES, const)}
    rows = [(user.encode(), rating, {_key(k): v for k, v in scores.items()}) for user, (rating, scores) in sorted(accounts.items())]
    return constants, rows


def _rank_correlation(a, b):
    """Spearman's rank correlation, ties sharing their average rank."""
    def ranks(series):
        _unique, inverse, counts = np.unique(np.asarray(series, dtype=np.float64), return_inverse=True, return_counts=True)
        return (np.cumsum(counts) - (counts - 1) / 2.0)[inverse]
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


@check("observed difficulty recovers the planted order of the charts, and a chart few have played stays out")
def _recovers():
    from rasmai.bot.state import cohort
    from rasmai.engine.cohort import MIN_PLAYERS_DIFFICULTY

    problems = []
    const, delta, accounts, rng = _world()
    # three charts nobody else touched, harder than listed by two levels: played by 3, one short of enough, and exactly enough
    extra = {"Thin 3": 3, "Edge 11": MIN_PLAYERS_DIFFICULTY - 1, "Edge 12": MIN_PLAYERS_DIFFICULTY}
    constants = {**_constants(const), **{label: 13.0 for label in extra}}
    ids = sorted(accounts, key=lambda user: -accounts[user][0])
    for label, count in extra.items():
        for user in ids[:count]:
            rating, scores = accounts[user]
            z = 1.5 * (11.2 + 1.5 * (rating - 13600) / 1000.0 - 15.0) + rng.logistic(0, 1)
            scores[_stored(label)] = round(float(np.clip(99 + 2 * (1 - np.exp(-0.9 * z)) if z > 0 else 99 + 1.6 * z, 20, 101)), 4)
    with _scratch(), _charts(constants) as index:
        _store(accounts)
        found = {name: cohort.difficulty(index.get(_key(_stored(name))).key) for name in list(NAMES) + list(extra)}
        shown = [name for name in NAMES if found[name]]
        shift = {name: found[name]["expected"] - found[name]["rate"] for name in shown}      # positive: cleared less often than expected
        if len(shown) < CHARTS // 2:
            problems.append(f"only {len(shown)} of {CHARTS} charts had enough players to be shown")
        rank = _rank_correlation([shift[n] for n in shown], [delta[NAMES.index(n)] for n in shown])
        if not rank >= BAR:
            problems.append(f"observed shifts line up with the planted offsets at rank correlation {rank:.2f}, below {BAR}")
        harder = sum(1 for n in shown if shift[n] > 0)
        if not 0.25 * len(shown) < harder < 0.75 * len(shown):
            problems.append(f"{harder} of {len(shown)} charts came out harder than their level: the shifts all lean one way")
        if abs(np.corrcoef([shift[n] for n in shown], [const[NAMES.index(n)] for n in shown])[0, 1]) > 0.3:
            problems.append("how much harder a chart played than expected follows its listed constant, which is the trend the level bands are there to take out")
        if found["Thin 3"] or found["Edge 11"]:
            problems.append("a chart under the minimum number of players was shown")
        edge = found["Edge 12"]
        if not edge or edge["players"] != MIN_PLAYERS_DIFFICULTY:
            problems.append(f"a chart with exactly the minimum of players was not shown: {edge}")
        elif not edge["rate"] <= edge["expected"]:
            problems.append("a thin chart planted two levels harder was cleared more often than expected")
        counted, harder_list, easier_list = cohort.outliers()
        if counted != PLAYERS or not harder_list or not easier_list:
            problems.append(f"the harder and easier lists came out {len(harder_list)} and {len(easier_list)} for {counted} players")
        if (any(row["rate"] >= row["expected"] or row["lean"] != "harder" for row in harder_list)
                or any(row["rate"] <= row["expected"] or row["lean"] != "easier" for row in easier_list)
                or any(row["players"] < MIN_PLAYERS_DIFFICULTY for row in harder_list + easier_list)):
            problems.append("a chart is in the wrong one of the harder and easier lists, or has too few players")
    return problems


@check("two builds of the same cohort are equal, whatever order the accounts arrive in")
def _deterministic():
    from rasmai.bot.state import cohort
    from rasmai.engine import cohort as model

    const, _delta, accounts, _rng = _world(seed=3, players=40)
    with _scratch(), _charts(_constants(const)):
        _store(accounts)
        cohort.players()
        held = cohort._built
    a = held.cohort
    rows = [(tag, float(a.ratings[i]), {a.keys[c]: float(v) for c, v in zip(a.cols[a.indptr[i]:a.indptr[i + 1]], a.vals[a.indptr[i]:a.indptr[i + 1]])})
            for i, tag in enumerate(a.tags)]
    b = model.build_cohort(reversed(rows), {key: float(c) for key, c in zip(a.keys, a.constants)})
    same = all(np.array_equal(getattr(a, name), getattr(b, name)) for name in ("constants", "ratings", "indptr", "cols", "vals")) and a.tags == b.tags
    return [] if same and model.fit_difficulty(b).charts == held.found.charts else ["the order the accounts arrive in changes the cohort or its fit"]


@check("an account that opts out changes nobody's result, still gets its own picks, and leaves the counted players at once")
def _optout():
    from rasmai.bot.state import cohort
    from rasmai.storage.db import get_connected_account
    from rasmai.web.dashboard.cohort import difficulty_payload, likeyou_payload
    from rasmai.web.dashboard.public_profile import set_sharing, sharing_payload

    problems = []
    const, _delta, accounts, _rng = _world(seed=5, players=PLAYERS + 1)
    ids = sorted(accounts)
    leaver = ids[-1]
    viewer = _median_rating(accounts, exclude=leaver)

    def answers():
        return likeyou_payload(get_connected_account(viewer), None), difficulty_payload(None)

    with _scratch(), _charts(_constants(const)):
        _store(accounts, optout=(leaver,))
        if cohort.players() != PLAYERS:
            problems.append(f"{cohort.players()} players counted with one opted out from the start, expected {PLAYERS}")
        expected = answers()
        # the account that opted out is still answered, from its own scores as they are now
        mine = likeyou_payload(get_connected_account(leaver), None)
        if mine["reason"] != "" or not mine["picks"]:
            problems.append(f"an opted-out account got no picks of its own: {mine['reason']!r}, {len(mine['picks'])} picks")

    # an account that opted out is as good as absent: everyone else's result is what it is with the account never stored
    with _scratch(), _charts(_constants(const)):
        _store({user: accounts[user] for user in ids[:-1]})
        if answers() != expected:
            problems.append("an opted-out account's scores changed somebody else's result")

    # the same account leaving later, while it is counted: gone from what is held at once, and the fit is redone without it
    with _scratch(), _charts(_constants(const)):
        _store(accounts)
        if cohort.players() != PLAYERS + 1:
            problems.append("an account that has not opted out was not counted")
        set_sharing(leaver, None, cohort=False)
        held = cohort._built
        if held.cohort.players != PLAYERS or held.found.charts:
            problems.append("what was held still had the account's row, or the difficulty fitted with its scores, after it left")
        if cohort.players() != PLAYERS:
            problems.append(f"switching the opt-out on left {cohort.players()} counted, expected {PLAYERS}")
        if answers() != expected:
            problems.append("somebody's result depends on whether the account left before the build or after it")
        if sharing_payload(leaver, None)["cohort"] is not False:
            problems.append("the opt-out does not read back from the sharing state")
    return problems


@check("the opt-out is a setting of its own that survives other changes to the settings, and the beta switches survive it")
def _setting():
    from rasmai.storage.db import get_user_settings, upsert_connected_account
    from rasmai.web.dashboard.beta import set_beta, wants
    from rasmai.web.dashboard.public_profile import set_sharing, sharing_payload

    problems = []
    with _scratch():
        user = _id(1)
        upsert_connected_account(user, "intl", "cookie://" + "a" * 64, {"name": "Player", "rating": 12000})
        if sharing_payload(user, None).get("cohort") is not True:
            problems.append("a person who never chose is not counted by default")
        set_beta(user, {"likeyou": True, "difficulty": True})
        if set_sharing(user, None, cohort=False).get("cohort") is not False:
            problems.append("switching the opt-out on does not show in the state it returns")
        set_sharing(user, True, {"best50": True}, account={"shareSlug": "abcdefghij"})
        if sharing_payload(user, None).get("cohort") is not False:
            problems.append("changing another sharing setting put the person back in the count")
        if not (wants(user, "likeyou") and wants(user, "difficulty")):
            problems.append("changing a sharing setting switched the beta features off")
        if set_sharing(user, None, cohort=True).get("cohort") is not True or get_user_settings(user).get("cohort") is not True:
            problems.append("the opt-out did not turn back off")
        if set_sharing(user, None).get("cohort") is not True:
            problems.append("a request that does not mention it changed the opt-out")
        keys = set(sharing_payload(user, None))
        if "cohort" not in keys or {"on", "url", "sections", "card", "embed", "colour", "colours", "visual", "visuals"} - keys:
            problems.append(f"the sharing state lost a key or did not gain cohort: {sorted(keys)}")
    return problems


@check("neighbours never include the viewer, whose own row is left out, and the closest player to an identical record is its twin")
def _not_self():
    from rasmai.engine import cohort as model

    problems = []
    const, _delta, accounts, _rng = _world(seed=7, players=50)
    constants, everyone = _model_input(const, accounts)
    tag, rating, own = everyone[sorted(accounts).index(_median_rating(accounts))]
    with_twin = model.build_cohort(everyone + [(b"twin", rating, own)], constants)
    dense = np.array([own.get(name, np.nan) for name in with_twin.keys])
    others = with_twin.without(tag)
    if tag in others.tags or others.players != with_twin.players - 1:
        problems.append("the viewer's own row was not taken out")
    order = model._neighbours(others, dense, rating)
    if not len(order) or others.tags[order[0]] != b"twin":
        problems.append("the closest player to an identical record was not its twin")
    if tag in [others.tags[i] for i in order]:
        problems.append("the viewer was among their own neighbours")
    mine = model.like_you(with_twin, own, rating, tag)
    left = model.like_you(model.build_cohort([row for row in everyone if row[0] != tag] + [(b"twin", rating, own)], constants), own, rating)
    if mine.picks != left.picks or mine.neighbours != left.neighbours:
        problems.append("the viewer's own row changed their result")
    return problems


@check("players like you offers charts the person has no top score on and can reach, from the minimum of players, and says nothing otherwise")
def _picks_and_minimums():
    from rasmai.engine import cohort as model

    problems = []
    const, _delta, accounts, _rng = _world(seed=9)
    constants, everyone = _model_input(const, accounts)
    viewer = sorted(accounts).index(_median_rating(accounts))
    rating, own = everyone[viewer][1], everyone[viewer][2]
    others = [row for i, row in enumerate(everyone) if i != viewer]
    result = model.like_you(model.build_cohort(others, constants), own, rating)
    if result.reason or not result.picks or result.neighbours < model.MIN_NEIGHBOURS:
        problems.append(f"no picks for a viewer with a full cohort: {result.reason!r}, {result.neighbours} neighbours")
    reach = max(constants[k] for k, v in own.items() if v >= 97.0)
    for pick in result.picks:
        if pick["yours"] is not None and pick["typical"] - pick["yours"] < model.MIN_GAP:
            problems.append("a pick the person already scores as well on was offered")
        if pick["constant"] > reach + model.REACH_ABOVE + 1e-9:
            problems.append(f"a pick at {pick['constant']} is above the viewer's reach of {reach}")
        if not model.MIN_CHART_NEIGHBOURS <= pick["neighbours"] <= model.K_NEIGHBOURS:
            problems.append(f"a pick rests on {pick['neighbours']} neighbours")
        if pick["typical"] < model.SCORES_WELL:
            problems.append("a pick's typical score is not a good one")
    if len(result.picks) > model.PICKS:
        problems.append(f"{len(result.picks)} picks, expected at most {model.PICKS}")
    if not any(pick["yours"] is None for pick in result.picks):
        problems.append("every pick was a chart the person has played: unplayed charts never came up")

    # fewer players than the minimum shows nothing, a viewer with too few scores is told so, and nobody in the rating window means nobody like them
    small = model.like_you(model.build_cohort(others[:model.MIN_COHORT - 1], constants), own, rating)
    if small.picks or small.reason != "not_enough_players":
        problems.append(f"a cohort under the minimum still produced {len(small.picks)} picks ({small.reason!r})")
    full = model.build_cohort(others, constants)
    if model.like_you(full, dict(list(own.items())[:model.MIN_SHARED - 1]), rating).reason != "not_enough_scores":
        problems.append("a viewer with fewer than the minimum of scores was not told so")
    far = model.like_you(full, own, rating + 10 * model.RATING_WINDOW)
    if far.picks or far.reason != "not_enough_players" or far.neighbours:
        problems.append("players outside the rating window were counted as neighbours")
    return problems


@check("the cache shows nothing below the minimum cohort, and nothing it shows names anybody")
def _private():
    from rasmai.bot.state import cohort
    from rasmai.engine.cohort import MIN_COHORT
    from rasmai.storage.db import get_connected_account
    from rasmai.web.dashboard.cohort import difficulty_payload, likeyou_payload

    problems = []
    const, _delta, accounts, _rng = _world(seed=13)
    ids = sorted(accounts)
    seen = []

    class Collect(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    handler, root = Collect(), logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        with _scratch(), _charts(_constants(const)):
            _store({user: accounts[user] for user in ids[:MIN_COHORT - 1]})
            viewer = ids[0]
            payload = likeyou_payload(get_connected_account(viewer), None)
            if payload["ready"] or payload["picks"] or payload["players"] != MIN_COHORT - 1:
                problems.append(f"under the minimum cohort the picks said ready={payload['ready']} with {len(payload['picks'])} picks")
            hard = difficulty_payload(None)
            if hard["ready"] or hard["harder"] or hard["easier"]:
                problems.append("under the minimum cohort the difficulty lists were not empty")

            _store({user: accounts[user] for user in ids[MIN_COHORT - 1:]})
            cohort.reset()
            full = likeyou_payload(get_connected_account(viewer), None)
            hard = difficulty_payload(None)
            serialised = json.dumps([full, hard], ensure_ascii=False)
            if not full["ready"] or not full["picks"]:
                problems.append(f"a full cohort gave no picks: {full['reason']!r}")
            # an account's tag is its id, so the id and its bytes are what must not come out
            secrets = ids + [user.encode().hex() for user in ids]
            if any(secret in serialised for secret in secrets + [str(accounts[user][0]) + '"' for user in ids[:5]]):
                problems.append("an account id or tag reached a payload")
            if set(full) != {"ok", "ready", "players", "picks", "reason", "judgements"} or set(hard) != {"ok", "ready", "players", "harder", "easier"}:
                problems.append(f"a payload carries {sorted(full)} and {sorted(hard)}")
            if any(set(pick) != {"title", "chartType", "difficulty", "level", "constant", "cover", "yours", "typical", "neighbours", "average"} for pick in full["picks"]):
                problems.append("a pick carries something unexpected")
            if any(set(row) != {"title", "chartType", "difficulty", "level", "rate", "expected", "lean", "players", "cover", "average"} for row in hard["harder"] + hard["easier"]):
                problems.append("a chart in the difficulty lists carries something unexpected")
        logged = "\n".join(seen)
        if any(secret in logged for secret in secrets):
            problems.append("an account id or tag was logged")
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
    return problems


@check("a chart's average is the median of everyone's best on it, and absent below the minimum of players")
def _means():
    from rasmai.bot.state import cohort
    from rasmai.engine.cohort import MIN_AVERAGE

    problems = []
    const, _delta, accounts, _rng = _world(seed=13)
    with _scratch(), _charts(_constants(const)) as index:
        _store(accounts)
        cohort._held()
        for name in NAMES:
            scores = [s[_stored(name)] for _rating, s in accounts.values() if _stored(name) in s]
            got = cohort.average(index.get(_key(_stored(name))).key)
            if len(scores) >= MIN_AVERAGE:
                if got is None or abs(got - float(np.median(scores))) > 1e-3:
                    problems.append(f"{name}: {len(scores)} players, average {got}, expected {float(np.median(scores)):.3f}")
            elif got is not None:
                problems.append(f"{name}: {len(scores)} players but an average was shown")
        if not any(cohort.average(index.get(_key(_stored(name))).key) is not None for name in NAMES):
            problems.append("no chart had an average")
    return problems


@check("your judgements are set beside the middle of the players like you, only from five of them, and nobody's own profile or id comes out")
def _judged():
    from rasmai.engine.cohort import K_NEIGHBOURS, MIN_JUDGED, compare_judgements
    from rasmai.storage.db import get_connected_account
    from rasmai.web.dashboard import cohort as route
    from rasmai.web.dashboard.cohort import likeyou_payload

    def profile(per100, late=0.5, kinds=("tap", "break")):
        return {"types": [{"kind": k, "per100": per100 + i, "clean": 0.9 - per100 / 10} for i, k in enumerate(kinds)],
                "lostPerPlay": per100, "lateShare": late, "plays": 6}

    problems = []
    mine = profile(2.0)
    crowd = [profile(1.0 + i / 10, late=0.4 + i / 10) for i in range(MIN_JUDGED)]
    got = compare_judgements(mine, crowd)
    if got is None or got["players"] != MIN_JUDGED or [t["kind"] for t in got["types"]] != ["tap", "break"]:
        problems.append(f"five neighbours with a profile gave {got}")
    elif abs(got["types"][0]["theirPer100"] - 1.2) > 1e-9 or abs(got["types"][1]["theirPer100"] - 2.2) > 1e-9             or abs(got["theirLostPerPlay"] - 1.2) > 1e-9 or abs(got["theirLateShare"] - 0.6) > 1e-9:
        problems.append(f"the middle of five planted profiles came out as {got}")
    if compare_judgements(mine, crowd[:-1]) is not None or compare_judgements(None, crowd) is not None:
        problems.append("fewer than five neighbours, or nobody's own profile, still gave a comparison")
    if [t["kind"] for t in compare_judgements(mine, crowd[:-1] + [profile(1.0, kinds=("tap",))])["types"]] != ["tap"]:
        problems.append("a note type only four neighbours have was shown")
    if compare_judgements(mine, crowd[:-1] + [profile(1.0, late=None)])["theirLateShare"] is not None:
        problems.append("a timing split only four neighbours have was shown")

    const, _delta, accounts, _rng = _world(seed=13)
    ids = sorted(accounts)
    viewer = _median_rating(accounts)
    planted = {user: profile(1.0 + n / 50) for n, user in enumerate(ids)}
    kept = route.load_judgements, route.judgement_profile
    # stands in for the stored pages: one clean play and one failed one for everybody, with the account kept on them
    route.load_judgements = lambda user: [{"achievement": 99.0, "who": user}, {"achievement": 50.0, "who": user}]
    seen = []

    def profile_of(rows, only=None):
        seen.append(len(rows))
        return planted.get(rows[0]["who"]) if rows and (only is None or rows[0]["who"] == only) else None
    try:
        route.judgement_profile = profile_of
        with _scratch(), _charts(_constants(const)):
            _store(accounts)
            payload = likeyou_payload(get_connected_account(viewer), None)
            there = payload["judgements"]
            if there is None or not MIN_JUDGED <= there["players"] <= K_NEIGHBOURS:
                problems.append(f"a full cohort gave the viewer {there and there['players']} neighbours' judgements")
            elif there["lostPerPlay"] != planted[viewer]["lostPerPlay"]:
                problems.append("the viewer's own side of the comparison is not their own profile")
            if any(secret in json.dumps(payload) for secret in ids + [user.encode().hex() for user in ids]):
                problems.append("an account id or tag reached the judgement comparison")
            if not seen or any(n != 1 for n in seen):
                problems.append("a play under the floor reached the judgement profile")
            route.judgement_profile = lambda rows: profile_of(rows, only=viewer)
            if likeyou_payload(get_connected_account(viewer), None)["judgements"] is not None:
                problems.append("with no neighbour holding judgement pages the comparison still appeared")
    finally:
        route.load_judgements, route.judgement_profile = kept
    return problems


@check("with a beta switched off the routes answer 404 not_enabled and the chart detail has no observed key; switched on, both answer")
def _beta_gate():
    from rasmai.bot.state.cache import CachedAnalysis
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import SongInfo
    from rasmai.web.dashboard import routes
    from rasmai.web.dashboard.beta import set_beta
    from rasmai.web.dashboard.lookup import chart_payload

    class Fake:
        def __init__(self):
            self.sent = []

        def _send_json(self, status, body):
            self.sent.append((status, body))

    def ask(path, user):
        handler = Fake()
        routes.handle_get(handler, path, {}, {"id": user})
        return handler.sent[0]

    problems = []
    const, _delta, accounts, _rng = _world(seed=17)
    viewer = sorted(accounts)[40]
    kept = routes.analysis_for_user
    routes.analysis_for_user = lambda *args, **kwargs: None
    try:
        with _scratch(), _charts(_constants(const)) as index:
            _store(accounts)
            analyzer = MaimaiRatingAnalyzer()
            analyzer._chart_index = index
            analyzer.songs = [SongInfo(name=NAMES[3].replace(" ", ""), chart_type="dx", difficulty_type="master", accuracy=99.0, level="13")]
            cached = CachedAnalysis(user_id=viewer, region="intl", analyzer=analyzer, recommendations=[], value_charts=[])
            for path in ("/internal/me/likeyou", "/internal/me/difficulty"):
                status, body = ask(path, viewer)
                if status != 404 or body != {"ok": False, "error": "not_enabled"}:
                    problems.append(f"{path} answered {status} {body} with the switch off")
            if any("observed" in chart for chart in chart_payload(cached, NAMES[3], "dx", "master")["charts"]):
                problems.append("the chart detail carries observed with the switch off")
            if (status := ask("/internal/me/likeyou", "999999999999999999")[0]) != 404:
                problems.append(f"somebody without an account was answered {status}")

            set_beta(viewer, {"likeyou": True, "difficulty": True})
            for path, keys in (("/internal/me/likeyou", {"picks"}), ("/internal/me/difficulty", {"harder", "easier"})):
                status, body = ask(path, viewer)
                if status != 200 or not body.get("ok") or not keys <= set(body):
                    problems.append(f"{path} answered {status} {sorted(body)} with the switch on")
            charts = chart_payload(cached, NAMES[3], "dx", "master")["charts"]
            there = [chart for chart in charts if "observed" in chart]
            if len(there) != len(charts):
                problems.append("the chart detail has no observed key with the switch on")
            elif there[0]["observed"] is None:
                problems.append("a chart a dozen players have played has no observed difficulty")
            elif set(there[0]["observed"]) != {"rate", "expected", "players", "lean"}:
                problems.append(f"observed carries {sorted(there[0]['observed'])}")
    finally:
        routes.analysis_for_user = kept
    return problems
