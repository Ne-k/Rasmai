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


@check("an account's avatar is kept as bytes beside its profile, reads back as it was, and only a new one replaces it")
def _avatar_column():
    import base64
    import json

    from rasmai.storage.db import get_connected_account, update_account_snapshot, upsert_connected_account
    from rasmai.storage.db.pack import pack

    problems = []
    store, was = _scratch_database()
    try:
        png, other = bytes(range(256)) * 24, b"\x89PNG second picture"
        encoded = base64.b64encode(png).decode("ascii")
        given = {"name": "k", "rating": 15000, "avatar_base64": encoded}
        upsert_connected_account("avatar-check", "intl", "", given, {"charts": []})
        if given.get("avatar_base64") != encoded:
            problems.append("storing a profile took the avatar out of the caller's own dict")
        c = store.get_database_connection()
        row = c.execute("SELECT official_profile, avatar, json_extract(official_profile, '$.name') AS name "
                        "FROM connected_accounts WHERE user_id = 'avatar-check'").fetchone()
        c.close()
        if "avatar_base64" in json.loads(row["official_profile"]) or row["avatar"] != png:
            problems.append("the avatar is still base64 inside the profile's JSON, 8 KB an account, rather than bytes in its column")
        if row["name"] != "k":
            problems.append("the dashboard's SQL can no longer read the name out of the stored profile")
        if ((get_connected_account("avatar-check") or {}).get("officialProfile") or {}).get("avatar_base64") != encoded:
            problems.append("the avatar did not read back as the same base64 it was stored as")

        update_account_snapshot("avatar-check", None, {"charts": [1]})
        update_account_snapshot("avatar-check", {"name": "k", "rating": 15001}, None)
        update_account_snapshot("avatar-check", {"name": "k", "rating": 15002, "avatar_base64": ""}, None)
        upsert_connected_account("avatar-check", "intl", "", {"name": "k"})
        profile = (get_connected_account("avatar-check") or {}).get("officialProfile") or {}
        if profile.get("avatar_base64") != encoded:
            problems.append("a profile saved without a picture, or none saved at all, wiped the avatar already held")
        update_account_snapshot("avatar-check", {"name": "k", "avatar_base64": base64.b64encode(other).decode("ascii")}, None)
        profile = (get_connected_account("avatar-check") or {}).get("officialProfile") or {}
        if profile.get("avatar_base64") != base64.b64encode(other).decode("ascii"):
            problems.append("a new avatar did not replace the old one")

        lean = get_connected_account("avatar-check", with_snapshot=False) or {}
        if "latestSnapshot" in lean or not (lean.get("officialProfile") or {}).get("avatar_base64"):
            problems.append("with_snapshot=False still read the stored scores, or lost the profile with them")
        if (get_connected_account("avatar-check") or {}).get("latestSnapshot") != {"charts": [1]}:
            problems.append("the stored scores no longer read by default")

        # a row stored before the column existed: pack moves its avatar out, and it reads the same either side
        c = store.get_database_connection()
        with c:
            c.execute("UPDATE connected_accounts SET avatar = NULL, official_profile = ? WHERE user_id = 'avatar-check'",
                      (json.dumps({"name": "old", "avatar_base64": encoded}),))
        c.close()
        if ((get_connected_account("avatar-check") or {}).get("officialProfile") or {}).get("avatar_base64") != encoded:
            problems.append("a profile stored before the avatar column no longer reads its avatar")
        done = pack()
        c = store.get_database_connection()
        row = c.execute("SELECT official_profile, avatar FROM connected_accounts WHERE user_id = 'avatar-check'").fetchone()
        c.close()
        if done.get("avatars") != 1 or row["avatar"] != png or "avatar_base64" in json.loads(row["official_profile"]):
            problems.append(f"packing did not move the old row's avatar into its column ({done.get('avatars')} moved)")
        if ((get_connected_account("avatar-check") or {}).get("officialProfile") or {}).get("avatar_base64") != encoded:
            problems.append("a packed avatar did not read back as it was")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("unlinking an account leaves no row with that person's id in any table")
def _unlink_everything():
    from rasmai.storage.db import delete_connected_account, set_beta_feedback, upsert_connected_account

    problems = []
    store, was = _scratch_database()
    try:
        upsert_connected_account("gone", "intl", "", {"name": "k"}, {"charts": []})
        set_beta_feedback("gone", "patterns", "better", "fine")
        c = store.get_database_connection()
        tables = [name for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                  if any(col[1] == "user_id" for col in c.execute(f"PRAGMA table_info({name})").fetchall())]
        with c:
            for table in tables:
                # one row in every table keyed by a person, whatever else it needs; SQLite takes text for any type
                columns = c.execute(f"PRAGMA table_info({table})").fetchall()
                values = {col[1]: "gone" if col[1] == "user_id" else "x" for col in columns
                          if col[1] == "user_id" or (col[3] and col[4] is None) or col[5]}
                c.execute(f"INSERT OR IGNORE INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                          tuple(values.values()))
        c.close()
        delete_connected_account("gone")
        c = store.get_database_connection()
        left = [t for t in tables if c.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id = 'gone'").fetchone()[0]]
        c.close()
        if left:
            problems.append(f"after unlinking, rows for that person are still in {', '.join(left)}")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("a server that removes the bot has its settings forgotten")
def _guild_left():
    import asyncio
    import types

    from rasmai.bot.core import bot
    from rasmai.storage.db import get_guild_settings, set_guild_settings

    problems = []
    store, was = _scratch_database()
    try:
        set_guild_settings("1234", {"leaderboard": False})
        set_guild_settings("5678", {"leaderboard": False})
        handler = getattr(bot, "on_guild_remove", None)
        if handler is None:
            problems.append("the bot has no on_guild_remove, so a server that removed it keeps its settings for good")
        else:
            asyncio.run(handler(types.SimpleNamespace(id=1234, name="left")))
            if get_guild_settings("1234") or not get_guild_settings("5678"):
                problems.append("leaving a server did not clear its settings, or cleared another server's")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("debug exports keep the newest forty and drop the rest")
def _exports_rotate():
    import pathlib
    import tempfile

    from rasmai.util import export_debug_payload

    problems = []
    folder = pathlib.Path(tempfile.mkdtemp())
    for n in range(45):
        (folder / f"maimai-export-20200101-000000-{n:06d}.json").write_text("{}", encoding="utf-8")
    (folder / "something-else.json").write_text("{}", encoding="utf-8")
    written = export_debug_payload({"x": 1}, folder)
    kept = sorted(p.name for p in folder.glob("maimai-export-*.json"))
    if len(kept) != 40 or written.name not in kept or "maimai-export-20200101-000000-000005.json" in kept:
        problems.append(f"{len(kept)} exports after writing one to a folder of 45; the newest forty should stay")
    if not (folder / "something-else.json").exists():
        problems.append("rotating the exports deleted a file that was not one")
    return problems


@check("fetching the chart database gives up on a git that hangs instead of holding the lock for good")
def _clone_timeout():
    import pathlib
    import subprocess
    import tempfile

    from rasmai.scraping.otoge import db as otoge

    problems = []
    seen = []

    def hang(args, **kwargs):
        seen.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout") or 0)

    def fine(args, **kwargs):
        seen.append(kwargs.get("timeout"))

    instance = otoge.CachedOtogeDB.__new__(otoge.CachedOtogeDB)
    instance.repo_path = pathlib.Path(tempfile.mkdtemp()) / "repo"
    real = otoge.subprocess.run
    try:
        otoge.subprocess.run = fine
        instance._clone_or_update_repo()
        otoge.subprocess.run = hang
        if instance._clone_or_update_repo() is not False:
            problems.append("a git that timed out did not count as a failed fetch")
    finally:
        otoge.subprocess.run = real
    if seen[:2] != [300, 120]:
        problems.append(f"the clone and sparse-checkout ran with timeouts {seen[:2]}; without one a stalled GitHub holds every analysis")
    return problems


@check("a play is measured against the bests stored before it in real time, whatever offset each stamp was written with")
def _play_order_by_moment():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    from rasmai.storage.db import history, scores

    problems = []
    was = store.DATABASE_PATH
    try:
        store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "o.sqlite3", False
        chart = "song|dx|master"
        # a read stamped 06:06 at -04:00 is 10:06 UTC; it already holds the 98.5 set by the 11:52 +09:00 play
        # (02:52 UTC, hours earlier), which on the clock faces alone sorts after it
        scores.record_chart_scores("u", [
            (chart, "2026-09-29T20:00:00+09:00", 97.0, 900, "", "", "play", 1000, 1),       # an earlier play: 97.0
            (chart, "2026-09-30T11:52:00+09:00", 98.5, 950, "", "", "play", 1000, 1),       # the play that set 98.5
            (chart, "2026-09-30T06:06:40-04:00", 98.5, 950, "", "", "best"),                # the read that afterwards saw it
            (chart, "2026-09-30T23:30:00+09:00", 98.5, 950, "", "", "play", 1000, 2),       # a later play that only ties it
        ])
        marked = {p["played_at"]: p["achievement"] > p["best_before"] + 0.00005 for p in history.load_play_history("u")}
        if marked.get("2026-09-30T11:52:00+09:00") is not True:
            problems.append("the play that set the best was not marked a new best: the read made after it was counted as older")
        if marked.get("2026-09-30T23:30:00+09:00") is not False:
            problems.append("a play that only tied a stored best was marked a new best")
        if marked.get("2026-09-29T20:00:00+09:00") is not True:
            problems.append("the first play on the chart was not a new best")
        ordered = [row["played_at"] for row in scores.load_chart_scores("u", [chart])]
        if ordered != ["2026-09-29T20:00:00+09:00", "2026-09-30T11:52:00+09:00", "2026-09-30T06:06:40-04:00", "2026-09-30T23:30:00+09:00"]:
            problems.append(f"a chart's scores are not in the order they happened: {ordered}")
        recorded = {p["played_at"]: p["best_before"] for p in scores.load_recorded_plays("u")}
        if recorded.get("2026-09-30T11:52:00+09:00") != 97.0:
            problems.append(f"the model's self-check saw best {recorded.get('2026-09-30T11:52:00+09:00')} before the play, not 97.0")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems
