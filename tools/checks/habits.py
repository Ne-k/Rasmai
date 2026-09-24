
from tools.checks import check


@check("what the chart database says about how someone picks charts")
def _play_habits():
    from rasmai.engine.insights import habits as H
    from rasmai.scraping import dxdata

    class Chart:
        def __init__(self, title, released, notes=700, constant=13.0, difficulty="master"):
            self.title, self.released, self.notes = title, released, notes
            self.constant, self.difficulty, self.chart_type = constant, difficulty, "dx"

    class Index:
        def __init__(self, charts):
            self.charts = charts

        def get(self, key, level=None):
            return self.charts.get(key)

    problems = []
    key = ("old song", "dx", "master")
    index = Index({key: Chart("Old Song", "2020-01-01")})
    plays = [{"songName": "Old Song", "musicType": "dx", "difficulty": "master",
              "playedAt": "2026-01-01 12:00:00"} for _ in range(8)]
    age = H.chart_age(plays, index)
    if round(age.get("medianYears", 0)) != 6:
        problems.append(f"a chart released in 2020 played in 2026 should read about six years old: {age}")
    if age.get("freshShare") != 0.0:
        problems.append(f"none of those plays were on a chart under a year old: {age}")
    if H.chart_age(plays[:3], index):
        problems.append("three plays is not enough to say how someone picks charts")

    # the history is keyed by version name, and those do not sort into the order they came out in:
    # comparing against the wrong end of it reports the re-rate backwards
    stored = {"constants": {"resung|dx|master": {"UNiVERSE": 13.5, "maimaiでらっくす PLUS": 13.0}},
              "versions": [["maimaiでらっくす PLUS", "2020-01-23"], ["UNiVERSE", "2021-09-16"]]}
    kept = dxdata.cached
    dxdata.cached = lambda: stored

    class Song:
        name, chart_type, difficulty_type, accuracy = "Re-sung", "dx", "master", 100.5

    class Pool:
        def __init__(self, keys):
            self.in_pool = set(keys)

    class Best50:
        def __init__(self, keys):
            self.new_pool, self.old_pool = Pool(keys), Pool([])

    try:
        song_key = ("re-sung", "dx", "master")
        moved = H.rerate_effect([Song()], Index({song_key: Chart("Re-sung", "2020-01-23", constant=13.5)}),
                                Best50([song_key]))
        if moved.get("charts") != 1:
            problems.append(f"a re-rated chart in the best 50 should be counted: {moved}")
        if moved.get("rating", 0) <= 0:
            problems.append(f"a constant revised from 13.0 up to 13.5 should have added rating, not taken it: {moved}")
        # a chart nobody re-rated, and one that is re-rated but outside the pools, both count for nothing
        if H.rerate_effect([Song()], Index({song_key: Chart("Re-sung", "2020-01-23", constant=13.5)}), Best50([])):
            problems.append("a chart outside the best 50 changed nothing and should not be counted")
    finally:
        dxdata.cached = kept

    counts = {key: 4}
    struck = H.notes_struck(Index({key: Chart("Old Song", "2020-01-01", notes=700)}), counts)
    if struck.get("notes") != 2800:
        problems.append(f"four clears of a 700-note chart is 2800 notes: {struck}")
    if H.notes_struck(Index({key: Chart("Old Song", "2020-01-01", notes=700)}), {key: -1}):
        problems.append("a chart whose play count is unknown should not be counted as played")
    return problems


@check("the first track of a credit is only called cold when the plays say so")
def _warm_up():
    import random
    from rasmai.engine.insights import habits as H

    class Chart:
        key = ("a song", "dx", "master")
        title, chart_type, difficulty = "A Song", "dx", "master"
        constant, notes, released, locked = 13.0, 700, "2020-01-01", False

    class Index:
        def get(self, key, level=None):
            return Chart() if key == Chart.key else None

    class Profile:
        def chart_expectation(self, key, constant, best):
            return 99.0, 0.8

    def plays(count, first_offset, seed):
        rng = random.Random(seed)
        out = []
        for i in range(count):
            track = 1 if i % 4 == 0 else (i % 4) + 1
            shift = first_offset if track == 1 else 0.0
            out.append({"chart_key": "a song|dx|master", "track": track,
                        "achievement": 99.0 + shift + rng.gauss(0, 0.4)})
        return out

    index, profile, bests = Index(), Profile(), {}
    problems = []

    # too few plays to ask the question at all, however large the gap looks
    if H.warm_up(plays(40, -1.0, 1), index, profile, bests):
        problems.append("40 plays is not enough to say anything about warming up")

    # plays with nothing in them: the answer has to be silence, not a small number dressed up
    quiet = H.warm_up(plays(400, 0.0, 2), index, profile, bests)
    if quiet:
        problems.append(f"plays with no warm-up effect in them still produced one: {quiet}")

    # and a real gap has to come through, the right way round
    cold = H.warm_up(plays(400, -1.2, 3), index, profile, bests)
    if not cold:
        problems.append("a first track a full point under the rest was not noticed")
    else:
        if not cold.get("colder"):
            problems.append(f"a worse first track should read as playing cold: {cold}")
        if cold.get("gap", 0) > -0.5:
            problems.append(f"the gap should be about a point: {cold}")
        if cold.get("p", 1) > H.WARM_UP_P:
            problems.append(f"a gap that was reported should have cleared the bar: {cold}")

    # the other way round too: someone who starts strong and tires
    warm = H.warm_up(plays(400, +1.2, 4), index, profile, bests)
    if warm and warm.get("colder"):
        problems.append(f"a better first track should not read as playing cold: {warm}")
    return problems
