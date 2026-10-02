from contextlib import contextmanager

from tools.checks import check

DISCORD = "100000000000000001"
OTHER_DISCORD = "100000000000000002"


@contextmanager
def _scratch():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    was = store.DATABASE_PATH
    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "identity.sqlite3", False
    try:
        yield store
    finally:
        store.DATABASE_PATH, store._database_ready = was, False


def _google(sub="g-test-1", email="player@example.test", verified=True):
    return {"provider": "google", "subject": sub, "email": email, "emailVerified": verified}


def _discord(sub=DISCORD, email="player@example.test", verified=True):
    return {"provider": "discord", "subject": sub, "email": email, "emailVerified": verified}


def _resolve(one, session=None):
    from rasmai.storage.db import resolve_identity
    return resolve_identity(one["provider"], one["subject"], one["email"], one["emailVerified"], session)


def _count(store, table, where="1=1", *args):
    c = store.get_database_connection()
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]
    finally:
        c.close()


def _link_maimai(user_id, name, token="a" * 64, region="intl"):
    from rasmai.storage.db import upsert_connected_account
    upsert_connected_account(user_id, region, f"cookie://{token}", {"name": name, "rating": 12000})


@check("a verified email that matches an earlier sign-in links to that account, and an unverified one never does")
def _email_match():
    import pathlib

    from rasmai.storage.db import account_exists, create_person

    problems = []
    with _scratch() as store:
        made = create_person([_google()], "2026-10-02")
        user = made.get("userId", "")
        if not user.startswith("w") or len(user) != 21:
            problems.append(f"a Google-only account was not given a site id: {made}")
        same = _resolve(_discord(OTHER_DISCORD, "  Player@Example.TEST "))
        # a Discord sign-in the site account does not hold yet joins it by the address, and the data moves to that Discord id
        if same.get("status") != "signed_in":
            problems.append(f"a verified, matching email did not sign in: {same}")
        if _count(store, "people") != 1:
            problems.append("matching on an email made a second account")
        stranger = _resolve(_google("g-test-2", "player@example.test", verified=False))
        if stranger.get("status") != "needs_terms":
            problems.append(f"an unverified email matched an account: {stranger}")
        if _count(store, "identities", "email_hash <> ''") < 1:
            problems.append("the email hash was not kept for a verified sign-in")
        if _count(store, "identities", "subject = 'g-test-2'") != 0:
            problems.append("an unverified sign-in that was only resolved left an identity behind")
        raw = store.DATABASE_PATH.read_bytes() + pathlib.Path(str(store.DATABASE_PATH) + "-wal").read_bytes()
        if b"player@example.test" in raw.lower():
            problems.append("the email address itself reached the database file")
        if account_exists("w" + "0" * 20):
            problems.append("an account exists that nobody made")
    return problems


@check("creating a person records the terms version and time, and refuses a version that is not a date")
def _terms_recorded():
    from rasmai.storage.db import create_person

    problems = []
    with _scratch() as store:
        for bad in ("", "latest", "2026-10-2", "2026-10-02x"):
            try:
                create_person([_google("g-bad")], bad)
                problems.append(f"terms version {bad!r} was accepted")
            except ValueError:
                pass
        if _count(store, "people") or _count(store, "identities"):
            problems.append("a refused creation left rows behind")
        user = create_person([_google("g-ok")], "2026-10-02")["userId"]
        c = store.get_database_connection()
        row = c.execute("SELECT terms_version, terms_accepted_at, created_at FROM people WHERE user_id = ?", (user,)).fetchone()
        c.close()
        if not row or row["terms_version"] != "2026-10-02" or not row["terms_accepted_at"] or not row["created_at"]:
            problems.append("the terms version and the time were not recorded")
        try:
            create_person([_google("g-two"), _google("g-three")] + [_discord(), _discord(OTHER_DISCORD)], "2026-10-02")
            problems.append("two Discord sign-ins were joined into one account")
        except ValueError:
            pass
        made = create_person([_google("g-four", "four@example.test"), _discord(OTHER_DISCORD, "four@example.test")], "2026-10-02")
        if made.get("userId") != OTHER_DISCORD:
            problems.append(f"an account with a Discord sign-in was not made under the Discord id: {made}")
    return problems


@check("joining two accounts that both have a maimai account asks first, and deletes nothing until told which to keep")
def _merge_needs_choice():
    from rasmai.storage.db import create_person, get_connected_account, merge_accounts

    problems = []
    for keep in ("from", "to"):
        with _scratch() as store:
            web = create_person([_google()], "2026-10-02")["userId"]
            _link_maimai(web, "web player", "b" * 64)
            _link_maimai(DISCORD, "discord player", "c" * 64)
            asked = merge_accounts(web, DISCORD)
            if asked.get("status") != "needs_choice" or asked.get("fromSummary", {}).get("player") != "web player" \
                    or asked.get("toSummary", {}).get("player") != "discord player" or asked["toSummary"].get("rating") != 12000:
                problems.append(f"two linked accounts did not come back as a question with both summaries: {asked}")
            if not (get_connected_account(web) and get_connected_account(DISCORD)):
                problems.append("asking which to keep deleted an account")
            try:
                merge_accounts(web, DISCORD, "both")
                problems.append("a keep that is neither from nor to was accepted")
            except ValueError:
                pass
            done = merge_accounts(web, DISCORD, keep)
            if done.get("status") != "merged":
                problems.append(f"keep={keep} did not merge: {done}")
            survivor = get_connected_account(DISCORD) or {}
            wanted = "web player" if keep == "from" else "discord player"
            if (survivor.get("officialProfile") or {}).get("name") != wanted:
                problems.append(f"keep={keep} kept {(survivor.get('officialProfile') or {}).get('name')!r}, expected {wanted!r}")
            if get_connected_account(web) is not None or _count(store, "people", "user_id = ?", web) or _count(store, "identities", "user_id = ?", web):
                problems.append(f"keep={keep} left rows under the site id")
            if _count(store, "identities", "user_id = ? AND provider = 'google'", DISCORD) != 1:
                problems.append(f"keep={keep} lost the Google sign-in on the way")
    return problems


@check("joining moves everything to the Discord id and re-seals the stored sign-in so the Discord id can open it")
def _merge_moves_data():
    from rasmai.bot.state.prefs import get_prefs
    from rasmai.storage.db import (create_person, get_connected_account, load_chart_scores, merge_accounts,
                                   record_chart_scores, set_user_settings)

    problems = []
    with _scratch() as store:
        web = create_person([_google()], "2026-10-02")["userId"]
        token = "d" * 64
        _link_maimai(web, "web player", token)
        record_chart_scores(web, [("song|dx|master", "2026-09-29T20:00:00+09:00", 97.0, 900, "", "", "play", 1000, 1)])
        set_user_settings(web, {"notify": True})
        done = merge_accounts(web, DISCORD, "to", _discord())
        if done.get("status") != "merged":
            problems.append(f"the merge did not go through: {done}")
        moved = get_connected_account(DISCORD) or {}
        if moved.get("token") != f"cookie://{token}":
            problems.append("the sign-in could not be read under the Discord id after the move: it was not re-sealed")
        if not load_chart_scores(DISCORD, ["song|dx|master"]):
            problems.append("the recorded plays did not move to the Discord id")
        if not get_prefs(DISCORD).get("notify"):
            problems.append("the settings did not move to the Discord id")
        for table in ("connected_accounts", "chart_scores", "user_settings", "people"):
            if _count(store, table, "user_id = ?", web):
                problems.append(f"{table} still has rows under the site id")
        if _count(store, "people", "user_id = ?", DISCORD) != 1 or _count(store, "identities", "user_id = ?", DISCORD) != 2:
            problems.append("the person and both sign-ins did not end up under the Discord id")
    return problems


@check("deleting an account takes its sign-ins and its person row with it")
def _delete_takes_identities():
    from rasmai.storage.db import create_person, delete_connected_account

    problems = []
    with _scratch() as store:
        web = create_person([_google("g-gone", "gone@example.test")], "2026-10-02")["userId"]
        _link_maimai(web, "gone")
        keeper = create_person([_google("g-stay", "stay@example.test")], "2026-10-02")["userId"]
        if not delete_connected_account(web):
            problems.append("the account was not reported deleted")
        if _count(store, "identities", "user_id = ?", web) or _count(store, "people", "user_id = ?", web):
            problems.append("a deleted account left its sign-ins or its person row")
        if _count(store, "people", "user_id = ?", keeper) != 1 or _count(store, "identities", "user_id = ?", keeper) != 1:
            problems.append("deleting one account touched another")
        again = _resolve(_google("g-gone", "gone@example.test"))
        if again.get("status") != "needs_terms":
            problems.append(f"a deleted person signing in again was not asked for consent as a new one: {again}")
    return problems


@check("Google first: sign in, accept, link maimai, then Discord joins it under the Discord id")
def _google_first():
    from rasmai.storage.db import create_person, get_connected_account, resolve_identity, sign_in_providers

    problems = []
    with _scratch() as store:
        google = _google("g-first", "walk@example.test")
        step = _resolve(google)
        if step.get("status") != "needs_terms":
            problems.append(f"a first Google sign-in was not asked for consent: {step}")
        if _count(store, "people") or _count(store, "identities"):
            problems.append("something was created before consent")
        web = create_person([google], "2026-10-02")["userId"]
        again = _resolve(google)
        if again != {"status": "signed_in", "userId": web}:
            problems.append(f"signing in again did not return the same account: {again}")
        if sign_in_providers(web) != ["google"]:
            problems.append(f"the account section would show {sign_in_providers(web)}")
        _link_maimai(web, "walk player", "e" * 64)
        # Discord arrives while the Google session is open: link=1 in the site
        joined = resolve_identity("discord", DISCORD, "walk@example.test", True, web)
        if joined.get("status") != "signed_in" or joined.get("userId") != DISCORD:
            problems.append(f"linking Discord did not end on the Discord id: {joined}")
        account = get_connected_account(DISCORD) or {}
        if account.get("token") != "cookie://" + "e" * 64 or (account.get("officialProfile") or {}).get("name") != "walk player":
            problems.append("the maimai account did not follow the person to the Discord id")
        if _count(store, "people") != 1 or _count(store, "identities", "user_id = ?", DISCORD) != 2:
            problems.append("the merge left more than one account or lost a sign-in")
        # either sign-in now opens the one account
        for one in (google, _discord()):
            if _resolve(one) != {"status": "signed_in", "userId": DISCORD}:
                problems.append(f"{one['provider']} no longer opens the merged account")
        # a Discord sign-in alone, after Google had been used, also finds it
        if sign_in_providers(DISCORD) != ["discord", "google"]:
            problems.append(f"the merged account reports {sign_in_providers(DISCORD)}")
    return problems


@check("Discord first: sign in, accept, then Google with the same verified email links and makes no second account")
def _discord_first():
    from rasmai.storage.db import create_person

    problems = []
    with _scratch() as store:
        discord = _discord(DISCORD, "both@example.test")
        if _resolve(discord).get("status") != "needs_terms":
            problems.append("a first Discord sign-in was not asked for consent")
        made = create_person([discord], "2026-10-02")
        if made.get("userId") != DISCORD:
            problems.append(f"the account was not made under the Discord id: {made}")
        linked = _resolve(_google("g-second", "BOTH@example.test"))
        if linked != {"status": "signed_in", "userId": DISCORD}:
            problems.append(f"Google with the same verified email did not open the Discord account: {linked}")
        if _count(store, "people") != 1:
            problems.append("a second account was made")
        unverified = _resolve(_google("g-third", "both@example.test", verified=False))
        if unverified.get("status") != "needs_terms":
            problems.append("an unverified Google email opened an account")
        # an account from before sign-ins were recorded is opened by its Discord id with no consent step
        _link_maimai(OTHER_DISCORD, "old player")
        old = _resolve(_discord(OTHER_DISCORD, "", False))
        if old != {"status": "signed_in", "userId": OTHER_DISCORD}:
            problems.append(f"an existing account was asked for consent again: {old}")
        # a site account cannot take over a Discord account that is not its own, nor can two Discord accounts share one
        web = create_person([_google("g-web", "web@example.test")], "2026-10-02")["userId"]
        if _resolve(_discord(OTHER_DISCORD), web).get("userId") != OTHER_DISCORD:
            problems.append("a site account could not join an old Discord account")
        if _resolve(_discord(DISCORD), OTHER_DISCORD).get("error") != "identity_taken":
            problems.append("one Discord account joined another")
    return problems


@check("the sign-in routes answer in the shape the site expects, and a site-only id is accepted where a Discord id is")
def _identity_routes():
    import json as jsonlib
    import urllib.error
    import urllib.request

    from rasmai.security import decode_opaque_user_id
    from rasmai.web import web_server

    problems = []
    kept = web_server.INTERNAL_API_SECRET
    web_server.INTERNAL_API_SECRET = "check-only-secret"
    server = web_server.InternalApiServer(host="127.0.0.1", port=0)
    with _scratch():
        try:
            server.start()
            port = server.httpd.server_address[1]
            counter = [0]

            def call(path, body=None, user=None, client=None):
                counter[0] += 1
                headers = {"X-Rasmai-Internal": "check-only-secret", "X-Rasmai-Client": client or f"identity-check-{counter[0]}",
                           "Content-Type": "application/json"}
                if user:
                    headers["X-Rasmai-User"] = jsonlib.dumps({"id": user, "name": "t"})
                data = jsonlib.dumps(body).encode() if body is not None else None
                request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers,
                                                 method="POST" if body is not None else "GET")
                try:
                    with urllib.request.urlopen(request, timeout=10) as answer:
                        return answer.status, jsonlib.loads(answer.read())
                except urllib.error.HTTPError as error:
                    return error.code, jsonlib.loads(error.read() or b"{}")

            g = {"provider": "google", "subject": "g-route", "email": "route@example.test", "emailVerified": True}
            if call("/internal/auth/resolve", g) != (200, {"ok": True, "status": "needs_terms"}):
                problems.append(f"resolve for a stranger answered {call('/internal/auth/resolve', g)}")
            status, made = call("/internal/auth/create", {"identities": [g], "termsVersion": "2026-10-02"})
            web = made.get("userId", "")
            if status != 200 or set(made) != {"ok", "userId"} or not web.startswith("w"):
                problems.append(f"create answered {status} {made}")
            if call("/internal/auth/create", {"identities": [g], "termsVersion": "soon"})[0] != 400:
                problems.append("create accepted a terms version that is not a date")
            if call("/internal/auth/resolve", {**g, "provider": "twitter"})[0] != 400:
                problems.append("resolve accepted a provider that is not Google or Discord")
            if call("/internal/auth/resolve", {**g, "subject": "x" * 300})[0] != 400:
                problems.append("resolve accepted an overlong subject")
            if call("/internal/auth/resolve", {**g, "email": "a" * 300})[0] != 400:
                problems.append("resolve accepted an overlong email")
            if call("/internal/auth/resolve", {**g, "sessionUserId": "not-an-id"})[0] != 400:
                problems.append("resolve accepted a session user that is no id")
            if call("/internal/auth/resolve", g) != (200, {"ok": True, "status": "signed_in", "userId": web}):
                problems.append("resolve for a known sign-in did not answer signed_in with the id")
            _link_maimai(web, "web player", "f" * 64)
            _link_maimai(DISCORD, "discord player", "0" * 64)
            d = {"provider": "discord", "subject": DISCORD, "email": "", "emailVerified": False, "sessionUserId": web}
            status, choice = call("/internal/auth/resolve", d)
            expected = {"ok", "status", "from", "to", "fromSummary", "toSummary"}
            if status != 200 or choice.get("status") != "needs_choice" or set(choice) != expected or choice["from"] != web \
                    or choice["to"] != DISCORD or set(choice["fromSummary"]) != {"player", "rating", "region"}:
                problems.append(f"resolve for two linked accounts answered {status} {choice}")
            if call("/internal/auth/merge", {"from": web, "to": DISCORD})[0] != 400:
                problems.append("merge without keep was accepted")
            if call("/internal/auth/merge", {"from": DISCORD, "to": web, "keep": "to"})[0] != 400:
                problems.append("merge accepted a Discord id as the site side")
            status, merged = call("/internal/auth/merge", {"from": web, "to": DISCORD, "keep": "from", "identity": d})
            if (status, merged) != (200, {"ok": True, "userId": DISCORD}):
                problems.append(f"merge answered {status} {merged}")
            _link_maimai(OTHER_DISCORD, "other player", "1" * 64)
            clash = {"provider": "discord", "subject": DISCORD, "email": "", "emailVerified": False, "sessionUserId": OTHER_DISCORD}
            if call("/internal/auth/resolve", clash) != (409, {"ok": False, "error": "identity_taken"}):
                problems.append("a Discord account joining another Discord account was not answered identity_taken")
            # a site-only id signs the dashboard routes in
            fresh = call("/internal/auth/create", {"identities": [{**g, "subject": "g-route-2", "email": ""}], "termsVersion": "2026-10-02"})[1]["userId"]
            status, me = call("/internal/me", user=fresh)
            if status != 200 or me.get("providers") != ["google"] or me.get("linked") is not False:
                problems.append(f"the overview of a site-only account answered {status} {me}")
            status, link = call("/internal/me/link-start", {"region": "intl"}, user=fresh)
            url = link.get("connectUrl", "")
            if status != 200 or set(link) != {"ok", "connectUrl"} or "/connect/?code=" not in url \
                    or decode_opaque_user_id(url.split("user=")[-1]) != fresh:
                problems.append(f"link-start answered {status} {link}")
            if call("/internal/me/link-start", {"region": "cn"}, user=fresh)[0] != 400:
                problems.append("link-start accepted a region that is not intl or jp")
            if call("/internal/me/link-start", {"region": "intl"})[0] != 401:
                problems.append("link-start answered with nobody signed in")
            if call("/internal/me", user="w" + "G" * 20)[0] != 401:
                problems.append("a malformed site id was accepted as a signed-in user")
            if call("/internal/me/admin", user=fresh)[0] != 404:
                problems.append("a site-only account was shown the developer page")
            # one visitor's attempts are limited, and refused with 429 rather than failing
            answers = [call("/internal/auth/resolve", {**g, "provider": "x"}, client="identity-check-flood")[0] for _ in range(40)]
            if 429 not in answers or answers[0] != 400:
                problems.append("a flood of sign-in resolves from one visitor was not limited")
        finally:
            server.stop()
            web_server.INTERNAL_API_SECRET = kept
    return problems


@check("an account made on the site is skipped by every part that assumes a Discord user")
def _web_id_guards():
    import asyncio

    from rasmai.bot.tasks.history_watch import HistoryWatch
    from rasmai.bot.ui.login import dm_login_card
    from rasmai.storage.db import create_person
    from rasmai.web.dashboard import admin

    problems = []
    with _scratch():
        web = create_person([_google("g-guard")], "2026-10-02")["userId"]
        if admin.is_admin(web):
            problems.append("a site-only id counted as the admin")
        if admin.people([web, DISCORD]) != {}:
            problems.append("the developer page tried to name a site-only id from Discord")

        class NoDiscord:
            def get_user(self, *_):
                raise AssertionError("looked a site-only id up in Discord")

            async def fetch_user(self, *_):
                raise AssertionError("fetched a site-only id from Discord")

        if asyncio.run(dm_login_card(NoDiscord(), web, "intl", "x")) is not False:
            problems.append("a login card was attempted for a site-only id")
        watch = HistoryWatch(NoDiscord(), object())
        try:
            asyncio.run(watch._note(web, {"added": 1, "bests": [], "rating": 12000}))
        except Exception as error:
            problems.append(f"the daily note failed for a site-only id: {error}")
    return problems
