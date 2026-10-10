from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional, Any
from urllib.parse import urlparse, parse_qs
import gzip
import hmac
import json
import queue
import re
import sys
import threading
import logging

from rasmai.config import (
    DEBUG_EXPORT_JSON,
    INTERNAL_API_SECRET,
    MAIMAI_BASE_URLS,
    WEBSERVER_HOST,
    WEBSERVER_PORT,
    region_supported,
    unsupported_region_text,
)
from rasmai.storage.db import (
    consume_login_code,
    get_database_connection,
    get_connected_account,
    is_discord_id,
    is_web_id,
    login_code_expiry,
    login_code_issued_at,
    login_code_verified,
    mark_login_code_verified,
    peek_login_code,
    upsert_connected_account,
)
from rasmai.web import dashboard
from rasmai.errors import report
from rasmai.web.links import build_login_link_payload
from rasmai.scraping.scraper import MaimaiRatingAnalyzer
from rasmai.scraping.scraper.session import SessionRejected
from rasmai.security import (decode_opaque_user_id, login_attempt_allowed, normalize_login_token,
                             public_limiter, public_reason, sega_id_token)
from rasmai.util import _json_safe, export_debug_payload

logger = logging.getLogger(__name__)


class _QueueingServer(ThreadingHTTPServer):
    """The stdlib server, listening with a queue long enough for a page opening at once.

    The stdlib default backlog is five: the sixth connection arriving before the first is
    accepted is refused outright, not queued. A dashboard asks for six things as it opens, so
    two people opening theirs together was enough to turn requests into 503s. Measured with
    a load test of the dashboard: 89% of requests refused at 50 clients, every one of them in 0ms.

    A thousand people opening theirs at once is six thousand connections, and the thread taking
    them shares the interpreter with the builds, so it falls behind in bursts: at 128, 42% were
    refused. Linux holds up to net.core.somaxconn of these (4096 by default); Windows holds 200
    whatever is asked, so a local run understates this.
    """

    request_queue_size = 1024

    # A fixed set of threads answering, rather than one started per connection. Starting one waits
    # for it to get the interpreter, which the builds keep busy, so under a crowd the thread taking
    # connections spent its time starting threads and the queue above overflowed regardless of its
    # length: a load test had 40% refused at a thousand people, a read that needs no analysis among them.
    # Connections past these wait their turn, accepted, instead of being refused.
    workers = 64

    def server_activate(self) -> None:
        super().server_activate()
        self._accepted: "queue.SimpleQueue" = queue.SimpleQueue()
        for _ in range(self.workers):
            threading.Thread(target=self._answer, name="internal-api", daemon=True).start()

    def process_request(self, request, client_address) -> None:
        self._accepted.put((request, client_address))

    def _answer(self) -> None:
        while True:
            taken = self._accepted.get()
            if taken is None:
                return
            self.process_request_thread(*taken)

    def handle_error(self, request, client_address) -> None:
        # the other end hung up before its answer went out, a page closed or a proxy that gave up:
        # nobody is left to answer, and the traceback the stdlib prints for it is noise
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        # logged rather than printed, so it is reported like every other error and is not only in the container's output
        logger.exception("internal api: a request failed before it was answered")

    def server_close(self) -> None:
        super().server_close()
        for _ in range(self.workers if hasattr(self, "_accepted") else 0):     # none when the bind itself failed
            self._accepted.put(None)


class InternalApiServer:
    """The bot's side of the website: JSON only, for the Next.js server to call.

    The public site (pages, Discord sign-in, sessions, the Turnstile check, headers and
    rate limits) is the Next.js app in `web/`. It talks to this server over the local
    network with a shared secret and tells it who the signed-in person is."""

    def __init__(self, host: str = WEBSERVER_HOST, port: int = WEBSERVER_PORT):
        self.host = host
        self.port = port
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not INTERNAL_API_SECRET and self.host not in ("127.0.0.1", "localhost", "::1"):
            # the API takes the caller's word for who they are, so with no secret anything that can reach
            # the port is any user; the bot itself carries on without the website
            logger.error("The internal API was NOT started: RASMAI_INTERNAL_SECRET is empty and %s is not a "
                         "loopback address. Set RASMAI_INTERNAL_SECRET to start it.", self.host)
            return

        class Handler(BaseHTTPRequestHandler):
            timeout = 20

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                status = args[1] if len(args) > 1 else ""
                path = urlparse(self.path).path
                # the dashboard polls these every couple of seconds; at info they bury everything else
                said = logger.debug if path in ("/internal/me/refresh", "/internal/me/beta",
                                                "/health", "/api/health") else logger.info
                said(f"internal api: {self.command} {path} -> {status}")

            # ---- plumbing

            def _authorized(self) -> bool:
                if not INTERNAL_API_SECRET:
                    return True
                # bytes, because compare_digest raises on a str that is not ASCII, and a header can be anything
                return hmac.compare_digest(self.headers.get("X-Rasmai-Internal", "").encode("utf-8"),
                                           INTERNAL_API_SECRET.encode("utf-8"))

            def _user(self) -> Optional[Dict[str, Any]]:
                """The signed-in person, as the web server authenticated them: a Discord id, or the id of an account made on the site.

                :rtype: Optional[Dict[str, Any]]
                """
                raw = self.headers.get("X-Rasmai-User", "")
                if not raw:
                    return None
                try:
                    user = json.loads(raw)
                except json.JSONDecodeError:
                    return None
                if not isinstance(user, dict) or not (is_discord_id(user.get("id")) or is_web_id(user.get("id"))):
                    return None
                return {"id": str(user["id"]), "name": str(user.get("name", "")), "handle": str(user.get("handle", "")),
                        "avatar": str(user.get("avatar", ""))}

            def _client_key(self) -> str:
                """The visitor's address as the web server saw it, for per-client limits.

                :rtype: str
                """
                return self.headers.get("X-Rasmai-Client", "") or self.client_address[0]

            def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(_json_safe(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                if payload.get("retryAfter"):
                    # said in the header too, where a client that drops bodies can still read it
                    self.send_header("Retry-After", str(payload["retryAfter"]))
                if len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", ""):
                    body = gzip.compress(body, compresslevel=6)
                    self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _parse_payload(self, limit: int = 65536) -> Dict[str, Any]:
                content_type = self.headers.get("Content-Type", "")
                length = int(self.headers.get("Content-Length", "0"))
                if length > limit:
                    raise ValueError("request body too large")
                raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
                if "application/json" in content_type:
                    return json.loads(raw_body or "{}")
                parsed = parse_qs(raw_body)
                return {key: values[0] for key, values in parsed.items() if values}

            # ---- routes

            def do_GET(self) -> None:  # noqa: N802
                route = urlparse(self.path)
                query = parse_qs(route.query)
                if route.path in ("/health", "/api/health"):
                    # a bot whose database has gone is not healthy, however well it answers: the container's
                    # health check reads this, so a stale bind mount shows up in docker ps instead of in every command
                    try:
                        get_database_connection().close()
                    except Exception as error:
                        logger.error("the health check could not open the database: %s", error)
                        self._send_json(503, {"ok": False, "error": "database"})
                        return
                    self._send_json(200, {"ok": True, "time": datetime.now().isoformat()})
                    return
                if not self._authorized():
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                if route.path.startswith("/internal/jacket/"):
                    dashboard.jacket(self, route.path[len("/internal/jacket/"):])
                    return
                if route.path.startswith("/internal/area-image/"):
                    dashboard.area_image(self, route.path[len("/internal/area-image/"):])
                    return
                if route.path.startswith("/internal/nameplate/"):
                    dashboard.nameplate(self, route.path[len("/internal/nameplate/"):])
                    return
                if route.path.startswith("/internal/me"):
                    user = self._user()
                    if user is None:
                        self._send_json(401, {"ok": False, "error": "signed_out"})
                        return
                    try:
                        handled = dashboard.handle_get(self, route.path, query, user)
                    except dashboard.StillBuilding as wait:
                        self._send_json(503, {"ok": False, "error": "building", "retryAfter": wait.seconds,
                                          "position": wait.position, "eta": wait.eta})
                        return
                    except Exception as error:
                        # answered and reported, as a POST is: unanswered, the site saw the connection drop and told the
                        # person the bot was unreachable, every time, while nothing here said why
                        error_id = report(error, f"dashboard read {route.path} failed",
                                          {"Page": route.path, "Query": ", ".join(sorted(query)), "User": user.get("id")})
                        self._send_json(500, {"ok": False, "error": "server", "errorId": error_id})
                        return
                    if not handled:
                        self._send_json(404, {"ok": False, "error": "not_found"})
                    return
                if route.path == "/internal/status":
                    self._status(query)
                    return
                if route.path == "/internal/statuspage":
                    from rasmai.web.statuspage import status_payload
                    self._send_json(200, status_payload())
                    return
                if route.path == "/internal/statuspage/history":
                    from rasmai.storage.db.status import status_history
                    self._send_json(200, status_history())
                    return
                if route.path.startswith("/internal/public/"):
                    # no sign-in: the slug is the whole credential, and the payload carries only
                    # what its owner opted into. A profile switched off answers as if it never existed.
                    slug = route.path[len("/internal/public/"):]
                    if not public_limiter.allow(self._client_key()):
                        self._send_json(429, {"ok": False, "error": "rate_limited"})
                        return
                    try:
                        shared = dashboard.public_payload(slug)
                    except Exception:
                        # a shared link is opened by people with no way to report a fault: answer, log, move on
                        logger.exception("building a public profile failed")
                        self._send_json(502, {"ok": False, "error": "unavailable"})
                        return
                    if shared is None:
                        # an address answering to nothing is a typo or somebody working through
                        # addresses, and that is what the strict limit is for. Counting every read
                        # against it instead shut the page, its picture and the link preview out
                        # after ten views between them.
                        login_attempt_allowed(self._client_key())
                        self._send_json(404, {"ok": False, "error": "not_found"})
                        return
                    self._send_json(200, shared)
                    return
                if route.path == "/internal/servers":
                    self._send_json(200, dashboard.servers_payload())
                    return
                if route.path == "/internal/notice":
                    self._send_json(200, dashboard.notice_payload())
                    return
                if route.path == "/internal/connect-info":
                    self._connect_info(query)
                    return
                self._send_json(404, {"ok": False, "error": "not_found"})

            def _status(self, query: Dict[str, Any]) -> None:
                opaque = (query.get("user") or [""])[0].strip()
                code = (query.get("code") or [""])[0].strip()
                user_id = decode_opaque_user_id(opaque) if opaque else None
                if not user_id:
                    self._send_json(200, {"connected": False})
                    return
                account = get_connected_account(user_id)
                connected = bool(account)
                if connected and code:
                    # linked *by this link*: the account was written after the code was issued
                    issued = login_code_issued_at(code)
                    try:
                        updated = datetime.fromisoformat(str(account.get("updatedAt", "")))
                    except ValueError:
                        updated = None
                    connected = bool(issued and updated and updated >= issued)
                profile = (account or {}).get("officialProfile") or {}
                self._send_json(200, {
                    "connected": connected,
                    "player": profile.get("name", "") if connected else "",
                    "region": (account or {}).get("region", "") if connected else "",
                })

            def _connect_info(self, query: Dict[str, Any]) -> None:
                code = (query.get("code") or [""])[0].strip()
                opaque = (query.get("user") or [""])[0].strip()
                user_id = decode_opaque_user_id(opaque) if opaque else None
                if not user_id:
                    self._send_json(400, {"ok": False, "kind": "invalid_user"})
                    return
                record = peek_login_code(code)
                if not record or record[0] != user_id:
                    self._send_json(400, {"ok": False, "kind": "expired"})
                    return
                region = record[1] if record[1] in MAIMAI_BASE_URLS else "intl"
                if not region_supported(region):
                    # a code issued for a region nobody can sign in from yet: no gateway link to follow
                    self._send_json(400, {"ok": False, "kind": "region", "region": region,
                                          "error": unsupported_region_text(region)})
                    return
                login_info = build_login_link_payload(opaque, code, region)
                try:
                    expires_at = login_code_expiry(datetime.fromisoformat(record[2]))
                except ValueError:
                    expires_at = login_code_expiry()
                self._send_json(200, {
                    "ok": True,
                    "method": login_info["method"],        # "bookmark" (International) or "segaid" (Japan)
                    "loginLink": login_info["loginLink"],
                    "bookmarklet": login_info["bookmarklet"],
                    "expiresAt": expires_at.isoformat(),
                    "expiresDisplay": expires_at.strftime("%H:%M"),
                    "region": region,
                    "verified": login_code_verified(code),   # the web server passed the human check for this code
                })

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if not self._authorized():
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                try:
                    # an export of a big account is a few hundred KB; nothing else posted here comes near 64 KB
                    payload = self._parse_payload(limit=4 * 1024 * 1024 if path == "/internal/me/import" else 65536)
                except Exception as error:
                    self._send_json(400, {"ok": False, "error": f"invalid_request: {error}"})
                    return
                try:
                    if path.startswith("/internal/auth/"):
                        if not dashboard.handle_auth(self, path, payload):
                            self._send_json(404, {"ok": False, "error": "not_found"})
                        return
                    if path.startswith("/internal/me"):
                        user = self._user()
                        if user is None:
                            self._send_json(401, {"ok": False, "error": "signed_out"})
                            return
                        if dashboard.handle_post(self, path, user, payload):
                            return
                        self._send_json(404, {"ok": False, "error": "not_found"})
                        return
                    if path == "/internal/verify":
                        self._verify(payload)
                        return
                    if path == "/internal/login":
                        self._login(payload)
                        return
                    self._send_json(404, {"ok": False, "error": "not_found"})
                except dashboard.StillBuilding as wait:
                    self._send_json(503, {"ok": False, "error": "building", "retryAfter": wait.seconds,
                                          "position": wait.position, "eta": wait.eta})
                except Exception as error:
                    error_id = report(error, f"internal api {self.path.split('?')[0]} failed", {"Page": self.path.split("?")[0]})
                    self._send_json(502, {"ok": False, "kind": "unknown", "error": public_reason(error), "errorId": error_id})

            def _verify(self, payload: Dict[str, Any]) -> None:
                """The web server verified a Turnstile token for this code; remember it on the code.

                :param payload: The request body.
                :type payload: Dict[str, Any]
                """
                opaque_user = str(payload.get("user", "")).strip()
                code = str(payload.get("code", "")).strip()
                user_id = decode_opaque_user_id(opaque_user) if opaque_user else None
                record = peek_login_code(code)
                if not user_id or not record or record[0] != user_id:
                    self._send_json(401, {"ok": False, "kind": "expired", "error": "invalid or expired login code"})
                    return
                mark_login_code_verified(code)
                self._send_json(200, {"ok": True, "verified": True})

            def _login(self, payload: Dict[str, Any]) -> None:
                """A login code plus what proves the account: for International, the session cookie the
                bookmarklet read on SEGA's gateway; for Japan, the SEGA ID, password and Aime card typed on
                the connect page.

                :param payload: The request body.
                :type payload: Dict[str, Any]
                """
                opaque_user = str(payload.get("user", "")).strip()
                code = str(payload.get("code", "")).strip()
                token = str(payload.get("token", "")).strip()
                sega_id = str(payload.get("segaId", "")).strip()
                password = str(payload.get("password", ""))
                require_verified = bool(payload.get("requireVerified"))

                def fail(status: int, kind: str, message: str) -> None:
                    self._send_json(status, {"ok": False, "kind": kind, "error": message})

                if not login_attempt_allowed(self._client_key()):
                    fail(429, "rate_limited", "too many sign-in attempts")
                    return
                if not opaque_user or not code or not (token or (sega_id and password)):
                    fail(400, "no_login", "missing required form fields")
                    return
                user_id = decode_opaque_user_id(opaque_user)
                if not user_id:
                    fail(401, "invalid_user", "invalid user identifier")
                    return
                record = peek_login_code(code)
                if not record or record[0] != user_id:
                    fail(401, "expired", "invalid or expired login code")
                    return
                if require_verified and not login_code_verified(code):
                    fail(403, "verify", "complete the check on the connect page first")
                    return
                region = record[1] if record[1] in MAIMAI_BASE_URLS else "intl"
                if not region_supported(region):
                    # before the maintenance check: a server coming back would not make this one work
                    fail(400, "region", unsupported_region_text(region))
                    return
                # the session can only be proved against the score site, and the Aime gateway being up says
                # nothing about that one. Refusing here leaves the login code unspent, so the same link works later.
                if region == "jp":
                    try:
                        aime = int(str(payload.get("aime") or "1").strip())
                    except ValueError:
                        aime = 0
                    if not sega_id or not password:
                        fail(400, "no_login", "enter the SEGA ID and password you use on maimaidx.jp")
                        return
                    if len(sega_id) > 256 or len(password) > 256 or not 1 <= aime <= 20:
                        fail(400, "no_login", "the SEGA ID, password or Aime card number is not valid")
                        return
                    final_token = sega_id_token(sega_id, password, aime - 1)
                else:
                    if not re.fullmatch(r"[A-Za-z0-9]{64}", token):
                        fail(400, "no_login", "session token has an unexpected format")
                        return
                    final_token = normalize_login_token(token)
                down = dashboard.servers_down_note(region)
                if down:
                    fail(503, "maintenance", down)
                    return
                try:
                    official_profile = MaimaiRatingAnalyzer().fetch_official_player_profile(final_token, region)
                except SessionRejected as error:
                    # the sign-in itself was turned down: for Japan, a wrong SEGA ID, password or card
                    logger.info("A sign-in was refused while linking (%s): %s", region, public_reason(error))
                    # the login code is still unspent here, so the way on is the same link, not a new /login
                    fail(401, "credentials" if region == "jp" else "upstream", public_reason(error) if region == "jp" else
                         "maimai didn't accept that sign-in - it's probably expired or already used. Sign in to the gateway "
                         "again and press the bookmark. Your login link still works.")
                    return
                except Exception as error:
                    reason = public_reason(error)
                    # a 5xx from the score site is the site, not the session: name it as such and keep the link alive
                    server_side = bool(re.search(r"HTTP 5\d\d", str(error)))
                    if server_side:
                        logger.info("maimai DX NET could not confirm a session right now: %s", reason)
                        fail(503, "maintenance", "maimai DX NET answered with an error; it is probably down")
                    else:
                        logger.exception("Failed to validate connected token")
                        fail(502, "upstream", reason)
                    return
                # the session works: spend the code now, so nothing above can burn the link on its way to failing
                if not consume_login_code(code):
                    fail(401, "expired", "invalid or expired login code")
                    return
                upsert_connected_account(user_id, region, final_token, official_profile=_json_safe(official_profile))
                # linking only proves the session works; the scores still have to be read. Start that
                # here so the dashboard and the first command find them ready instead of scraping on demand.
                try:
                    account = get_connected_account(user_id)
                    if account is not None:
                        dashboard.refresh_jobs.start(user_id, account)
                except Exception:
                    logger.exception("Could not start the first score read after linking")
                if DEBUG_EXPORT_JSON:
                    export_debug_payload({
                        "connectedAt": datetime.now().isoformat(), "source": "api/login",
                        "userId": user_id, "region": region, "officialProfile": official_profile,
                    })
                self._send_json(200, {
                    "ok": True, "connected": True, "region": region,
                    "player": {"name": getattr(official_profile, "name", ""), "rating": getattr(official_profile, "rating", "")},
                })

        self.httpd = _QueueingServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Internal API for the website listening on http://{self.host}:{self.port}")
        # a restart empties every analysis: rebuild the recently active ones before they ask, behind anyone who does
        threading.Thread(target=dashboard.warm_recent, name="warm-analyses", daemon=True).start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
