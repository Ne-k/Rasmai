from tools.checks import ROOT, check


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
    allowed = re.search(r"\[((?:\"[a-z/]+\",?\s*)+)\]\.includes\(path\)", web)
    posts = set(re.findall(r'"/internal/me/([a-z/]+)"', routes[routes.index("def handle_post"):]))
    if not allowed:
        problems.append("the site no longer allow-lists which writes under /api/me it will forward")
    else:
        site_posts = set(re.findall(r'"([a-z/]+)"', allowed.group(1)))
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
