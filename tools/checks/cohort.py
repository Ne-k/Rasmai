from contextlib import contextmanager

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


@check("observed difficulty recovers the planted order of the charts, follows no trend with the listed constant, and keeps a chart few have played out")
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
        harder_by = {name: found[name]["expected"] - found[name]["rate"] for name in shown}      # positive: cleared less often than expected
        if len(shown) < CHARTS // 2:
            problems.append(f"only {len(shown)} of {CHARTS} charts had enough players to be shown")
        rank = _rank_correlation([harder_by[n] for n in shown], [delta[NAMES.index(n)] for n in shown])
        if not rank >= BAR:
            problems.append(f"charts line up with the planted offsets at rank correlation {rank:.2f}, below {BAR}")
        harder = sum(1 for n in shown if harder_by[n] > 0)
        if not 0.25 * len(shown) < harder < 0.75 * len(shown):
            problems.append(f"{harder} of {len(shown)} charts came out harder than their level: the shifts all lean one way")
        if abs(np.corrcoef([harder_by[n] for n in shown], [const[NAMES.index(n)] for n in shown])[0, 1]) > 0.3:
            problems.append("how much harder a chart played than expected follows its listed constant, which the level bands are there to take out")
        if found["Thin 3"] or found["Edge 11"]:
            problems.append("a chart under the minimum number of players was shown")
        edge = found["Edge 12"]
        if not edge or edge["players"] != MIN_PLAYERS_DIFFICULTY:
            problems.append(f"a chart with exactly the minimum of players was not shown: {edge}")
        elif not edge["rate"] <= edge["expected"]:
            problems.append("a thin chart planted two levels harder was cleared more often than expected")
        if {row["lean"] for row in found.values() if row} - {"harder", "easier", "same"}:
            problems.append("a chart's lean is not one of harder, easier or same")
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


@check("an account that opts out changes nobody's numbers and leaves the counted players at once, and the opt-out is a setting that survives other changes")
def _optout():
    from rasmai.bot.state import cohort
    from rasmai.storage.db import get_user_settings, upsert_connected_account
    from rasmai.web.dashboard.beta import set_beta, wants
    from rasmai.web.dashboard.public_profile import set_sharing, sharing_payload

    problems = []
    const, _delta, accounts, _rng = _world(seed=5, players=PLAYERS + 1)
    ids = sorted(accounts)
    leaver = ids[-1]
    with _scratch(), _charts(_constants(const)) as index:
        keys = [index.get(_key(_stored(name))).key for name in NAMES]
        _store(accounts, optout=(leaver,))
        if cohort.players() != PLAYERS:
            problems.append(f"{cohort.players()} players counted with one opted out from the start, expected {PLAYERS}")
        expected = [cohort.difficulty(key) for key in keys]
    # an account that opted out is as good as absent: everyone's numbers are what they are with the account never stored
    with _scratch(), _charts(_constants(const)) as index:
        _store({user: accounts[user] for user in ids[:-1]})
        if [cohort.difficulty(index.get(_key(_stored(name))).key) for name in NAMES] != expected:
            problems.append("an opted-out account's scores changed somebody's numbers")
    # the same account leaving later, while it is counted: gone from what is held at once
    with _scratch(), _charts(_constants(const)):
        _store(accounts)
        if cohort.players() != PLAYERS + 1:
            problems.append("an account that has not opted out was not counted")
        set_sharing(leaver, None, cohort=False)
        if cohort._built.cohort.players != PLAYERS or cohort._built.found.charts:
            problems.append("what was held still had the account's row, or the fit made with its scores, after it left")
        if cohort.players() != PLAYERS:
            problems.append(f"switching the opt-out on left {cohort.players()} counted, expected {PLAYERS}")
    with _scratch():
        user = _id(1)
        upsert_connected_account(user, "intl", "cookie://" + "a" * 64, {"name": "Player", "rating": 12000})
        if sharing_payload(user, None).get("cohort") is not True:
            problems.append("a person who never chose is not counted by default")
        set_beta(user, {"patterns": True})
        if set_sharing(user, None, cohort=False).get("cohort") is not False:
            problems.append("switching the opt-out on does not show in the state it returns")
        set_sharing(user, True, {"best50": True}, account={"shareSlug": "abcdefghij"})
        if sharing_payload(user, None).get("cohort") is not False:
            problems.append("changing another sharing setting put the person back in the count")
        if not wants(user, "patterns"):
            problems.append("changing a sharing setting switched a beta feature off")
        if set_sharing(user, None, cohort=True).get("cohort") is not True or get_user_settings(user).get("cohort") is not True:
            problems.append("the opt-out did not turn back off")
        if set_sharing(user, None).get("cohort") is not True:
            problems.append("a request that does not mention it changed the opt-out")
    return problems


@check("a chart's line shows how many players, the clear rate and the expected one, names nobody, and is empty below the minimum of players")
def _line():
    import logging
    from rasmai.bot.state import cohort
    from rasmai.engine.cohort import MIN_COHORT, MIN_PLAYERS_DIFFICULTY

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
        with _scratch(), _charts(_constants(const)) as index:
            keys = [index.get(_key(_stored(name))).key for name in NAMES]
            _store({user: accounts[user] for user in ids[:MIN_COHORT - 1]})
            if any(cohort.observed_line(key) or cohort.difficulty(key) for key in keys):
                problems.append("under the minimum cohort a chart still got a line")
            _store({user: accounts[user] for user in ids[MIN_COHORT - 1:]})
            cohort.reset()
            lines = {key: cohort.observed_line(key) for key in keys}
            rows = {key: cohort.difficulty(key) for key in keys}
            shown = [key for key in keys if rows[key]]
            if not shown:
                problems.append("a full cohort gave no chart a line")
            for key in shown:
                row, line = rows[key], lines[key]
                if set(row) != {"rate", "expected", "players", "lean"} or row["players"] < MIN_PLAYERS_DIFFICULTY or not 0 <= row["rate"] <= 1 or not 0 <= row["expected"] <= 1:
                    problems.append(f"a chart's numbers are {row}")
                if f"of {row['players']} players" not in line or f"{row['rate']:.0%}" not in line or "not hard data" not in line:
                    problems.append(f"a chart's line reads {line!r}")
            if any(lines[key] for key in keys if not rows[key]):
                problems.append("a chart with no numbers still got a line")
            secrets = ids + [user.encode().hex() for user in ids]
            if any(secret in "".join(lines.values()) + str(rows) for secret in secrets):
                problems.append("an account id or tag reached a chart's line")
        if any(secret in "\n".join(seen) for secret in secrets):
            problems.append("an account id or tag was logged")
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
    return problems
