from tools.checks import ROOT, check
from tools.checks.stubs import stub_get


@check("a public profile carries only what its owner turned on")
def _public_profile():
    import tempfile, pathlib
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        from rasmai.bot.state.prefs import PUBLIC_SECTIONS
        from rasmai.storage.db import get_connected_account, upsert_connected_account
        from rasmai.web.dashboard.public_profile import public_payload, set_sharing, sharing_payload
        problems = []
        # the stored snapshot keeps rows against a field list, not dicts: building the profile from
        # dict-shaped charts passed every test and crashed on every real account
        from rasmai.bot.state.snapshots import CHART_FIELDS
        rows = [[f"song {i}", "dx", "master", 100.2 - i * 0.01, 300 - i, "13+", 13.7, "FC", "", i < 20, 2900]
                for i in range(60)]
        upsert_connected_account("u1", "intl", "cookie://x",
                                 official_profile={"name": "Nek", "rating": 13551, "totalPlayCount": 574},
                                 snapshot={"fields": list(CHART_FIELDS), "charts": rows, "recordedAt": "2026-09-14T04:00:00"})
        account = get_connected_account("u1")

        if sharing_payload("u1", account)["on"]:
            problems.append("a fresh account is already sharing; the profile must be opt-in")
        state = set_sharing("u1", True, {"best50": True}, account=account)
        slug = state["url"].rsplit("/", 1)[-1]
        from rasmai.web.dashboard.public_profile import SLUG_LENGTH
        if not state["on"] or len(slug) < SLUG_LENGTH:
            problems.append(f"turning sharing on gave no usable link: {state}")
            return problems

        shown = public_payload(slug)
        if shown is None:
            problems.append("the link does not answer while sharing is on")
            return problems
        if "userId" in shown or "token" in shown or "u1" in str(shown):
            problems.append("the public payload leaks the account behind it")
        for name in PUBLIC_SECTIONS:
            if name != "best50" and name in shown:
                problems.append(f"{name} was never turned on but is on the profile")
        if "best50" not in shown:
            problems.append("best50 was turned on but is missing")
        elif len(shown["best50"]["new"]) != 15 or len(shown["best50"]["old"]) != 35:
            problems.append(f"the pools did not fill from the stored rows: "
                            f"{len(shown['best50']['new'])} new, {len(shown['best50']['old'])} old")
        elif not shown["best50"]["new"][0]["title"]:
            problems.append("the charts came back nameless: the snapshot rows were not read")

        # switching it off has to take effect at once, not at the next link
        account = get_connected_account("u1")
        set_sharing("u1", False, account=account)
        if public_payload(slug) is not None:
            problems.append("the link still answers after sharing was switched off")

        # a fresh link must break the old one
        set_sharing("u1", True, account=get_connected_account("u1"))
        again = set_sharing("u1", True, rotate=True, account=get_connected_account("u1"))
        if public_payload(slug) is not None:
            problems.append("the old link still answers after a new one was issued")
        if public_payload(again["url"].rsplit("/", 1)[-1]) is None:
            problems.append("the new link does not answer")
        return problems
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False


@check("the chart speeds save only as the game's option IDs, the same table the site's player reads")
def _speeds():
    import re, tempfile, pathlib
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        from rasmai.bot.state.prefs import DEFAULTS, NOTE_SPEEDS, TOUCH_SPEEDS, clean_speed, get_prefs, set_speeds, update_prefs
        problems = []
        rules = (ROOT / "web" / "lib" / "chart" / "rules.mjs").read_text(encoding="utf-8")
        touch = [int(n) for n in re.findall(r"\d+", re.search(r"TOUCH_SPEED = \[([^\]]*)\]", rules).group(1))]
        if tuple(touch) != TOUCH_SPEEDS or len(NOTE_SPEEDS) != 38 or NOTE_SPEEDS[14] != 550 or NOTE_SPEEDS[-1] != 5000:
            problems.append("the bot's speed tables no longer match web/lib/chart/rules.mjs")
        if DEFAULTS.get("note_speed") != 550 or DEFAULTS.get("touch_speed") != 350:
            problems.append(f"the speed defaults are not the player's 4.50: {DEFAULTS.get('note_speed')}, {DEFAULTS.get('touch_speed')}")
        if get_prefs("u1")["note_speed"] != 550:
            problems.append("a fresh account has no note speed")
        if (set_speeds("u1", note_speed=700, touch_speed=5000) or {}).get("note_speed") != 700 or get_prefs("u1")["touch_speed"] != 5000:
            problems.append("a valid speed from the site did not save")
        for bad in (701, 0, True, "700", 7.0, [700]):
            if set_speeds("u1", note_speed=bad) is not None:
                problems.append(f"the site saved a note speed that is not the game's: {bad!r}")
        if set_speeds("u1", note_speed=900, touch_speed=901) is not None or get_prefs("u1")["note_speed"] != 700:
            problems.append("one bad speed in a save let the other one through")
        if clean_speed("7", NOTE_SPEEDS) != 800 or clean_speed("sonic", TOUCH_SPEEDS) != 5000 or clean_speed("4.50", TOUCH_SPEEDS) != 350:
            problems.append("what Discord sends (the game's numbers) does not map onto the option IDs")
        if clean_speed("7.10", NOTE_SPEEDS) is not None or clean_speed("nan", NOTE_SPEEDS) is not None or clean_speed("11", NOTE_SPEEDS) is not None:
            problems.append("Discord can type a speed the game does not have")
        update_prefs("u1", note_speed=12345)
        if get_prefs("u1")["note_speed"] != 550:
            problems.append("a stored speed outside the table is handed to the renderers")
        return problems
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False


@check("the linking walkthroughs are web sized and small enough for Discord")
def _walkthrough():
    from rasmai.config import WALKTHROUGH_DIR
    # a master dropped in by mistake is both a slow page and an upload Discord refuses
    DISCORD_LIMIT = 8 * 1024 * 1024
    SENSIBLE = 6 * 1024 * 1024
    problems = []
    for clip in ("desktop", "ios-safari"):
        video = WALKTHROUGH_DIR / f"{clip}.mp4"
        poster = WALKTHROUGH_DIR / f"{clip}.jpg"
        if not video.is_file():
            problems.append(f"{video} is missing, so the /login button has nothing to send")
            continue
        size = video.stat().st_size
        if size > DISCORD_LIMIT:
            problems.append(f"{clip}.mp4 is {size / 1048576:.1f} MB, over Discord's {DISCORD_LIMIT / 1048576:.0f} MB limit")
        elif size > SENSIBLE:
            problems.append(f"{clip}.mp4 is {size / 1048576:.1f} MB; transcode it before shipping")
        if not poster.is_file():
            problems.append(f"{poster.name} is missing, so the video box collapses before it loads")
        elif poster.stat().st_mtime < video.stat().st_mtime - 60:
            problems.append(f"{poster.name} is older than {clip}.mp4: the poster is from a previous cut")
    return problems


@check("the band on every page asks only whether the saved login still works, without building the dashboard or reading the scores")
def _session_route():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    from rasmai.web.dashboard import routes
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    problems = []
    kept = routes.analysis_for_user, routes.get_connected_account
    asked = []

    def no_analysis(*args, **kwargs):
        raise AssertionError("the analysis was loaded")

    def account(user_id, with_snapshot=True):
        asked.append(with_snapshot)
        return kept[1](user_id, with_snapshot=with_snapshot)
    routes.analysis_for_user, routes.get_connected_account = no_analysis, account
    try:
        from rasmai.storage.db import mark_session_expired, upsert_connected_account
        upsert_connected_account("333", "intl", "cookie://abc")
        mark_session_expired("333", "2026-10-01T10:00:00")

        class Fake:
            def __init__(self):
                self.sent = []

            def _send_json(self, status, body):
                self.sent.append((status, body))
        answers = []
        for who in ("333", "444"):
            handler = Fake()
            try:
                routes.handle_get(handler, "/internal/me/session", {}, {"id": who})
            except AssertionError as error:
                problems.append(str(error))
            answers.append(handler.sent)
        if answers != [[(200, {"sessionExpired": "2026-10-01T10:00:00"})], [(200, {"sessionExpired": ""})]] or any(asked):
            problems.append(f"the session route answered {answers}, reading the scores {asked}")
    finally:
        routes.analysis_for_user, routes.get_connected_account = kept
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("the developer page answers one account and 404s for everyone else")
def _admin():
    from rasmai.config import ADMIN_USER_ID
    from rasmai.web.dashboard import routes
    from rasmai.web.dashboard.admin import is_admin
    problems = []
    if not ADMIN_USER_ID.isdigit():
        problems.append(f"the admin id should be a Discord snowflake, it is {ADMIN_USER_ID!r}")
    for other in ("", "0", ADMIN_USER_ID + "1", ADMIN_USER_ID[:-1], " " + ADMIN_USER_ID):
        if is_admin(other):
            problems.append(f"{other!r} was let in")
    if not is_admin(ADMIN_USER_ID):
        problems.append("the admin id itself was refused")

    class Fake:
        def __init__(self):
            self.sent = []

        def _send_json(self, status, body):
            self.sent.append((status, body))

    for who in (ADMIN_USER_ID + "9", "1"):
        handler = Fake()
        routes.handle_get(handler, "/internal/me/admin", {}, {"id": who})
        if not handler.sent or handler.sent[0][0] != 404:
            problems.append(f"the route answered {handler.sent} to {who}, expected a 404")
        elif handler.sent[0][1].get("error") != "not_found":
            problems.append(f"the refusal names the page: {handler.sent[0][1]}")

    # the page lists both halves of what the bot reaches, and neither is allowed to throw on the
    # awkward server: no icon, no member count, not sharded, and no record of the bot joining
    import sys, types
    from rasmai.web.dashboard import admin as admin_module
    was = sys.modules.get("rasmai.bot.core")

    class Server:
        def __init__(self, **fields):
            self.__dict__.update(fields)

    joined = types.SimpleNamespace(joined_at=None)
    sys.modules["rasmai.bot.core"] = types.SimpleNamespace(bot=types.SimpleNamespace(guilds=[
        Server(id=1, name="small", icon=None, member_count=None, owner_id=None, me=None, shard_id=None),
        Server(id=2, name="big", icon=None, member_count=900, owner_id=None, me=joined, shard_id=0),
    ]))
    try:
        listed = admin_module.guilds_payload()
    except Exception as error:
        listed = []
        problems.append(f"a server the gateway told us little about broke the list: {type(error).__name__}: {error}")
    finally:
        if was is not None:
            sys.modules["rasmai.bot.core"] = was
        else:
            sys.modules.pop("rasmai.bot.core", None)
    if [g["name"] for g in listed] != ["big", "small"]:
        problems.append(f"servers should be listed biggest first: {[g.get('name') for g in listed]}")
    if listed and listed[1]["members"] != 0:
        problems.append("a server with no member count should read as zero, not None")

    handler = Fake()
    routes.handle_get(handler, "/internal/me/admin", {}, {"id": ADMIN_USER_ID})
    body = handler.sent[0][1] if handler.sent else {}
    for half in ("guilds_list", "accounts_list"):
        if half not in body:
            problems.append(f"the developer page no longer carries {half}")
    return problems


def _notice_writes(admin, notice_payload):
    from rasmai.storage.db import site_notice_set
    problems = []
    if not (notice_payload().get("text") and notice_payload().get("id")):
        problems.append("with nothing set the site should still have its built-in banner")

    stored = site_notice_set("  Two   spaces  collapse ", "warning", "https://example.com", by=admin)
    shown = notice_payload()
    if shown.get("text") != "Two spaces collapse" or shown.get("tone") != "warning":
        problems.append(f"the banner should read back as it was set: {shown.get('text')!r} {shown.get('tone')!r}")
    if "setBy" in shown:
        problems.append("the payload names who set the banner, and visitors should not see that")
    if site_notice_set("Two spaces collapse")["id"] != stored["id"]:
        problems.append("the same words should keep their id, so a dismissal is not undone by a re-save")
    if site_notice_set("Different words entirely")["id"] == stored["id"]:
        problems.append("new words should get a new id, so everyone sees the new banner")
    for bad in ("http://insecure", "javascript:alert(1)", "data:text/html,<script>", "https://x.example/\" onmouseover="):
        if site_notice_set("x", "notice", bad)["link"]:
            problems.append(f"a link that is not a plain https address should be dropped: {bad!r}")
    if site_notice_set("x", "purple")["tone"] != "notice":
        problems.append("an unknown tone should fall back rather than reach the page as a class name")
    if len(site_notice_set("A" * 5000)["text"]) > 300:
        problems.append("a banner should not be able to run the length of the page")
    # a right-to-left override can print a link backwards, and a zero-width space hides inside a word
    tricky = "Go to " + chr(0x202E) + "moc.live" + chr(0x202C) + " now" + chr(0x200B) + "please"
    if site_notice_set(tricky)["text"] != "Go to moc.live nowplease":
        problems.append("characters that let text lie about itself should not survive")
    if site_notice_set("one" + chr(10) + "two" + chr(13) + chr(10) + "three")["text"] != "one two three":
        problems.append("a banner is one line, however it was typed")
    # a row the command never wrote, as if the table had been edited by hand or restored from a backup
    from rasmai.storage.db.sources import _clean
    forged = _clean({"text": "x", "tone": "evil", "link": "javascript:alert(1)", "id": "i"})
    if forged["link"] or forged["tone"] != "notice":
        problems.append("a row that never went through the command should still be cleaned when read")

    site_notice_set("")
    if notice_payload().get("text"):
        problems.append("a banner taken down should stay down, not fall back to the built-in one")
    return problems


@check("the site banner is set by one account, in one place, and says only what it was told to")
def _site_notice():
    import discord
    import tempfile, pathlib
    from rasmai.bot.core import bot
    from rasmai.config import ADMIN_USER_ID, CONTROL_GUILD_ID
    from rasmai.storage.db import connection as store
    from rasmai.web.dashboard import notice_payload

    problems = []
    # the command must not be in the global set, or it lands in every server's picker
    if any(command.name == "notice" for command in bot.tree.get_commands()):
        problems.append("/notice is registered globally, so everyone can see it")
    if CONTROL_GUILD_ID and not any(c.name == "notice" for c in bot.tree.get_commands(guild=discord.Object(id=CONTROL_GUILD_ID))):
        problems.append("/notice is not registered in the control guild, so nobody can reach it")

    source = (ROOT / "rasmai" / "bot" / "commands" / "notice.py").read_text(encoding="utf-8")
    if "ADMIN_USER_ID" not in source:
        problems.append("/notice does not check who is running it")
    if not ADMIN_USER_ID:
        problems.append("no admin account is set, so the check would let anyone through")

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        problems += _notice_writes(ADMIN_USER_ID, notice_payload)
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


def _web_text():
    """Every line of the site that could name an address on the bot."""
    out = []
    for root in (ROOT / "web" / "app", ROOT / "web" / "components", ROOT / "web" / "lib"):
        for path in root.rglob("*.ts*"):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            out.append(path.read_text(encoding="utf-8"))
    return chr(10).join(out)


@check("the website and the bot agree on every address between them")
def _seam_addresses():
    import re
    web = _web_text()
    server = (ROOT / "rasmai" / "web" / "web_server.py").read_text(encoding="utf-8")
    routes = (ROOT / "rasmai" / "web" / "dashboard" / "routes.py").read_text(encoding="utf-8")
    problems = []

    # the dashboard's own reads: the site asks /api/me/<name>, the bot answers /internal/me/<name>,
    # and a rename on one side alone leaves a button that quietly answers 404
    asked = set(re.findall(r"/api/me/([a-z-]+)", web))
    answered = set(re.findall(r'"/internal/me/([a-z-]+)"', routes))
    for name in sorted(asked - answered):
        problems.append(f"the site calls /api/me/{name} and the bot serves no /internal/me/{name}")
    for name in sorted(answered - asked):
        problems.append(f"the bot serves /internal/me/{name} and nothing on the site asks for it")

    # everything else the site proxies, against what the server dispatches, prefixes included
    served = set(re.findall(r'(?:(?:route\.)?path == |startswith\()"(/internal/[a-z/-]*)"', server))
    served |= {path.rstrip("/") for path in served}
    for target in sorted(set(re.findall(r'internal\(\s*[`"](/internal/[a-z-]+)', web))):
        if target == "/internal/me":
            continue
        if target not in served and target + "/" not in served:
            problems.append(f"the site proxies {target} and the bot dispatches no such path")

    # writes are allow-listed on both sides, and a list that drifts is a form that stops working
    allowed = re.search(r"\[((?:\"[a-z/-]+\",?\s*)+)\]\.includes\(path\)", web)
    # what handle_post lets through its gate, not every path its source mentions: beta feedback had a
    # branch of its own and was still turned away as not found, because the gate never listed it
    from rasmai.web.dashboard import routes as route_table
    posts = {path[len("/internal/me/"):] for path in route_table.WRITES}
    if not allowed:
        problems.append("the site no longer allow-lists which writes under /api/me it will forward")
    else:
        site_posts = set(re.findall(r'"([a-z/-]+)"', allowed.group(1)))
        for name in sorted(site_posts - posts):
            problems.append(f"the site forwards a write to /api/me/{name} that the bot does not accept")
        for name in sorted(posts - site_posts):
            problems.append(f"the bot accepts a write at /internal/me/{name} that the site will not forward")
    return problems


@check("the bot's side of the website answers, and refuses anyone without the shared secret")
def _seam_live():
    import json as jsonlib
    import urllib.error
    import urllib.request
    from rasmai.config import ADMIN_USER_ID
    from rasmai.web import web_server

    kept = web_server.INTERNAL_API_SECRET
    web_server.INTERNAL_API_SECRET = "check-only-secret"
    server = web_server.InternalApiServer(host="127.0.0.1", port=0)
    problems = []
    try:
        server.start()
        port = server.httpd.server_address[1]

        def ask(path, secret=True, user=None):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
            if secret:
                request.add_header("X-Rasmai-Internal", "check-only-secret")
            if user is not None:
                request.add_header("X-Rasmai-User", jsonlib.dumps(user))
            try:
                with urllib.request.urlopen(request, timeout=10) as answer:
                    return answer.status, answer.read()
            except urllib.error.HTTPError as error:
                return error.code, error.read()

        # the shared secret is the whole door: nothing behind it may answer without one
        for path in ("/internal/notice", "/internal/servers", "/internal/me", "/internal/me/admin"):
            status, _ = ask(path, secret=False)
            if status != 401:
                problems.append(f"{path} answered {status} with no shared secret, expected 401")

        # the container's health check is deliberately in front of that door
        status, _ = ask("/health", secret=False)
        if status != 200:
            problems.append(f"/health answered {status} without a secret; the container check reads it")

        # the two the site polls for every visitor, signed in or not
        for path in ("/internal/notice", "/internal/servers"):
            status, body = ask(path)
            if status != 200:
                problems.append(f"{path} answered {status}, expected 200")
                continue
            try:
                jsonlib.loads(body)
            except ValueError:
                problems.append(f"{path} did not answer with JSON")

        # a dashboard read with nobody signed in is a refusal, never a stack trace
        status, _ = ask("/internal/me/charts")
        if status not in (401, 404):
            problems.append(f"/internal/me/charts answered {status} with nobody signed in, expected a refusal")

        # the developer page is one account's, and everyone else is told it does not exist
        stranger = ("1" + ADMIN_USER_ID)[:19] if ADMIN_USER_ID.isdigit() else "100000000000000001"
        status, _ = ask("/internal/me/admin", user={"id": stranger})
        if status != 404:
            problems.append(f"/internal/me/admin answered {status} to a stranger, expected 404")
        # a user header that is not a Discord id is not a user, however well formed the JSON is
        status, _ = ask("/internal/me/charts", user={"id": "1"})
        if status != 401:
            problems.append(f"a made-up user id was accepted: /internal/me/charts answered {status}")

        for path in ("/internal/nothing-here", "/nope"):
            status, _ = ask(path)
            if status != 404:
                problems.append(f"{path} answered {status}, expected 404")
    finally:
        server.stop()
        web_server.INTERNAL_API_SECRET = kept
    return problems


@check("the site tells a browser to refuse http for a year, and nothing it serves needs http")
def _hsts():
    import re

    config = (ROOT / "web" / "next.config.ts").read_text(encoding="utf-8")
    problems = []
    found = re.search(r'max-age=(\d+)([^"]*)', config)
    if not found:
        problems.append("the site does not tell a browser to stay on https at all")
        return problems
    months = int(found.group(1)) / (30 * 24 * 60 * 60)
    if not 11.5 <= months <= 12.5:
        problems.append(f"the browser is told to stay on https for {months:.1f} months, not twelve")
    if "includeSubDomains" not in found.group(2):
        problems.append("the subdomains are left out, so one of them could still be served over http")
    if "Strict-Transport-Security" not in config:
        problems.append("the max-age is written somewhere that is not the header that carries it")
    # a page that asks for anything over http breaks outright once the browser refuses http
    if "upgrade-insecure-requests" not in config:
        problems.append("anything still written as http would be blocked rather than fetched over https")
    # and none of it may be sent while the site itself is being served over http, or a browser
    # pins a development machine to https for a year
    if "secure ?" not in config:
        problems.append("the header is sent even when the site is not on https, which pins a dev box for a year")
    return problems


@check("signing in to the site with Discord never revokes the token, which would uninstall Rasmai from the person's account")
def _discord_sign_in_keeps_install():
    source = (ROOT / "web" / "lib" / "discord.ts").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith(("//", "*", "/*")))
    if "revoke" in code:
        return ["web/lib/discord.ts revokes the sign-in token, which ends the whole authorization and takes the account install's commands with it"]
    return []


@check("the key behind every login code is written for its owner and nobody else")
def _secret_file():
    import os
    import pathlib
    import stat
    import tempfile

    import rasmai.security as sec

    problems = []
    # POSIX modes are not a thing on Windows, where os.chmod only moves the read-only bit, so the
    # bits are asserted where they exist and the primitive is asserted everywhere.
    source = (ROOT / "rasmai" / "security.py").read_text(encoding="utf-8")
    if "secret_path.write_text" in source:
        problems.append("the login secret is written under the umask, which on a normal host leaves "
                        "it readable by everyone on the machine")
    if "os.O_CREAT, 0o600" not in source.replace("os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600",
                                                 "os.O_CREAT, 0o600"):
        problems.append("the login secret is not created owner-only")

    was_path, was_cache = sec.DATABASE_PATH, sec._master_secret_cache
    was_env = os.environ.pop("MAIMAI_TOTP_SECRET", None)
    try:
        home = pathlib.Path(tempfile.mkdtemp())
        sec.DATABASE_PATH = home / "maimai.sqlite3"
        sec._master_secret_cache = None
        if len(sec.get_master_secret()) < 32:
            problems.append("the login secret is too short to sign anything with")
        key = home / "secret.key"
        if not key.is_file():
            problems.append("no login secret was written")
        elif os.name != "nt":
            mode = stat.S_IMODE(key.stat().st_mode)
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                problems.append(f"the login secret is readable beyond its owner: {oct(mode)}")
    finally:
        sec.DATABASE_PATH, sec._master_secret_cache = was_path, was_cache
        if was_env:
            os.environ["MAIMAI_TOTP_SECRET"] = was_env
    return problems


@check("a shared profile shows what the dashboard shows: the same traits, the same wheel, the same jackets")
def _shared_profile():
    from rasmai.engine.analysis import ChartIndex, ChartRef
    from rasmai.web.dashboard.public_profile import _cover_for, _traits_on_show

    problems = []

    # maimai stores a title with its spaces taken out, so an exact lookup finds a jacket for the
    # Japanese titles and none of the English ones. Two thirds of a best 50 came out blank.
    index = ChartIndex()
    index.add(ChartRef(title="New York Back Raise", chart_type="dx", difficulty="expert", constant=12.6,
                       level="12+", notes=0, genre="", artist="", cover="jacket.png", version=25, bpm=0.0))
    if _cover_for(index, "NewYorkBackRaise", "dx", "expert") != "jacket.png":
        problems.append("a title stored without its spaces found no jacket; the index matches it loosely and this did not")
    if _cover_for(index, "New York Back Raise", "dx", "expert") != "jacket.png":
        problems.append("a title stored as the database spells it found no jacket")
    if _cover_for(None, "New York Back Raise", "dx", "expert"):
        problems.append("a jacket was produced with no chart database loaded")

    # the page ranks and draws with the dashboard's own rules, which read these off every axis. Send
    # a trait without them and the wheel filters everything out and shows nothing at all.
    source = (ROOT / "rasmai" / "web" / "dashboard" / "public_profile.py").read_text(encoding="utf-8")
    for field in ("dimension", "verified", "leaning", "count", "offset", "english"):
        if f'"{field}"' not in source:
            problems.append(f"a shared trait does not carry {field}, which the site reads to rank and draw it")
    if "insights.notable(axes)" not in source:
        problems.append("the shared page is not handed the confirmed traits the dashboard is handed")

    if "insights.family_axes(axes)" not in source:
        problems.append("the shared page is sent no families, so its wheel is a different picture "
                        "of the same player from the dashboard's")

    # and one rule, in one place: picking again on the server is how the two pages came to disagree
    page = (ROOT / "web" / "components" / "PublicProfile.tsx").read_text(encoding="utf-8")
    if "twoSides" not in page:
        problems.append("the shared profile picks its own traits instead of using the dashboard's rule")
    if "traitFamilies" not in page:
        problems.append("the shared profile ignores the families, so its wheel is drawn on single traits")

    # who charted a song is not a skill, and the filter belongs with the rule rather than beside every
    # call to it: the shared profile forgot it and told a player they were good at a charter's name
    rules = (ROOT / "web" / "components" / "dash" / "traits" / "rules.ts").read_text(encoding="utf-8")
    inside = rules.split("export function twoSides", 1)
    if len(inside) < 2:
        problems.append("twoSides is gone; the two pages will drift apart again")
    elif "NOT_A_SKILL" not in inside[1].split(chr(10) + "}", 1)[0]:
        problems.append("twoSides does not drop the traits that are not skills, so a charter's name "
                        "can be named as something a player is good at")

    # a short address, and every door it has to pass through agreeing on what one looks like. A link
    # already passed around is 24 characters and has to keep working, so the bound was widened rather
    # than moved.
    from rasmai.web.dashboard.public_profile import SLUG_CHARS, SLUG_LENGTH, _fresh_slug
    import re as _re

    if SLUG_LENGTH > 12:
        problems.append(f"a share address is {SLUG_LENGTH} characters, which is no longer short")
    if len(SLUG_CHARS) ** SLUG_LENGTH < 10 ** 15:
        problems.append(f"only {len(SLUG_CHARS) ** SLUG_LENGTH:,} addresses exist, which is guessable")
    fresh = _fresh_slug()
    # the file holds other addresses of its own, so read the bound out of the slug lookup itself
    lookup = (ROOT / "rasmai" / "storage" / "db" / "accounts.py").read_text(encoding="utf-8")
    bot = _re.search(r'\[A-Za-z0-9_-\]\{(\d+),(\d+)\}', lookup.split("def account_by_share_slug", 1)[-1])
    if not bot or int(bot.group(1)) > SLUG_LENGTH or int(bot.group(2)) < 24:
        problems.append("the bot and the site disagree about what a share address looks like")
    for name, path in (("the public API", ROOT / "web" / "app" / "api" / "public" / "[slug]" / "route.ts"),
                       ("the page", ROOT / "web" / "app" / "p" / "[slug]" / "page.tsx"),
                       ("the card", ROOT / "web" / "app" / "p" / "[slug]" / "card.png" / "route.tsx")):
        text = path.read_text(encoding="utf-8")
        bounds = _re.search(r"const SLUG = /\^\[A-Za-z0-9_-\]\{(\d+),(\d+)\}\$/", text)
        if not bounds:
            problems.append(f"{name} does not say what a share address looks like")
            continue
        low, high = int(bounds.group(1)), int(bounds.group(2))
        if low > SLUG_LENGTH:
            problems.append(f"{name} refuses a {SLUG_LENGTH}-character address, which is what is handed out")
        if high < 24:
            problems.append(f"{name} refuses the 24-character addresses already passed around")
    if not _re.fullmatch(r"[A-Za-z0-9]{%d}" % SLUG_LENGTH, fresh):
        problems.append(f"a fresh share address is not letters and digits: {fresh!r}")

    # reading a profile is an ordinary page view and costs several calls between the page, its
    # picture and whoever opens the link. Counting those against the sign-in allowance shut the
    # preview out after ten of them.
    from rasmai.security import public_limiter, _login_limiter
    if public_limiter.limit <= _login_limiter.limit:
        problems.append("a shared profile is read on the sign-in allowance, which a single link "
                        "preview can exhaust on its own")
    served = (ROOT / "rasmai" / "web" / "web_server.py").read_text(encoding="utf-8")
    if "public_limiter.allow" not in served:
        problems.append("shared profiles are not read on their own allowance")
    for page in ("web/app/p/[slug]/page.tsx", "web/app/p/[slug]/card.png/route.tsx"):
        if "client" not in (ROOT / page).read_text(encoding="utf-8"):
            problems.append(f"{page} asks the bot without saying who for, so every reader shares one allowance")

    del _traits_on_show
    return problems


@check("what a shared link turns into in Discord is the owner's to set, and the card reads the setting")
def _card_choices():
    import pathlib as _pathlib
    import re
    import tempfile

    from rasmai.bot.state.prefs import CARD_FIELDS, CARD_VISUALS, EMBED_FIELDS
    from rasmai.storage.db import connection as store
    from rasmai.web.dashboard.public_profile import set_sharing, sharing_payload

    was, store.DATABASE_PATH = store.DATABASE_PATH, _pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    problems = []
    try:
        # the switches round-trip, and the ones left alone are left alone
        state = set_sharing("u1", True, None, False, {"shareSlug": "abcdefghij"},
                            card={"chart": False, "plays": True}, embed={"region": False})
        if state["card"]["chart"] is not False or state["card"]["plays"] is not True:
            problems.append(f"a card switch did not stick: {state['card']}")
        if state["embed"]["region"] is not False:
            problems.append(f"an embed switch did not stick: {state['embed']}")
        if state["card"]["gain"] is not True:
            problems.append("switching one thing off switched another off with it")
        again = sharing_payload("u1", {"shareSlug": "abcdefghij"})
        if again["card"] != state["card"] or again["embed"] != state["embed"]:
            problems.append("the Account tab is shown something other than what was saved")

        # the colour is the one field that is not a yes or a no, and it is drawn straight into the
        # markup of a picture, so anything that is not a colour has to come back as the one they had
        for bad in ("red", "#12345", "javascript:alert(1)", "", "#gggggg"):
            kept = set_sharing("u1", None, None, False, {"shareSlug": "abcdefghij"}, colour=bad)["colour"]
            if not re.fullmatch(r"#[0-9a-f]{6}", kept):
                problems.append(f"{bad!r} was accepted as a colour and came back as {kept!r}")
        if set_sharing("u1", None, None, False, {"shareSlug": "abcdefghij"}, colour="#21C3E3")["colour"] != "#21c3e3":
            problems.append("a colour the browser sent in capitals was refused")

        # a picture nobody drew is a blank card, and anything unknown falls back rather than failing
        for bad in ("rainbow", "", "<script>", None):
            kept = set_sharing("u1", None, None, False, {"shareSlug": "abcdefghij"}, visual=bad)["visual"]
            if kept not in CARD_VISUALS:
                problems.append(f"{bad!r} was accepted as a picture and came back as {kept!r}")
        if set_sharing("u1", None, None, False, {"shareSlug": "abcdefghij"}, visual="best50")["visual"] != "best50":
            problems.append("a picture the window offered was refused")

        # two of them need a section the profile may not be carrying, and the window has to say so
        offered = {row["key"]: row for row in set_sharing("u1", None, {"traits": False}, False,
                                                          {"shareSlug": "abcdefghij"})["visuals"]}
        if set(offered) != set(CARD_VISUALS):
            problems.append(f"the window is offered {sorted(offered)}, not the pictures that exist")
        if offered["traits"]["ready"]:
            problems.append("the traits wheel is offered while the profile does not carry its traits")
        if not offered["curve"]["ready"] or not offered["figures"]["ready"]:
            problems.append("a picture that needs nothing was marked unavailable")

        # the name and the rating are what makes it their profile, so neither is a switch
        for banned in ("name", "rating"):
            if banned in CARD_FIELDS or banned in EMBED_FIELDS:
                problems.append(f"{banned} can be switched off, and then the card is nobody's profile")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False

    # a profile that answers has to say what it chose, or the card falls back for everybody
    shared = (ROOT / "rasmai" / "web" / "dashboard" / "public_profile.py").read_text(encoding="utf-8")
    if '"card": {name: bool' not in shared.replace("'", '"'):
        problems.append("a shared profile does not carry its card choices, so the card cannot read them")

    # and both halves of the site have to read them
    picture = (ROOT / "web" / "app" / "p" / "[slug]" / "card.png" / "route.tsx").read_text(encoding="utf-8")
    page = (ROOT / "web" / "app" / "p" / "[slug]" / "page.tsx").read_text(encoding="utf-8")
    if "shared.card" not in picture:
        problems.append("the picture ignores what its owner chose to put on it")
    for source, what in ((picture, "the picture"), (page, "the unfurl")):
        if "#[0-9a-f]{6}" not in source:
            problems.append(f"{what} takes a colour from the payload without checking it is one")

    # Discord keeps its own copy of a picture, keyed on the address. A rating is read every few days
    # but a picture changes the moment somebody picks a different one, so the address has to carry
    # the choices as well: without them the proxy went on serving the old picture and only the
    # accent colour, which lives in the payload rather than the picture, appeared to change.
    stamp = page.split("function card(", 1)[-1].split(chr(10) + "}", 1)[0]
    for field in ("profile.card", "profile.embed", "profile.colour", "profile.visual"):
        if field not in stamp:
            problems.append(f"the card address does not move when {field.split('.')[-1]} changes, "
                            "so Discord keeps showing the old picture")

    # and the picture is drawn larger than it is shown, or it arrives blown up from half the size
    if "SCALE" not in picture or "const u = " not in picture:
        problems.append("the picture is drawn at the size it is shown, which reads as soft")

    # the window asks this site for the preview rather than the address the bot publishes: those can
    # differ, and the page only allows pictures from itself
    sheet = (ROOT / "web" / "components" / "dash" / "EmbedCard.tsx").read_text(encoding="utf-8")
    if "`/p/${slug}/card.png" not in sheet:
        problems.append("the preview asks another address for the picture, which the page will refuse")
    if "showModal" not in sheet:
        problems.append("the customiser is not a window of its own")

    # Satori draws neither a fragment nor a text node inside an svg. Both fail as a blank card with
    # nothing said anywhere a reader would look, so the pictures are arrays and the labels are html.
    if "<text" in picture:
        problems.append("a picture draws an svg text node, which Satori refuses outright")
    if "<>" in picture.split("<svg", 1)[-1].split("</svg>", 1)[0]:
        problems.append("a picture puts a fragment inside its svg, which Satori refuses outright")
    if "profile.embed" not in page or "card?.on === false" not in page:
        problems.append("the unfurl ignores what its owner chose to put on it")

    # a picture Discord gives the full width to should not be tall beside it. Measured in the card's
    # own units, which is the shape: the file itself is drawn at a multiple of them.
    size = re.search(r"const CARD = \{ width: (\d+), height: (\d+) \}", picture)
    if not size:
        problems.append("the picture does not say what shape it is")
    elif int(size.group(2)) > 460:
        problems.append(f"the card picture is {size.group(2)} tall beside {size.group(1)} wide, "
                        "which pushes the text off the screen")
    return problems


@check("a link to the site unfurls in Discord as the card we wrote, and never as somebody's own markup")
def _link_embeds():
    import json
    import re

    problems = []
    source = (ROOT / "web" / "lib" / "embed.ts").read_text(encoding="utf-8")

    # Discord reads 3,000 bytes and renders 40 components, and refuses the payload without saying so.
    # https://discord.com/developers/docs/link-previews/component-embeds
    for name, wanted in (("LIMIT", 3000), ("PIECES", 40), ("LINK", 5)):
        found = re.search(rf"^const {name} = (\d+);", source, re.M)
        if not found or int(found.group(1)) != wanted:
            problems.append(f"{name} in embed.ts is {found and found.group(1)}, and Discord's rule is {wanted}")

    # the payload sits inside a script tag, so a title carrying "</script>" would end the tag early
    if r"\u003c" not in source:
        problems.append("the JSON is not escaping '<', so text in an embed could close its own script tag")

    # and a name is text, not markup: a player called "[x](http://evil)" must not plant a link
    if "replace(/([" not in source:
        problems.append("nothing is escaping markdown, so a player's name could carry formatting or a link")

    # the pages that should carry one, and the fallback that stands whenever this payload cannot
    for page, why in ((ROOT / "web" / "app" / "page.tsx", "the front page"),
                      (ROOT / "web" / "app" / "p" / "[slug]" / "page.tsx", "a shared profile")):
        text = page.read_text(encoding="utf-8")
        if "DiscordEmbed" not in text:
            problems.append(f"{why} has no component embed, so its links unfurl as the plain card")

    # a shared profile card says no more than the page's own header does to anyone holding the link
    shared = (ROOT / "web" / "app" / "p" / "[slug]" / "page.tsx").read_text(encoding="utf-8")
    for section in ("best50", "recent"):
        if f'"{section}"' in shared or f".{section}" in shared:
            problems.append(f"the shared-profile card reaches for {section}; a card in a channel is "
                            "seen by everyone there, and that section belongs on the page")

    # the tag Discord actually looks for, spelled exactly
    tag = (ROOT / "web" / "components" / "DiscordEmbed.tsx").read_text(encoding="utf-8")
    for wanted in ('id="discord:component-embed"', 'type="application/json"'):
        if wanted not in tag:
            problems.append(f"the embed tag is missing {wanted}, and Discord matches both exactly")

    # a section without something off to the side is refused outright, and Discord says so only in its
    # own debugger: BASE_TYPE_REQUIRED, and the link shows no card at all. The type carries the rule.
    if "accessory?: " in source:
        problems.append("a section's accessory is optional in the types, and Discord requires one: "
                        "leave it out and the whole embed is refused")
    built = source.split("export function headline", 1)[-1].split(chr(10) + "}", 1)[0]
    if "accessory" not in built:
        problems.append("headline builds a section without an accessory, which Discord refuses")

    # Discord keeps its own copy of every picture, keyed on the address and held far longer than the
    # preview is. A card address that never changes goes on showing last week's rating.
    profile = (ROOT / "web" / "app" / "p" / "[slug]" / "page.tsx").read_text(encoding="utf-8")
    if "card.png?v=" not in profile:
        problems.append("the card address carries nothing that moves when the profile does, so "
                        "Discord's copy of it never gets replaced")

    # a button may only be a link, and only ever carry these keys
    button = re.search(r"type: 2, style: LINK, label: [^}]+}", source)
    if not button:
        problems.append("buttons are not built as link buttons; any other style invalidates the payload")
    elif set(re.findall(r"(\w+):", button.group(0))) - {"type", "style", "label", "url", "emoji", "disabled"}:
        problems.append(f"a button carries a key Discord refuses: {button.group(0)}")

    del json
    return problems


@check("a tester's word on a beta is kept once, checked before it is stored, and reaches the developer page")
def _beta_feedback():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    from rasmai.web.dashboard.beta import FEATURES, beta_state

    problems = []
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    try:
        from rasmai.storage.db import (VERDICTS, beta_feedback, beta_feedback_tally, set_beta_feedback)
        from rasmai.storage.db.feedback import SAID_LIMIT
        feature = next(iter(FEATURES))
        user = "feedback-check-user"

        # a verdict nobody offered is refused rather than written down, because the page reads this by eye
        if set_beta_feedback(user, feature, "brilliant") is not None:
            problems.append("a verdict that is not one of the three was stored anyway")
        if beta_feedback():
            problems.append("a refused verdict was written down regardless")

        for verdict in VERDICTS:
            if set_beta_feedback(user, feature, verdict) is None:
                problems.append(f"{verdict!r} is offered as a verdict and refused when given")
        if len(beta_feedback()) != 1:
            problems.append("saying it again left a second row, so the page shows one person twice")

        # a note is a note: whitespace collapsed and anything past the limit cut rather than refused
        stored = set_beta_feedback(user, feature, "better", "  a   long  " + "x" * (SAID_LIMIT * 2))
        if stored is None or len(stored["said"]) != SAID_LIMIT:
            problems.append(f"a note was not cut to {SAID_LIMIT}, so one person can fill the table")

        tally = beta_feedback_tally().get(feature, {})
        if tally.get("better") != 1 or sum(tally.values()) != 1:
            problems.append(f"the count of what people said does not add up: {tally}")

        # the page shows a person what they already said, so they are not guessing whether it saved
        said = {row["key"]: row.get("said") for row in beta_state(user)["features"]}
        if not said.get(feature):
            problems.append("the beta panel does not carry back what this person already said")
        for key in FEATURES:
            if key != feature and said.get(key):
                problems.append(f"{key} was given somebody else's answer")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False

    # the developer page is where it is read, and it is the one page nobody else may open
    panel = (ROOT / "web" / "components" / "dash" / "admin" / "Panel.tsx").read_text(encoding="utf-8")
    if "betaFeedback" not in panel or "betaTally" not in panel:
        problems.append("the developer page does not show what anybody said about a beta")
    admin = (ROOT / "rasmai" / "web" / "dashboard" / "admin.py").read_text(encoding="utf-8")
    if "beta_feedback" not in admin:
        problems.append("the developer page is never sent the feedback to show")
    return problems


def _fake_image_get(answers, calls):
    """A stand-in for requests.get that answers from ``answers`` by address and notes every call."""
    import io

    class Answer:
        def __init__(self, status, kind, body):
            self.status_code, self.headers, self.raw = status, {"Content-Type": kind}, io.BytesIO(body)
            read = self.raw.read
            self.raw.read = lambda size=-1, decode_content=False: read(size)

        def close(self):
            pass

    def get(url, **kwargs):
        calls.append(url)
        return Answer(*answers.get(url, (404, "text/html", b"")))
    return get


@check("the name plate is read off a page shaped like maimai DX NET's, relative or not, and nothing is made up")
def _nameplate_parse():
    from rasmai.scraping.scraper.profile import ProfilePages, parse_nameplate_url
    problems = []
    base = "https://maimaidx-eng.com"
    plate = f"{base}/maimai-mobile/img/NamePlate/9b1f0c6a2d3e4f50.png"
    # the collection page: the SETTING box shows the plate in use first, then every plate owned
    collection = ('<div class="see_through_block m_15 m_t_0 p_10 t_l f_0 p_r"><div class="f_0">'
                  f'<img src="{plate}" class="w_396 m_r_10"></div></div>'
                  '<div class="see_through_block m_15 p_10"><form action="/maimai-mobile/collection/nameplate/set/">'
                  f'<img src="{base}/maimai-mobile/img/NamePlate/000000000000aaaa.png" class="w_396 m_r_10">'
                  '</form></div>')
    found = parse_nameplate_url(collection, base)
    if found != plate:
        problems.append(f"the plate in use was not read off the collection page: {found!r}")
    if parse_nameplate_url('<img class="w_396 m_r_10" src="/maimai-mobile/img/NamePlate/9b1f0c6a2d3e4f50.png">', base) != plate:
        problems.append("a plate given as a path was not made into a full address")
    if parse_nameplate_url('<img class="w_396 m_r_10" src="/maimai-mobile/img/Frame/abc.png">', base):
        problems.append("a frame was taken for a name plate")
    player_page = ('<div class="see_through_block m_15 m_t_0 p_10 t_l f_0 p_r">'
                   f'<img src="{base}/maimai-mobile/img/Icon/3f4e4f3f4aa69f9b.png" class="w_112 f_l">'
                   '<div class="name_block f_l f_16">Nek</div><div class="rating_block">13551</div></div>')
    player, _ = ProfilePages()._parse_official_player_info(player_page, "intl")
    if player.nameplate_url:
        problems.append(f"a profile page with no plate on it came back with one: {player.nameplate_url}")
    player, _ = ProfilePages()._parse_official_player_info(player_page + f'<img src="{plate}">', "intl")
    if player.nameplate_url != plate:
        problems.append("a plate on the profile page itself was not kept with the profile")
    return problems


@check("a name plate is only ever fetched from maimai DX NET, and a picture too big to be one is refused")
def _nameplate_cache():
    import tempfile, pathlib
    from rasmai.scraping.scraper import nameplates
    problems = []
    was_dir = nameplates.NAMEPLATE_DIR
    nameplates.NAMEPLATE_DIR = pathlib.Path(tempfile.mkdtemp())
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    good = "https://maimaidx-eng.com/maimai-mobile/img/NamePlate/9b1f0c6a2d3e4f50.png"
    huge = "https://maimaidx.jp/maimai-mobile/img/NamePlate/0000000000000001.png"
    calls = []
    with stub_get(nameplates, _fake_image_get({good: (200, "image/png", png),
                                               huge: (200, "image/png", png + b"\0" * (2 * 1024 * 1024))}, calls)):
        try:
            for stranger in ("https://evil.example/maimai-mobile/img/NamePlate/9b1f0c6a2d3e4f50.png",
                             "https://maimaidx-eng.com.evil.example/maimai-mobile/img/NamePlate/x.png",
                             "http://maimaidx-eng.com/maimai-mobile/img/NamePlate/9b1f0c6a2d3e4f50.png",
                             "https://maimaidx-eng.com/maimai-mobile/img/Icon/3f4e4f3f4aa69f9b.png"):
                if nameplates.cache_nameplate(stranger) or nameplates.nameplate_key(stranger):
                    problems.append(f"{stranger} was taken for a maimai DX NET name plate")
            if calls:
                problems.append(f"a refused address was still fetched: {calls}")
            if nameplates.cache_nameplate(huge) or list(nameplates.NAMEPLATE_DIR.glob("*")):
                problems.append("a two-megabyte answer was kept as a name plate")
            key = nameplates.cache_nameplate(good)
            path = nameplates.nameplate_path(key)
            if not key or path is None or path.read_bytes() != png:
                problems.append("a plate from maimai DX NET was not cached")
            calls.clear()
            nameplates.cache_nameplate(good)
            if calls:
                problems.append("a cached plate was fetched again")
        finally:
            nameplates.NAMEPLATE_DIR = was_dir
    return problems


@check("a shared profile carries the owner's name plate when there is one, and nothing when there is not")
def _nameplate_public():
    import base64, tempfile, pathlib
    from rasmai.scraping.scraper import nameplates
    from rasmai.storage.db import connection as store
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    was_dir = nameplates.NAMEPLATE_DIR
    nameplates.NAMEPLATE_DIR = pathlib.Path(tempfile.mkdtemp())
    problems = []
    with stub_get(nameplates, _fake_image_get({}, [])):
        try:
            from rasmai.storage.db import get_connected_account, upsert_connected_account
            from rasmai.web.dashboard.public_profile import public_payload, set_sharing
            plate = "https://maimaidx-eng.com/maimai-mobile/img/NamePlate/9b1f0c6a2d3e4f50.png"
            gone = "https://maimaidx-eng.com/maimai-mobile/img/NamePlate/00000000000000ff.png"
            key = nameplates.nameplate_key(plate)
            (nameplates.NAMEPLATE_DIR / f"{key}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            avatar = base64.b64encode(b"\x89PNG\r\n\x1a\nicon").decode("ascii")
            shown = {}
            for user, url in (("with", plate), ("without", ""), ("unreachable", gone)):
                upsert_connected_account(user, "intl", "cookie://x", official_profile={
                    "name": user, "rating": 13000, "avatar_base64": avatar, "nameplate_url": url})
                profile = (get_connected_account(user) or {}).get("officialProfile") or {}
                # the avatar is lifted out into its own column; the plate has to stay behind in the JSON
                if profile.get("nameplate_url", "") != url or profile.get("avatar_base64") != avatar:
                    problems.append(f"{user}: the plate or the avatar did not come back as stored: {profile.get('nameplate_url')!r}")
                state = set_sharing(user, True, account=get_connected_account(user))
                shown[user] = public_payload(state["url"].rsplit("/", 1)[-1]) or {}
            if shown["with"].get("nameplate") != f"/api/nameplate/{key}":
                problems.append(f"the plate is missing from a profile that has one: {shown['with'].get('nameplate')!r}")
            for user in ("without", "unreachable"):
                if "nameplate" in shown[user]:
                    problems.append(f"a profile {user} a plate still carries one: {shown[user]['nameplate']!r}")
        finally:
            store.DATABASE_PATH = was
            store._database_ready = False
            nameplates.NAMEPLATE_DIR = was_dir
    return problems


@check("the status payload speaks Statuspage's words, ranks them, and counts people waiting on a build but not warm-ups")
def _statuspage():
    import pathlib
    import tempfile
    from concurrent.futures import Future

    from rasmai.storage.db import connection as store
    from rasmai.web import statuspage as S
    from rasmai.web.dashboard import analysis as A

    problems = []
    if S.worst(["operational", "degraded_performance", "under_maintenance"]) != "degraded_performance":
        problems.append("a degraded component did not outrank one under maintenance")
    if S.worst(["operational", "major_outage", "partial_outage"]) != "major_outage" or S.worst([]) != "operational":
        problems.append("the worst state, or the state of nothing at all, came out wrong")

    def job(priority, taken):
        future = Future()
        future.priority, future.taken = priority, taken
        return future

    held = dict(A._pending)
    A._pending.clear()
    try:
        A._pending.update({"asked": job(A.NOW, False), "warm": job(A.LATER, False), "building": job(A.NOW, True)})
        got = S._analysis()
        if got["waiting"] != 1 or got["state"] != S.OPERATIONAL:
            problems.append(f"one person waiting, one warm-up and one running counted as {got['waiting']} waiting, {got['state']}")
        A._pending.update({f"line-{i}": job(A.NOW, False) for i in range(S.LONG_LINE + 1)})
        if S._analysis()["state"] != S.DEGRADED:
            problems.append("a long line of people waiting did not read as degraded")
    finally:
        A._pending.clear()
        A._pending.update(held)

    was = store.DATABASE_PATH
    try:
        store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "s.sqlite3", False
        payload = S.status_payload()
        words = {S.OPERATIONAL, S.MAINTENANCE, S.DEGRADED, S.PARTIAL, S.MAJOR}
        if payload["components"].get("database") != S.OPERATIONAL or payload["metrics"].get("accounts") != 0:
            problems.append(f"an empty, working database read as {payload['components'].get('database')!r}, {payload['metrics'].get('accounts')!r} accounts")
        if not set(payload["components"].values()) <= words or payload["status"] not in words:
            problems.append(f"a state outside Statuspage's vocabulary: {payload['components']}")
        if "diskFreeMb" not in payload["metrics"] or "uptimeSeconds" not in payload["metrics"]:
            problems.append(f"the payload had no free disk space or uptime: {payload['metrics']}")

        import asyncio
        import threading
        import time
        from datetime import datetime, timedelta
        from rasmai.bot import core
        from rasmai.scraping.otoge.db import REFRESH_AFTER

        # images: a few renders failing in a row is a partial outage, one is not
        kept_render = core.RENDER_HEALTH["failing"]
        try:
            core.RENDER_HEALTH["failing"] = 1
            if S.status_payload()["components"].get("images") != S.OPERATIONAL:
                problems.append("one failed render took the images down")
            core.RENDER_HEALTH["failing"] = S.RENDER_FAILS
            if S.status_payload()["components"].get("images") != S.PARTIAL:
                problems.append("renders failing in a row did not read as a partial outage of the images")
        finally:
            core.RENDER_HEALTH["failing"] = kept_render

        # disk: under the floor, a working database reads as degraded
        kept_floor = S.LOW_DISK_MB
        try:
            S.LOW_DISK_MB = 10 ** 12
            if S.status_payload()["components"].get("database") != S.DEGRADED:
                problems.append("a disk nearly full did not read as a degraded database")
        finally:
            S.LOW_DISK_MB = kept_floor

        # chart data: fresh is fine, a few refreshes missed or never fetched is degraded
        kept_stamp = S.CHART_STAMP
        folder = pathlib.Path(tempfile.mkdtemp())
        try:
            S.CHART_STAMP = str(folder / "last_update.txt")
            for age, expect in ((timedelta(hours=5), S.OPERATIONAL), (2 * REFRESH_AFTER + timedelta(days=1), S.DEGRADED)):
                pathlib.Path(S.CHART_STAMP).write_text((datetime.now() - age).isoformat())
                got = S._charts()
                if got["state"] != expect or got["ageHours"] != round(age.total_seconds() / 3600):
                    problems.append(f"chart data {age} old read as {got}, not {expect}")
            S.CHART_STAMP = str(folder / "missing.txt")
            if S._charts()["state"] != S.DEGRADED:
                problems.append("chart data never fetched did not read as degraded")
        finally:
            S.CHART_STAMP = kept_stamp

        # the bot's own loop: one that answers is a lag in ms, one that is stuck is the full wait
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True).start()
        kept_loop, kept_stuck = core.bot.loop, S.STUCK_LOOP_S
        try:
            core.bot.loop = loop
            lag = S.loop_lag_ms()
            if lag is None or not 0 <= lag < 500:
                problems.append(f"a free loop answered in {lag} ms")
            S.STUCK_LOOP_S = 0.2
            loop.call_soon_threadsafe(time.sleep, 0.6)
            if S.loop_lag_ms() != 200:
                problems.append("a stuck loop was not reported as stuck")
        finally:
            core.bot.loop, S.STUCK_LOOP_S = kept_loop, kept_stuck
            loop.call_soon_threadsafe(loop.stop)
        core.bot.loop = kept_loop
        if S.loop_lag_ms() is not None:
            problems.append("a bot that is not running reported a loop lag")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("the status history counts a stretch with no sample as down, and a slow component as still up")
def _status_history():
    import pathlib
    import tempfile
    from datetime import datetime, timedelta, timezone

    from rasmai.storage.db import connection as store
    from rasmai.storage.db import status

    problems = []
    was = store.DATABASE_PATH
    try:
        store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "h.sqlite3", False
        if status.status_history()["days"]:
            problems.append("a database with no samples reported days")
        day = datetime(2026, 9, 29, tzinfo=timezone.utc)
        now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
        for slot in range(288):
            at = day + timedelta(minutes=5 * slot)
            if 120 <= slot < 132:
                continue                    # an hour with the bot not running
            state = "degraded_performance" if slot < 3 else "operational"
            status.record_status_sample({"components": {"bot": state}, "metrics": {"gatewayMs": 90, "analysisWaiting": 0}}, at)
        history = status.status_history(now)
        first, today = history["days"][0], history["days"][-1]
        got = first["components"]["bot"]
        if (first["day"], first["expected"], first["samples"], got["up"], got["degraded"]) != ("2026-09-29", 288, 276, 276, 3):
            problems.append(f"the day with a gap read as {first}")
        if (today["day"], today["expected"], today["samples"]) != ("2026-09-30", 144, 0):
            problems.append(f"the day the bot has not recorded since midnight read as {today}")
        # the last twenty-four hours before noon on the 30th hold the second half of the 29th: 144 slots
        if len(history["recent"]) != 144 or history["since"] != "2026-09-29T00:00:00+00:00":
            problems.append(f"{len(history['recent'])} recent readings, first sample {history['since']}")
    finally:
        store.DATABASE_PATH, store._database_ready = was, False
    return problems


@check("the bot's side of the website is not opened to the network without a secret, and an odd secret header is a refusal")
def _seam_fails_closed():
    import http.client
    import urllib.error
    import urllib.request
    from rasmai.web import web_server

    kept = web_server.INTERNAL_API_SECRET
    problems = []
    servers = []
    try:
        # no secret and a host the network can reach: the API must not start (port 0 so nothing collides)
        web_server.INTERNAL_API_SECRET = ""
        open_door = web_server.InternalApiServer(host="0.0.0.0", port=0)
        servers.append(open_door)
        open_door.start()
        if open_door.httpd is not None or open_door.thread is not None:
            problems.append("the internal API started on 0.0.0.0 with no shared secret")

        # a header that is not ASCII is a wrong secret, not an error in the handler
        web_server.INTERNAL_API_SECRET = "check-only-secret"
        server = web_server.InternalApiServer(host="127.0.0.1", port=0)
        servers.append(server)
        server.start()
        port = server.httpd.server_address[1]
        for secret, want in (("café", 401), ("check-only-secret", 200)):
            request = urllib.request.Request(f"http://127.0.0.1:{port}/internal/notice", headers={"X-Rasmai-Internal": secret})
            try:
                with urllib.request.urlopen(request, timeout=10) as answer:
                    got = answer.status
            except urllib.error.HTTPError as error:
                got = error.code
            except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
                got = f"no answer ({error})"
            if got != want:
                problems.append(f"/internal/notice with the header {secret!r} answered {got}, expected {want}")
    finally:
        for each in servers:
            each.stop()
        web_server.INTERNAL_API_SECRET = kept
    return problems


@check("International and Japan accounts are sent to a login, a China one is told why at every step, and a Japan sign-in is kept encrypted")
def _regions():
    import json as jsonlib
    import pathlib
    import tempfile
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from rasmai import config
    from rasmai.config import SUPPORTED_REGIONS, region_supported, unsupported_region_text
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.security import create_opaque_user_id, decrypt_token, encrypt_token, read_sega_id_token
    from rasmai.storage.db import connection as store
    from rasmai.web import web_server

    problems = []
    if SUPPORTED_REGIONS != ("intl", "jp") or not region_supported("jp") or region_supported("cn"):
        problems.append(f"the supported regions are {SUPPORTED_REGIONS}; International and Japan have a sign-in, China has none")
    if "WeChat" not in unsupported_region_text("cn"):
        problems.append("the China explanation does not say how that region signs in")
    try:
        MaimaiRatingAnalyzer().fetch_official_player_profile("cookie://" + "a" * 64, "cn")
        problems.append("a China account was sent somewhere to sign in")
    except ValueError as error:
        if "China" not in str(error):
            problems.append(f"refusing a China account did not say why: {error}")

    # a stored sign-in only opens on the account it was stored for
    sealed = encrypt_token("segaid://x", "100000000000000001")
    if not sealed.startswith("enc2:") or decrypt_token(sealed, "100000000000000001") != "segaid://x":
        problems.append("a stored sign-in is not written with AES-256-GCM, or does not open again")
    if decrypt_token(sealed, "100000000000000002"):
        problems.append("a stored sign-in moved onto another account's row still opened")

    # the bookmarklet runs on SEGA's international page, so its own words are all a player sees there
    script = (ROOT / "web" / "app" / "api" / "login.js" / "route.ts").read_text(encoding="utf-8")
    if "if(region!=='intl')" not in script:
        problems.append("the bookmarklet sends a Japan or China login on instead of saying where it goes")
    if "SEGA ID" not in script or "Japanese or Chinese" not in script:
        problems.append("the bookmarklet's messages do not send a Japan player to the SEGA ID sign-in")
    # the error words live in the translation files, one set per language
    import json
    for lang in ("en", "ja"):
        errors = json.loads((ROOT / "web" / "messages" / f"{lang}.json").read_text(encoding="utf-8")).get("errors", {})
        for kind in ("region", "credentials"):
            if not all(errors.get(kind, {}).get(part) for part in ("headline", "detail", "hint")):
                problems.append(f"the site has no {lang} words for the {kind} refusal, so it would show 'Something went wrong'")
    if 'method === "segaid"' not in (ROOT / "web" / "app" / "connect" / "page.tsx").read_text(encoding="utf-8"):
        problems.append("the connect page has no SEGA ID form for a Japan code")

    # a stand-in for maimaidx.jp: the sign-in page hands out a form token as _t, the right SEGA ID and
    # password send on to the Aime list, card 1 opens and the profile page answers
    right = {"segaId": "player@example.jp", "password": "correct horse:battery/staple"}
    player_page = ('<div class="see_through_block m_15 m_t_0 p_10 t_l f_0 p_r">'
                   '<div class="name_block f_l f_16">ＪＰプレイヤー</div><div class="rating_block">15123</div></div>')

    class FakeJapan(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _cookies(self):
            return dict(part.strip().split("=", 1) for part in (self.headers.get("Cookie") or "").split(";") if "=" in part)

        def _answer(self, status, body="", location="", cookie=""):
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            if cookie:
                self.send_header("Set-Cookie", f"{cookie}; Path=/")
            data = body.encode("utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path)
            cookies = self._cookies()
            if path.path == "/maimai-mobile/":
                self._answer(200, "<form><input name='token' value='form-token'></form>", cookie="_t=form-token")
            elif path.path == "/maimai-mobile/aimeList/submit/":
                card = urllib.parse.parse_qs(path.query).get("idx", [""])[0]
                if cookies.get("signed") == "1" and card == "0":
                    self._answer(302, location="/maimai-mobile/home/", cookie="userId=opened")
                else:
                    self._answer(302, location="/maimai-mobile/error/")
            elif path.path == "/maimai-mobile/home/":
                self._answer(200, "home")
            elif path.path == "/maimai-mobile/playerData/" and cookies.get("userId") == "opened":
                self._answer(200, player_page)
            else:
                self._answer(404, "not here")

        def do_POST(self):
            form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()))
            if (self.path == "/maimai-mobile/submit/" and form.get("token") == "form-token"
                    and form.get("segaId") == right["segaId"] and form.get("password") == right["password"]):
                self._answer(302, location=f"http://127.0.0.1:{fake.server_address[1]}/maimai-mobile/aimeList/", cookie="signed=1")
            else:
                self._answer(200, "<form><input name='token' value='form-token'></form>")

    fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeJapan)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    real_jp = config.MAIMAI_BASE_URLS["jp"]
    config.MAIMAI_BASE_URLS["jp"] = f"http://127.0.0.1:{fake.server_address[1]}"

    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    kept = web_server.INTERNAL_API_SECRET
    web_server.INTERNAL_API_SECRET = "check-only-secret"
    # neither the maintenance clock nor a first score read may run against the stand-in
    kept_down, kept_start = web_server.dashboard.servers_down_note, web_server.dashboard.refresh_jobs.start
    web_server.dashboard.servers_down_note = lambda region="intl": ""
    web_server.dashboard.refresh_jobs.start = lambda *args, **kwargs: None
    server = web_server.InternalApiServer(host="127.0.0.1", port=0)
    try:
        from rasmai.storage.db import get_connected_account, issue_login_code, peek_login_code
        server.start()
        port = server.httpd.server_address[1]

        def ask(path, body=None):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                             data=jsonlib.dumps(body).encode() if body is not None else None,
                                             headers={"X-Rasmai-Internal": "check-only-secret",
                                                      "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=30) as answer:
                    return answer.status, jsonlib.loads(answer.read() or b"{}")
            except urllib.error.HTTPError as error:
                return error.code, jsonlib.loads(error.read() or b"{}")

        user_id = "100000000000000077"
        opaque = create_opaque_user_id(user_id)
        code = issue_login_code(user_id, "cn")
        status, body = ask(f"/internal/connect-info?code={code}&user={opaque}")
        if status != 400 or body.get("kind") != "region" or body.get("loginLink"):
            problems.append(f"the connect page for a China code answered {status} {body}, expected the region refusal")
        status, body = ask("/internal/login", {"code": code, "user": opaque, "token": "a" * 64})
        if status != 400 or body.get("kind") != "region":
            problems.append(f"a China hand-off answered {status} {body}, expected the region refusal")
        if not peek_login_code(code):
            problems.append("refusing a China hand-off spent its login code")

        code = issue_login_code(user_id, "intl")
        status, body = ask(f"/internal/connect-info?code={code}&user={opaque}")
        if status != 200 or "lng-tgk-aime-gw.am-all.net" not in str(body.get("loginLink")) or body.get("method") != "bookmark":
            problems.append(f"an International code no longer gets its gateway link: {status} {body}")

        code = issue_login_code(user_id, "jp")
        status, body = ask(f"/internal/connect-info?code={code}&user={opaque}")
        if status != 200 or body.get("method") != "segaid" or body.get("loginLink") or body.get("bookmarklet"):
            problems.append(f"a Japan code was not offered the SEGA ID sign-in: {status} {body}")
        status, body = ask("/internal/login", {"code": code, "user": opaque})
        if status != 400 or body.get("kind") != "no_login":
            problems.append(f"a Japan hand-off with no SEGA ID answered {status} {body}")
        for wrong, why in (({**right, "password": "wrong"}, "a wrong password"), ({**right, "aime": "2"}, "an Aime card that is not there")):
            status, body = ask("/internal/login", {"code": code, "user": opaque, **wrong})
            if status != 401 or body.get("kind") != "credentials":
                problems.append(f"a Japan sign-in with {why} answered {status} {body}, expected the credentials refusal")
            if not peek_login_code(code):
                problems.append(f"a Japan sign-in with {why} spent its login code")
        status, body = ask("/internal/login", {"code": code, "user": opaque, **right, "aime": "1"})
        if status != 200 or body.get("region") != "jp" or (body.get("player") or {}).get("name") != "ＪＰプレイヤー":
            problems.append(f"a right SEGA ID and password did not link the Japan account: {status} {body}")
        else:
            stored = read_sega_id_token((get_connected_account(user_id) or {}).get("token", ""))
            if stored != (right["segaId"], right["password"], 0):
                problems.append(f"the linked Japan account's sign-in does not open to what was typed: {stored}")
            raw = store.get_database_connection().execute(
                "SELECT token FROM connected_accounts WHERE user_id = ?", (user_id,)).fetchone()[0]
            if not str(raw).startswith("enc2:"):
                problems.append("the Japan sign-in was stored without AES-256-GCM")
            files = b"".join(path.read_bytes() for path in store.DATABASE_PATH.parent.iterdir() if path.is_file())
            for secret in (right["password"], right["segaId"]):
                if secret.encode("utf-8") in files:
                    problems.append(f"the Japan account's {'password' if secret == right['password'] else 'SEGA ID'} is readable in the database files")
    finally:
        server.stop()
        fake.shutdown()
        config.MAIMAI_BASE_URLS["jp"] = real_jp
        web_server.dashboard.servers_down_note, web_server.dashboard.refresh_jobs.start = kept_down, kept_start
        web_server.INTERNAL_API_SECRET = kept
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems

@check("a dashboard read that fails inside the bot is answered and logged, not dropped, so the site can say what happened")
def _dashboard_read_fails_loudly():
    import json as jsonlib
    import logging
    import re
    import urllib.error
    import urllib.request

    from rasmai.web import dashboard, web_server

    problems = []
    kept_secret, kept_get = web_server.INTERNAL_API_SECRET, dashboard.handle_get
    web_server.INTERNAL_API_SECRET = "check-only-secret"

    def broken(handler, path, query, user):
        if path == "/internal/me":
            raise KeyError("something only this account has")
        return kept_get(handler, path, query, user)
    dashboard.handle_get = broken
    logged = []

    class Catch(logging.Handler):
        def emit(self, record):
            logged.append(record)
    catch = Catch(level=logging.ERROR)
    logging.getLogger().addHandler(catch)
    server = web_server.InternalApiServer(host="127.0.0.1", port=0)
    try:
        server.start()
        port = server.httpd.server_address[1]

        def call(path):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={
                "X-Rasmai-Internal": "check-only-secret", "X-Rasmai-User": jsonlib.dumps({"id": "123456789012345678", "name": "t"})})
            try:
                with urllib.request.urlopen(request, timeout=10) as answer:
                    return answer.status, jsonlib.loads(answer.read())
            except urllib.error.HTTPError as error:
                return error.code, jsonlib.loads(error.read() or b"{}")
            except (urllib.error.URLError, ConnectionError) as error:
                return 0, {"dropped": type(error).__name__}
        answered = call("/internal/me")
        rest = {key: value for key, value in answered[1].items() if key != "errorId"}
        if answered[0] != 500 or rest != {"ok": False, "error": "server"} or not re.fullmatch(r"[0-9A-F]{8}", str(answered[1].get("errorId"))):
            problems.append(f"a dashboard read that failed was answered {answered}")
        if not any(record.exc_info for record in logged):
            problems.append("the failure was not logged with its traceback, so nobody could find out why")
        if call("/health")[0] != 200:
            problems.append("the server stopped answering after one read failed")
    finally:
        server.stop()
        logging.getLogger().removeHandler(catch)
        dashboard.handle_get, web_server.INTERNAL_API_SECRET = kept_get, kept_secret
    return problems


@check("every error is posted to the error webhook under an id with what was going on, a repeat as one line, no addresses, not the developer page's, and the person is given the id")
def _error_reports():
    import asyncio
    import logging
    import re
    import types

    import discord
    from rasmai import errors

    problems = []
    posted = []
    kept = errors.ERROR_WEBHOOK_URL, errors._enqueue
    errors.ERROR_WEBHOOK_URL, errors._enqueue = "https://discord.com/api/webhooks/1/check", posted.append
    errors._seen.clear()
    errors._sent.clear()
    handler = errors.ErrorWebhook()
    root = logging.getLogger()
    root.addHandler(handler)

    def fail(text):
        raise ValueError(text)          # one line, so two calls are the same error twice, as a real bug met twice is
    try:
        try:
            fail("the page at https://maimaidx-eng.com/maimai-mobile/?token=secret said no")
        except ValueError as error:
            first = errors.report(error, "/analyze failed", {"Command": "/analyze", "User": "someone (123)"})
        if not re.fullmatch(r"[0-9A-F]{8}", first) or len(posted) != 1:
            problems.append(f"a report gave the id {first!r} and posted {len(posted)} time(s)")
        else:
            post = posted[0]
            embed = post["embeds"][0]
            text = json_dump = str(post)
            if post["username"] != "Rasmai · Errors" or not post["avatar_url"].endswith("/app/icon-512.png") or post["allowed_mentions"] != {"parse": []}:
                problems.append(f"the post was sent as {post['username']!r} with {post['avatar_url']!r}")
            if first not in embed["title"] or "ValueError" not in embed["description"] or "Traceback" not in embed["description"]:
                problems.append(f"the post did not carry the id, the error and its traceback: {embed['title']!r}")
            if "secret" in json_dump or "maimaidx-eng.com" in text:
                problems.append("an address, and the token in it, reached the webhook")
            if not any(field["name"] == "Command" and field["value"] == "/analyze" for field in embed["fields"]):
                problems.append(f"what was going on was not in the post: {embed['fields']}")
            logged_by = next((field["value"] for field in embed["fields"] if field["name"] == "Logged by"), "")
            if "`tools.checks.web`" not in logged_by and "`__main__`" not in logged_by and "rasmai.errors" in logged_by:
                problems.append(f"the post says it was logged by the reporter, not by what reported: {logged_by!r}")
            if first in embed["description"].splitlines()[0]:
                problems.append(f"the id is in the message as well as the title: {embed['description'][:80]!r}")
        # the same error again: one line pointing at the first, still under its own id
        try:
            fail("the page at https://maimaidx-eng.com/x said no")
        except ValueError as error:
            second = errors.report(error, "/analyze failed", {"User": "another (456)"})
        if len(posted) != 2 or "embeds" in posted[-1] or second not in posted[-1]["content"] or first not in posted[-1]["content"]:
            problems.append(f"a repeat was posted as {posted[-1] if len(posted) > 1 else None}")
        # the developer page's errors are its own
        before = len(posted)
        logging.getLogger("rasmai.web.dashboard.admin").error("the developer page broke")
        try:
            raise KeyError("x")
        except KeyError as error:
            errors.report(error, "dashboard read failed", {"Page": "/internal/me/admin"})
        if len(posted) != before:
            problems.append("an error on the developer page was posted")
        # a logged error with no one to tell is posted too, under an id of its own
        logging.getLogger("rasmai.bot.tasks.somewhere").error("a background job failed")
        if len(posted) != before + 1 or not re.search(r"Error [0-9A-F]{8}", posted[-1]["embeds"][0]["title"]):
            problems.append("an error logged in a background job was not posted")
        # a flood is capped, and the next post says how many were left out
        errors._sent[:] = [__import__("time").monotonic()] * errors.PER_MINUTE
        logging.getLogger("rasmai.flood").error("one too many")
        if len(posted) != before + 1:
            problems.append("an error past the per-minute cap was posted")
        errors._sent.clear()
        logging.getLogger("rasmai.after").error("after the flood")
        if "not posted" not in str(posted[-1].get("content", "")):
            problems.append("the post after a flood did not say how many were left out")
        # no webhook, nothing posted, and the reporter never raises
        errors.ERROR_WEBHOOK_URL = ""
        before = len(posted)
        logging.getLogger("rasmai.quiet").error("nobody listening")
        if len(posted) != before:
            problems.append("an error was posted with no webhook set")
        errors.ERROR_WEBHOOK_URL = "https://discord.com/api/webhooks/1/check"

        # the person: a command's own failure, a command that raised, and a broken button all give them the id
        from rasmai.bot import core
        from rasmai.bot.builders.results import view
        from rasmai.bot.ui.views import OwnerOnlyView

        class Response:
            def __init__(self):
                self.said = []

            def is_done(self):
                return False

            async def send_message(self, text, **options):
                self.said.append(text)

        async def no_context(interaction):
            return {"User": "check"}
        kept_context = core.command_context
        core.command_context = view.command_context = no_context
        try:
            interaction = types.SimpleNamespace(user=types.SimpleNamespace(id=1), response=Response(), followup=None, command=None)
            reply = asyncio.run(view.failure_reply(interaction, "Couldn't look that up.", ValueError("bad page")))
            if not re.search(r"send your error ID `[0-9A-F]{8}` along with it", reply["content"]):
                problems.append(f"a command's failure told the person {reply['content']!r}")
            interaction.command = types.SimpleNamespace(name="analyze", qualified_name="analyze")
            asyncio.run(core.on_app_command_error(interaction, discord.app_commands.CommandInvokeError(interaction.command, RuntimeError("boom"))))
            if not interaction.response.said or not re.search(r"send your error ID `[0-9A-F]{8}` along with it", interaction.response.said[-1]):
                problems.append(f"a command that raised told the person {interaction.response.said}")
            errors._seen.clear()           # the button's report in full, not as a repeat of the command's above
            menu = OwnerOnlyView(1, timeout=None)
            pressed = types.SimpleNamespace(user=types.SimpleNamespace(id=1), response=Response(), followup=None)
            asyncio.run(menu.on_error(pressed, RuntimeError("boom"), discord.ui.Button(label="Refresh")))
            if not pressed.response.said or not re.search(r"send your error ID `[0-9A-F]{8}` along with it", pressed.response.said[-1]):
                problems.append(f"a broken button told the person {pressed.response.said}")
            if "Refresh" not in str(posted[-1]):
                problems.append("the broken button's report did not say which button it was")
        finally:
            core.command_context = view.command_context = kept_context
    finally:
        root.removeHandler(handler)
        errors.ERROR_WEBHOOK_URL, errors._enqueue = kept
        errors._seen.clear()
        errors._sent.clear()
    return problems


@check("a name with Japanese, full-width letters or an emoji reaches the bot unchanged: the user header is plain ASCII, so fetch accepts it, and the bot reads it back")
def _user_header_survives_any_name():
    import http.server
    import json as jsonlib
    import shutil
    import subprocess
    import threading

    node = shutil.which("node")
    if node is None:
        return []           # shortcut: no Node on this machine to run the site's own code with; the site's build covers it where there is one
    names = ["Darkful", "café", "ゆうき", "Dark 🌙 ful", "ｄａｒｋ", 'quo"te\\slash', "🇯🇵 日本語 mixed"]
    problems = []
    seen = []

    class Bot(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            # as the bot reads it: http.server decodes a header as Latin-1, and the value is then parsed as JSON
            seen.append(jsonlib.loads(self.headers.get("X-Rasmai-User", "{}")).get("name"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Bot)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    script = ("import { headerJson } from %s;\nconst names = JSON.parse(process.argv[1]);\nconst out = [];\n"
              "for (const name of names) {\n  try {\n    const header = headerJson({ id: '1', name, handle: 'h', avatar: '' });\n"
              "    if (/[^\x20-\x7e]/.test(header)) { out.push('not ascii: ' + name); continue; }\n"
              "    await fetch('http://127.0.0.1:%d/', { headers: { 'X-Rasmai-User': header } });\n"
              "  } catch (error) { out.push('threw for ' + name + ': ' + error.message.slice(0, 60)); }\n}\nconsole.log(JSON.stringify(out));\n"
              ) % (jsonlib.dumps((ROOT / "web" / "lib" / "headerJson.ts").as_uri()), server.server_address[1])
    try:
        done = subprocess.run([node, "--input-type=module", "-e", script, jsonlib.dumps(names)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
        failed = jsonlib.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else [f"node said: {done.stderr[-200:]}"]
    except (subprocess.TimeoutExpired, ValueError) as error:
        failed = [f"could not run the site's code: {type(error).__name__}"]
    finally:
        server.shutdown()
    if failed:
        problems.append(f"names that could not be sent: {failed}")
    if seen != names:
        problems.append(f"the bot read {seen}, not {names}")
    return problems


@check("a planned maintenance on the status page takes over the site's banner from three days out until it's done, and the stored one comes back after")
def _maintenance_band():
    from datetime import datetime, timedelta, timezone
    from rasmai.web.dashboard import overview

    problems = []
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    iso = lambda moment: moment.isoformat().replace("+00:00", ".000Z")
    soon = {"id": "m1", "name": "Database move", "status": "NOTSTARTEDYET", "start": iso(now + timedelta(days=1)), "duration": 60}
    later = {"id": "m2", "name": "Far off", "status": "NOTSTARTEDYET", "start": iso(now + timedelta(days=5)), "duration": 60}
    going = {"id": "m3", "name": {"en": "Server swap"}, "status": "INPROGRESS", "start": iso(now - timedelta(minutes=10)), "end": iso(now + timedelta(hours=2))}
    done = {"id": "m4", "name": "Old", "status": "COMPLETED", "start": iso(now - timedelta(days=1)), "duration": 30}
    kept = overview._maintenances
    try:
        overview._maintenances = lambda: [later, soon, done]
        band = overview.planned_maintenance(now)
        if not band or "Database move" not in band["text"] or band["at"] != (now + timedelta(days=1)).isoformat() or band["id"] != "maintenance-m1-soon":
            problems.append(f"a maintenance tomorrow did not make the band, or named the wrong time: {band}")
        if band and (band["tone"] != "warning" or not band["link"].startswith("https://")):
            problems.append(f"the maintenance band is not a warning linking the status page: {band}")
        overview._maintenances = lambda: [soon, going]
        band = overview.planned_maintenance(now)
        if not band or "Server swap" not in band["text"] or "right now" not in band["text"] or band["at"] != (now + timedelta(hours=2)).isoformat():
            problems.append(f"one under way did not lead with when it should end: {band}")
        overview._maintenances = lambda: [later, done]
        if overview.planned_maintenance(now) is not None:
            problems.append("a maintenance five days out, or one already done, made the band")
        overview._maintenances = lambda: [dict(soon, start=iso(now - timedelta(hours=2)))]
        if overview.planned_maintenance(now) is not None:
            problems.append("a maintenance whose hour has passed still made the band")
        overview._maintenances = lambda: []
        if overview.notice_payload().get("id", "").startswith("maintenance-"):
            problems.append("the band stayed on maintenance with none planned")
    finally:
        overview._maintenances = kept
    if overview._maintenances() != []:
        problems.append("the sweep asked the real status page about maintenance")
    return problems


@check("the status check survives a gateway that reports no latency, and a dashboard read that maimai DX NET refuses is told to the person without being reported as a bug")
def _outages():
    import logging
    from rasmai.bot import core
    from rasmai.web import statuspage
    from rasmai.web.dashboard import refresh
    problems = []
    cls = type(core.bot)
    kept = cls.latency, cls.is_ready
    try:
        cls.is_ready = lambda self: True
        for value in (float("inf"), float("nan")):
            cls.latency = property(lambda self, value=value: value)
            try:
                if statuspage._bot()["gatewayMs"] != 0:
                    problems.append(f"a latency of {value} was reported as a number of milliseconds")
            except OverflowError:
                problems.append(f"a latency of {value} broke the status check")
            except ValueError:
                problems.append(f"a latency of {value} broke the status check")
    finally:
        cls.latency, cls.is_ready = kept

    class Records(logging.Handler):
        def __init__(self):
            super().__init__(logging.DEBUG)
            self.seen = []

        def emit(self, record):
            self.seen.append(record)
    grab = Records()
    log = logging.getLogger("rasmai.web.dashboard.refresh")
    log.addHandler(grab)
    kept_analyzer = refresh.MaimaiRatingAnalyzer
    try:
        for error, bug in ((ValueError("maimai DX NET is having trouble right now (HTTP 503). Try again in a few minutes."), False), (KeyError("a bug"), True)):
            class Analyzer:
                def fetch_official_maimai_snapshot(self, *args):
                    raise error
            refresh.MaimaiRatingAnalyzer = Analyzer
            grab.seen.clear()
            job = {"running": True}
            refresh.refresh_jobs._read("1", {"token": "t", "region": "intl"}, job, lambda *a: None)
            reported = any(record.levelno >= logging.ERROR for record in grab.seen)
            if reported != bug:
                problems.append(f"{type(error).__name__} was {'reported' if reported else 'not reported'} as a bug")
            if job.get("stage") != "failed" or not job.get("error"):
                problems.append(f"the person was not told the read failed after {type(error).__name__}: {job}")
    finally:
        refresh.MaimaiRatingAnalyzer = kept_analyzer
        log.removeHandler(grab)
    return problems
