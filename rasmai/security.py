from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from datetime import timedelta
from typing import List, Dict, Optional, Tuple
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import logging

from rasmai.config import DATABASE_PATH

logger = logging.getLogger(__name__)


LOGIN_CODE_TTL = timedelta(minutes=10)


LOGIN_ATTEMPTS_PER_WINDOW = 10


LOGIN_ATTEMPT_WINDOW = timedelta(minutes=10)


_master_secret_cache: Optional[str] = None


def _own_only(path) -> None:
    """Narrow a file to its owner, where the system has the notion. Never raises."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_master_secret() -> str:
    """The HMAC key behind one-time codes and opaque user ids.

    :rtype: str
    """
    global _master_secret_cache
    if _master_secret_cache:
        return _master_secret_cache
    configured = os.getenv("MAIMAI_TOTP_SECRET")
    if configured:
        _master_secret_cache = configured
        return configured
    secret_path = DATABASE_PATH.parent / "secret.key"
    try:
        if secret_path.exists():
            stored = secret_path.read_text(encoding="utf-8").strip()
            if stored:
                _own_only(secret_path)      # a key written before this was owner-only is narrowed now
                _master_secret_cache = stored
                return stored
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_urlsafe(48)
        # every login code and every opaque id is signed with this, so it is written owner-only from
        # the start rather than created under the umask and narrowed a moment later
        handle = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(generated)
        _master_secret_cache = generated
        return generated
    except OSError as error:
        logger.error(f"Could not persist a login secret ({error}); using a per-process one")
        _master_secret_cache = secrets.token_urlsafe(48)
        return _master_secret_cache


def create_opaque_user_id(user_id: str) -> str:
    payload = base64.urlsafe_b64encode(user_id.encode("utf-8")).decode("ascii").rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(get_master_secret().encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).digest()).decode("ascii").rstrip("=")
    return f"{payload}.{signature}"


def decode_opaque_user_id(opaque: str) -> Optional[str]:
    try:
        payload, signature = opaque.split(".", 1)
        payload_bytes = base64.urlsafe_b64decode(payload + "===")
        user_id = payload_bytes.decode("utf-8")
        expected = base64.urlsafe_b64encode(hmac.new(get_master_secret().encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).digest()).decode("ascii").rstrip("=")
        if hmac.compare_digest(signature, expected):
            return user_id
    except Exception:
        return None
    return None


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class RateLimiter:
    """Sliding window per key: at most `limit` events in `window` seconds. Thread-safe, memory-bounded."""

    def __init__(self, limit: int, window_seconds: float, max_keys: int = 20000):
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._events: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            events = [t for t in self._events.get(key, []) if now - t < self.window]
            if len(events) >= self.limit:
                self._events[key] = events
                return False
            events.append(now)
            self._events[key] = events
            if len(self._events) > self.max_keys:
                stale = [k for k, ts in self._events.items() if not ts or now - ts[-1] >= self.window]
                for k in stale[: len(self._events) - self.max_keys // 2]:
                    self._events.pop(k, None)
            return True


_login_limiter = RateLimiter(LOGIN_ATTEMPTS_PER_WINDOW, LOGIN_ATTEMPT_WINDOW.total_seconds())
# a shared profile being read. The strict limit below it is what stops somebody trying addresses
# until one answers; reading a profile whose address is already known is an ordinary page view, and
# a page view costs more than one call: the page, the picture Discord shows above it, and whoever
# opens the link afterwards.
public_limiter = RateLimiter(120, 60)         # shared profiles read per client
refresh_limiter = RateLimiter(3, 900)         # score reads started from the site per account
import_limiter = RateLimiter(5, 900)          # exports merged back from the site per account


def login_attempt_allowed(client_key: str) -> bool:
    """Per-client sliding window on sign-in attempts.

    :param client_key: Who the request came from, for rate limiting.
    :type client_key: str
    :rtype: bool
    """
    return _login_limiter.allow(client_key)


_URL = re.compile(r"https?://\S+")


# requests and urllib3 failures whose messages are hostnames, pool sizes and retry counts
_NETWORK_ERRORS = {"ConnectionError", "ConnectTimeout", "ReadTimeout", "Timeout", "SSLError", "MaxRetryError",
                   "NewConnectionError", "RemoteDisconnected", "ProtocolError", "ChunkedEncodingError", "ProxyError"}


def public_reason(error: BaseException, limit: int = 160) -> str:
    """An error as text safe to show a user: no addresses, no session material, bounded length.

    :param error: What went wrong.
    :type error: BaseException
    :param limit: Most entries to return.
    :type limit: int
    :rtype: str
    """
    name = type(error).__name__
    text = str(error)
    if name in _NETWORK_ERRORS or "HTTPSConnectionPool" in text or "Max retries exceeded" in text:
        return "maimai DX NET could not be reached"
    if name in ("TimeoutError", "CancelledError", "FutureTimeoutError"):
        return "the read took too long and was stopped"
    if name == "HTTPError":
        return "maimai DX NET answered with an error page"
    text = _URL.sub("[url]", text).replace("\n", " ").strip()
    return (text or name)[:limit]


# Stored sign-ins (an International session key, or a Japan account's SEGA ID and password) are
# encrypted with AES-256-GCM: authenticated encryption, so a stored value that was altered or moved
# fails to open instead of opening as something else. Each value is bound to the account it belongs to
# (its user id is the additional data), so one account's value copied onto another's row does not
# open either. The key is stretched from the secret with scrypt, which makes guessing a weak secret
# expensive; set MAIMAI_TOKEN_KEY to keep it apart from the login secret and out of the data folder.
# Values written before this (``enc:``, Fernet: AES-128-CBC with HMAC-SHA256) still open, and are
# re-encrypted the first time the database is opened (see `upgrade_token`).
TOKEN_PREFIX = "enc2:"
LEGACY_TOKEN_PREFIX = "enc:"
_TOKEN_KDF_SALT = b"rasmai/stored-token-key/v2"
_TOKEN_AAD = b"rasmai/stored-token/v2|"

_token_cipher: Optional[Fernet] = None
_token_keys: Optional[List[AESGCM]] = None
_token_lock = threading.Lock()


def _cipher() -> Fernet:
    """The key values written before AES-256-GCM were encrypted with; kept only to read them.

    :rtype: Fernet
    """
    global _token_cipher
    if _token_cipher is None:
        digest = hashlib.sha256(("token:" + get_master_secret()).encode("utf-8")).digest()
        _token_cipher = Fernet(base64.urlsafe_b64encode(digest))
    return _token_cipher


def _stretch(secret: str) -> AESGCM:
    key = hashlib.scrypt(secret.encode("utf-8"), salt=_TOKEN_KDF_SALT, n=2 ** 15, r=8, p=1,
                         maxmem=64 * 1024 * 1024, dklen=32)
    return AESGCM(key)


def _aead_keys() -> List[AESGCM]:
    """The AES-256-GCM keys, current first, each stretched once per process with scrypt.

    With MAIMAI_TOKEN_KEY set, the key from the login secret stays second, so values sealed before the
    setting was made still open and are moved onto it the next time the database is opened.

    :rtype: List[AESGCM]
    """
    global _token_keys
    with _token_lock:
        if _token_keys is None:
            configured = os.getenv("MAIMAI_TOKEN_KEY", "").strip()
            _token_keys = [_stretch(configured)] if configured else []
            if not configured or configured != get_master_secret():
                _token_keys.append(_stretch(get_master_secret()))
        return _token_keys


def encrypt_token(token: str, owner: str = "") -> str:
    """A sign-in, encrypted for storage with AES-256-GCM and bound to the account it belongs to.

    :param token: The sign-in to store.
    :type token: str
    :param owner: The Discord user id of the account it belongs to.
    :type owner: str
    :rtype: str
    """
    nonce = os.urandom(12)
    sealed = _aead_keys()[0].encrypt(nonce, token.encode("utf-8"), _TOKEN_AAD + str(owner).encode("utf-8"))
    return TOKEN_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def _open_token(stored: str, owner: str) -> Tuple[str, bool]:
    """A stored sign-in opened, and whether it is sealed the current way (so needs no re-encrypting).

    :param stored: The stored value.
    :type stored: str
    :param owner: The Discord user id of the account whose row it was read from.
    :type owner: str
    :rtype: Tuple[str, bool]
    """
    if stored.startswith(TOKEN_PREFIX):
        try:
            raw = base64.urlsafe_b64decode(stored[len(TOKEN_PREFIX):].encode("ascii"))
        except ValueError:
            raw = b""
        for position, key in enumerate(_aead_keys()):
            try:
                opened = key.decrypt(raw[:12], raw[12:], _TOKEN_AAD + str(owner).encode("utf-8")).decode("utf-8")
                return opened, position == 0
            except (InvalidTag, ValueError):
                continue
        logger.error("A stored sign-in could not be opened (key changed, or the value was altered)")
        return "", True
    if stored.startswith(LEGACY_TOKEN_PREFIX):
        try:
            return _cipher().decrypt(stored[len(LEGACY_TOKEN_PREFIX):].encode("ascii")).decode("utf-8"), False
        except (InvalidToken, ValueError):
            logger.error("Stored session key could not be decrypted (login secret changed?)")
            return "", True
    return stored, not stored


def decrypt_token(stored: str, owner: str = "") -> str:
    """A stored sign-in, opened; "" when it cannot be (a changed key, or a value altered or moved).

    :param stored: The stored value, as `encrypt_token` wrote it or as an older version did.
    :type stored: str
    :param owner: The Discord user id of the account whose row it was read from.
    :type owner: str
    :rtype: str
    """
    return _open_token(stored, owner)[0]


def upgrade_token(stored: str, owner: str) -> Optional[str]:
    """The stored value re-encrypted the current way, or None when it already is or cannot be opened.

    :param stored: The stored value.
    :type stored: str
    :param owner: The Discord user id of the account it belongs to.
    :type owner: str
    :rtype: Optional[str]
    """
    opened, current = _open_token(str(stored or ""), owner)
    return encrypt_token(opened, owner) if opened and not current else None


def normalize_login_token(raw_token: str) -> str:
    trimmed = raw_token.strip()
    if trimmed.startswith("cookie://"):
        return trimmed
    return f"cookie://{trimmed}"


SEGA_ID_TOKEN = "segaid://"


def sega_id_token(sega_id: str, password: str, aime: int = 0) -> str:
    """The stored sign-in of a Japan account: its SEGA ID, password and which Aime card to open.

    maimaidx.jp has no session a server can replay the way the international Aime gateway's is, so a
    Japan account is signed in afresh from these on every read. The whole token is encrypted before it
    is stored (`encrypt_token`), like every other one, and never leaves the bot.

    :param sega_id: The SEGA ID.
    :type sega_id: str
    :param password: Its password.
    :type password: str
    :param aime: Which card on the account's Aime list, counting from 0.
    :type aime: int
    :rtype: str
    """
    body = json.dumps({"id": sega_id, "password": password, "aime": int(aime)}, separators=(",", ":"))
    return SEGA_ID_TOKEN + base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii")


def read_sega_id_token(token: str) -> Optional[Tuple[str, str, int]]:
    """The SEGA ID, password and Aime card in a token from `sega_id_token`; None for anything else.

    :param token: The stored sign-in.
    :type token: str
    :rtype: Optional[Tuple[str, str, int]]
    """
    token = str(token or "").strip()
    if not token.startswith(SEGA_ID_TOKEN):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(token[len(SEGA_ID_TOKEN):].encode("ascii")).decode("utf-8"))
        sega_id, password, aime = str(body["id"]), str(body["password"]), int(body.get("aime", 0))
    except (ValueError, KeyError, TypeError):
        return None
    if not sega_id or not password or aime < 0:
        return None
    return sega_id, password, aime
