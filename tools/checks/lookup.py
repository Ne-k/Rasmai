
from tools.checks import ROOT, check


@check("a version the player's region has not had yet is never suggested to them")
def _version_rollover():
    from rasmai.bot.builders.charts import VERSION_NAMES, version_name
    from rasmai.engine.analysis.charts import ChartIndex, ChartRef
    from rasmai.engine.analysis.rating import version_major

    def chart(version, intl):
        return ChartRef(title=f"v{version}", chart_type="std", difficulty="master", constant=13.0,
                        level="13", notes=800, genre="", artist="", cover="", version=version, intl=intl)

    problems = []
    index = ChartIndex("intl")
    index.current_version = 26                      # the player is on CiRCLE PLUS, as international is
    # the chart database tracks the Japanese game, so the next version's charts appear months early
    if index.playable(chart(27, intl=False)):
        problems.append("a chart from a version international has not had yet should not be suggested")
    if not index.playable(chart(26, intl=False)):
        problems.append("the flag lags on the player's own version, so those charts must still be suggested")
    if not index.playable(chart(27, intl=True)):
        problems.append("once the flag says international has it, a newer chart is suggestable")
    if not index.playable(chart(25, intl=True)):
        problems.append("an older chart that international has should be suggested")
    if index.playable(chart(25, intl=False)):
        problems.append("an older chart international never got should stay hidden")

    # the first three digits are the version, and a PLUS shares its major with the version it extends
    if version_major("270") != 27 or version_major("265") != version_major("260"):
        problems.append("version codes should fold a PLUS into the version it extends")
    for code in ("260", "265", "270"):
        if code not in VERSION_NAMES:
            problems.append(f"version {code} has no name")
    named = version_name({"version": "27000"})
    if named != "MAGiCAL":
        problems.append(f"the newest version should be named, not numbered: {named}")
    return problems


@check("the lookup finds a chart by its artist or its charter, on both the site and the bot")
def _search_by_credit():
    import rasmai.bot.builders.charts.index as charts_index
    from rasmai.bot.builders.charts import search_titles

    problems = []
    # a table of our own, so this proves the same thing on a fresh checkout where the chart
    # database has not been downloaded yet, and proves it the same way every run
    kept = {name: getattr(charts_index, name) for name in
            ("_shared_index", "_titles", "_search", "_search_bones", "_aliases", "_credits")}

    class Stub:
        def values(self):
            return []

    class Chart:
        def __init__(self, title, artist, designer):
            self.title, self.artist, self.designer = title, artist, designer

    # the artist of one is a word inside the other's title, which is what makes the order mean something
    made_up = [Chart("Rotation Study", "Blues", "譜面-100号"),
               Chart("Slow Rotation Blues", "Another Band", "someone else")]

    class Fake(Stub):
        def values(self):
            return made_up

    try:
        charts_index._shared_index = Fake()          # so nothing tries to fetch the real database
        charts_index._titles = [chart.title for chart in made_up]
        charts_index._aliases = {"held": "so the table is not rebuilt mid-check"}
        # the real indexing runs, so dropping a credited field from it fails here too
        charts_index._build_search({}, Fake())

        for typed, what in (("blues", "artist"), ("譜面-100号", "charter")):
            hits = search_titles(typed, limit=5)
            if "Rotation Study" not in hits:
                problems.append(f"searching the {what} {typed!r} did not find the song they are credited on")
        # a name typed in full means that name, above a song that merely contains it in its title
        ranked = search_titles("blues", limit=5)
        if ranked and ranked[0] != "Rotation Study":
            problems.append(f"a credited name typed in full put {ranked[0]!r} first, ahead of what they made")
        # a title still beats a credit: someone typing a song name means the song
        first = (search_titles("Slow Rotation Blues", limit=5) or [""])[0]
        if first != "Slow Rotation Blues":
            problems.append(f"searching an exact title put {first!r} first instead of the song itself")
        # and a name too short to mean one person must not drag half the database in
        if any(len(key) < 4 for key in charts_index._credit_keys("譜面-100号")):
            problems.append("a two or three letter credit key would match almost everything")
    finally:
        for name, value in kept.items():
            setattr(charts_index, name, value)

    # then against the real database, wherever it has been downloaded
    index = charts_index._shared_index
    if index is None or not any(True for _ in index.values()):
        return problems
    from rasmai.web.dashboard.lookup import search_payload
    titles = [chart.title.casefold() for chart in index.values()]

    def credited(field):
        for chart in index.values():
            name = str(getattr(chart, field, "") or "").strip()
            if len(name) >= 5 and name != "-" and not any(name.casefold() in title for title in titles):
                return name
        return ""

    for field, what in (("artist", "artist"), ("designer", "charter")):
        name = credited(field)
        if not name:
            continue
        theirs = {chart.title for chart in index.values() if str(getattr(chart, field, "") or "") == name}
        hits = search_titles(name, limit=20)
        mine = len(theirs & set(hits))
        if not mine:
            problems.append(f"searching the {what} {name!r} found none of the {len(theirs)} songs they are credited on")
        elif mine < min(len(theirs), len(hits)) // 2:
            problems.append(f"searching the {what} {name!r} returned {len(hits)} songs, only {mine} of them theirs")
    name = credited("artist")
    if name and "charters" not in (search_payload(None, name, limit=1) or [{}])[0]:
        problems.append("a search result on the site no longer says who charted the song")
    return problems


@check("a song still behind an unlock is never offered as something to go and play")
def _locked_songs():
    from rasmai.engine.analysis import build_chart_index
    from rasmai.scraping import dxdata

    problems = []
    # the flag has to survive the trip from dxrating, through the stored copy, into the index
    distilled = dxdata.distil({"songs": [{
        "title": "Locked Song", "isLocked": True,
        "sheets": [{"type": "dx", "difficulty": "master", "level": "13", "internalLevelValue": 13.0,
                    "noteCounts": {"tap": 400, "hold": 100, "slide": 80, "touch": 20, "break": 40, "total": 640}}],
    }, {
        "title": "Open Song", "isLocked": False,
        "sheets": [{"type": "dx", "difficulty": "master", "level": "13", "internalLevelValue": 13.0,
                    "noteCounts": {"tap": 400, "hold": 100, "slide": 80, "touch": 20, "break": 40, "total": 640}}],
    }], "versions": []})
    sheets = distilled.get("sheets") or {}
    locked_facts = [key for key, facts in sheets.items() if facts.get("k")]
    if len(locked_facts) != 1 or not locked_facts[0].startswith("lockedsong|"):
        problems.append(f"the locked flag did not survive being stored: {sheets}")

    # the index reads dxrating from the stored copy, so it is handed this one for the moment
    kept = dxdata.cached
    dxdata.cached = lambda: distilled
    try:
        index = build_chart_index({
            "locked song": {"title": "Locked Song", "artist": "x", "dx_lev_mas_i": "13.0", "dx_lev_mas": "13"},
            "open song": {"title": "Open Song", "artist": "x", "dx_lev_mas_i": "13.0", "dx_lev_mas": "13"},
        }, region="intl")
    finally:
        dxdata.cached = kept
    by_title = {chart.title: chart for chart in index.values()}
    if len(by_title) != 2:
        problems.append(f"the two test charts did not both reach the index: {sorted(by_title)}")
    if "Locked Song" in by_title and not by_title["Locked Song"].locked:
        problems.append("a chart dxrating calls locked did not reach the index as locked")
    if "Open Song" in by_title and by_title["Open Song"].locked:
        problems.append("a chart nobody called locked reached the index as locked")

    # and every place that offers a chart the player has not played has to honour it
    for module in ("rasmai/engine/analysis/picks/candidates.py", "rasmai/engine/analysis/unplayed.py",
                   "rasmai/engine/analysis/planning/build.py", "rasmai/bot/builders/charts/pick.py"):
        if "locked" not in (ROOT / module).read_text(encoding="utf-8"):
            problems.append(f"{module} offers unplayed charts without checking whether they are locked")
    return problems


@check("a chart is only offered abroad when both sources agree it left Japan, and the page says where it is")
def _region_gate():
    from rasmai.engine.analysis.charts import ChartIndex, ChartRef
    from rasmai.web.dashboard.lookup import _regions

    def chart(**over):
        base = dict(title="LOSTPHANTASIA", chart_type="dx", difficulty="master", constant=12.9, level="12+",
                    notes=700, genre="", artist="", cover="", version=24)
        base.update(over)
        return ChartRef(**base)

    problems = []
    index = ChartIndex("intl")
    index.current_version = 26
    # the case it was found on: dxrating had it on every cabinet, the chart database had it as Japan
    # only, and dxrating's word alone put it in front of a player who could not play it
    if index.playable(chart(intl=True, intl_known=True, listed_intl=False)):
        problems.append("a chart the database says never left Japan was offered to a player abroad")
    if not index.playable(chart(intl=True, intl_known=True, listed_intl=True)):
        problems.append("a chart both sources say is abroad was withheld")
    # the one place the database's own flag is known to lag: the version the player is on
    if not index.playable(chart(intl=True, intl_known=True, listed_intl=False, version=26)):
        problems.append("a chart of the player's own version was withheld on a flag known to lag there")
    if index.playable(chart(intl=False, intl_known=True, listed_intl=True)):
        problems.append("a chart dxrating says is Japan only was offered to a player abroad")

    # and nothing is withheld from a player on the cabinet the database tracks
    japan = ChartIndex("jp")
    japan.current_version = 27
    if not japan.playable(chart(intl=False, intl_known=True, listed_intl=False)):
        problems.append("a Japanese player was refused a Japanese chart")

    # the lookup spans every region, so it has to say which ones have each chart
    if _regions(chart(intl=True, listed_intl=True, regions="jic")) != ["jp", "intl", "cn"]:
        problems.append("a chart on every cabinet was not said to be")
    if "intl" in _regions(chart(intl=True, listed_intl=False, regions="jic")):
        problems.append("a chart only one source calls international was shown as international")
    if _regions(chart(intl=False, listed_intl=False, regions="jc")) != ["jp", "cn"]:
        problems.append("a Japan and China chart was not said to be one")
    return problems


@check("a song is found by the names people type for it, not only by its own title")
def _search_aliases():
    import pathlib
    import tempfile

    from rasmai.scraping import aliases
    from rasmai.storage.db import connection as store

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    aliases._memo = (0.0, None)      # a table an earlier check loaded from the real database would be served for five minutes
    problems = []
    try:
        # the file's own shape: [title, artist, [spellings]]
        table = aliases.distil({"entries": [["+♂", "someone", ["+boy", "plus male"]],
                                            ["ケロ⑨destiny", "Silver Forest", ["kero destiny"]],
                                            ["no aliases", "x", []],
                                            ["broken"]]})
        if len(table) != 2:
            problems.append(f"the alias file read as {len(table)} songs, expected the two that have any")
        if table.get("+♂") != ["+boy", "plus male"]:
            problems.append(f"a song's other names were not kept under its folded title: {table}")

        # nothing is searched by until it has been stored, and a bad answer leaves what is held alone
        if aliases.aliases_for("+♂"):
            problems.append("aliases were served from an empty database")
        from rasmai.storage.db import source_state_set
        import json as _json
        source_state_set(aliases.SOURCE, payload=_json.dumps(table))
        aliases._memo = (0.0, None)
        if aliases.aliases_for("+♂") != ["+boy", "plus male"]:
            problems.append("a stored alias did not come back for its song")
        if aliases.aliases_for("a song nobody wrote"):
            problems.append("a song with no aliases was given some")

        # the search table has to take them, or storing them changes nothing anyone can see
        source = (ROOT / "rasmai" / "bot" / "builders" / "charts" / "index.py").read_text(encoding="utf-8")
        if "party_aliases.aliases_for" not in source:
            problems.append("the aliases are stored but nothing searches by them")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False
        aliases._memo = (0.0, None)
    return problems


@check("the untitled song, listed with an empty name, finds its chart instead of counting as unknown")
def _untitled_song():
    from rasmai.engine import analysis

    problems = []
    index = analysis.build_chart_index({"untitled": {"title": "　", "artist": "x0o0x_", "dx_lev_mas": "12+", "dx_lev_mas_i": "12.8"}})
    chart = index.get(("", "dx", "master"), "12+")
    if chart is None or chart.constant != 12.8:
        problems.append("a score on the untitled song found no chart, so every restart fetched the whole database again for it")
    if index.get(("", "dx", "expert")) is not None:
        problems.append("an empty title matched a difficulty the untitled song does not have")
    return problems


@check("a chart the player's own song list on maimai DX NET leaves out is never offered to them, only when the list shows unplayed songs too, and only for them")
def _unlisted_charts():
    import copy
    from rasmai.engine.analysis import build_chart_index
    from rasmai.scraping import dxdata
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    problems = []

    def row(title, score, kind="dx"):
        blocks = (f'<div class="music_score_block">{score}</div><div class="music_score_block">1,000 / 1,920</div>' if score else "")
        return (f'<div><img class="music_kind_icon" src="/img/music_{kind}.png"><div class="music_expert_score_back">'
                f'<div class="music_lv_block">12</div><div class="music_name_block">{title}</div>{blocks}</div></div>')
    page = row("Played Song", "99.5000%") + row("Open Song", "") + row("雲外蒼電 -Dreaming Voltage-", "", "dx")
    analyzer = MaimaiRatingAnalyzer()
    listed, unplayed = analyzer._listed_official_charts(page, 2)
    if ("opensong", "dx", "expert") not in listed or ("playedsong", "dx", "expert") not in listed or unplayed != 2:
        problems.append(f"the song list read as {sorted(listed)} with {unplayed} unplayed")
    only_played, none_unplayed = analyzer._listed_official_charts(row("Played Song", "99.5000%"), 2)
    if none_unplayed != 0:
        problems.append("a list of played songs only was counted as showing unplayed ones")

    kept = dxdata.cached
    dxdata.cached = lambda: None
    try:
        held = build_chart_index({
            title.casefold(): {"title": title, "artist": "x", "dx_lev_exp_i": "12.2", "dx_lev_exp": "12"}
            for title in ("Played Song", "Open Song", "Locked Song")
        }, region="intl")
    finally:
        dxdata.cached = kept
    by_title = {chart.title: chart for chart in held.values()}

    def offered(player):
        index = player.chart_index
        return sorted(title for title, chart in by_title.items() if index.playable(chart))
    mine = MaimaiRatingAnalyzer()
    mine._chart_index = copy.copy(held)
    mine.listed_charts = listed
    if offered(mine) != ["Open Song", "Played Song"]:
        problems.append(f"with Locked Song missing from the player's list, {offered(mine)} were offered")
    other = MaimaiRatingAnalyzer()
    other._chart_index = copy.copy(held)
    if offered(other) != ["Locked Song", "Open Song", "Played Song"]:
        problems.append(f"another player's list hid charts from someone without one: {offered(other)}")
    stored = MaimaiRatingAnalyzer()
    stored._chart_index = copy.copy(held)
    stored.stored_unlisted = frozenset(tuple(key.split("|")) for key in mine.chart_index.unlisted_keys())
    if offered(stored) != ["Open Song", "Played Song"]:
        problems.append(f"an analysis rebuilt from the stored copy offered {offered(stored)}")
    # a chart of the version the player is on that Japan's database has not marked as abroad yet: `playable` lets it
    # through for them, so the list has to keep it out too, and the stored copy has to hold it
    import dataclasses
    lagging = dataclasses.replace(by_title["Open Song"], title="Lagging Song", intl=False, listed_intl=False, version=26)
    late = MaimaiRatingAnalyzer()
    late._chart_index = copy.copy(held)
    late._chart_index.add(lagging)
    late._chart_index.current_version = 26
    late.listed_charts = listed
    if late.chart_index.playable(lagging) or "laggingsong|dx|expert" not in late.chart_index.unlisted_keys():
        problems.append("a current-version chart Japan's database lags on was offered, or left out of the stored copy, though the player's list leaves it out")
    # and the other way: a chart the region flags call Japan-only that the player's list shows is theirs to play
    flagged = dataclasses.replace(by_title["Open Song"], title="Flagged Song", intl=False, listed_intl=False, intl_known=True, version=20)
    shown = MaimaiRatingAnalyzer()
    shown._chart_index = copy.copy(held)
    shown._chart_index.add(flagged)
    shown.listed_charts = set(listed) | {("flaggedsong", "dx", "expert")}
    if not shown.chart_index.playable(flagged) or shown.chart_index.also_here_keys() != ["flaggedsong|dx|expert"]:
        problems.append("a chart the player's list shows was kept out by the region flags, or left out of the stored copy")
    unread = MaimaiRatingAnalyzer()
    unread._chart_index = copy.copy(shown._chart_index)
    if unread.chart_index.playable(flagged):
        problems.append("without a list, a chart the region flags rule out was offered")
    unread.stored_also_here = frozenset({("flaggedsong", "dx", "expert")})
    if not unread.chart_index.playable(flagged):
        problems.append("an analysis rebuilt from the stored copy forgot a chart the player's list showed")
    # the saved differences answer every chart the way the whole list did, which is what lets the list go after a read
    swapped = MaimaiRatingAnalyzer()
    swapped._chart_index = copy.copy(shown._chart_index)
    swapped.stored_unlisted = frozenset(tuple(key.split("|")) for key in shown.chart_index.unlisted_keys())
    swapped.stored_also_here = frozenset(tuple(key.split("|")) for key in shown.chart_index.also_here_keys())
    differs = [chart.title for chart in shown.chart_index.values() if swapped.chart_index.playable(chart) != shown.chart_index.playable(chart)]
    if differs:
        problems.append(f"after the list is let go, {differs} answered differently from the saved differences")
    source = (ROOT / "rasmai" / "bot" / "state" / "snapshots.py").read_text(encoding="utf-8")
    if "analyzer.listed_charts = None" not in source:
        problems.append("the whole song list is kept in memory for the cached hour after the differences were saved")
    if '"alsoHere"' not in source or "stored_also_here" not in source:
        problems.append("the charts the list showed beyond the region flags are not kept with the stored copy")
    if '"unlisted"' not in source or "stored_unlisted" not in source:
        problems.append("the locked charts are not kept with the stored copy, so a restart would offer them again")
    return problems
