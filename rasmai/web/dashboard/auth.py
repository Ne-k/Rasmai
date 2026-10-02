from typing import Any, Dict
import logging

from rasmai.bot.state.forget import forget_user
from rasmai.config import region_supported, unsupported_region_text
from rasmai.security import RateLimiter, login_attempt_allowed
from rasmai.storage.db import (account_exists, clean_identity, create_person, is_discord_id, is_web_id,
                               merge_accounts, resolve_identity)
from rasmai.web.links import build_login_session_payload

logger = logging.getLogger(__name__)

# sign-ins resolved per visitor. The site calls these on every return from Google or Discord, and a
# person signs in a few times a day at most, so this stops a script walking identities, not a person.
auth_limiter = RateLimiter(30, 600)

REGIONS = ("intl", "jp")


def _forget(*user_ids: str) -> None:
    for user_id in user_ids:
        forget_user(user_id)


def _answer(handler: Any, outcome: Dict[str, Any], with_status: bool = False) -> None:
    status = outcome["status"]
    if status == "error":
        handler._send_json(409 if outcome["error"] == "identity_taken" else 404, {"ok": False, "error": outcome["error"]})
    elif status in ("needs_choice", "needs_terms"):
        handler._send_json(200, {"ok": True, **outcome})
    else:
        merged = outcome.get("merged") or outcome.get("from")
        if merged:
            # what the process holds for either side predates the data that just joined them
            _forget(merged, outcome["userId"])
        handler._send_json(200, {"ok": True, **({"status": "signed_in"} if with_status else {}), "userId": outcome["userId"]})


def handle_auth(handler: Any, path: str, payload: Dict[str, Any]) -> bool:
    """The three sign-in steps the site calls: resolve whose account a sign-in opens, create one after consent, merge two; True when answered.

    :param handler: The request being answered.
    :type handler: Any
    :param path: The request path.
    :type path: str
    :param payload: The request body.
    :type payload: Dict[str, Any]
    :rtype: bool
    """
    if path not in ("/internal/auth/resolve", "/internal/auth/create", "/internal/auth/merge"):
        return False
    if not auth_limiter.allow(handler._client_key()):
        handler._send_json(429, {"ok": False, "error": "rate_limited"})
        return True
    body = payload if isinstance(payload, dict) else {}
    try:
        if path == "/internal/auth/resolve":
            session = body.get("sessionUserId")
            if session and not (is_discord_id(session) or is_web_id(session)):
                raise ValueError("bad session user")
            one = clean_identity(body)
            _answer(handler, resolve_identity(one["provider"], one["subject"], one["email"], one["emailVerified"],
                                              str(session) if session else None), with_status=True)
        elif path == "/internal/auth/create":
            identities = body.get("identities")
            if not isinstance(identities, list):
                raise ValueError("identities must be a list")
            _answer(handler, create_person(identities, str(body.get("termsVersion") or "")))
        else:
            if body.get("keep") not in ("from", "to"):
                raise ValueError("keep must be from or to")
            outcome = merge_accounts(str(body.get("from") or ""), str(body.get("to") or ""), body["keep"], body.get("identity") or None)
            _answer(handler, outcome)
    except ValueError as error:
        handler._send_json(400, {"ok": False, "error": "bad_request", "message": str(error)})
    return True


def start_link(handler: Any, user: Dict[str, Any], payload: Dict[str, Any]) -> None:
    """Give the signed-in person, a site-only account included, the connect page that links their maimai account.

    :param handler: The request being answered.
    :type handler: Any
    :param user: The signed-in person.
    :type user: Dict[str, Any]
    :param payload: The request body, ``{"region": "intl" | "jp"}``.
    :type payload: Dict[str, Any]
    """
    region = str((payload or {}).get("region") or "")
    if region not in REGIONS:
        handler._send_json(400, {"ok": False, "error": "bad_region"})
        return
    if not login_attempt_allowed(f"link:{user['id']}"):
        handler._send_json(429, {"ok": False, "error": "rate_limited"})
        return
    if not account_exists(user["id"]):
        handler._send_json(404, {"ok": False, "error": "not_found"})
        return
    if not region_supported(region):
        handler._send_json(400, {"ok": False, "error": "region", "message": unsupported_region_text(region)})
        return
    handler._send_json(200, {"ok": True, "connectUrl": build_login_session_payload(user["id"], region)["connectUrl"]})
