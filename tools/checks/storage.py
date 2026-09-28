from tools.checks import check


def _scratch_database():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    was = store.DATABASE_PATH
    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "storage.sqlite3", False
    return store, was


@check("an account's stored scores are packed, carry the recent plays once, and rows stored before either still read")
def _packed_snapshot():
    import json

    from rasmai.bot.state import snapshots
    from rasmai.storage.db import get_connected_account, upsert_connected_account

    problems = []
    store, was = _scratch_database()
    try:
        plays = [{"songName": "x", "idx": f"1,{n}", "achievement": 1000000 - n} for n in range(50)]
        snapshot = {"name": "k", "fields": list(snapshots.CHART_FIELDS),
                    "charts": [["song %d" % n, "std", "master", 99.5, 280, "13", 13.0, "", "", False, 2000] for n in range(800)],
                    "recentPlays": plays}
        upsert_connected_account("storage-check", "intl", "", {"name": "k"}, snapshot)
        c = store.get_database_connection()
        raw = c.execute("SELECT latest_snapshot FROM connected_accounts WHERE user_id = 'storage-check'").fetchone()[0]
        c.close()
        text = len(json.dumps(snapshot, ensure_ascii=False))
        if not isinstance(raw, bytes) or len(raw) * 3 > text:
            problems.append(f"the snapshot is stored as {type(raw).__name__} of {len(raw)} bytes against {text} of JSON; "
                            f"packed it is about a fifth, and it is most of what an account costs on disk")
        if (get_connected_account("storage-check") or {}).get("latestSnapshot") != snapshot:
            problems.append("a packed snapshot did not read back as it was stored")

        # a row written before packing, with the list under both keys, still reads
        c = store.get_database_connection()
        with c:
            c.execute("UPDATE connected_accounts SET latest_snapshot = ? WHERE user_id = 'storage-check'",
                      (json.dumps({**snapshot, "recent": plays}),))
        c.close()
        if (get_connected_account("storage-check") or {}).get("latestSnapshot", {}).get("recent") != plays:
            problems.append("a snapshot stored as text before packing no longer reads")

        # a quiet read's plays land where a rebuild reads them, once
        fresh = [{"songName": "y", "idx": "2,1", "achievement": 1005000}]
        snapshots.store_recent("storage-check", fresh)
        stored = (get_connected_account("storage-check") or {}).get("latestSnapshot") or {}
        if "recent" in stored:
            problems.append("the recent plays are still stored twice, 35 KB a player for nothing")
        rebuilt = snapshots.analyzer_from_snapshot("storage-check", get_connected_account("storage-check"))
        if rebuilt is None or rebuilt.recent_songs != fresh:
            problems.append("an analysis rebuilt after a quiet read came back with older plays than the read found")
        snapshots.store_recent("storage-check", [])
        if ((get_connected_account("storage-check") or {}).get("latestSnapshot") or {}).get("recentPlays") != fresh:
            problems.append("an empty read, which is a failed one, wiped the stored plays")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("a source's stored payload is packed, and a check that changes nothing leaves it alone")
def _packed_sources():
    from rasmai.storage.db import source_state_get, source_state_set

    problems = []
    store, was = _scratch_database()
    try:
        big = '{"rows":[' + ",".join('{"title":"曲%d","n":%d}' % (n, n) for n in range(3000)) + "]}"
        source_state_set("storage-check", etag="a", payload=big)
        source_state_set("storage-check", etag="b")      # nothing new at the source: only the tag and the time move
        state = source_state_get("storage-check") or {}
        if state.get("payload") != big or state.get("etag") != "b":
            problems.append("a stored payload did not come back as it went in, or lost it when only the tag changed")
        c = store.get_database_connection()
        raw = c.execute("SELECT payload FROM news_state WHERE source = 'storage-check'").fetchone()[0]
        c.close()
        if not isinstance(raw, bytes) or len(raw) * 3 > len(big.encode("utf-8")):
            problems.append(f"a {len(big)}-character payload is stored as {len(raw)} bytes; the chart tables were 3.9 MB as text")
        source_state_set("storage-check-small", payload="{}")
        if (source_state_get("storage-check-small") or {}).get("payload") != "{}":
            problems.append("a small payload did not come back as it went in")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("analyses share one song catalog and one chart index, and each keeps the version it is on")
def _shared_catalog():
    from rasmai.engine import analysis
    from rasmai.scraping.otoge.db import CachedOtogeDB

    problems = []
    one, two = CachedOtogeDB(), CachedOtogeDB()
    if one.songs_data and one.songs_data is not two.songs_data:
        problems.append("each analysis unpickles its own copy of the song catalog, five megabytes a time")
    songs = one.songs_data or {"t": {"title": "t", "lev_mas_i": "13.0", "lev_mas": "13"}}
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    first, second = MaimaiRatingAnalyzer(), MaimaiRatingAnalyzer()
    if first.otoge_db.songs_data and first.chart_index._exact is not second.chart_index._exact:
        problems.append("each analyzer builds its own chart index, six megabytes a time, 500 of them cached")
    a, b = analysis.chart_index_for(songs, "intl"), analysis.chart_index_for(songs, "intl")
    if a._exact is not b._exact:
        problems.append("each analysis builds its own chart index, six megabytes a time, 500 of them cached")
    a.current_version = 99
    if b.current_version == 99 or a.stamp == b.stamp:
        problems.append("one player's version, or the stamp memos are keyed by, reached another player's index")
    if len(analysis.chart_index_for(songs, "jp")) and analysis.chart_index_for(songs, "jp")._exact is a._exact:
        problems.append("the Japanese index is the international one")
    return problems


@check("a jacket refresh keeps the .webp and drops the .png nothing reads beside it")
def _jackets_kept_once():
    import pathlib
    import tempfile

    from rasmai.scraping.otoge.db import CachedOtogeDB

    problems = []
    root = pathlib.Path(tempfile.mkdtemp())
    source = root / "repo" / "maimai" / "jacket"
    source.mkdir(parents=True)
    for name in ("both.png", "both.webp", "only.png"):
        (source / name).write_bytes(b"x")
    (root / "jackets").mkdir()
    (root / "jackets" / "old.png").write_bytes(b"x")
    (root / "jackets" / "old.webp").write_bytes(b"x")
    db = CachedOtogeDB.__new__(CachedOtogeDB)
    db.repo_path, db.jacket_dir = root / "repo", root / "jackets"
    db._keep_jackets()
    kept = sorted(p.name for p in db.jacket_dir.iterdir())
    if kept != ["both.webp", "old.webp", "only.png"]:
        problems.append(f"after a refresh the jackets are {kept}; a .png beside its .webp is never opened, "
                        f"and those were 78 of the folder's 98 MB")
    return problems


@check("packing an old database packs every account and source, merges the two play lists, keeps a copy and shrinks the file")
def _pack_old_rows():
    import json
    import pathlib

    from rasmai.storage.db import get_connected_account, source_state_get
    from rasmai.storage.db.pack import pack

    problems = []
    store, was = _scratch_database()
    try:
        c = store.get_database_connection()
        old, fresh = [{"idx": "1,1"}], [{"idx": "2,2"}]
        rows = [["song %d" % n, "std", "master", 99.5, 280, "13", 13.0, "", "", False, 2000] for n in range(800)]
        with c:
            for n in range(40):
                c.execute("INSERT INTO connected_accounts (user_id, region, token, latest_snapshot, created_at, updated_at) "
                          "VALUES (?, 'intl', '', ?, '', '')",
                          (f"pack-{n}", json.dumps({"charts": rows, "recentPlays": old, "recent": fresh})))
            c.execute("INSERT INTO news_state (source, payload, checked_at) VALUES ('pack', ?, '')", ("x" * 50000,))
        c.close()
        done = pack()
        if done["accounts"] != 40 or done["sources"] != 1:
            problems.append(f"packed {done}, expected all 40 accounts and the one source")
        snapshot = (get_connected_account("pack-3") or {}).get("latestSnapshot") or {}
        if "recent" in snapshot or snapshot.get("recentPlays") != fresh:
            problems.append("the later of the two play lists was not the one kept")
        if (source_state_get("pack") or {}).get("payload") != "x" * 50000:
            problems.append("a packed source payload did not read back")
        if not done["after"] < done["before"] / 2:
            problems.append(f"the file went from {done['before']} to {done['after']} bytes; VACUUM is what gives the space back")
        if not pathlib.Path(str(store.DATABASE_PATH) + ".before-pack").exists():
            problems.append("no copy of the database was kept from before packing")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems
