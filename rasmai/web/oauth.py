from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlsplit
import base64
import binascii
import hashlib
import hmac
import io
import json
import logging
import re
import secrets
import time

from PIL import Image, ImageOps

from rasmai.config import get_public_base_url
from rasmai.security import _hash_code, decode_opaque_user_id, decrypt_token, encrypt_token, get_master_secret
from rasmai.storage.db import (login_code_name, login_code_verified, peek_login_code, oauth_app_add, oauth_app_delete, oauth_app_get, oauth_app_set, oauth_apps, oauth_code_add, oauth_code_get,
                               oauth_code_spend, oauth_code_waiting, oauth_icon_get, oauth_icon_set, oauth_purge, oauth_ticket_add, oauth_ticket_get, oauth_token_get,
                               oauth_tokens_drop)
from rasmai.web.grants import OAUTH_PREFIX, clean_origin, signed

logger = logging.getLogger(__name__)

Answer = Tuple[int, Dict[str, Any]]

MAX_APPS = 10
MAX_REDIRECTS = 10
TICKET_SECONDS = 600
CODE_SECONDS = 300
TOKEN_SECONDS = 3600
SCOPES = ("maimai:clal", "openid")
ICON_BYTES = 256 * 1024         # the biggest picture file a developer may send
ICON_PIXELS = 2048 * 2048       # and the biggest picture that file may claim to hold: 16 MB once opened, and far more than an icon needs
ICON_SIZE = 128                 # the square it is kept as

# Whether an app has to be looked at on the developer page before it may send players anywhere but its developer's own machine.
# Off for now: every registered redirect works, nobody can ask for a review and the page offers none. A player is still
# shown the app's name, its maker and where it sends them, in the extension's own window, and decides. Everything a
# review does is still here behind this one word.
REVIEW = False

# the characters a URL is written in, less "#": no space, quote, backslash or control character reaches a redirect or a page
_URL = re.compile(r"[A-Za-z0-9\-._~:/?\[\]@!$&'()*+,;=%]{1,200}")
_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43,128}")
_VERIFIER = re.compile(r"[A-Za-z0-9\-._~]{43,128}")
_CLAL = re.compile(r"[A-Za-z0-9]{64}")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _word(given: Any) -> str:
    """An id, code, token or secret as it was sent. They are only ever ASCII text, so anything else is "", which matches nothing."""
    return given if isinstance(given, str) and given.isascii() else ""


def _address(text: Any) -> bool:
    """Whether this is somewhere a redirect may go: https, or http on the developer's own machine."""
    return isinstance(text, str) and bool(_URL.fullmatch(text)) and bool(clean_origin(text))


def _local(uri: str) -> bool:
    return urlsplit(uri).hostname in ("localhost", "127.0.0.1")


def done_page() -> str:
    """This site's own page a player ends on, as the redirect of an app with nowhere to send them: a Discord bot, say.

    No code goes there. The app asks the token endpoint with its PKCE verifier until the player has answered.
    """
    return f"{get_public_base_url()}/oauth/done"


# This site's own application, for linking a Rasmai account with the extension. It is nobody's to register or edit: it is
# made here, verified, with a secret nobody is given, and its requests are started from a player's own link page.
RASMAI_APP = "rasmai-account-linking-1"


def rasmai_app() -> Dict[str, Any]:
    """This site's own application: made the first time it is needed, and put right if the site's address has changed since."""
    secret = hmac.new(get_master_secret().encode("utf-8"), b"oauth-rasmai-app", hashlib.sha256).hexdigest()
    wanted = {"redirects": [done_page()], "review": "verified", "secret_hash": _hash_code(secret)}
    app = oauth_app_get(RASMAI_APP)
    if not app:
        # owned by nobody, so it is on no developer's list
        oauth_app_add(RASMAI_APP, "", "Rasmai", "Rasmai", 1)
        app = oauth_app_get(RASMAI_APP)
    if any(app[key] != value for key, value in wanted.items()):
        oauth_app_set(RASMAI_APP, **wanted)
        app = oauth_app_get(RASMAI_APP)
    return app


def _login_key(held: Dict[str, Any]) -> Tuple[str, str]:
    """The login code and user a ticket of this site's own was started under. A login code is otherwise kept only as a hash, so here it is kept sealed."""
    code, _dot, user = decrypt_token(held["state"], _sealed_for(RASMAI_APP)).partition(".")
    return code, user


def _label(held: Dict[str, Any]) -> str:
    """Who a link's ticket is for: as the app that started it said, or for this site's own, as the login code was named when it was made."""
    if held["client_id"] == RASMAI_APP:
        return login_code_name(_login_key(held)[0])
    return held["state"] if held["redirect_uri"] == done_page() else ""


def _link_page(held: Dict[str, Any]) -> str:
    """The link page one of this site's own tickets was started from."""
    code, user = _login_key(held)
    return f"{get_public_base_url()}/connect/?{urlencode({'code': code, 'user': user})}"


def _https(text: Any) -> bool:
    return _address(text) and text.startswith("https://")


def _sealed_for(client_id: str) -> str:
    """What a stored sign-in is bound to, so one app's row opened as another's does not open."""
    return f"oauth:{client_id}"


def _back(uri: str, **added: str) -> str:
    """A redirect URI with these added to whatever query it already has; the empty ones are left out."""
    return uri + ("&" if "?" in uri else "?") + urlencode({key: value for key, value in added.items() if value})


def _icon_path(app: Dict[str, Any]) -> str:
    """Where the site serves an app's picture, "" with none. The mark in it changes with the picture, so the address can be cached."""
    return f"/api/oauth/icon/{app['id']}?v={app['icon']}" if app["icon"] else ""


def clean_icon(data: bytes) -> Optional[bytes]:
    """A picture a developer sent, redrawn as a square PNG; None when it is not a PNG, JPEG or WebP this site will open.

    Nothing of the file itself is kept. Only its pixels are read, cropped to a square and written out again, so whatever
    else the file carried (metadata, a second file after the picture, a page or a script dressed as one) is not in what
    players are served. An SVG is not a picture in this sense, it is a document that can run scripts, so it is refused.

    :param data: The file as it was sent.
    :type data: bytes
    :rtype: Optional[bytes]
    """
    try:
        with Image.open(io.BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as picture:
            # asked before a pixel is read: a few bytes can claim a picture too big to hold in memory
            if picture.width * picture.height > ICON_PIXELS:
                return None
            square = ImageOps.fit(ImageOps.exif_transpose(picture).convert("RGBA"), (ICON_SIZE, ICON_SIZE))
        # what Pillow read beside the pixels, the colour profile above all, which it would write back out byte for byte
        square.info.clear()
        redrawn = io.BytesIO()
        square.save(redrawn, "PNG", optimize=True)
        return redrawn.getvalue()
    except Exception:  # Pillow raises a dozen kinds for a file that is not what it says it is
        return None


def _shown(app: Dict[str, Any]) -> Dict[str, Any]:
    """An app as its developer sees it."""
    return {"id": app["id"], "name": app["name"], "description": app["description"], "website": app["website"], "privacy": app["privacy"],
            "redirects": app["redirects"], "hasSecret": bool(app["secret_hash"]), "review": app["review"], "icon": _icon_path(app),
            "blocked": bool(app["blocked"]),
            "createdAt": app["created_at"]}


def _asked(app: Dict[str, Any], uri: str, scopes: List[str], who: str = "") -> Dict[str, Any]:
    """What a player is told before they answer: who asks, where they are sent, for what, and whom the app says the request is for."""
    verified = app["review"] == "verified"
    # with reviews on, the picture only once it was reviewed: an app nobody looked at could wear anyone's logo
    return {"app": {"name": app["name"], "by": app["owner_name"], "website": app["website"], "privacy": app["privacy"],
                    "verified": verified, "icon": _icon_path(app) if verified or not REVIEW else ""},
            # whether there is such a thing as a review: with none, the page and the window say nothing of one
            "redirectHost": urlsplit(uri).netloc, "scopes": scopes, "reviews": REVIEW, **({"for": who} if who else {})}


def review_stamp(app: Dict[str, Any]) -> str:
    """A mark of what a reviewer was shown, so an app changed between the look and the press is not approved unseen.

    Keyed with the master secret and long: a developer cannot work out two apps that share a mark and swap one for the other.
    """
    seen = json.dumps([app["name"], app["owner_name"], app["website"], app["privacy"], app["icon"], app["redirects"]])
    return hmac.new(get_master_secret().encode("utf-8"), b"review-stamp:" + seen.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def apps_payload(user_id: str) -> Dict[str, Any]:
    """The signed-in developer's own apps, oldest first."""
    return {"ok": True, "max": MAX_APPS, "maxRedirects": MAX_REDIRECTS, "reviews": REVIEW, "donePage": done_page(),
            "apps": [_shown(app) for app in oauth_apps(user_id)]}


def _name(given: Any) -> str:
    return _line(given, 40) or ""


def _line(given: Any, limit: int) -> Optional[str]:
    """Text a developer typed, on one line with its spaces single; None when it is not text, is too long or holds what cannot be shown."""
    line = " ".join(given.split()) if isinstance(given, str) else None
    return line if line is not None and len(line) <= limit and line.isprintable() else None


def _changes(app: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """What an update asks to change, checked: ``(the error word, "" when it is fine; the columns to set)``."""
    changes: Dict[str, Any] = {}
    if payload.get("name") is not None:
        changes["name"] = _name(payload["name"])
        if not changes["name"]:
            return "bad_app", {}
    if payload.get("description") is not None:
        changes["description"] = _line(payload["description"], 200)
        if changes["description"] is None:
            return "bad_app", {}
    for key in ("website", "privacy"):
        if payload.get(key) is not None:
            if payload[key] != "" and not _https(payload[key]):
                return "bad_app", {}
            changes[key] = payload[key]
    if payload.get("redirects") is not None:
        given = payload["redirects"]
        # this site's own pages are no app's to send a player to, the done page aside: an address a slash away from it
        # would be saved as an ordinary redirect and never work
        own = get_public_base_url() + "/"
        if not isinstance(given, list) or len(given) > MAX_REDIRECTS or not all(_address(uri) for uri in given) \
                or any(uri.startswith(own) and uri != done_page() for uri in given):
            return "bad_redirect", {}
        changes["redirects"] = list(dict.fromkeys(given))
    # what players are shown, or where their sign-in is sent, is no longer what was looked at
    if app["review"] == "verified" and (any(changes.get(key, app[key]) != app[key] for key in ("name", "website", "privacy"))
                                        or any(not _local(uri) and uri not in app["redirects"] for uri in changes.get("redirects", ()))):
        changes["review"] = "pending"
    return "", changes


def app_write(path: str, user: Dict[str, Any], payload: Dict[str, Any]) -> Answer:
    """A developer making, changing or deleting one of their own apps.

    :param path: The request path, one of the five under ``/internal/me/apps``.
    :type path: str
    :param user: The signed-in developer.
    :type user: Dict[str, Any]
    :param payload: The request body.
    :type payload: Dict[str, Any]
    :returns: The HTTP status and the answer.
    :rtype: Answer
    """
    # who players are told made the app. A Discord handle is one account's and nobody else's; the name on a Google account
    # is whatever its owner typed, "Rasmai" included, so an account with no handle is named as what it is instead
    by = user.get("handle") or "a Google account"
    if path == "/internal/me/apps":
        name, app_id = _name(payload.get("name")), secrets.token_urlsafe(18)
        if not name:
            return 400, {"ok": False, "error": "bad_app"}
        if not oauth_app_add(app_id, user["id"], by, name, MAX_APPS):
            return 409, {"ok": False, "error": "too_many"}
        return 200, {"ok": True, "app": _shown(oauth_app_get(app_id))}
    app = oauth_app_get(_word(payload.get("id")))
    # someone else's app is answered exactly as one that does not exist
    if not app or app["user_id"] != user["id"]:
        return 404, {"ok": False, "error": "no_such_app"}
    if path == "/internal/me/apps/delete":
        oauth_app_delete(app["id"])
        return 200, {"ok": True}
    extra: Dict[str, Any] = {}
    if path == "/internal/me/apps/secret":
        extra["secret"] = secrets.token_urlsafe(32)
        changes: Dict[str, Any] = {"secret_hash": _hash_code(extra["secret"])}
    elif path == "/internal/me/apps/review":
        if not REVIEW:
            return 404, {"ok": False, "error": "not_found"}
        if not (_https(app["website"]) and _https(app["privacy"]) and any(not _local(uri) for uri in app["redirects"])):
            return 400, {"ok": False, "error": "bad_app"}
        # asking again about an app that is already verified does not take that away
        changes = {} if app["review"] == "verified" else {"review": "pending"}
    elif path == "/internal/me/apps/icon":
        png = None
        if payload.get("image"):
            try:
                sent = base64.b64decode(_word(payload["image"]), validate=True)
            except (binascii.Error, ValueError):
                sent = b""
            png = clean_icon(sent) if 0 < len(sent) <= ICON_BYTES else None
            if png is None:
                return 400, {"ok": False, "error": "bad_icon"}
        oauth_icon_set(app["id"], png)
        # the first half of the picture's SHA-256: the approval window checks the picture it is served against it
        changes = {"icon": hashlib.sha256(png).hexdigest()[:32] if png else ""}
        # the picture is part of what players are shown, so a verified app's new one is looked at again
        if app["review"] == "verified" and changes["icon"] != app["icon"]:
            changes["review"] = "pending"
    else:
        refused, changes = _changes(app, payload)
        if refused:
            return 400, {"ok": False, "error": refused}
    if changes.get("review") == "pending":
        logger.warning("an app is waiting for review on the developer page: %s (%s), from %s", changes.get("name", app["name"]), app["id"], user["id"])
    # a verified app keeps the maker's name it was reviewed with, which is the one players are shown
    named = {} if app["review"] == "verified" and "review" not in changes else {"owner_name": by}
    oauth_app_set(app["id"], **named, **changes)
    return 200, {"ok": True, "app": _shown(oauth_app_get(app["id"])), **extra}


def _usable(app: Dict[str, Any], uri: str) -> bool:
    """Whether the app may have a player sent to this redirect: one of its own, and with reviews on, anywhere but the developer's machine only once reviewed."""
    # with the done page the app is handed no code and asks with its verifier alone, which whoever made the link also holds:
    # it is only for an app with a client secret, so that nobody but the app can ask
    return (not app["blocked"] and uri in app["redirects"] and (_local(uri) or app["review"] == "verified" or not REVIEW)
            and (uri != done_page() or bool(app["secret_hash"])))


def begin(query: Dict[str, str]) -> Answer:
    """The authorize request, checked, and a ticket for the extension to answer it with.

    :param query: The request's parameters as the app sent the player with them.
    :type query: Dict[str, str]
    :rtype: Answer
    """
    oauth_purge()
    if query.get("ticket"):
        # a link an app with no website started for one player: the request is already here, waiting for its one answer
        held = oauth_ticket_get(_hash_code(_word(query["ticket"])))
        app = oauth_app_get(held["client_id"]) if held else None
        if not app or held["redirect_uri"] != done_page() or not _usable(app, held["redirect_uri"]):
            return 200, {"ok": False, "error": "invalid_request", "description": "This link has run out. Ask the app for a new one."}
        # an app with no website has no page to go back to; this site's own goes back to the link page
        return 200, {"ok": True, "ticket": query["ticket"], **_asked(app, held["redirect_uri"], held["scope"].split(), _label(held)),
                     "cancel": _link_page(held) if app["id"] == RASMAI_APP else ""}
    app = oauth_app_get(query.get("client_id", ""))
    uri = query.get("redirect_uri", "")
    # with no app or a redirect that is not the app's there is nowhere safe to send the player, so the page keeps them
    if not app:
        return 200, {"ok": False, "error": "invalid_client", "description": "No application has that client_id."}
    if app["blocked"]:
        return 200, {"ok": False, "error": "invalid_client", "description": "Rasmai has blocked this application."}
    if uri not in app["redirects"]:
        return 200, {"ok": False, "error": "invalid_redirect", "description": "That redirect_uri is not one registered for the application."}
    if uri == done_page():
        # a player only ends there through a link the app started itself, with its secret, saying who it is for
        return 200, {"ok": False, "error": "invalid_request", "description": "A request that ends on Rasmai's done page is started at /oauth/link."}
    state, scopes = query.get("state", ""), list(dict.fromkeys(query.get("scope", "").split()))
    challenge = query.get("code_challenge", "")
    if query.get("response_type") != "code":
        refused = ("unsupported_response_type", "response_type must be code.")
    elif len(state) > 512:
        # too long to hand back either
        state, refused = "", ("invalid_request", "state is longer than 512 characters.")
    elif not _CHALLENGE.fullmatch(challenge) or query.get("code_challenge_method") != "S256":
        refused = ("invalid_request", "PKCE is required: a code_challenge of 43 to 128 characters with code_challenge_method=S256.")
    elif "maimai:clal" not in scopes or any(scope not in SCOPES for scope in scopes):
        refused = ("invalid_scope", "scope must be maimai:clal, with openid if wanted.")
    elif not _usable(app, uri):
        refused = ("unauthorized_client", "Until Rasmai has reviewed the application it can only redirect to localhost or 127.0.0.1.")
    else:
        ticket = secrets.token_urlsafe(24)
        oauth_ticket_add(_hash_code(ticket), app["id"], uri, " ".join(scopes), state, challenge, int(time.time()) + TICKET_SECONDS)
        return 200, {"ok": True, "ticket": ticket, **_asked(app, uri, scopes), "cancel": _back(uri, error="access_denied", state=state)}
    return 200, {"ok": False, "error": refused[0], "description": refused[1],
                 "redirect": _back(uri, error=refused[0], error_description=refused[1], state=state)}


def request(ticket: str) -> Answer:
    """What a waiting request asks, for the extension's approval window.

    The window shows only the ``signed`` copy, which names this ticket and runs out with it: what it tells the player is
    then what this site said, whatever answered the request.
    """
    held = oauth_ticket_get(_hash_code(ticket))
    app = oauth_app_get(held["client_id"]) if held else None
    if not app:
        return 404, {"ok": False, "error": "expired"}
    asked = _asked(app, held["redirect_uri"], held["scope"].split(), _label(held))
    return 200, {"ok": True, **asked, "signed": signed(OAUTH_PREFIX, {"v": 1, "ticket": ticket, "exp": held["expires_at"], **asked})}


def answer(payload: Dict[str, Any], approve: bool) -> Answer:
    """The player's answer to a request: the ticket is spent, and on approval their sign-in is held, sealed, behind a code.

    :param payload: ``ticket``, and when approving ``clal`` and the cookie's ``expires`` in Unix seconds.
    :type payload: Dict[str, Any]
    :param approve: Whether the player approved.
    :type approve: bool
    :rtype: Answer
    """
    clal = _word(payload.get("clal")).strip().removeprefix("clal=")
    # before the ticket is spent, so a sign-in that was read wrongly can be sent again
    if approve and not _CLAL.fullmatch(clal):
        return 400, {"ok": False, "error": "bad_clal"}
    ticket_hash = _hash_code(_word(payload.get("ticket")))
    held = oauth_ticket_get(ticket_hash)
    app = oauth_app_get(held["client_id"]) if held else None
    # an approval of this site's own request does not spend it: the login it leads to can be refused, by maimai or because
    # it is down, and tried again, and it is the login code that works once. Every other answer spends the ticket
    if held and not (approve and app and app["id"] == RASMAI_APP):
        held = oauth_ticket_get(ticket_hash, spend=True)
    # asked again, since the app may have lost the redirect or its review in the minutes the ticket waited
    if not held or not app or not _usable(app, held["redirect_uri"]):
        return 400, {"ok": False, "error": "expired"}
    polled = held["redirect_uri"] == done_page()
    if app["id"] == RASMAI_APP:
        # this site's own: nothing is kept. Declined, the player is back on their link page; approved, the site links the
        # account with the sign-in it was just sent, under the login code that page holds
        code, user = _login_key(held)
        return 200, {"ok": True, "login": {"code": code, "user": user}} if approve else {"ok": True, "redirect": _link_page(held)}
    if not approve:
        if polled:
            # kept with no sign-in, as the answer the app is given when it asks
            oauth_code_add(_hash_code(secrets.token_urlsafe(32)), app["id"], held["redirect_uri"], held["scope"], held["challenge"], "", 0,
                           int(time.time()) + CODE_SECONDS)
        return 200, {"ok": True, "redirect": _back(held["redirect_uri"], error="access_denied", state="" if polled else held["state"])}
    try:
        expires = max(0, int(float(payload.get("expires") or 0)))
    except (TypeError, ValueError, OverflowError):
        expires = 0
    code = secrets.token_urlsafe(32)
    oauth_code_add(_hash_code(code), app["id"], held["redirect_uri"], held["scope"], held["challenge"],
                   encrypt_token(clal, _sealed_for(app["id"])), expires, int(time.time()) + CODE_SECONDS)
    # the done page is told nothing: the code stays here, for the app to ask for
    return 200, {"ok": True, "redirect": held["redirect_uri"] if polled else _back(held["redirect_uri"], code=code, state=held["state"])}


def rasmai_link(payload: Dict[str, Any]) -> Answer:
    """A player's link page starting a request of this site's own, so the extension can be asked for their sign-in in one press.

    It is the login code that is trusted, as it is when the sign-in is pasted: the ticket only carries it to the answer.

    :param payload: ``code`` and ``user`` as the link page holds them, and ``requireVerified`` when the site runs its human check.
    :type payload: Dict[str, Any]
    :rtype: Answer
    """
    oauth_purge()
    code, user = _word(payload.get("code")), _word(payload.get("user"))
    user_id = decode_opaque_user_id(user) if user else None
    if not user_id:
        return 400, {"ok": False, "kind": "invalid_user", "error": "invalid user identifier"}
    record = peek_login_code(code)
    if not record or record[0] != user_id:
        return 400, {"ok": False, "kind": "expired", "error": "invalid or expired login code"}
    if record[1] == "jp":
        return 400, {"ok": False, "kind": "region", "error": "a Japan account is linked with its SEGA ID"}
    if payload.get("requireVerified") and not login_code_verified(code):
        return 403, {"ok": False, "kind": "verify", "error": "complete the check on the connect page first"}
    if rasmai_app()["blocked"]:
        return 403, {"ok": False, "kind": "blocked", "error": "linking with the extension is switched off"}
    ticket = secrets.token_urlsafe(24)
    oauth_ticket_add(_hash_code(ticket), RASMAI_APP, done_page(), "maimai:clal", encrypt_token(f"{code}.{user}", _sealed_for(RASMAI_APP)), "",
                     int(time.time()) + TICKET_SECONDS)
    return 200, {"ok": True, "link": f"{get_public_base_url()}/oauth/authorize?ticket={ticket}"}


def link(payload: Dict[str, Any]) -> Answer:
    """An app with no website starting a request for one player: the link to give them, good for ten minutes and one answer.

    The app says who the link is for, and the player is shown that before they answer. Only the app can say it, with
    its secret, so a link passed on to someone else still names the person who asked for it.

    :param payload: ``client_id``, ``client_secret``, ``code_challenge``, ``code_challenge_method``, ``for`` and, if wanted, ``scope``.
    :type payload: Dict[str, Any]
    :rtype: Answer
    """
    oauth_purge()
    sent = {key: _word(payload.get(key)) for key in ("client_id", "client_secret", "code_challenge", "code_challenge_method", "scope")}
    app = oauth_app_get(sent["client_id"])
    if not app or not app["secret_hash"] or not hmac.compare_digest(_hash_code(sent["client_secret"]), app["secret_hash"]):
        return 401, {"error": "invalid_client", "error_description": "Unknown client_id, or a missing or wrong client_secret."}
    if not _usable(app, done_page()):
        return 400, {"error": "unauthorized_client", "error_description": "Rasmai's done page is not one of the application's redirects."}
    who, scopes = _line(payload.get("for"), 40), list(dict.fromkeys((sent["scope"] or "maimai:clal").split()))
    if not who:
        return 400, {"error": "invalid_request", "error_description": "for must say who the link is for, in up to 40 characters."}
    if not _CHALLENGE.fullmatch(sent["code_challenge"]) or sent["code_challenge_method"] != "S256":
        return 400, {"error": "invalid_request", "error_description": "PKCE is required: a code_challenge of 43 to 128 characters with code_challenge_method=S256."}
    if "maimai:clal" not in scopes or any(scope not in SCOPES for scope in scopes):
        return 400, {"error": "invalid_scope", "error_description": "scope must be maimai:clal, with openid if wanted."}
    ticket = secrets.token_urlsafe(24)
    oauth_ticket_add(_hash_code(ticket), app["id"], done_page(), " ".join(scopes), who, sent["code_challenge"], int(time.time()) + TICKET_SECONDS)
    return 200, {"link": f"{get_public_base_url()}/oauth/authorize?ticket={ticket}", "expires_in": TICKET_SECONDS, "interval": 5}


def token(payload: Dict[str, Any]) -> Answer:
    """The app exchanging its code, with the PKCE verifier, for an access token.

    :param payload: ``grant_type``, ``code``, ``redirect_uri``, ``client_id``, ``code_verifier`` and, for an app with one, ``client_secret``.
    :type payload: Dict[str, Any]
    :rtype: Answer
    """
    oauth_purge()
    sent = {key: _word(payload.get(key)) for key in ("grant_type", "code", "redirect_uri", "client_id", "code_verifier", "client_secret")}
    if sent["grant_type"] != "authorization_code":
        return 400, {"error": "unsupported_grant_type", "error_description": "grant_type must be authorization_code."}
    app = oauth_app_get(sent["client_id"])
    if not app or (app["secret_hash"] and not hmac.compare_digest(_hash_code(sent["client_secret"]), app["secret_hash"])):
        return 401, {"error": "invalid_client", "error_description": "Unknown client_id, or a missing or wrong client_secret."}
    if sent["redirect_uri"] == done_page():
        # an app with no website was never handed a code: it asks with its verifier until the player has answered
        if not _usable(app, sent["redirect_uri"]):
            return 400, {"error": "unauthorized_client", "error_description": "The application cannot use Rasmai's done page."}
        if not _VERIFIER.fullmatch(sent["code_verifier"]):
            return 400, {"error": "invalid_grant", "error_description": "code_verifier must be the 43 to 128 characters the code_challenge was made from."}
        held = oauth_code_waiting(app["id"], sent["redirect_uri"], _b64(hashlib.sha256(sent["code_verifier"].encode("ascii")).digest()))
        if not held:
            return 400, {"error": "authorization_pending", "error_description": "The player has not answered yet."}
        if not held["clal"]:
            return 400, {"error": "access_denied", "error_description": "The player declined."}
        code_hash = held["code_hash"]
    else:
        code_hash = _hash_code(sent["code"])
        held = oauth_code_get(code_hash)
        if held and held["used"]:
            # a code seen twice may have been stolen, so what its first use was given ends too
            oauth_tokens_drop(code_hash)
            held = None
    # the redirect is asked about again: the app may have lost it, or its review, since the player approved
    if not held or held["client_id"] != app["id"] or held["redirect_uri"] != sent["redirect_uri"] or not _usable(app, held["redirect_uri"]):
        return 400, {"error": "invalid_grant", "error_description": "The code is wrong, expired or already used, or was issued for another client_id or redirect_uri."}
    if not _VERIFIER.fullmatch(sent["code_verifier"]) or not hmac.compare_digest(
            _b64(hashlib.sha256(sent["code_verifier"].encode("ascii")).digest()), held["challenge"]):
        return 400, {"error": "invalid_grant", "error_description": "code_verifier does not match the code_challenge."}
    access = secrets.token_urlsafe(32)
    if not oauth_code_spend(code_hash, _hash_code(access), int(time.time()) + TOKEN_SECONDS):
        return 400, {"error": "invalid_grant", "error_description": "The code is already used."}
    return 200, {"access_token": access, "token_type": "Bearer", "expires_in": TOKEN_SECONDS, "scope": held["scope"]}


def userinfo(access: str) -> Answer:
    """The player's sign-in, for the app holding a live access token."""
    held = oauth_token_get(_hash_code(access))
    # the app is asked for too: one deleted with its developer's account leaves its tokens until the next purge, and one blocked gets nothing
    app = oauth_app_get(held["client_id"]) if held else None
    clal = decrypt_token(held["clal"], _sealed_for(held["client_id"])) if app and not app["blocked"] else ""
    if not clal:
        return 401, {"error": "invalid_token"}
    sub = hmac.new(get_master_secret().encode("utf-8"), f"oauth-sub:{held['client_id']}:{clal}".encode("utf-8"), hashlib.sha256).digest()
    return 200, {"sub": _b64(sub)[:22], "maimai_clal": clal, "maimai_clal_expires_at": held["clal_expires"]}


def icon(handler: Any, app_id: str) -> None:
    """An app's picture as this site redrew it, or 404.

    :param handler: The request being answered.
    :type handler: Any
    :param app_id: The app's client id.
    :type app_id: str
    """
    png = oauth_icon_get(app_id) if re.fullmatch(r"[A-Za-z0-9_-]{24}", app_id or "") else None
    if png is None:
        handler._send_json(404, {"ok": False, "error": "not_found"})
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "image/png")
    handler.send_header("Content-Length", str(len(png)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(png)


def handle_get(path: str, query: Dict[str, str]) -> Optional[Answer]:
    """The reads under ``/internal/oauth/``; None for a path that is not one."""
    if path == "/internal/oauth/begin":
        return begin(query)
    if path == "/internal/oauth/request":
        return request(query.get("ticket", ""))
    return None


def handle_post(path: str, payload: Dict[str, Any]) -> Optional[Answer]:
    """The writes under ``/internal/oauth/``; None for a path that is not one."""
    if path in ("/internal/oauth/approve", "/internal/oauth/deny"):
        return answer(payload, approve=path.endswith("/approve"))
    if path == "/internal/oauth/token":
        return token(payload)
    if path == "/internal/oauth/link":
        return link(payload)
    if path == "/internal/oauth/rasmai":
        return rasmai_link(payload)
    if path == "/internal/oauth/userinfo":
        return userinfo(_word(payload.get("token")))
    return None
