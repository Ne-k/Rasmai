from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit
import base64
import hashlib
import hmac
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rasmai.config import get_public_base_url
from rasmai.security import get_master_secret
from rasmai.storage.db import link_bots_get

GRANT_SECONDS = 24 * 3600       # how long a grant is good for, so a bot taken off the list is refused within a day
SIGNED_PREFIX = b"aime-grant."  # what is signed is this and the grant's body, so the key's signature on anything else is not a grant
OAUTH_PREFIX = b"aime-oauth."   # an OAuth request is signed under its own words, so neither is ever taken for the other

_key: Optional[Ed25519PrivateKey] = None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _signing_key() -> Ed25519PrivateKey:
    """The key grants are signed with: made from the master secret, so there is no second secret to keep and it survives a restart."""
    global _key
    if _key is None:
        _key = Ed25519PrivateKey.from_private_bytes(hmac.new(get_master_secret().encode("utf-8"), b"aime-link-grant-v1", hashlib.sha256).digest())
    return _key


def public_key() -> str:
    """The public half, as the Aime sign-in helper holds it in ``GRANT_KEYS``. It is not a secret.

    :rtype: str
    """
    return _b64(_signing_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def signed(prefix: bytes, payload: Dict[str, Any]) -> str:
    """``body.signature`` for the Aime sign-in helper to check: the payload as JSON, and this site's signature over the prefix and that body.

    :param prefix: What kind of note this is, ``SIGNED_PREFIX`` or ``OAUTH_PREFIX``.
    :type prefix: bytes
    :param payload: What the note says.
    :type payload: Dict[str, Any]
    :rtype: str
    """
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_b64(_signing_key().sign(prefix + body.encode('ascii')))}"


def clean_origin(text: str) -> str:
    """A site's origin as a browser writes it, ``https://host`` or ``https://host:port``; "" when it is not one a sign-in may go to.

    Only https, or http on this machine for developing, which is all the extension sends to.

    :param text: An origin or any address on the site.
    :type text: str
    :rtype: str
    """
    try:
        parts = urlsplit((text or "").strip())
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return ""
    if not host or parts.username or parts.password:
        return ""
    if parts.scheme != "https" and not (parts.scheme == "http" and host in ("localhost", "127.0.0.1")):
        return ""
    default = 443 if parts.scheme == "https" else 80
    return f"{parts.scheme}://{host}" + (f":{port}" if port and port != default else "")


def verified_bots() -> Dict[str, str]:
    """Every site a grant is issued for, as origin to name: this site itself, then the bots the developer listed."""
    own = clean_origin(get_public_base_url())
    return {**link_bots_get(), **({own: "Rasmai"} if own else {})}


def issue_grant(origin: str) -> Optional[Tuple[str, str, int]]:
    """A signed note that a site is a verified bot, for the Aime sign-in helper to check before it sends a sign-in there.

    The grant names the site's origin, so it is no use to any other site, and it expires, so taking a bot off the list ends it.

    :param origin: The site asking, as an origin.
    :type origin: str
    :returns: ``(grant, the bot's name, when it expires in Unix seconds)``, or None for a site that is not listed.
    :rtype: Optional[Tuple[str, str, int]]
    """
    origin = clean_origin(origin)
    name = verified_bots().get(origin) if origin else None
    if not name:
        return None
    expires = int(time.time()) + GRANT_SECONDS
    return signed(SIGNED_PREFIX, {"v": 1, "name": name, "origin": origin, "exp": expires}), name, expires
