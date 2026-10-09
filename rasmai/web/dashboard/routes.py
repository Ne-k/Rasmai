from datetime import datetime
from typing import Dict, List, Any, Optional
import json
import logging
import re

from rasmai.bot.builders.charts.index import search_titles
from rasmai.bot.builders.kamaitachi import kamaitachi_file
from rasmai.security import import_limiter, kamaitachi_limiter, public_reason, refresh_limiter
from rasmai.storage.db import delete_connected_account, get_connected_account, is_discord_id, is_web_id
from rasmai.bot.state import cohort
from rasmai.bot.state.cache import cache_get, forget_analysis
from rasmai.bot.state.forget import forget_user
from rasmai.web.dashboard.admin import (account_detail, accounts_payload, admin_payload, guilds_payload,
                                        is_admin, start_update)
from rasmai.web.dashboard.analysis import analysis_for_user
from rasmai.web.dashboard.areas import areas_payload
from rasmai.web.dashboard.auth import start_link
from rasmai.web.dashboard.lookup import chart_payload, patterns_payload, search_payload, video_payload
from rasmai.web.dashboard.overview import overview_payload
from rasmai.web.dashboard.picks import new_charts_payload, picks_payload
from rasmai.web.dashboard.refresh import refresh_jobs
from rasmai.web.dashboard.scores import charts_payload, export_payload, play_payload, recent_payload
from rasmai.web.dashboard.imports import import_kamaitachi, import_payload
from rasmai.storage.db import VERDICTS, set_beta_feedback
from rasmai.web.dashboard.beta import FEATURES, beta_state, set_beta
from rasmai.web.dashboard.public_profile import set_sharing

logger = logging.getLogger(__name__)


# reads that never look at the analysis, so never wait on one
ANSWERED_WITHOUT_ANALYSIS = ("/internal/me/refresh", "/internal/me/beta", "/internal/me/admin", "/internal/me/titles", "/internal/me/session")
# opened as a plain link: the browser cannot be told to come back, so these wait out the queue
DOWNLOADS = ("/internal/me/export", "/internal/me/kamaitachi", "/internal/me/image")
READS_SNAPSHOT = ("/internal/me", "/internal/me/", "/internal/me/areas")
# every write handle_post answers; one missing here is refused as not found before its branch is reached,
# which is how beta feedback went unanswered while the site forwarded it
WRITES = ("/internal/me/refresh", "/internal/me/unlink", "/internal/me/import", "/internal/me/sharing",
          "/internal/me/beta", "/internal/me/beta/feedback", "/internal/me/admin/update", "/internal/me/kamaitachi/import")


def handle_get(handler: Any, path: str, query: Dict[str, List[str]], user: Dict[str, Any]) -> bool:
    """Dashboard reads for the signed-in person, as the web server authenticated them; True when answered.

    :param handler: The request being answered.
    :type handler: Any
    :param path: The request path.
    :type path: str
    :param query: The query string, parsed.
    :type query: Dict[str, List[str]]
    :param user: The signed-in person.
    :type user: Dict[str, Any]
    :rtype: bool
    """
    # Whether the analysis is ready is settled before the account is read: while a crowd queues,
    # most asks are answered "come back", and reading and unpacking the account first was a
    # millisecond and a half of the interpreter per ask, which starved the thread taking connections.
    cached = None
    if path not in ANSWERED_WITHOUT_ANALYSIS:
        cached = analysis_for_user(user["id"], patient=path in DOWNLOADS)
    # the stored scores only for the two pages that show them: unpacking them was a millisecond and
    # a half of every other request, which only needs to know the account is there
    account = get_connected_account(user["id"], with_snapshot=path in READS_SNAPSHOT)

    if path in ("/internal/me", "/internal/me/"):
        handler._send_json(200, overview_payload(user, account))
        return True
    if path == "/internal/me/session":
        # asked on every page, for the band at the top: only whether maimai still takes the saved login, never the whole dashboard
        handler._send_json(200, {"sessionExpired": (account or {}).get("sessionExpired") or ""})
        return True
    if path == "/internal/me/refresh":
        handler._send_json(200, refresh_jobs.status(user["id"]))
        return True
    if path == "/internal/me/beta":
        # the switches and how far chart reading has got: light enough for the page to poll while it runs
        handler._send_json(200, beta_state(user["id"]))
        return True
    if path == "/internal/me/admin":
        # one account only, and anyone else is told the route does not exist rather than that it is refused
        if not is_admin(user["id"]):
            logger.warning("developer page refused for %s", user["id"])
            handler._send_json(404, {"ok": False, "error": "not_found"})
            return True
        who = (query.get("user") or [""])[0].strip()
        if who:
            if not (is_discord_id(who) or is_web_id(who)):
                handler._send_json(400, {"ok": False, "error": "bad_user"})
                return True
            detail = account_detail(who)
            handler._send_json(200 if detail else 404, detail or {"ok": False, "error": "not_found"})
            return True
        handler._send_json(200, {**admin_payload(), "accounts_list": accounts_payload(), "guilds_list": guilds_payload()})
        return True
    if account is None:
        handler._send_json(404, {"ok": False, "error": "not_linked"})
        return True

    if path == "/internal/me/charts":
        handler._send_json(200, {"charts": charts_payload(cached) if cached else []})
        return True
    if path == "/internal/me/picks":
        if cached is None:
            handler._send_json(404, {"ok": False, "error": "no_snapshot"})
            return True
        handler._send_json(200, picks_payload(cached, (query.get("challenge") or ["balanced"])[0][:12], (query.get("level") or [""])[0][:24]))
        return True
    if path == "/internal/me/new":
        if cached is None:
            handler._send_json(404, {"ok": False, "error": "no_snapshot"})
            return True
        handler._send_json(200, new_charts_payload(cached, (query.get("challenge") or ["balanced"])[0][:12],
                                                   (query.get("difficulty") or ["any"])[0], (query.get("level") or [""])[0][:4],
                                                   (query.get("focus") or [""])[0][:6]))
        return True
    if path == "/internal/me/recent":
        handler._send_json(200, {"plays": recent_payload(user["id"], cached)})
        return True
    if path == "/internal/me/play":
        idx = (query.get("idx") or [""])[0][:64].strip()
        try:
            detail = play_payload(cached, idx) if cached and idx else None
        except Exception as error:      # the site refused the sign-in or the page; the rest of the tab stands
            handler._send_json(502, {"ok": False, "error": "read_failed", "reason": public_reason(error)})
            return True
        if detail is None:
            handler._send_json(404, {"ok": False, "error": "no_play"})
            return True
        handler._send_json(200, detail)
        return True
    if path == "/internal/me/areas":
        handler._send_json(200, areas_payload(user["id"], account, cached))
        return True
    if path == "/internal/me/search":
        handler._send_json(200, {"songs": search_payload(cached, (query.get("q") or [""])[0][:80])})
        return True
    if path == "/internal/me/titles":
        q = query.get("q")
        if q is None:
            handler._send_json(400, {"ok": False, "error": "query_required"})
        elif not q[0].strip():
            handler._send_json(400, {"ok": False, "error": "empty_query"})
        else:
            handler._send_json(200, {"titles": search_titles(q[0][:80], 100)})
        return True
    if path == "/internal/me/patterns":
        handler._send_json(200, patterns_payload(cached, (query.get("tag") or [""])[0][:60].strip(), (query.get("level") or [""])[0][:4].strip(),
                                                 (query.get("difficulty") or [""])[0][:10].strip().lower()))
        return True
    if path == "/internal/me/video":
        handler._send_json(200, video_payload(cached, (query.get("title") or [""])[0][:200].strip()))
        return True
    if path == "/internal/me/chart":
        title = (query.get("title") or [""])[0][:200].strip()
        cover = (query.get("cover") or [""])[0][:80].strip()
        if not title and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cover):
            handler._send_json(400, {"ok": False, "error": "no_title"})
            return True
        detail = chart_payload(cached, title, (query.get("type") or [""])[0][:8].lower(), (query.get("difficulty") or [""])[0][:12].lower(), cover=cover)
        if detail is None:
            # the player may hold scores on a song the database has not learned yet
            mine = [s for s in (cached.analyzer.songs if cached else []) if str(s.name).casefold() == title.casefold()] if title else []
            if mine:
                handler._send_json(404, {"ok": False, "error": "unknown_song", "title": mine[0].name, "charts": [
                    {"chart_type": s.chart_type or "std", "difficulty": str(s.difficulty_type).lower(), "level": s.level,
                     "constant": round(float(s.difficulty or 0), 2), "accuracy": round(float(s.accuracy or 0), 4), "rating": int(s.rating or 0)}
                    for s in mine]})
                return True
            handler._send_json(404, {"ok": False, "error": "no_song"})
            return True
        handler._send_json(200, detail)
        return True
    if path == "/internal/me/image":
        # the same picture the matching command attaches, drawn by the same builder
        from rasmai.web.dashboard.files import image_export
        image_export(handler, cached, (query.get("kind") or [""])[0].strip())
        return True

    if path == "/internal/me/export":
        if cached is None:
            handler._send_json(404, {"ok": False, "error": "no_snapshot"})
            return True
        body = json.dumps(export_payload(cached), ensure_ascii=False, indent=2).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Disposition", f'attachment; filename="rasmai-scores-{datetime.now().strftime("%Y%m%d-%H%M")}.json"')
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path == "/internal/me/kamaitachi":
        if cached is None:
            handler._send_json(404, {"ok": False, "error": "no_snapshot"})
            return True
        body, filename, _counts = kamaitachi_file(cached)
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    return False


def handle_post(handler: Any, path: str, user: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> bool:
    """Dashboard writes for the signed-in person: start a score read, import an export, or unlink; True when answered.

    :param handler: The request being answered.
    :type handler: Any
    :param path: The request path.
    :type path: str
    :param user: The signed-in person.
    :type user: Dict[str, Any]
    :rtype: bool
    """
    if path == "/internal/me/link-start":
        # for any signed-in account, a site-only one that has no maimai account yet included, so it is answered before the linked-account check
        start_link(handler, user, payload or {})
        return True
    if path not in WRITES:
        return False
    if path == "/internal/me/admin/update":
        # about the bot's own chart databases rather than about an account, so it is answered before
        # the linked-account check, and refused the same way the developer page itself is
        if not is_admin(user["id"]):
            logger.warning("chart database update refused for %s", user["id"])
            handler._send_json(404, {"ok": False, "error": "not_found"})
            return True
        started = start_update(str((payload or {}).get("source") or ""))
        handler._send_json(202 if started.get("ok") else 409, started)
        return True
    if path == "/internal/me/unlink":
        # also for an account with no maimai linked: that is how a site-only person deletes their sign-ins and record of agreement
        delete_connected_account(user["id"])
        forget_user(user["id"])
        cohort.drop(user["id"])
        handler._send_json(200, {"ok": True})
        return True
    account = get_connected_account(user["id"])
    if account is None:
        handler._send_json(404, {"ok": False, "error": "not_linked"})
        return True
    if path == "/internal/me/beta":
        handler._send_json(200, set_beta(user["id"], (payload or {}).get("on") or {}))
        return True
    if path == "/internal/me/beta/feedback":
        # a verdict on a feature that exists, from the person whose session this is. Anything
        # else is refused rather than stored: the developer page reads this table by eye.
        body = payload or {}
        feature = str(body.get("feature") or "")
        if feature not in FEATURES:
            handler._send_json(400, {"ok": False, "error": "no_such_feature"})
            return True
        stored = set_beta_feedback(user["id"], feature, str(body.get("verdict") or ""), body.get("said") or "")
        if stored is None:
            handler._send_json(400, {"ok": False, "error": "no_such_verdict", "allowed": list(VERDICTS)})
            return True
        handler._send_json(200, beta_state(user["id"]))
        return True
    if path == "/internal/me/sharing":
        body = payload or {}
        state = set_sharing(user["id"], body.get("on"), body.get("sections"), bool(body.get("rotate")), account,
                            body.get("card"), body.get("embed"), body.get("colour"), body.get("visual"), body.get("cohort"))
        handler._send_json(200, state)
        return True
    if path == "/internal/me/refresh":
        running = refresh_jobs.status(user["id"])
        if not running.get("running") and not refresh_limiter.allow(user["id"]):
            handler._send_json(429, {"ok": False, "error": "refresh_cooldown",
                                     "message": "Three reads per quarter hour from the site; Discord commands still work."})
            return True
        handler._send_json(202, refresh_jobs.start(user["id"], account))
        return True
    if path == "/internal/me/import":
        from rasmai.bot.builders.charts import shared_index
        from rasmai.scraping.scraper import MaimaiRatingAnalyzer
        if not import_limiter.allow(user["id"]):
            handler._send_json(429, {"ok": False, "error": "rate_limited", "message": "Five imports per quarter hour."})
            return True
        cached = cache_get(user["id"])      # whatever is on hand: the import is forgotten and rebuilt after anyway
        try:
            result = import_payload(user["id"], payload or {}, cached.analyzer if cached else MaimaiRatingAnalyzer(),
                                    cached.analyzer.chart_index if cached else shared_index())
        except ValueError as error:
            handler._send_json(400, {"ok": False, "error": "bad_export", "message": str(error)})
            return True
        except Exception:      # a shape nobody exported: the file is refused, not the server
            logger.exception("import refused")
            handler._send_json(400, {"ok": False, "error": "bad_export", "message": "That file could not be read as a Rasmai export."})
            return True
        forget_analysis(user["id"])       # the recorded plays feed the model; the next look rebuilds with them
        handler._send_json(200, {"ok": True, **result})
        return True
    if path == "/internal/me/kamaitachi/import":
        from rasmai.bot.builders.charts import shared_index
        from rasmai.scraping.kamaitachi import KamaitachiError, valid_username
        from rasmai.scraping.scraper import MaimaiRatingAnalyzer
        username = str((payload or {}).get("username") or "").strip()
        if not valid_username(username):
            handler._send_json(400, {"ok": False, "error": "bad_username"})
            return True
        if not kamaitachi_limiter.allow(user["id"]):
            handler._send_json(429, {"ok": False, "error": "rate_limited", "message": "Five reads from Kamaitachi per quarter hour."})
            return True
        cached = cache_get(user["id"])
        try:
            result = import_kamaitachi(user["id"], username, cached.analyzer if cached else MaimaiRatingAnalyzer(),
                                    cached.analyzer.chart_index if cached else shared_index())
        except KamaitachiError as error:
            handler._send_json(404 if error.kind == "no_such_user" else 502,
                               {"ok": False, "error": error.kind, **({} if error.kind == "no_such_user" else {"message": str(error)})})
            return True
        forget_analysis(user["id"])
        handler._send_json(200, {"ok": True, **result})
        return True
    return False
