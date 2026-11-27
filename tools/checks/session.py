
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


@check("after a command, someone whose maimai sign-in is refused is told privately to link again, with a link, at most once an hour, and not after /login or when the sign-in works")
def _relink_reminder():
    import asyncio, tempfile, pathlib, types

    import discord
    from rasmai.bot import core
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        from rasmai.storage.db import mark_session_expired, upsert_connected_account
        problems = []
        upsert_connected_account("111", "intl", "cookie://abc")
        upsert_connected_account("222", "intl", "cookie://def")
        mark_session_expired("111")

        def ran(user_id, name, fails=False):
            sent = []

            class Followup:
                async def send(self, text, **options):
                    if fails:
                        raise discord.HTTPException(types.SimpleNamespace(status=404, reason="nope"), "never answered")
                    sent.append((text, options))
            interaction = types.SimpleNamespace(user=types.SimpleNamespace(id=user_id), followup=Followup())
            asyncio.run(core.on_app_command_completion(interaction, types.SimpleNamespace(qualified_name=name)))
            return sent
        from rasmai.storage import db
        kept_account, unpacked = db.get_connected_account, []

        def account(user_id, with_snapshot=True):
            unpacked.append(with_snapshot)
            return kept_account(user_id, with_snapshot)
        db.get_connected_account = account
        try:
            told = ran("111", "best50")
        finally:
            db.get_connected_account = kept_account
        if any(unpacked) or not unpacked:
            problems.append(f"the reminder read the account with its stored scores ({unpacked}), after every command")
        if len(told) != 1:
            problems.append(f"someone who needs to link again was told {told} after a command")
        else:
            text, options = told[0]
            buttons = [item for item in options["view"].children if getattr(item, "url", None)] if options.get("view") else []
            if options.get("ephemeral") is not True or "needs to be relinked" not in text or "can't fetch anything new" not in text \
                    or not buttons or not buttons[0].url.endswith("/me/#relink"):
                problems.append(f"the reminder was {text!r} with {options}")
        # once an hour at most
        if ran("111", "best50"):
            problems.append("the reminder came twice within the hour")
        core._relink_told["111"] -= core.RELINK_EVERY
        if len(ran("111", "best50")) != 1:
            problems.append("the reminder did not come back after an hour")
        core._relink_told.clear()
        if ran("111", "login") or ran("222", "best50"):
            problems.append("the reminder came after /login, or for someone whose sign-in works")
        try:
            core._relink_told.clear()
            ran("111", "best50", fails=True)
            if "111" in core._relink_told:
                problems.append("a reminder that could not be sent counted as sent, so the next hour gets none")
        except Exception as error:
            problems.append(f"a command that never answered made the reminder fail: {error!r}")
        return problems
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False


@check("a command that meets a refused login says so once: the relink message with its button, as the note on the last read or as the reply itself, and no reminder after it")
def _relink_once():
    import asyncio, tempfile, pathlib, types

    from rasmai.bot import core
    from rasmai.bot.builders.results import stored, view
    from rasmai.scraping.scraper import SessionRejected
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    kept = stored._analysis_from_store
    problems = []
    try:
        from rasmai.storage.db import get_connected_account, mark_session_expired, upsert_connected_account
        upsert_connected_account("555", "intl", "cookie://abc")
        mark_session_expired("555")

        def interaction():
            sent = []

            class Followup:
                async def send(self, text, **options):
                    sent.append((text, options))
            return types.SimpleNamespace(user=types.SimpleNamespace(id=555), followup=Followup()), sent

        async def from_store(user_id, account):
            return "the last read"
        stored._analysis_from_store = from_store
        # results from the last read: the note under them is the relink message
        core._relink_told.clear()
        first, sent = interaction()
        got = asyncio.run(stored._stale_analysis(first, "555", get_connected_account("555", False), SessionRejected("refused")))
        asyncio.run(core.on_app_command_completion(first, types.SimpleNamespace(qualified_name="analyze")))
        buttons = [item for item in sent[0][1]["view"].children if getattr(item, "url", None)] if sent and sent[0][1].get("view") else []
        if got != "the last read" or len(sent) != 1 or "needs to be relinked" not in sent[0][0] or "last read" not in sent[0][0] or not buttons \
                or "refused" in sent[0][0]:
            problems.append(f"a command shown the last read sent {[text for text, _ in sent]}")
        # another failure says what it was, with no relink message
        core._relink_told.clear()
        other, sent = interaction()
        asyncio.run(stored._stale_analysis(other, "555", get_connected_account("555", False), TimeoutError()))
        if len(sent) != 1 or "needs to be relinked" in sent[0][0] or "/refresh" not in sent[0][0] or core._relink_told:
            problems.append(f"a read that timed out sent {[text for text, _ in sent]}")
        # nothing stored to show: the reply is the relink message, and nothing follows
        core._relink_told.clear()
        bare, sent = interaction()
        reply = asyncio.run(view.failure_reply(bare, "Something went wrong while analyzing your account.", SessionRejected("refused")))
        asyncio.run(core.on_app_command_completion(bare, types.SimpleNamespace(qualified_name="analyze")))
        if "needs to be relinked" not in reply["content"] or reply["view"] is None or sent:
            problems.append(f"a command with nothing to show replied {reply['content']!r} and then sent {sent}")
        plain = asyncio.run(view.failure_reply(bare, "Couldn't look that up.", ValueError("bad page")))
        if not plain["content"].startswith("Couldn't look that up.") or plain["view"] is not None:
            problems.append(f"another failure replied {plain}")
    finally:
        stored._analysis_from_store = kept
        core._relink_told.clear()
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


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
        # "old" is also a developer: the application is other people's way in, and outlives a maimai sign-in left to lapse
        connection = get_database_connection()
        try:
            with connection:
                connection.execute("INSERT INTO oauth_apps (id, user_id, name, created_at) VALUES ('app-of-old', 'old', 'Old app', '2026-09-01T00:00:00')")
        finally:
            connection.close()
        gone = purge_expired_accounts(now)
        if sorted(gone) != ["edge", "old"]:
            problems.append(f"deleted {gone}, expected old and edge")
        from rasmai.storage.db import delete_connected_account
        connection = get_database_connection()
        try:
            kept_apps = [row[0] for row in connection.execute("SELECT id FROM oauth_apps WHERE user_id = 'old'")]
        finally:
            connection.close()
        from rasmai.storage.db import account_exists
        if not account_exists("old") or account_exists("edge"):
            problems.append("a developer whose sign-in was deleted no longer counts as an account, so they could never link maimai again")
        if kept_apps != ["app-of-old"]:
            problems.append(f"an expired sign-in's deletion took its developer's applications with it: {kept_apps}")
        delete_connected_account("old")
        connection = get_database_connection()
        try:
            if connection.execute("SELECT 1 FROM oauth_apps WHERE user_id = 'old'").fetchone():
                problems.append("deleting an account outright left its applications behind")
        finally:
            connection.close()
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


@check("while maimai DX NET is down nobody is warned or deleted, and the hours it was down are added to the deadline of that region's accounts only; scheduled maintenance holds the sweep without moving any deadline, and a failed postpone does not stop the hourly sweep")
def _deletion_waits_for_dxnet():
    import asyncio, tempfile, pathlib, sqlite3
    from datetime import datetime
    from rasmai.bot import core
    from rasmai.bot.tasks.presence import JST
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    from rasmai import storage
    from rasmai.bot.tasks.presence import Maintenance
    kept = core._regions_down, core._warn_expiring_accounts, core._purge_expired_accounts, core.maintenance_at
    kept_postpone = storage.db.postpone_account_deletions
    problems = []
    try:
        from rasmai.storage.db import get_connected_account, mark_session_expired, upsert_connected_account
        for user_id, region in (("intl-due", "intl"), ("jp-due", "jp"), ("fine", "intl")):
            upsert_connected_account(user_id, region, f"cookie://{user_id}")
        mark_session_expired("intl-due", "2026-09-01T10:00:00")
        mark_session_expired("jp-due", "2026-09-01T10:00:00")
        ran = []

        async def warn():
            ran.append("warn")
        core._warn_expiring_accounts = warn
        core._purge_expired_accounts = lambda: ran.append("purge")
        # Japan's three hours of daily maintenance: nothing runs, and no deadline moves, even with a site that is not answering
        core.maintenance_at = lambda now=None, region="intl": Maintenance(region == "jp", datetime.now(JST))
        core._regions_down = lambda: ["intl", "jp"]
        asyncio.run(core._expired_account_sweep.coro())
        if ran or {get_connected_account(u)["sessionExpired"] for u in ("intl-due", "jp-due")} != {"2026-09-01T10:00:00"}:
            problems.append(f"during scheduled maintenance the sweep ran {ran} or moved a deadline")
        core.maintenance_at = lambda now=None, region="intl": Maintenance(False, datetime.now(JST))
        core._regions_down = lambda: ["intl"]
        asyncio.run(core._expired_account_sweep.coro())
        if ran:
            problems.append(f"with the site down the sweep still ran {ran}")
        if get_connected_account("intl-due")["sessionExpired"] != "2026-09-01T11:00:00":
            problems.append(f"the international deadline did not move an hour: {get_connected_account('intl-due')['sessionExpired']}")
        if get_connected_account("jp-due")["sessionExpired"] != "2026-09-01T10:00:00":
            problems.append("a region whose site is up had its deadline moved")
        if get_connected_account("fine")["sessionExpired"]:
            problems.append("an account that is not expired was given an expiry")
        def locked(*args):
            raise sqlite3.OperationalError("database is locked")
        storage.db.postpone_account_deletions = locked
        try:
            asyncio.run(core._expired_account_sweep.coro())
        except Exception as error:
            problems.append(f"a failed postpone escaped the sweep, which stops the hourly loop: {error!r}")
        storage.db.postpone_account_deletions = kept_postpone
        if ran:
            problems.append(f"a failed postpone went on to {ran}")
        core._regions_down = lambda: []
        asyncio.run(core._expired_account_sweep.coro())
        if ran != ["warn", "purge"]:
            problems.append(f"with the site back the sweep ran {ran}, not the warning then the deletion")
        return problems
    finally:
        core._regions_down, core._warn_expiring_accounts, core._purge_expired_accounts, core.maintenance_at = kept
        storage.db.postpone_account_deletions = kept_postpone
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
    rings = posters._skill_chart_svg(profile, a.songs, moved=moved).count('class="rs-ch-recent"')
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


def _export_analyzer():
    """A real account, analysed, from a debug export on this machine; None where there is none to build from."""
    import json

    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import PlayerInfo, SongInfo
    from tools.checks import ROOT

    # where the bot writes its exports, and the two folders they have been kept in by hand
    exports = sorted((p for folder in ("debug", "debug/maimai-exports", "data") for p in (ROOT / folder).glob("*.json")), key=lambda p: p.stat().st_size)
    # the folders also hold caches and other checks' leftovers: an export is the one with a player and their songs
    data = next((d for d in (json.loads(p.read_text(encoding="utf-8")) for p in exports) if isinstance(d, dict) and d.get("songs") and d.get("player")), None)
    if data is None:
        return None
    a = MaimaiRatingAnalyzer()
    a.player = PlayerInfo(**{k: v for k, v in data["player"].items() if k in PlayerInfo.__dataclass_fields__})
    a.songs = [SongInfo(**{k: v for k, v in r.items() if k in SongInfo.__dataclass_fields__}) for r in data["songs"]]
    a.recent_songs = data.get("recentSongsData") or []
    a.found = a.generate_recommendations()
    return a


@check("a roll of 1 to 60 tiles, and /analyze's picks beside its road, keep to the 16:9 frame at the fewest tiles across that fit")
def _rolls_fit_the_frame():
    import dataclasses, re

    from rasmai.images import posters
    from rasmai.images.render import generate_poster_html

    from tools.checks import ROOT

    # fit_across and the /analyze board work the frame out from these, so each must still be what the stylesheet draws
    css = (ROOT / "rasmai/images/templates/rasmai.css").read_text(encoding="utf-8")
    problems = [f"rasmai.css no longer has {rule!r}, which the tile arithmetic assumes" for rule in (
        "body { width: 2400px; min-height: 1350px;", "padding: 32px 40px 24px;", "aspect-ratio: 5 / 4;",
        ".tracks { display: grid; grid-template-columns: repeat(var(--across, 5), minmax(0, 1fr)); gap: 14px; }",
        ".an-board { --gap: 16px; --lane: 26px; display: grid; gap: 0 24px;", "minmax(0, 1fr)) 10px; gap: var(--gap) 52px; }") if rule not in css]
    if (posters.fit_across(6), posters.fit_across(30), posters.fit_across(60)) != (6, 8, 12):
        problems.append(f"6, 30 and 60 tiles go {posters.fit_across(6)}, {posters.fit_across(30)} and {posters.fit_across(60)} across, not 6, 8 and 12")
    if "--across:8" not in posters._roll(["<div></div>"] * 30):
        problems.append("a roll of 30 tiles is not laid the way fit_across says")
    a = _export_analyzer()
    if a is None:
        return problems
    movers = [r for r in a.found[0] if r.category not in ("near", "try")]
    # the picks stand beside the road on one tile width, so each length of one is tried against each length of the other
    for picks in range(1, min(len(movers), 15) + 1):
        for steps in (0, 1, 4, 5, 9, 16):
            plan = dataclasses.replace(a.plan, steps=a.plan.steps[:steps]) if a.plan else None
            page = generate_poster_html(movers[:picks], "p", 14000, 0, 0, 0, plan=plan)
            left = re.search(r'an-split" style="--left:(\d+)px', page)
            if left and not 0 < int(left[1]) < 2296:
                problems.append(f"/analyze with {picks} picks and {steps} steps gives the picks {left[1]}px beside the road")
    return problems[:8]


@check("with its image drawn a reply's embed keeps the links to its charts and leaves the figures to the image; without one it carries them")
def _embeds_lean_on_the_image():
    import asyncio, pathlib, re, sys, tempfile

    from rasmai.bot.builders.charts import level, scores
    from rasmai.bot.builders.history import recent
    from rasmai.bot.builders.results import embeds
    from rasmai.bot.state.cache import CachedAnalysis
    from rasmai.bot.ui import formatting
    from rasmai.storage.db import connection as store

    a = _export_analyzer()
    if a is None:
        return []
    LONG = ("analyze", "dxscore, past the image's rows")
    # the five that can be asked for as text alone, then the lists, which have no image only when the render fails
    results = {
        "analyze": lambda c, t: embeds.build_analyze(c, text_only=t),
        "plan": lambda c, t: embeds.build_plan(c, None, False, 0, text_only=t),
        "session": lambda c, t: embeds.build_session(c, embeds.SESSION_DEFAULT, text_only=t),
        "new": lambda c, t: embeds.build_new(c, None, text_only=t),
        "profile": lambda c, t: embeds.build_profile(c, text_only=t),
    }
    lists = {
        "b50": lambda c, t: scores.build_b50(c, 1, 0),
        "dxscore": lambda c, t: scores.build_dxscore(c, 1, 0),
        "dxscore, past the image's rows": lambda c, t: scores.build_dxscore(c, 1, 4),
        "charts level": lambda c, t: level.build_level(c, 1, "13", "weakest", 0),
        "recent": lambda c, t: recent.build_recent(c, 1, 0),
    }
    pages = {}
    patched = [m for name, m in list(sys.modules.items()) if name.startswith("rasmai.bot.builders") and hasattr(m, "try_render")]
    kept = [m.try_render for m in patched]
    was = store.DATABASE_PATH

    async def run():
        from rasmai.web.dashboard.beta import set_beta
        set_beta("1", {"images": True})     # the rolls and the lean embeds belong to the new look, so this draws in it
        out = {}
        for name, build in {**results, **lists}.items():
            for bare in (False, True):
                async def drawn(html, name=name, bare=bare):
                    pages[name] = html or ""
                    return None if bare and name in lists else b"png"
                for module in patched:
                    module.try_render = drawn
                cached = CachedAnalysis(user_id="1", region="intl", analyzer=a, recommendations=a.found[0], value_charts=a.found[1])
                out[name, bare] = (await build(cached, bare))[0]
        # a render that fails is the other way to have no image: asked for with its picture, answered without
        async def failed(html):
            return None
        for module in patched:
            module.try_render = failed
        for name, build in results.items():
            cached = CachedAnalysis(user_id="1", region="intl", analyzer=a, recommendations=a.found[0], value_charts=a.found[1])
            out[name, "failed"] = (await build(cached, False))[0]
        # the bot's own lines are longer than these: its tier marks are custom emoji, and a link with no cover spells out a whole
        # title. Every link is stretched until eight lines cannot share a field, to see that none is then dropped
        async def png(html):
            return b"png"
        for module in patched:
            module.try_render = png
        real = formatting.chart_link
        formatting.chart_link = scores.chart_link = lambda *args, **kwargs: real(*args, **kwargs)[:-1] + "?" + "x" * 60 + ")"
        try:
            for name in LONG:
                cached = CachedAnalysis(user_id="1", region="intl", analyzer=a, recommendations=a.found[0], value_charts=a.found[1])
                out[name, "long"] = (await {**results, **lists}[name](cached, False))[0]
        finally:
            formatting.chart_link = scores.chart_link = real
        return out

    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "embeds.sqlite3", False
    try:
        made = asyncio.run(run())
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
        for module, own in zip(patched, kept):
            module.try_render = own
    problems = []
    said = lambda e: (e.description or "") + "".join(f.name + f.value for f in e.fields)
    # a figure is a percentage or a score's move to its target; a link's address is long but says nothing
    figures = lambda e: said(e).count("%") + said(e).count("→")
    for name in {**results, **lists}:
        lean, full = made[name, False], made[name, True]
        if figures(lean) > figures(full) or (name in results and figures(lean) == figures(full)):
            problems.append(f"/{name}: the embed beside its image repeats the figures the image shows ({figures(lean)} of the {figures(full)} it has with no image)")
        if "](http" in said(full) and "](http" not in said(lean):
            problems.append(f"/{name}: the embed beside its image lost the links to its charts")
        if name in results and said(made[name, "failed"]) != said(full):
            problems.append(f"/{name}: when its image fails to render the embed is not the one that carries every figure")
        for embed in (lean, full):
            broken = [f.name for f in embed.fields if not f.name or not 0 < len(f.value) <= 1024]
            if broken or len(embed) > 6000 or len(embed.fields) > 25 or len(embed.description or "") > 4096:
                problems.append(f"/{name}: Discord would refuse this embed: {len(embed)} characters, {len(embed.fields)} fields, bad fields {broken}")
    # a run of links, or a field of them, ends where the next would not fit: the numbers go on without a gap
    for name in LONG:
        numbers = [int(n) for n in re.findall(r"` *(\d+)`", said(made[name, "long"]))]
        runs = [numbers[i] for i in range(1, len(numbers)) if numbers[i] not in (numbers[i - 1] + 1, 1)]
        if not numbers or runs:
            problems.append(f"/{name}: the links beside the image skip a number, so a chart on the image has no link: {numbers}")
    # a page past the image's rows says how many it holds: each has its line, none dropped at a field's cap
    late = made["dxscore, past the image's rows", "long"]
    span = re.search(r"(\d+)-(\d+) of", late.fields[0].name) if late.fields else None
    held = sum(len(re.findall(r"^` *\d+`", f.value, re.M)) for f in late.fields)
    if span and held != int(span[2]) - int(span[1]) + 1:
        problems.append(f"/dxscore: a page past the image's rows names {span[0][:-3]} and links {held} of them")
    # what the /analyze embed gave up is on its poster: how the player plays, and the best-50 cutoffs
    profile = (a.analysis_summary or {}).get("profile", {})
    if any(f.name == "Style" for f in made["analyze", False].fields) or not any(f.name == "Style" for f in made["analyze", True].fields):
        problems.append("/analyze: the Style, Levels and Best-50 fields are not left to the poster when there is one, or are missing when there is none")
    if str(profile.get("comfortConstant")) not in pages.get("analyze", "") or "cutoffs" not in pages.get("analyze", "").lower():
        problems.append("/analyze: the poster does not show the comfort level and best-50 cutoffs its embed no longer does")
    return problems


@check("the profile's quick wins, stretch goals and new charts link each chart to its page")
def _profile_lists_link():
    from rasmai.bot.builders.results import embeds

    problems = []
    a = _export_analyzer()
    if a is None:
        return []      # no export on this machine to build from
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


@check("a Japan read signed out part way is a passing failure, and an International one still asks for /login")
def _japan_mid_read():
    import types

    from rasmai.scraping.scraper.analyzer import MaimaiRatingAnalyzer
    from rasmai.scraping.scraper.session import SessionRejected

    problems = []
    analyzer = MaimaiRatingAnalyzer()

    def bounced(location):
        return types.SimpleNamespace(get=lambda url, **kw: types.SimpleNamespace(status_code=302, headers={"Location": location}, text=""))

    try:
        analyzer._fetch_official_html(bounced("https://maimaidx.jp/maimai-mobile/error/"), "https://maimaidx.jp/maimai-mobile/record/", "")
        problems.append("a bounced Japan page did not raise")
    except SessionRejected:
        problems.append("a Japan read signed out part way was treated as a dead sign-in: it would stop the account's reads "
                        "and start its deletion clock while the stored SEGA ID still works")
    except ValueError:
        pass
    try:
        analyzer._fetch_official_html(bounced("https://maimaidx-eng.com/maimai-mobile/error/"), "https://maimaidx-eng.com/maimai-mobile/record/", "")
        problems.append("a bounced International page did not raise")
    except SessionRejected:
        pass
    except ValueError:
        problems.append("an International read signed out part way no longer asks for /login")
    return problems


@check("a reply whose waiting message was deleted while it was built goes out as a new message with its picture and buttons, and any other refusal is still an error")
def _deleted_reply():
    import asyncio
    import io
    import types
    import discord
    from rasmai.bot.builders.results.view import deliver

    problems = []
    answered = types.SimpleNamespace(status=404, reason="Not Found")

    def interaction(code):
        sent = []

        async def edit_original_response(**options):
            for file in options["attachments"]:
                file.fp.read()          # a refused upload still reads the file to its end
            raise discord.NotFound(answered, {"code": code, "message": "Unknown"})

        async def send(**options):
            sent.append({**options, "bytes": [file.fp.read() for file in options["files"]]})
            return "new message"

        return types.SimpleNamespace(edit_original_response=edit_original_response, followup=types.SimpleNamespace(send=send),
                                     user=types.SimpleNamespace(id=1), command=types.SimpleNamespace(qualified_name="b50"), sent=sent)

    embed, view = discord.Embed(title="Best 50"), discord.ui.View()
    gone = interaction(10008)
    landed = asyncio.run(deliver(gone, True, embed=embed, files=[discord.File(io.BytesIO(b"png"), filename="rasmai.png")], view=view))
    if landed != "new message" or len(gone.sent) != 1:
        problems.append(f"a deleted reply was not sent again: {landed!r}, {len(gone.sent)} sent")
    elif gone.sent[0]["bytes"] != [b"png"] or gone.sent[0].get("embed") is not embed or gone.sent[0].get("view") is not view or gone.sent[0]["ephemeral"] is not True:
        problems.append("the new message lost its picture, embed, buttons or privacy")
    other = interaction(10015)
    try:
        asyncio.run(deliver(other, False, embed=embed, files=[], view=None))
        problems.append("an unknown webhook was answered with a new message instead of reaching the error handling")
    except discord.NotFound:
        pass
    return problems


@check("each new-look image takes one of the background layouts the stylesheet draws, and over many images every layout comes up")
def _backdrops_vary():
    import re

    from rasmai.images import posters

    css = (ROOT / "rasmai/images/templates/rasmai.css").read_text(encoding="utf-8")
    problems = [f"rasmai.css has no body.{c}::before for the {c} layout" for c in posters.BACKDROPS if c and f"body.{c}::before" not in css]
    seen = set()
    for _ in range(200):
        page = posters._page("x", "p", "", "1", "", "", "", "", "narrow")
        classes = re.search(r'<body class="([^"]*)"', page)[1].split()
        if "narrow" not in classes:
            problems.append("the page lost the class it was asked for when a layout was added")
            break
        seen.add(next((c for c in classes if c in posters.BACKDROPS), ""))
    if seen != set(posters.BACKDROPS):
        problems.append(f"200 images drew only the layouts {sorted(seen)} of {list(posters.BACKDROPS)}")
    return problems


@check("the images keep their classic look unless the account switched the new one on at the site, every image the bot draws goes through that switch, and switching drops the images already drawn")
def _image_theme_switch():
    import pathlib, re, tempfile, types
    from datetime import datetime

    from rasmai.bot.state.cache import cache_get, cache_put, forget_analysis
    from rasmai.images import cards, pages, posters, render
    from rasmai.bot.builders.plates import _drawn
    from rasmai.images.pages import best50_image_html
    from rasmai.images.themes import themed
    from rasmai.storage.db import connection as store
    from rasmai.web.dashboard.beta import set_beta

    problems = []
    # a call in a builder that names an image function and opens it straight away skips the switch
    called = re.compile(r"\b(\w+_(?:image|card|poster)_html|generate_poster_html)\(")
    switched = set()
    for path in (ROOT / "rasmai" / "bot").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        switched |= set(re.findall(r"themed\([^,]+, (?:posters\.)?(\w+)\)", text))
        for number, line in enumerate(text.splitlines(), 1):
            if not line.lstrip().startswith(("from ", "import ", "def ")):
                problems += [f"{path.relative_to(ROOT)}:{number} draws {name} without the theme switch"
                             for name in called.findall(line) if not name.startswith("plate")]
    # the classic copy is looked up by the new function's name, so a rename on either side would hand everyone the new look
    drawn = [next(getattr(m, n) for m in (pages, cards, posters, render) if hasattr(m, n)) for n in sorted(switched)]
    if len(drawn) < 17:
        problems.append(f"only {len(drawn)} images are drawn through the theme switch: {sorted(switched)}")
    was = store.DATABASE_PATH
    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "themes.sqlite3", False
    try:
        for draw in drawn:
            if not themed("7", draw).__module__.startswith("rasmai.images.classic."):
                problems.append(f"{draw.__name__} is not drawn classic for an account that never switched")
        if _drawn(types.SimpleNamespace(user_id="7")):
            problems.append("the plates, which have no classic look, are drawn for an account that never switched")
        # the classic page takes the call the builders make for the new one, and still shows its own header
        page = themed("7", best50_image_html)([], [], "p", "", lambda cover, css: "", 14000, 302)
        if "14302" not in re.sub(r"<[^>]+>", "", page) or "rp-cells" not in page:
            problems.append("the classic best 50 does not draw its header and cells from the call the builders make for the new look")
        cache_put(types.SimpleNamespace(user_id="7", created=datetime.now(), images={"b50": b"png"}))
        set_beta("7", {"patterns": True})
        if not cache_get("7").images:
            problems.append("switching another beta dropped the images already drawn")
        set_beta("7", {"images": True})
        if [d for d in drawn if themed("7", d) is not d]:
            problems.append("an account that switched the new look on still gets the classic one")
        if not _drawn(types.SimpleNamespace(user_id="7")):
            problems.append("an account that switched the new look on gets no plates image")
        if cache_get("7").images:
            problems.append("switching the look keeps the images drawn in the old one")
        if themed(None, best50_image_html) is best50_image_html:
            problems.append("an image drawn for nobody in particular is not classic")
    finally:
        forget_analysis("7")
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("the Blitz worker draws the images one page at a time through its pipe; Chromium draws the classic recent board, any page the worker fails on or dies over, and every image when the worker is missing or RASMAI_RENDERER is chromium")
def _blitz_renderer():
    import asyncio, pathlib, sys, tempfile

    from rasmai.images import render

    # a stand-in for blitz that speaks its pipe protocol: a byte count and the page in, a byte count and the "image" back
    worker = pathlib.Path(tempfile.mkdtemp()) / "worker.py"
    worker.write_text(
        "import sys\n"
        "src, out = sys.stdin.buffer, sys.stdout.buffer\n"
        "while len(head := src.read(4)) == 4:\n"
        "    html = src.read(int.from_bytes(head, 'little')).decode()\n"
        "    if 'DIE' in html: sys.exit(1)\n"
        "    reply = b'' if 'FAIL' in html else ('BLITZ %d' % len(html.encode())).encode()\n"
        "    out.write(len(reply).to_bytes(4, 'little') + reply); out.flush()\n", encoding="utf-8")
    spawn, chromium, kept = render.asyncio.create_subprocess_exec, render._render_with_chromium, dict(render._blitz)

    async def through_python(path, *args, **kwargs):
        return await spawn(sys.executable, str(worker), *args, **kwargs) if path == "blitz" else await spawn(path, *args, **kwargs)

    async def in_chromium(html):
        return b"CHROMIUM"

    def draw(*pages):
        async def run():
            return [await render.render_html_to_image(page) for page in pages]
        return asyncio.run(run())

    def use(path):
        render._stop_blitz()
        render._blitz.update(path=path, looked=True, loop=None, lock=None, proc=None)

    problems = []
    render.asyncio.create_subprocess_exec, render._render_with_chromium = through_python, in_chromium
    try:
        use("blitz")
        page = "<body>祭 best 50</body>"
        if draw(page) != [b"BLITZ %d" % len(page.encode())]:
            problems.append("a page is not drawn by the worker, or its size is sent in characters rather than bytes")
        if draw('<div class="recent-flow"></div>') != [b"CHROMIUM"]:
            problems.append("the classic recent board, whose columns Blitz cannot lay out, is not drawn by Chromium")
        classic = (ROOT / "rasmai" / "images" / "classic" / "templates" / "rasmai.html").read_text(encoding="utf-8")
        if not any(marker in classic for marker in render.BLITZ_UNSUPPORTED):
            problems.append("the classic recent board's markup no longer carries the marker that sends it to Chromium")

        async def failing_then_drawn():
            first = await render.render_html_to_image("FAIL")
            pid = render._blitz["proc"].pid
            second = await render.render_html_to_image("<p>next</p>")
            return first, second, pid == render._blitz["proc"].pid
        failed, after, same = asyncio.run(failing_then_drawn())
        if failed != b"CHROMIUM" or after != b"BLITZ 11" or not same:
            problems.append("a page the worker cannot draw does not go to Chromium with the worker kept for the next one")
        if draw("DIE", "<p>next</p>") != [b"CHROMIUM", b"BLITZ 11"]:
            problems.append("a worker that dies mid-page does not hand that page to Chromium and start afresh for the next")

        async def together():
            return await asyncio.gather(*(render.render_html_to_image("x" * n) for n in range(1, 9)))
        if asyncio.run(together()) != [b"BLITZ %d" % n for n in range(1, 9)]:
            problems.append("pages drawn at once come back mixed up: the worker's pipe is not kept to one page at a time")

        use(str(pathlib.Path(worker.parent) / "no-such-renderer"))
        if draw("<p>a</p>", "<p>b</p>") != [b"CHROMIUM", b"CHROMIUM"] or render._blitz["path"] is not None:
            problems.append("with no worker installed the images are not drawn by Chromium, or it is looked for again on every image")

        render._blitz.update(looked=False)
        was, render.RENDERER = render.RENDERER, "chromium"
        try:
            if render._blitz_path() is not None:
                problems.append("RASMAI_RENDERER=chromium does not turn the worker off")
            render._blitz.update(looked=False)
            render.RENDERER = ""
            if render._blitz_path() is not None:
                problems.append("with RASMAI_RENDERER unset a worker is still started, so a 'blitz' on PATH could be some other program")
        finally:
            render.RENDERER = was
    finally:
        render._stop_blitz()
        render.asyncio.create_subprocess_exec, render._render_with_chromium = spawn, chromium
        render._blitz.clear()
        render._blitz.update(kept)
    return problems


@check("a command whose read outlasts Discord's fifteen minutes tells the person by message to ask again, once, and is not reported as a bug; any other failure still is")
def _late_reply():
    import asyncio
    import logging
    import types
    from datetime import timedelta
    import discord
    from discord import app_commands
    from rasmai.bot import core
    from rasmai.bot.builders.results.view import failure_reply
    from rasmai.bot.ui.views import OwnerOnlyView

    problems = []
    seen = []

    class Grab(logging.Handler):
        def emit(self, record):
            seen.append(record)

    grab = Grab()
    logging.getLogger().addHandler(grab)
    answered = types.SimpleNamespace(status=401, reason="Unauthorized")

    def gone(code=50027):
        return discord.HTTPException(answered, {"code": code, "message": "Invalid Webhook Token"})

    def interaction(minutes=20, closed=False):
        sent = []

        class User:
            id = 4242

            async def send(self, text):
                if closed:
                    raise discord.Forbidden(types.SimpleNamespace(status=403, reason="Forbidden"), {"code": 50007, "message": "Cannot send messages to this user"})
                sent.append(text)

        return types.SimpleNamespace(user=User(), created_at=discord.utils.utcnow() - timedelta(minutes=minutes), command=types.SimpleNamespace(qualified_name="analyze", name="analyze"),
                                     extras={}, guild_id=None, channel_id=None, data={}, namespace=[], sent=sent)

    def errors():
        return [r for r in seen if r.levelno >= logging.ERROR]

    try:
        late = interaction()
        reply = asyncio.run(failure_reply(late, "Something went wrong while analyzing your account.", gone()))
        if errors() or len(late.sent) != 1 or "`/analyze`" not in late.sent[0] or "again" not in late.sent[0] or reply.get("content") is not None:
            problems.append(f"a late reply was reported as a bug or the person was not told once: {[r.getMessage() for r in errors()]} {late.sent} {reply}")
        asyncio.run(failure_reply(late, "x", gone(10015)))
        if len(late.sent) != 1:
            problems.append("the same late command was told twice")

        seen.clear()
        shut = interaction(closed=True)
        asyncio.run(failure_reply(shut, "x", gone()))
        if errors():
            problems.append("a person who takes no messages from the bot made a late reply an error")

        seen.clear()
        ordinary = interaction(minutes=1)
        reply = asyncio.run(failure_reply(ordinary, "Something went wrong.", ValueError("boom")))
        if not errors() or ordinary.sent or "error ID" not in str(reply.get("content")):
            problems.append(f"an ordinary failure was not reported with an ID, or a message was sent: {reply} {ordinary.sent}")

        # the handler every command falls to: a late reply is a message, a command never acknowledged in time is still an error, a real bug still is
        seen.clear()
        late = interaction()
        error = app_commands.CommandInvokeError(types.SimpleNamespace(name="analyze"), gone())
        asyncio.run(core.on_app_command_error(late, error))
        if errors() or len(late.sent) != 1:
            problems.append(f"the global handler reported a late reply or stayed quiet: {[r.getMessage() for r in errors()]} {late.sent}")
        seen.clear()
        quick = interaction(minutes=0)
        unknown = discord.NotFound(types.SimpleNamespace(status=404, reason="Not Found"), {"code": 10062, "message": "Unknown interaction"})
        asyncio.run(core.on_app_command_error(quick, app_commands.CommandInvokeError(types.SimpleNamespace(name="analyze"), unknown)))
        if not errors() or quick.sent:
            problems.append("a command never acknowledged in time stopped being logged as an error, or was told 'ask again'")
        seen.clear()
        slow = interaction()
        asyncio.run(core.on_app_command_error(slow, app_commands.CommandInvokeError(types.SimpleNamespace(name="analyze"), unknown)))
        if errors() or len(slow.sent) != 1:
            problems.append("an unknown interaction after twenty minutes was treated as 'not acknowledged in time' instead of a late reply")

        # a button whose reply ran out of time
        seen.clear()
        button = interaction()

        async def press():
            view = OwnerOnlyView(4242, timeout=5)
            await view.on_error(button, gone(), discord.ui.Button())
        asyncio.run(press())
        if errors() or len(button.sent) != 1:
            problems.append(f"a button's late reply was reported as a broken button: {[r.getMessage() for r in errors()]} {button.sent}")
    finally:
        logging.getLogger().removeHandler(grab)
    return problems


@check("a command used where the app is only installed to the person's account answers in public unless the server turned off external apps")
def _external_apps():
    import types
    import discord
    from rasmai.bot.core import private_only
    problems = []

    def asked(guild, installed, allowed):
        return types.SimpleNamespace(guild=object() if guild else None, is_guild_integration=lambda: installed,
                                     permissions=discord.Permissions(use_external_apps=allowed))
    for guild, installed, allowed, private in ((False, False, False, False), (True, True, False, False),
                                               (True, False, True, False), (True, False, False, True)):
        if private_only(asked(guild, installed, allowed)) != private:
            problems.append(f"in a {'server' if guild else 'DM'}, {'added' if installed else 'not added'} to it, external apps "
                            f"{'allowed' if allowed else 'off'}: the reply was {'private' if not private else 'public'}")
    return problems
