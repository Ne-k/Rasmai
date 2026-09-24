
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
