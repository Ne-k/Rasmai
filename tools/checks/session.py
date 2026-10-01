
from tools.checks import ROOT, check


@check("an expired maimai session is flagged until the player links again")
def _expired():
    import tempfile, pathlib
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        from rasmai.storage.db import get_connected_account, mark_session_expired, upsert_connected_account
        problems = []
        upsert_connected_account("u1", "intl", "cookie://abc")
        if get_connected_account("u1")["sessionExpired"]:
            problems.append("a freshly linked account is already flagged")
        mark_session_expired("u1", "2026-09-13T10:00:00")
        if get_connected_account("u1")["sessionExpired"] != "2026-09-13T10:00:00":
            problems.append("the refusal was not recorded")
        mark_session_expired("u1", "2026-09-14T10:00:00")
        if get_connected_account("u1")["sessionExpired"] != "2026-09-13T10:00:00":
            problems.append("a later refusal moved the date; it should keep the first one")
        upsert_connected_account("u1", "intl", "cookie://new")
        if get_connected_account("u1")["sessionExpired"]:
            problems.append("linking again did not clear the flag, so the banner would never go away")
        # not every refusal is a dead cookie: maimai serves the same error page for passing faults,
        # so a read that lands afterwards has to clear the flag without making anyone link again
        from rasmai.storage.db import update_account_snapshot
        mark_session_expired("u1", "2026-09-13T10:00:00")
        update_account_snapshot("u1", {"name": "Nek"}, {"charts": []})
        if get_connected_account("u1")["sessionExpired"]:
            problems.append("a read that succeeded left the account flagged as expired")
        return problems
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False


@check("an account left expired for 30 days is deleted with everything stored for it, and no other")
def _expired_purge():
    import tempfile, pathlib
    from datetime import datetime
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        from rasmai.storage.db import (expired_accounts_due, get_connected_account, get_database_connection,
                                       mark_session_expired, purge_expired_accounts, session_deletes_at,
                                       upsert_connected_account)
        now = datetime(2026, 10, 20, 12, 0, 0)
        problems = []
        for user_id in ("old", "edge", "young", "fine", "relinked"):
            upsert_connected_account(user_id, "intl", f"cookie://{user_id}")
        mark_session_expired("old", "2026-09-16T07:08:00")        # 34 days before `now`
        mark_session_expired("edge", "2026-09-20T12:00:00")       # exactly 30 days
        mark_session_expired("young", "2026-09-30T15:51:00")      # 20 days
        mark_session_expired("relinked", "2026-09-01T00:00:00")
        upsert_connected_account("relinked", "intl", "cookie://again")   # linked again: the flag is cleared
        connection = get_database_connection()
        try:
            with connection:
                for user_id in ("old", "young"):
                    connection.execute("INSERT INTO rating_history (user_id, recorded_at, rating, best50, new_total, "
                                       "old_total, charts, plays) VALUES (?, ?, 13000, 13000, 4000, 9000, 1, 1)",
                                       (user_id, "2026-09-10T00:00:00"))
        finally:
            connection.close()

        if session_deletes_at("2026-09-16T07:08:00") != "2026-10-16T07:08:00":
            problems.append(f"the deletion date is not 30 days on: {session_deletes_at('2026-09-16T07:08:00')}")
        if session_deletes_at(""):
            problems.append("an account that is not expired was given a deletion date")
        due = [row["userId"] for row in expired_accounts_due(now)]
        if due != ["old", "edge"]:
            problems.append(f"due for deletion {due}, expected ['old', 'edge'] oldest first")
        if get_connected_account("old") is None:
            problems.append("listing what is due deleted something; it has to read only")
        gone = purge_expired_accounts(now)
        if sorted(gone) != ["edge", "old"]:
            problems.append(f"deleted {gone}, expected old and edge")
        for user_id in ("old", "edge"):
            if get_connected_account(user_id) is not None:
                problems.append(f"{user_id} was reported deleted but is still linked")
        for user_id in ("young", "fine", "relinked"):
            if get_connected_account(user_id) is None:
                problems.append(f"{user_id} was deleted, but it is not 30 days expired")
        connection = get_database_connection()
        try:
            left = {row["user_id"] for row in connection.execute("SELECT user_id FROM rating_history")}
        finally:
            connection.close()
        if left != {"young"}:
            problems.append(f"rating history left behind after the delete: {sorted(left)}")
        if purge_expired_accounts(now):
            problems.append("a second sweep deleted something again")
        if purge_expired_accounts(now, days=0) or expired_accounts_due(now, days=0):
            problems.append("an allowance of 0 days should keep expired accounts, not delete them")
        return problems
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False


@check("a play-count refresh drops every poster built for that level and nothing else")
def _forget():
    from rasmai.bot.state.cache import CachedAnalysis
    cached = CachedAnalysis(user_id="1", region="intl", analyzer=None, recommendations=[], value_charts=[])   # type: ignore[arg-type]
    cached.analyses = {("balanced", ""): 1, ("balanced", "13+"): 1, ("hard", ""): 1}
    cached.plans = {(None, False, "balanced", "", ""): 1, (None, False, "hard", "", ""): 1}
    cached.images = {"analyze:balanced:": 1, "analyze:balanced:level 13+": 1, "plan:None:False:balanced::": 1,
                     "new:master::balanced:": 1, "session:3:balanced:": 1, "analyze:hard:": 1, "profile:x": 1}
    cached.forget("balanced")
    problems = []
    stale = [k for k in list(cached.analyses) + list(cached.plans) + list(cached.images) if "balanced" in str(k)]
    if stale:
        problems.append(f"still cached after forgetting balanced: {stale}")
    if set(cached.images) != {"analyze:hard:", "profile:x"} or ("hard", "") not in cached.analyses:
        problems.append(f"forgetting balanced took other levels with it: {sorted(cached.images)}")
    return problems


@check("one full read per account, whichever side asked for it")
def _one_read():
    from rasmai.bot.state import reads
    problems = []
    reads.release("u1")
    if reads.claim("u1", reads.DISCORD) is not None:
        problems.append("a free account would not start a read")
    held = reads.claim("u1", reads.WEBSITE)
    if held != reads.DISCORD:
        problems.append(f"the website started a second read while Discord was reading: {held!r}")
    if reads.claim("u1", reads.DISCORD) != reads.DISCORD:
        problems.append("a second Discord read was allowed alongside the first")
    if reads.running("u1") != reads.DISCORD:
        problems.append("the slot does not say who holds it")
    reads.release("u1")
    if reads.running("u1") is not None:
        problems.append("the slot was not given back")
    if reads.claim("u1", reads.WEBSITE) is not None:
        problems.append("the account could not be read again after the slot was released")
    reads.release("u1")
    # one account reading must never block a different one
    reads.claim("u1", reads.DISCORD)
    if reads.claim("u2", reads.WEBSITE) is not None:
        problems.append("one account reading blocked a different account")
    reads.release("u1")
    reads.release("u2")
    return problems


@check("a play page met with a session maimai has closed signs in again rather than failing")
def _stale_session():
    from rasmai.bot.builders.history.lastplay import play_detail
    from rasmai.bot.state.cache import CachedAnalysis
    from rasmai.scraping.scraper import SessionRejected
    import rasmai.bot.builders.history.lastplay as lastplay

    class Analyzer:
        def __init__(self):
            self._official_session = object()      # a session from an earlier read, since closed
            self.recent_songs = []
            self.signed_in = 0
            self.reads = 0

        def fetch_official_player_profile(self, token, region):
            self.signed_in += 1
            self._official_session = object()

        def fetch_playlog_detail(self, idx, region):
            self.reads += 1
            if self.signed_in == 0:
                raise SessionRejected("maimai signed this session out")
            return {"notes": {}, "achievement": 99.0}

    analyzer = Analyzer()
    cached = CachedAnalysis(user_id="1", region="intl", analyzer=analyzer, recommendations=[], value_charts=[])   # type: ignore[arg-type]
    account = {"token": "cookie://x"}
    kept = lastplay.get_connected_account
    lastplay.get_connected_account = lambda user_id: account
    problems = []
    try:
        detail = play_detail(cached, "1,2")
        if not detail:
            problems.append("the retry returned nothing")
        if analyzer.signed_in != 1:
            problems.append(f"signed in {analyzer.signed_in} times, expected exactly one")
        if analyzer.reads != 2:
            problems.append(f"read the page {analyzer.reads} times, expected the failure and the retry")
        analyzer.reads = 0
        play_detail(cached, "1,2")
        if analyzer.reads:
            problems.append("the page was read again instead of being taken from the analysis")
        # a token maimai will not accept is a dead end, not an endless retry
        analyzer.signed_in = 0
        analyzer.fetch_official_player_profile = lambda token, region: (_ for _ in ()).throw(SessionRejected("dead"))
        try:
            play_detail(cached, "3,4")
            problems.append("a dead token should have raised")
        except SessionRejected:
            pass
    except Exception as error:
        problems.append(f"{type(error).__name__}: {error}")
    finally:
        lastplay.get_connected_account = kept
    return problems


@check("a judgement page read once opens from storage, without asking maimai again")
def _stored_judgements():
    import rasmai.web.dashboard.scores as scores
    from rasmai.bot.state.cache import CachedAnalysis

    stored = {"achievement": 98.5, "fast": 3, "late": 9, "combo": 400, "max_combo": 700, "sync": 0, "max_sync": 0,
              "notes": {"tap": {"critical": 10, "perfect": 5, "great": 1, "good": 0, "miss": 0}}}
    asked = []

    class Analyzer:
        recent_songs = []      # the play has scrolled off the fifty maimai still lists

    kept = scores.judgement_for
    scores.judgement_for = lambda user_id, idx: dict(stored) if idx == "kept" else None
    cached = CachedAnalysis(user_id="1", region="intl", analyzer=Analyzer(), recommendations=[], value_charts=[])   # type: ignore[arg-type]
    problems = []
    try:
        import rasmai.bot.builders.history as history
        held = history.play_detail
        history.play_detail = lambda c, idx: asked.append(idx) or dict(stored)
        try:
            page = scores.play_payload(cached, "kept")
            if page is None:
                problems.append("a stored page did not open once the site stopped listing the play")
            elif not page.get("lost"):
                problems.append("a stored page opened without what each note type cost")
            if asked:
                problems.append(f"maimai was asked for a page already stored: {asked}")
            if scores.play_payload(cached, "never") is not None:
                problems.append("a play with nothing stored and nothing listed should not open")
        finally:
            history.play_detail = held
    finally:
        scores.judgement_for = kept
    return problems


@check("the one account can update either chart database by hand, and nobody else can")
def _manual_updates():
    import json as _json

    from rasmai.web.dashboard import admin, routes

    class Answer:
        def __init__(self):
            self.code, self.body = 0, {}

        def _send_json(self, code, body):
            self.code, self.body = code, body

    problems = []
    held_admin, held_route = admin.is_admin, routes.start_update
    asked = []
    routes.start_update = lambda source: asked.append(source) or {"ok": True, "running": True}
    try:
        routes.is_admin = lambda user_id: user_id == "1"
        answer = Answer()
        routes.handle_post(answer, "/internal/me/admin/update", {"id": "1"}, {"source": "simai"})
        if answer.code != 202 or asked != ["simai"]:
            problems.append(f"the one account could not start an update: {answer.code} {answer.body}, asked {asked}")

        asked.clear()
        answer = Answer()
        routes.handle_post(answer, "/internal/me/admin/update", {"id": "2"}, {"source": "simai"})
        if answer.code != 404 or asked:
            problems.append(f"someone else started an update: {answer.code} {answer.body}, asked {asked}")
        if answer.body.get("error") != "not_found":
            problems.append("a refused update says it was refused, which tells the caller the page is there")
    finally:
        routes.start_update = held_route
        routes.is_admin = held_admin

    # only the two databases there are, and one at a time
    if admin.start_update("nonsense").get("ok"):
        problems.append("a database nobody has was updated")
    for source in admin.SOURCES:
        admin._updates[source] = {"running": True}
        if admin.start_update(source).get("ok"):
            problems.append(f"a second {source} update started while the first was still running")
        admin._updates.pop(source, None)

    # and the site is allowed to ask for it
    proxy = (ROOT / "web" / "app" / "api" / "me" / "[...rest]" / "route.ts").read_text(encoding="utf-8")
    if "admin/update" not in proxy:
        problems.append("the site cannot reach the update route, so the buttons do nothing")
    if not _json.dumps(admin.update_state()).startswith("{"):
        problems.append("the developer page cannot be told how the last update went")
    return problems


@check("the skill curve rings the dots a recent play set, and only those")
def _curve_rings_recent_bests():
    import types

    from rasmai.bot.state.snapshots import moved_by_recent
    from rasmai.images import posters
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import SongInfo

    problems = []
    a = MaimaiRatingAnalyzer()
    song = lambda name, acc: SongInfo(name=name, chart_type="dx", difficulty_type="master", accuracy=acc,
                                      rating=300, level="13+", difficulty=13.7)
    beaten, short, idle = song("Beaten", 100.5123), song("Short", 100.4), song("Idle", 99.9)
    a.songs = [beaten, short, idle]
    play = lambda name, acc: {"songName": name, "musicType": "dx", "difficulty": "master",
                              "achievement": int(round(acc * 10000)), "playedAt": "2026-09-28T10:00:00"}
    # a new best, and a play that fell short of the best already held
    a.recent_songs = [play("Beaten", 100.5123), play("Beaten", 99.0), play("Short", 99.2)]
    moved = moved_by_recent(a)
    if moved != [beaten]:
        problems.append(f"ringed {[s.name for s in moved]}; only the chart whose best came from a recent play should be")
    profile = types.SimpleNamespace(consistency=0.5, expected_accuracy=lambda c: 100.0,
                                    comfort_constant=0, reach_constant=0)
    rings = posters._skill_chart_svg(profile, a.songs, moved=moved).count('stroke="#f3efe4"')
    if rings != 1:
        problems.append(f"the curve drew {rings} rings for one recent best")
    return problems


@check("a Discord command that finds the website reading waits and takes that read, not a second one")
def _discord_waits_for_site():
    import asyncio
    import types

    import rasmai.bot.builders.results.loading as loading
    from rasmai.bot.state import cache, reads
    from rasmai.bot.state.cache import CachedAnalysis

    said = []

    async def edit(**fields):
        said.append(fields.get("content") or "")

    interaction = types.SimpleNamespace(user=types.SimpleNamespace(id=9101), edit_original_response=edit)
    fresh_reads = []

    async def fresh(interaction, user_id, force):
        fresh_reads.append(user_id)

    kept = (loading.touch_account, loading._fresh_analysis, reads.WAIT_POLL, reads.WAIT_LIMIT)
    loading.touch_account = lambda user_id: None
    loading._fresh_analysis = fresh
    reads.WAIT_POLL = 0.01
    problems = []
    try:
        async def site_reads():
            await asyncio.sleep(0.05)
            cache.cache_put(CachedAnalysis(user_id="9101", region="intl", analyzer=None, recommendations=[], value_charts=[]))   # type: ignore[arg-type]
            reads.release("9101")

        async def both():
            reads.claim("9101", reads.WEBSITE)
            site = asyncio.ensure_future(site_reads())
            got = await loading.load_analysis(interaction)
            await site
            return got

        got = asyncio.run(both())
        if got is None or got is not cache._analysis_cache.get("9101"):
            problems.append(f"the command did not come back with the website's read: {got!r}; it said {said}")
        if fresh_reads:
            problems.append("the command read the scores again after the website had just read them")
        if len(said) != 1 or "continue" not in said[0]:
            problems.append(f"the command should say once that it will continue, it said {said}")
        if reads.running("9101") is not None:
            problems.append("the read slot was left held")

        # a read that never ends still lets the command go, with the old advice
        said.clear()
        reads.WAIT_LIMIT = 0.05
        cache._analysis_cache.pop("9101", None)
        reads.claim("9101", reads.WEBSITE)
        if asyncio.run(loading.load_analysis(interaction)) is not None or fresh_reads:
            problems.append("a wait that ran out still returned scores or read them")
        if not said or "run this again" not in said[-1]:
            problems.append(f"a wait that ran out did not tell the person to run it again: {said}")
    finally:
        loading.touch_account, loading._fresh_analysis, reads.WAIT_POLL, reads.WAIT_LIMIT = kept
        reads.release("9101")
        cache._analysis_cache.pop("9101", None)
    return problems


@check("a website read pressed while Discord reads waits in the queue and takes that read, not a second one")
def _site_queues_behind_discord():
    import time

    from rasmai.bot.state import cache, reads
    from rasmai.bot.state.cache import CachedAnalysis
    from rasmai.web.dashboard.refresh import RefreshJobs

    jobs = RefreshJobs()
    site_reads = []

    def read(user_id, account, job, tell):
        site_reads.append(user_id)
        with jobs._lock:
            job.update({"running": False, "stage": "done"})

    jobs._read = read
    kept = reads.WAIT_POLL
    reads.WAIT_POLL = 0.01
    problems = []

    def settle():
        for _ in range(200):
            if not jobs.status("9102").get("running"):
                break
            time.sleep(0.01)
        return jobs.status("9102")

    try:
        reads.claim("9102", reads.DISCORD)
        started = jobs.start("9102", {"token": "cookie://x", "region": "intl"})
        time.sleep(0.05)
        waiting = jobs.status("9102")
        for shown in (started, waiting):
            if not shown.get("running") or shown.get("stage") != "queued" or "Discord" not in shown.get("detail", ""):
                problems.append(f"the site was not told it is queued behind Discord: {shown}")
                break
        if jobs.start("9102", {"token": "cookie://x", "region": "intl"}).get("stage") != "queued":
            problems.append("pressing the button again while queued did not return the queued job")
        cache.cache_put(CachedAnalysis(user_id="9102", region="intl", analyzer=None, recommendations=[], value_charts=[]))   # type: ignore[arg-type]
        reads.release("9102")
        done = settle()
        if done.get("stage") != "done" or done.get("running"):
            problems.append(f"the queued job did not finish with the Discord read: {done}")
        if site_reads:
            problems.append("the site read the scores again right after Discord had read them")

        # the Discord read failed and kept nothing: the queued job reads for itself once the slot is free
        cache._analysis_cache.pop("9102", None)
        jobs._jobs.pop("9102", None)
        reads.claim("9102", reads.DISCORD)
        jobs.start("9102", {"token": "cookie://x", "region": "intl"})
        reads.release("9102")
        done = settle()
        if site_reads != ["9102"] or done.get("stage") != "done":
            problems.append(f"after a failed Discord read the queued job did not read once: {site_reads}, {done}")
        if reads.running("9102") is not None:
            problems.append("the read slot was left held")
    finally:
        reads.WAIT_POLL = kept
        reads.release("9102")
        cache._analysis_cache.pop("9102", None)
    return problems


@check("the profile's quick wins, stretch goals and new charts link each chart to its page")
def _profile_lists_link():
    import json

    from rasmai.bot.builders.results import embeds
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import PlayerInfo, SongInfo
    from tools.checks import ROOT

    problems = []
    exports = sorted((ROOT / "debug").glob("*.json"), key=lambda p: p.stat().st_size)
    data = next((d for d in (json.loads(p.read_text(encoding="utf-8")) for p in exports) if d.get("songs")), None)
    if data is None:
        return []      # no export on this machine to build from
    a = MaimaiRatingAnalyzer()
    a.player = PlayerInfo(**{k: v for k, v in data["player"].items() if k in PlayerInfo.__dataclass_fields__})
    a.songs = [SongInfo(**{k: v for k, v in r.items() if k in SongInfo.__dataclass_fields__}) for r in data["songs"]]
    a.generate_recommendations()
    shown = [c for key in ("quickWins", "stretchGoals", "newChartsToTry") for c in (a.analysis_summary or {}).get(key) or []]
    if not shown:
        problems.append("the profile's lists came out empty for a real export")
    lines = [embeds._highlight(c) for c in shown]
    if any("](http" not in line for line in lines):
        problems.append(f"a chart on the profile is not linked to its page: {next(l for l in lines if '](http' not in l)[:80]}")
    if embeds._highlight("Oshama Scramble!") != "Oshama Scramble!":
        problems.append("an analysis made before the lists carried charts no longer shows its titles")
    return problems


@check("a deleted account cannot be read back out of the database file, its backup copy, debug exports or memory")
def _secure_erase():
    import json, sqlite3, tempfile, pathlib
    from rasmai.storage.db import connection as store
    folder = pathlib.Path(tempfile.mkdtemp())
    was, store.DATABASE_PATH = store.DATABASE_PATH, folder / "t.sqlite3"
    store._database_ready = False
    import rasmai.config as config
    kept_exports = config.DEBUG_EXPORT_DIR
    config.DEBUG_EXPORT_DIR = folder / "exports"
    problems = []
    try:
        from rasmai.storage.db import (delete_connected_account, get_connected_account, get_database_connection,
                                       set_user_settings, upsert_connected_account)
        marker = "ERASE-ME-7f3c9a"
        for user_id, name in (("gone", marker), ("stays", "KEEP-ME-18d2")):
            upsert_connected_account(user_id, "intl", f"cookie://{user_id}", official_profile={"name": name * 40})
            set_user_settings(user_id, {"layout": "both", "note": name * 40})
        # the one-off copy a database upgrade leaves beside the file
        source = sqlite3.connect(str(store.DATABASE_PATH))
        copy = sqlite3.connect(str(store.DATABASE_PATH) + ".before-pack")
        source.backup(copy)
        copy.close()
        source.close()
        config.DEBUG_EXPORT_DIR.mkdir(parents=True)
        for user_id in ("gone", "stays"):
            (config.DEBUG_EXPORT_DIR / f"maimai-export-2026-{user_id}.json").write_text(
                json.dumps({"userId": user_id, "player": "x"}, indent=2), encoding="utf-8")

        from rasmai.bot.state import cache, reads
        from rasmai.bot.state.cache import CachedAnalysis
        from rasmai.bot.state.forget import forget_user
        from rasmai.web.dashboard import admin
        cache._analysis_cache["gone"] = CachedAnalysis(user_id="gone", region="intl", analyzer=None,   # type: ignore[arg-type]
                                                       recommendations=[], value_charts=[])
        reads.claim("gone", reads.DISCORD)
        admin._PEOPLE["gone"] = {"name": "Gone"}

        # SQLite as Debian builds it zeroes deleted rows on its own, and as Windows' Python ships it does
        # not: start every connection with it off, so this passes only if the delete turns it on itself
        from rasmai.storage.db import accounts as account_store
        opened = account_store.get_database_connection

        def plain_connection():
            connection = opened()
            connection.execute("PRAGMA secure_delete = OFF")
            return connection

        account_store.get_database_connection = plain_connection
        try:
            delete_connected_account("gone")
        finally:
            account_store.get_database_connection = opened
        forget_user("gone")

        if get_connected_account("gone") is not None or get_connected_account("stays") is None:
            problems.append("the delete took the wrong account")
        get_database_connection().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for path in (store.DATABASE_PATH, pathlib.Path(str(store.DATABASE_PATH) + "-wal"),
                     pathlib.Path(str(store.DATABASE_PATH) + ".before-pack")):
            if path.exists() and marker.encode() in path.read_bytes():
                problems.append(f"the deleted account's text can still be read out of {path.name}")
        if b"KEEP-ME-18d2" not in store.DATABASE_PATH.read_bytes() + pathlib.Path(str(store.DATABASE_PATH) + "-wal").read_bytes():
            problems.append("the account that stays lost its data")
        left = sorted(p.name for p in config.DEBUG_EXPORT_DIR.glob("*.json"))
        if left != ["maimai-export-2026-stays.json"]:
            problems.append(f"debug exports after the delete: {left}, expected only the other account's")
        if "gone" in cache._analysis_cache or reads.running("gone") or "gone" in admin._PEOPLE:
            problems.append("the running bot still holds the deleted account in memory")
    finally:
        config.DEBUG_EXPORT_DIR = kept_exports
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("the owner is warned once, two days before the deletion, and the developer page stops listing what is gone")
def _deletion_warning():
    import tempfile, pathlib
    from datetime import datetime
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    problems = []
    try:
        from rasmai.storage.db import (accounts_to_warn, get_database_connection, mark_deletion_warned,
                                       mark_session_expired, upsert_connected_account)
        now = datetime(2026, 10, 14, 12, 0, 0)
        for user_id in ("soon", "later", "past", "fine"):
            upsert_connected_account(user_id, "intl", f"cookie://{user_id}")
        mark_session_expired("soon", "2026-09-15T13:00:00")     # deleted 15 Oct 13:00, a day and an hour away
        mark_session_expired("later", "2026-09-20T12:00:00")    # six days away
        mark_session_expired("past", "2026-09-10T12:00:00")     # already due: the sweep deletes, nobody is warned
        due = [a["userId"] for a in accounts_to_warn(now)]
        if due != ["soon"]:
            problems.append(f"warned {due}, expected only the account two days or less from deletion")
        mark_deletion_warned("soon", "2026-10-14T12:00:00")
        if accounts_to_warn(now):
            problems.append("an owner already warned would be messaged again")
        upsert_connected_account("soon", "intl", "cookie://again")
        mark_session_expired("soon", "2026-10-20T00:00:00")
        row = get_database_connection().execute(
            "SELECT deletion_warned FROM connected_accounts WHERE user_id = 'soon'").fetchone()
        if row["deletion_warned"]:
            problems.append("linking again kept the old warning, so a later expiry would never be warned about")

        # the developer page, which measures from the real now: an account past its deletion date is not
        # something to fix, nor is its failing read
        from datetime import timedelta
        real = datetime.now()
        connection = get_database_connection()
        with connection:
            connection.execute("UPDATE connected_accounts SET session_expired = ? WHERE user_id = 'past'",
                               ((real - timedelta(days=40)).isoformat(timespec="seconds"),))
            connection.execute("UPDATE connected_accounts SET session_expired = ? WHERE user_id = 'later'",
                               ((real - timedelta(days=10)).isoformat(timespec="seconds"),))
            for user_id in ("past", "later"):
                connection.execute("INSERT OR REPLACE INTO quiet_reads (user_id, read_at, plays_added, error) "
                                   "VALUES (?, '2026-10-14T00:00:00', 0, 'session expired')", (user_id,))
            connection.execute("INSERT OR REPLACE INTO quiet_reads (user_id, read_at, plays_added, error) "
                               "VALUES ('deleted-long-ago', '2026-10-14T00:00:00', 0, 'session expired')")
        from rasmai.web.dashboard import admin
        kept_people = admin.people
        admin.people = lambda ids: {}
        try:
            payload = admin.admin_payload()
        finally:
            admin.people = kept_people
        listed = [e["userId"] for e in payload["expired"]]
        failing = [r["userId"] for r in payload["failingReads"]]
        if "past" in listed:
            problems.append("an account past its deletion date still needs attention on the developer page")
        if "later" not in listed:
            problems.append("an expired account not yet due fell off the developer page")
        if failing:
            problems.append(f"failing reads listed for accounts that are expired or gone: {failing}")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("maimaidx.jp's missing intermediate certificate is supplied, a forged one is refused, and a failed handshake is repaired once")
def _maimai_tls():
    import pathlib
    import tempfile
    from datetime import datetime, timedelta, timezone
    from unittest import mock

    import requests
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    from rasmai.scraping import tls
    from rasmai.scraping.scraper import session as scraper_session

    problems = []
    was = tls.BUNDLE_DIR
    tls.BUNDLE_DIR = pathlib.Path(tempfile.mkdtemp()) / "ca"
    try:
        shipped = tls._shipped()
        if not shipped:
            return ["no intermediate certificate is shipped for maimaidx.jp"]
        now = datetime.now(timezone.utc)
        for path in shipped:
            cert = x509.load_pem_x509_certificate(path.read_bytes())
            if not tls.signed_by_a_trusted_root(cert):
                problems.append(f"{path.name} is not a CA signed directly by a root Python trusts, or has expired: replace it")
            elif cert.not_valid_after_utc - now < timedelta(days=60):
                problems.append(f"{path.name} expires on {cert.not_valid_after_utc:%Y-%m-%d}: replace it")

        bundle = pathlib.Path(tls.verify_for("https://maimaidx.jp/maimai-mobile/"))
        text = bundle.read_text(encoding="ascii")
        if shipped[0].read_text(encoding="ascii").strip() not in text or tls.certifi.where() and "BEGIN CERTIFICATE" not in text:
            problems.append("the bundle for maimai hosts lacks the shipped intermediate or the normal roots")
        if tls.verify_for("https://example.com/") is not True or tls.verify_for("https://discord.com/") is not True:
            problems.append("a host that is not a maimai host did not get ordinary verification")

        # a certificate that names a real root as its issuer but was signed by something else, and one that is not a CA
        root = tls._roots()[0]
        key = ec.generate_private_key(ec.SECP256R1())

        def forged(ca: bool, days: int = 365):
            builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Forged CA")]))
                       .issuer_name(root.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
                       .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
            return builder.sign(key, hashes.SHA256())

        if tls.signed_by_a_trusted_root(forged(True)):
            problems.append("an intermediate that only claims a trusted root as its issuer was accepted")
        if tls.signed_by_a_trusted_root(forged(False)):
            problems.append("a certificate that is not a CA was accepted as an intermediate")

        # the session verifies against the bundle, and a missing-issuer failure on a maimai host is retried once
        calls = []

        def flaky(self, method, url, *args, **kwargs):
            calls.append(kwargs.get("verify"))
            if len(calls) == 1:
                raise requests.exceptions.SSLError("certificate verify failed: unable to get local issuer certificate")
            return "answered"

        with mock.patch.object(requests.Session, "request", flaky), \
                mock.patch.object(scraper_session.PACER, "wait", lambda: None), \
                mock.patch.object(scraper_session, "learn_missing_intermediate", return_value=True) as learn:
            got = scraper_session.PacedSession().get("https://maimaidx.jp/maimai-mobile/")
        if got != "answered" or len(calls) != 2 or learn.call_count != 1 or not str(calls[1]).endswith("bundle.pem"):
            problems.append(f"a missing intermediate was not repaired once and retried: {calls}, learned {learn.call_count}")
        calls.clear()
        with mock.patch.object(requests.Session, "request", flaky), \
                mock.patch.object(scraper_session.PACER, "wait", lambda: None), \
                mock.patch.object(scraper_session, "learn_missing_intermediate", return_value=True) as learn:
            try:
                scraper_session.PacedSession().get("https://example.com/")
                problems.append("a failed handshake on a host that is not a maimai host was retried")
            except requests.exceptions.SSLError:
                if learn.call_count:
                    problems.append("an intermediate was fetched for a host that is not a maimai host")
    finally:
        tls.BUNDLE_DIR = was
    return problems
