from cryptography.fernet import Fernet, InvalidToken
from datetime import timedelta
from typing import List, Dict, Optional
import base64
import hashlib
import hmac
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
                _master_secret_cache = stored
                return stored
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_urlsafe(48)
        secret_path.write_text(generated, encoding="utf-8")
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
refresh_limiter = RateLimiter(3, 900)         # score reads started from the site per account


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


_token_cipher: Optional[Fernet] = None


def _cipher() -> Fernet:
    global _token_cipher
    if _token_cipher is None:
        digest = hashlib.sha256(("token:" + get_master_secret()).encode("utf-8")).digest()
        _token_cipher = Fernet(base64.urlsafe_b64encode(digest))
    return _token_cipher


def encrypt_token(token: str) -> str:
    return "enc:" + _cipher().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(stored: str) -> str:
    if not stored.startswith("enc:"):
        return stored
    try:
        return _cipher().decrypt(stored[4:].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.error("Stored session key could not be decrypted (login secret changed?)")
        return ""


def normalize_login_token(raw_token: str) -> str:
    trimmed = raw_token.strip()
    if trimmed.startswith("cookie://"):
        return trimmed
    return f"cookie://{trimmed}"
