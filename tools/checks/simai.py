
from tools.checks import ROOT, check


@check("a chart in simai is read the way maimai counts it")
def _simai_parse():
    from rasmai.engine.simai import parse

    problems = []
    # one of each thing the notation can say, at 120 BPM where a {4} comma is half a second:
    # a tap, a hold of one beat, a slide off a star, a break, a touch, and two struck together
    chart = parse("(120){4}1,2h[4:1],3-5[8:1],4b,C,{8}6/7,E")
    counts = chart.counts()
    # the star of a slide is played as a tap, so 1, the star of 3-5, 6 and 7 are four taps
    want = {"tap": 4, "hold": 1, "slide": 1, "touch": 1, "break": 1}
    if counts != want:
        problems.append(f"the sampler chart read as {counts}, expected {want}")
    if len(chart.notes) != 8:
        problems.append(f"the sampler chart has 8 notes, read as {len(chart.notes)}")
    held = [n for n in chart.notes if n.kind == "hold"]
    if held and abs(held[0].duration - 0.5) > 1e-6:
        problems.append(f"a one-beat hold at 120 BPM lasts half a second, read as {held[0].duration}")
    together = [n for n in chart.notes if n.each > 1]
    if len(together) != 2:
        problems.append(f"6/7 is two notes struck together, read as {len(together)}")

    # a slide written through several corners is judged once, so it is one note and not one each
    chained = parse("(120){4}1-4-7[8:1],E").counts()
    if chained != {"tap": 1, "hold": 0, "slide": 1, "touch": 0, "break": 0}:
        problems.append(f"a chained slide read as {chained}, expected one star and one slide")

    # a break mark after the length belongs to the slide, not to the star that fired it
    broken = parse("(120){4}1-5[8:1]b,E").counts()
    if broken != {"tap": 1, "hold": 0, "slide": 0, "touch": 0, "break": 1}:
        problems.append(f"a break slide read as {broken}, expected a plain star and a break slide")

    # a length written as a wait then a travel, which one chart in the game actually uses
    waited = parse("(120){4}1-5[0.375##1.9821],E")
    travel = [n for n in waited.notes if n.kind == "slide"]
    if not travel or abs(travel[0].duration - 1.9821) > 1e-6:
        problems.append(f"a slide that waits before it moves should travel for 1.9821s, read as {travel}")
    return problems


@check("a chart is refused only when the reader could not follow it, and disagreement is recorded")
def _simai_trust():
    from rasmai.engine.simai import parse
    from rasmai.scraping import simai

    good = "(120){4}1,2h[4:1],3-5[8:1],4b,C,{8}6/7,E"
    agrees = {"t": 4, "h": 1, "s": 1, "u": 1, "b": 1, "n": 8, "l": 13.0}
    problems = []
    reading = simai.read_chart(good, agrees)
    if reading is None:
        problems.append("a chart the reader followed from end to end was refused")
    elif reading.get("off") != 0.0:
        problems.append(f"a reading that matches its source was recorded as {reading.get('off')!r} away from it")

    # the counts come from a wiki rather than from the file, so the two differ on a chart now and
    # then. That is worth recording and is not grounds for throwing the reading away.
    apart = simai.read_chart(good, {**agrees, "n": 10})
    if apart is None:
        problems.append("a reading was thrown away because its source counted the chart differently")
    elif abs(float(apart.get("off") or 0) + 0.2) > 1e-6:
        problems.append(f"eight notes against a published ten is -0.2, recorded as {apart.get('off')!r}")

    # what is refused: notation the reader could not follow at all
    if not parse("(120){4}1,~~~,2,E").skipped:
        problems.append("notation the reader does not know went unnoticed")
    if simai.read_chart("(120){4}1,~~~,2,E", agrees) is not None:
        problems.append("a chart holding notation the reader could not follow was used anyway")
    if simai.read_chart("", agrees) is not None:
        problems.append("an empty chart was read as though it held something")
    if parse(good).skipped:
        problems.append("a chart made only of ordinary notation was reported as unreadable")

    held = {"a": {"off": 0.001}, "b": {"off": 0.05}, "c": {"off": -0.3}, "d": {}}
    if simai.disputed(held) != 2:
        problems.append(f"two of those readings sit far from their source, counted {simai.disputed(held)}")

    # a served file sometimes carries the next difficulty after the one that was asked for. Read
    # straight through, the two count as one chart: a 954-note Master read as 1,549 that way.
    from rasmai.engine.simai.parse import sections
    both = "(120){4}1,2,3,4,E&inote_5=(120){4}1,2,E"
    if len(sections(both)) != 2:
        problems.append(f"a file holding two charts was read as {len(sections(both))}")
    if len(parse(both).notes) != 4:
        problems.append(f"reading a two-chart file straight through made {len(parse(both).notes)} notes of the first four")
    four = {"t": 4, "h": 0, "s": 0, "u": 0, "b": 0, "n": 4, "l": 13.0}
    two = {**four, "n": 2}
    for wanted, label in ((four, "four"), (two, "two")):
        picked = simai.read_chart(both, wanted)
        # a zero here is the answer, not a missing one, so it is read with a default rather than "or"
        if picked is None or abs(float(picked.get("off", 1.0))) > 1e-9:
            problems.append(f"the {label}-note chart in a two-chart file was not the one picked")
    return problems


@check("the charts are read for everyone, and the tags they replaced are parked rather than gone")
def _simai_is_the_source():
    import pathlib
    import tempfile

    from rasmai.engine.analysis import ChartRef
    from rasmai.engine.insights.tags import chart_traits
    from rasmai.engine.simai import DEMANDS
    from rasmai.scraping import simai
    from rasmai.storage.db import connection as store
    from rasmai.web.dashboard.beta import FEATURES, set_beta, wants

    problems = []
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        # chart reading is how traits are measured now, so it is nobody's switch to flip
        if "simai" in FEATURES:
            problems.append("chart reading is back in the beta picker, so it is off for anyone who never found it")
        user = "promotion-check-user"
        if wants(user, "simai"):
            problems.append("a switch that no longer exists reported as on")
        if set_beta(user, {"simai": True})["on"].get("simai") is not None:
            problems.append("a feature that is no longer a beta was stored as one anyway")

        chart = ChartRef(title="anything", chart_type="dx", difficulty="master", constant=13.0, level="13",
                         notes=800, genre="", artist="", cover="", version=26, bpm=170.0)
        named = {demand[2] for demand in DEMANDS}
        held = simai.cached
        try:
            # a chart the reader found demanding: its demands have to reach the model with nothing switched on
            # the store keys a row by a string, not by the tuple the index uses
            simai.cached = lambda: ({"anything|dx|master": {"circles": 0.9, "lv": 13.0}}, {"circles": 0.01})
            simai._forget()
            labels = {label for _dimension, label in chart_traits(chart)}
            if not labels & named:
                problems.append("a chart the reader measured gave the model no trait at all")
        finally:
            simai.cached = held
            simai._forget()
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False

    # the tags simai replaced stay in the tree, commented out, so putting them back is uncommenting
    source = (ROOT / "rasmai" / "engine" / "insights" / "tags.py").read_text(encoding="utf-8")
    for call in ("mai_notes.note_traits(row)", "mai_notes.pattern_traits(row)"):
        if call not in source:
            problems.append(f"{call} is gone from tags.py rather than parked, so it cannot be put back")
        elif not any(line.strip().startswith("#") and call in line for line in source.splitlines()):
            problems.append(f"{call} is live again in tags.py, so both sources are naming traits at once")
    if not (ROOT / "rasmai" / "scraping" / "mai_notes.py").exists():
        problems.append("mai_notes.py is gone, and the charts are still measured against its manifest")
    return problems


@check("a chart crawl against a site that has stopped answering gives up instead of going round again")
def _simai_down():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    from rasmai.scraping import simai

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    asked = []

    def dead(chart_id):
        asked.append(chart_id)
        return None

    pending = [(f"song {n}|dx|master", f"id{n}", {"t": 1, "h": 0, "s": 0, "u": 0, "b": 0, "n": 1}) for n in range(50)]
    held_fetch, held_pending, held_pause = simai.fetch_chart, simai._pending, simai.PAUSE
    simai.fetch_chart, simai._pending, simai.PAUSE = dead, lambda known: pending, 0.0
    problems = []
    try:
        out = simai.refresh(40)
        if len(asked) > simai.MISSES:
            problems.append(f"a dead site was asked {len(asked)} times, expected to stop after {simai.MISSES}")
        if out:
            problems.append("a run that read nothing reported work done, so the caller would run it again")
    finally:
        simai.fetch_chart, simai._pending, simai.PAUSE = held_fetch, held_pending, held_pause
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("a weakness that only the charts' own notes can see is found, and only when asked for")
def _simai_model():
    import random

    from rasmai.engine.analysis import ChartIndex, ChartRef, build_play_profile, calculate_rating
    from rasmai.scraping import simai
    from rasmai.storage.models import SongInfo

    # a hundred charts, a third of them walking you round the ring, and a player who drops a point on exactly those.
    # Nothing else marks those charts out, so a trait can only find this by reading the notes.
    measured, index, songs = {}, ChartIndex(), []
    random.seed(5)
    spun = 0
    for n in range(120):
        circles = 0.05 if n % 3 == 0 else 0.0
        spun += bool(circles)
        key = f"chart {n}|dx|master"
        measured[key] = {"circles": circles, "lv": 13.0}
        index.add(ChartRef(title=f"chart {n}", chart_type="dx", difficulty="master", constant=13.0,
                           level="13", notes=700, genre="", artist="", cover="", version=25, bpm=170.0))
        accuracy = round(99.2 - (1.0 if circles else 0.0) + random.uniform(-0.15, 0.15), 4)
        songs.append(SongInfo(name=f"chart {n}", chart_type="dx", difficulty_type="master", accuracy=accuracy,
                              is_new=False, level="13", difficulty=13.0, rating=calculate_rating(13.0, accuracy)))

    held = simai.cached
    simai.cached = lambda: (measured, {"circles": 0.01})
    problems = []
    try:
        on = build_play_profile(songs, [], index, 26)
        found = next((a for a in on.trait_axes if a["label"] == "spinning round the ring"), None)
        if found is None:
            problems.append(f"the weakness planted on {spun} charts was not measured at all")
        elif found["offset"] > -0.3:
            problems.append(f"a point lost on every spin chart came out as {found['offset']:+.2f}, which is not it")
        elif not found["verified"]:
            problems.append(f"a weakness this plain should pass its own gate, got p={found['p']}")
    finally:
        simai.cached = held
    return problems


@check("a chart table kept in an older shape is re-read rather than trusted for good")
def _stale_manifest():
    import json
    import pathlib
    import tempfile

    from rasmai.scraping import mai_notes, simai
    from rasmai.storage.db import connection as store

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    held_fetch = mai_notes.fetch
    problems = []
    try:
        from rasmai.storage.db import source_state_get, source_state_set
        fresh = {"a song|dx|master": {"n": 1, "t": 1, "h": 0, "s": 0, "u": 0, "b": 0, "c": "abc", "l": 13.0}}
        asked = []

        def answer(etag=""):
            # the site only sends a body when it is not asked conditionally, which is the whole point:
            # a stored copy in the wrong shape has to drop its tag or it will be told nothing changed
            asked.append(etag)
            return ("unchanged", None, etag) if etag else ("changed", dict(fresh), "tag-1")

        mai_notes.fetch = answer

        # what a bot running older code left behind: the right charts, without the fields added since
        stale = {key: {f: v for f, v in row.items() if f not in ("c", "l")} for key, row in fresh.items()}
        source_state_set(mai_notes.SOURCE, etag="tag-1",
                         payload=json.dumps(stale, ensure_ascii=False, separators=(",", ":")))
        mai_notes._forget()

        if simai._pending({}):
            problems.append("a chart with no id was queued for reading anyway")
        charts = mai_notes.refresh_charts()
        if not charts or not next(iter(charts.values())).get("c"):
            problems.append("a stored copy in the old shape was handed back instead of being read again")
        if asked and asked[0]:
            problems.append(f"the old copy was re-read conditionally ({asked[0]!r}), so the site would answer 304 and change nothing")
        held = json.loads(source_state_get(mai_notes.SOURCE)["payload"])
        if held.get("v") != mai_notes.FORMAT:
            problems.append(f"the re-read copy was stored without its shape, as {held.get('v')!r}")
        if not simai._pending({}):
            problems.append("nothing was queued for reading even after the chart table came back with ids")
    finally:
        mai_notes.fetch = held_fetch
        mai_notes._forget()
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("a change to what is measured is answered from the charts already held, not another crawl")
def _simai_remeasure():
    import json
    import pathlib
    import tempfile

    from rasmai.engine.simai import features as measures
    from rasmai.scraping import mai_notes, simai, simai_bulk
    from rasmai.storage.db import connection as store

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    held_fetch, held_pause, held_version = simai.fetch_chart, simai.PAUSE, simai.VERSION
    # the clone is the next check's subject, not this one's, and it leaves a cache on disk that a
    # refresh would otherwise pour into this temporary database: thousands of charts nobody asked
    # for here, which is what this was measuring against twelve
    held_bulk, simai_bulk.load = simai_bulk.load, lambda known: 0
    problems = []
    try:
        from rasmai.storage.db import sheets_held, source_state_set
        sheet = "(120){4}1,2h[4:1],3-5[8:1],4b,C,{8}6/7,E"
        rows = {f"song {n}|dx|master": {"t": 4, "h": 1, "s": 1, "u": 1, "b": 1, "n": 8, "l": 13.0, "c": f"id{n}"}
                for n in range(12)}
        source_state_set(mai_notes.SOURCE, etag="x",
                         payload=json.dumps({"v": mai_notes.FORMAT, "rows": rows}, separators=(",", ":")))
        mai_notes._forget()
        simai.fetch_chart = lambda chart_id: sheet
        simai.PAUSE = 0.0
        simai.refresh(12)
        if sheets_held()["charts"] != 12:
            problems.append(f"the notation was not kept: {sheets_held()}")

        # the measures now mean something else, so every reading taken under the old ones is dropped
        simai.VERSION = measures.VERSION + 1
        simai._forget()
        if simai._stored():
            problems.append("readings taken under older measures were kept anyway")
        asked = []
        simai.fetch_chart = lambda chart_id: asked.append(chart_id)
        again = simai.remeasure()
        if asked:
            problems.append(f"the site was asked for {len(asked)} charts it had already given us")
        if again != 12:
            problems.append(f"{again} charts were measured again, expected 12")
        if sum(1 for row in simai._stored().values() if row) != 12:
            problems.append("the charts were measured again but the readings did not come back")
    finally:
        simai.fetch_chart, simai.PAUSE, simai.VERSION = held_fetch, held_pause, held_version
        simai_bulk.load = held_bulk
        simai._forget()
        mai_notes._forget()
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("the charts come out of one clone of the repository, and the site is only asked for the rest")
def _simai_bulk():
    import pathlib
    import tempfile
    import types

    from rasmai.scraping import mai_notes, simai_bulk
    from rasmai.storage.db import connection as store

    # one maidata file carries a whole song: every difficulty under its own &inote_N=
    song = """&title=Test Song[DX]
&wholebpm=120
&cabinet=DX

&inote_2=
(120){4}1,2,3,4,E

&inote_5=
(120){8}1,2,3,4,5,6,7,8,E
"""
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "genre" / "1_test_DX").mkdir(parents=True)
    (root / "genre" / "1_test_DX" / "maidata.txt").write_text(song, encoding="utf-8")
    was_checkout, simai_bulk.CHECKOUT = simai_bulk.CHECKOUT, root
    was_cache, simai_bulk.CACHE = simai_bulk.CACHE, pathlib.Path(tempfile.mkdtemp())
    was_charts, simai_bulk.CHARTS = simai_bulk.CHARTS, simai_bulk.CACHE / "charts.json.gz"
    was_stamp, simai_bulk.STAMP = simai_bulk.STAMP, simai_bulk.CACHE / "taken.json"
    was_update, simai_bulk.update = simai_bulk.update, lambda force=False: 0
    was_discard, simai_bulk.discard = simai_bulk.discard, lambda: None
    was_facts = mai_notes.cached_facts
    was_path, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    problems = []
    try:
        found = dict(simai_bulk.charts())
        if set(found) != {"test song|dx|basic", "test song|dx|master"}:
            problems.append(f"a song's difficulties were not split into charts the manifest could match: {list(found)}")
        if found and "8" not in found.get("test song|dx|master", ""):
            problems.append("the difficulties were read in the wrong order, so a chart carries another's notes")

        # the cache holds every chart the clone had, including ones the manifest does not name yet,
        # so a version that names them later needs no download
        simai_bulk._keep(found, "abc123")
        if set(simai_bulk.cached()) != set(found):
            problems.append("the cache on disk does not hold what the clone did")
        if int(simai_bulk._taken().get("charts") or 0) != len(found):
            problems.append("the cache does not say how much it holds, so an update cannot tell")
        big = {f"song {n}|dx|master": "(120){8}1,2,3,4,5,6,7,8," * 40 for n in range(200)}
        plain = sum(len(key.encode()) + len(body.encode()) for key, body in big.items())
        simai_bulk._keep(big, "abc123")
        packed = simai_bulk.CHARTS.stat().st_size
        if packed > plain / 4:
            problems.append(f"the cache is {packed} bytes for {plain} of notation, so it is barely packed")
        if set(simai_bulk.cached()) != set(big):
            problems.append("the cache did not come back the way it went in")
        simai_bulk._keep(found, "abc123")

        # only the charts the manifest lists are measured, because nothing else can check them
        facts = {"test song|dx|master": {"n": 8, "l": 13.0, "c": "abc"}}
        mai_notes.cached_facts = lambda: types.SimpleNamespace(
            exact=facts, get=lambda key: facts.get("|".join(key)))
        known = {}
        read = simai_bulk.load(known)
        if read != 1 or set(known) != {"test song|dx|master"}:
            problems.append(f"the cache measured {read} charts and held {list(known)}, expected only the listed one")
        if simai_bulk.load(known):
            problems.append("a chart already measured was measured out of the cache a second time")

        # the checkout itself is not kept: what is worth keeping is in the packed cache by then
        source = (ROOT / "rasmai" / "scraping" / "simai_bulk.py").read_text(encoding="utf-8")
        if "finally:" not in source or "discard()" not in source:
            problems.append("the clone is read without being deleted afterwards")

        # git writes its pack files read-only, and a delete that walks away from those leaves the
        # whole clone behind while reporting nothing
        import os as _os
        import stat as _stat
        pretend = pathlib.Path(tempfile.mkdtemp()) / "repo" / ".git" / "objects"
        pretend.mkdir(parents=True)
        locked = pretend / "pack"
        locked.write_bytes(b"x")
        _os.chmod(locked, _stat.S_IREAD)
        simai_bulk.discard, simai_bulk.CHECKOUT = was_discard, pretend.parent.parent
        try:
            simai_bulk.discard()
            if simai_bulk.CHECKOUT.exists():
                problems.append("a checkout with read-only files in it was left on disk")
        finally:
            simai_bulk.discard, simai_bulk.CHECKOUT = (lambda: None), root
            _os.chmod(locked, _stat.S_IWRITE) if locked.exists() else None

        # and what the clone did not have is still left for the site to be asked for
        facts["other song|dx|master"] = {"n": 8, "l": 13.0, "c": "def"}
        simai_bulk.load(known)
        if "other song|dx|master" in known:
            problems.append("a chart the clone does not hold was marked as read")
    finally:
        simai_bulk.CHECKOUT, simai_bulk.update = was_checkout, was_update
        simai_bulk.CACHE, simai_bulk.CHARTS, simai_bulk.STAMP = was_cache, was_charts, was_stamp
        simai_bulk.discard = was_discard
        mai_notes.cached_facts = was_facts
        store.DATABASE_PATH = was_path
        store._database_ready = False
    return problems


@check("a technique is found in the notes themselves: trills, jacks, streams, walks round the ring, delayed slides and fans")
def _techniques():
    from rasmai.engine.simai.parse import parse
    from rasmai.engine.simai.techniques import techniques

    def of(chart):
        return techniques(parse(chart).notes)

    problems = []
    # 1 2 1 2 1 2 1 2 at sixteenths: two places, swapped every note, which is a trill and not a jack
    trill = of("(180){16}1,2,1,2,1,2,1,2,E")
    if trill["trills"] <= 0:
        problems.append("an alternation between two buttons was not read as a trill")
    if trill["jacks"] > 0:
        problems.append("a trill was counted as a jack as well")

    # the same button over and over is a jack, and must not be read as a trill
    jack = of("(180){16}3,3,3,3,3,3,E")
    if jack["jacks"] <= 0:
        problems.append("the same button struck six times over was not read as a jack")
    if jack["trills"] > 0:
        problems.append("a jack was counted as a trill as well")

    # a long even run across the ring is a stream
    run = of("(180){16}1,2,3,4,5,6,7,8,1,2,3,4,E")
    if run["streams"] <= 0:
        problems.append("a long even run across the ring was not read as a stream")

    # pads walked in a row are a touch sweep; buttons are not
    sweep = of("(180){8}A1,A2,A3,A4,E")
    if sweep["touchSweeps"] <= 0:
        problems.append("touch pads walked in sequence were not read as a sweep")
    if of("(180){8}1,2,3,4,E")["touchSweeps"] > 0:
        problems.append("ring buttons were counted as a touch sweep")

    # slow, spread-out notes are none of these
    quiet = of("(90){1}1,2,1,2,E")
    if any(quiet.get(k, 0) for k in ("trills", "jacks", "streams", "touchSweeps")):
        problems.append(f"notes a second apart were read as a technique: {quiet}")

    # a slide picking up where the last ended is one stroke continued
    chain = of("(120){4}1-3[4:1],3-5[4:1],5-7[4:1],E")
    if chain["chainedSlides"] <= 0:
        problems.append("slides carrying on from one another were not read as chained")
    if of("(120){4}1-3[4:1],,,6-8[4:1],E")["chainedSlides"] > 0:
        problems.append("two unrelated slides were read as chained")

    # a run that never turns back is a stream going round the ring, not a trill
    circle = of("(180){8}1,2,3,4,5,6,7,8,E")
    if circle["circles"] <= 0:
        problems.append("notes stepping round the ring were not read as a walk round it")
    if circle["trills"] > 0:
        problems.append("a walk round the ring was counted as a trill")
    if of("(180){16}1,3,2,4,3,5,4,6,E")["circles"] > 0:
        problems.append("a trill that wanders was counted as a walk round the ring")
    if of("(180){8}1,4,7,2,5,8,E")["circles"] > 0:
        problems.append("notes thrown a third of the way round each time were read as walking it")

    # the two trills that are named apart from each other: on the spot, and across the machine
    if of("(180){16}1,2,1,2,1,2,1,2,E")["stationaryTrills"] <= 0:
        problems.append("a trill between two neighbours was not read as one on the spot")
    across = of("(180){16}1,5,1,5,1,5,1,5,E")
    if across["scatterTrills"] <= 0:
        problems.append("a trill between opposite sides was not read as one across the screen")
    if across["stationaryTrills"] > 0:
        problems.append("a trill across the screen was counted as one on the spot as well")

    # one hand pinned to a button while the other moves about
    axis = of("(180){16}1,3,1,4,1,5,1,6,E")
    if axis["axisTrills"] <= 0:
        problems.append("a trill against a held button was not read as one")
    if of("(180){16}1,2,1,2,1,2,1,2,E")["axisTrills"] > 0:
        problems.append("a trill between two buttons was read as one against a held button")

    # a star struck, notes played over the top of it, and only then the slide setting off
    if of("(120){4}1-5[2##1.5],2,3,4,E")["delayedSlides"] <= 0:
        problems.append("a slide held back while other notes were played was not read as delayed")
    if of("(120){4}1-5[4:1],,,,E")["delayedSlides"] > 0:
        problems.append("a slide with nothing played over it was read as delayed")

    # slides fired one after another from the same button, which is the hand going back to a spot
    if of("(120){4}1-3[4:1],1-4[4:1],1-5[4:1],E")["repeatedHeads"] <= 0:
        problems.append("three slides fired from one button were not read as repeated heads")
    if of("(120){4}1-3[4:1],2-4[4:1],3-5[4:1],E")["repeatedHeads"] > 0:
        problems.append("slides each starting somewhere new were read as repeated heads")

    # a slide followed straight back the way it came, while the first is still travelling
    if of("(120){4}1-5[4:1],5-1[4:1],E")["returnSlides"] <= 0:
        problems.append("a slide traced back the way it came was not read as a return")
    if of("(120){4}1>5[4:1],5>1[4:1],E")["returnSlides"] > 0:
        problems.append("two slides carrying on the same way round were read as a return")

    # the fan slide is written as one letter and is counted as itself, not as a spin
    if of("(120){4}1w5[4:1],E")["wifiSlides"] <= 0:
        problems.append("the fan slide was not read as one")
    if of("(120){4}1-5[4:1],E")["wifiSlides"] > 0:
        problems.append("a straight slide was read as a fan")

    # a trill while a slide from earlier is still travelling is one hand on its own
    over = of("(120){4}1-5[1:1],{16}3,4,3,4,3,4,3,4,E")
    if over["trillsOverSlides"] <= 0:
        problems.append("a trill played while a slide was still travelling was not read as one")
    if of("(120){16}3,4,3,4,3,4,3,4,E")["trillsOverSlides"] > 0:
        problems.append("a trill with both hands free was read as one played over a slide")

    # two looping slides on screen at once is where the arms cross; one after the other is not
    if of("(120){4}1p5[1:2],2q6[1:2],E")["crossedLoops"] <= 0:
        problems.append("two looping slides overlapping were not read as crossed")
    if of("(120){1}1p5[4:1],,,,2q6[4:1],E")["crossedLoops"] > 0:
        problems.append("two loops one after the other were read as crossed")
    if of("(120){4}1-5[1:2],2-6[1:2],E")["crossedLoops"] > 0:
        problems.append("two straight slides were read as loops")

    # and two slides travelling at once at very different speeds
    if of("(120){4}1-5[1:4],2-6[8:1],E")["mixedSpeedSlides"] <= 0:
        problems.append("two slides travelling at once at different speeds were not read as one")
    if of("(120){4}1-5[1:4],2-6[1:4],E")["mixedSpeedSlides"] > 0:
        problems.append("two slides travelling at the same speed were read as mismatched")

    # a technique is a share of the chart, so it cannot exceed it
    for key, value in trill.items():
        if not 0.0 <= value <= 1.0:
            problems.append(f"{key} came out at {value}, which is not a share of anything")
    return problems


@check("a trait only a tenth of charts have is still named, rather than falling off the bottom of a quartile")
def _rare_demand():
    from rasmai.engine.simai.features import CUT, DEMANDS, HARD, thresholds, traits

    # a hundred charts, ten of which have the thing: the quartile of that is zero, and a measure
    # judged against a level of zero is never named at all. That is what the fixed bar is for.
    problems = []
    rare = [(key, label, fixed) for key, _d, label, fixed in DEMANDS if fixed]
    for key, label, fixed in rare:
        rows = [{key: fixed if n < 10 else 0.0, "lv": 13.0} for n in range(100)]
        named = [name for _, name in traits(rows[0], thresholds(rows))]
        if label not in named:
            problems.append(f"{key} has a bar of its own and still went unnamed on a chart carrying it: {named}")
    if not any(key == "scatterTrills" for key, _, _f in rare):
        problems.append("scatter trills are on a tenth of charts, so a quartile of them is zero: they need a bar of their own")

    # and a measure most charts do have is left to the quartile, which must still refuse the bottom
    common = [{"quickSlides": n / 100, "lv": 13.0} for n in range(100)]
    levels = thresholds(common)
    if "fast slides" not in [name for _, name in traits(common[-1], levels)]:
        problems.append("the chart highest of all on a measure was not named for it")
    if "fast slides" in [name for _, name in traits(common[0], levels)]:
        problems.append("the chart lowest of all on a measure was named for it anyway")
    cut = thresholds([{"peak": float(n), "lv": 13.0} for n in range(100)]).get("peak") or 0.0
    if not 70 <= cut <= 80:
        problems.append(f"the top quarter of a hundred evenly spread charts starts at {cut}, not near {CUT * 100:.0f}")
    if HARD < 10:
        problems.append("the quartile is being taken over charts easier than the model is meant for")
    return problems


@check("a chart read from the notes is found even when maimai spaces its title differently")
def _simai_loose_title():
    from rasmai.scraping import simai

    # maimai writes a title with its own spacing and width; the sites that catalogue it do not.
    # Matching those exactly reached 62% of what a player has played, the looser match 95%.
    rows = {"o.n.e.　-in the name of love-|dx|master": {"trills": 0.9, "lv": 13.0}}
    levels = {"trills": 0.1}
    held = simai.cached
    simai.cached = lambda: (rows, levels)
    simai._loose = (None, {})
    problems = []
    try:
        if not simai.chart_traits(("o.n.e.　-in the name of love-", "dx", "master")):
            problems.append("a chart was not found under the very title it is stored as")
        if not simai.chart_traits(("O.N.E. -in the name of love-", "dx", "master")):
            problems.append("a chart was not found when the title was spaced the way maimai spaces it")
        if simai.chart_traits(("something else entirely", "dx", "master")):
            problems.append("a chart that is not held was matched to one that is")
        if simai.chart_traits(("o.n.e.　-in the name of love-", "std", "master")):
            problems.append("the loose match ignored the chart type, so a standard chart took a DX reading")
        if simai.chart_traits(("o.n.e.　-in the name of love-", "dx", "expert")):
            problems.append("the loose match ignored the difficulty, so one chart took another's reading")
    finally:
        simai.cached = held
        simai._loose = (None, {})
    return problems
