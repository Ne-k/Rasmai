from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging
import queue
import re
import secrets
import sys
import threading
import time
import traceback

import requests

from rasmai.config import ERROR_WEBHOOK_URL, PUBLIC_URL

logger = logging.getLogger(__name__)

USERNAME = "Rasmai · Errors"
AVATAR = f"{PUBLIC_URL}/app/icon-512.png"
# the developer page reports its own trouble to the one person who reads it, on the page itself
SKIPPED = ("rasmai.web.dashboard.admin",)
SKIPPED_PATHS = ("/internal/me/admin",)
REPEAT_WINDOW = 600         # seconds a second error of the same kind is posted as a line pointing at the first, not in full
PER_MINUTE = 20             # posts at most: a fault met by everyone at once must not take the webhook's rate limit with it
TRACE_CHARS = 3200          # of the traceback, its end: where it failed is at the bottom
_URL = re.compile(r"https?://\S+")
_STARTED = time.monotonic()

_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=200)
_seen: Dict[str, tuple] = {}        # the kind of error -> (its first id, when, how many since)
_sent: list = []                    # when the latest posts went out, for the per-minute cap
_dropped = 0
_guard = threading.Lock()


def new_id() -> str:
    """Eight characters someone can read out or paste, unique enough to find the one post among thousands."""
    return secrets.token_hex(4).upper()


def report(error: BaseException, what: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Log an error someone met, with what was going on, and return the id to show them.

    :param error: What went wrong.
    :type error: BaseException
    :param what: One line saying what was being done, such as "/analyze failed".
    :type what: str
    :param context: What else helps find the cause: the command and its options, the page, who.
    :type context: Optional[Dict[str, Any]]
    :returns: The error's id.
    :rtype: str
    """
    error_id = new_id()
    # logged as the module that reported it, so the post says where the error came from and not that it came through here
    where = logging.getLogger(sys._getframe(1).f_globals.get("__name__", __name__))
    where.error("%s (error %s)", what, error_id, exc_info=(type(error), error, error.__traceback__),
                extra={"error_id": error_id, "error_context": context or {}})
    return error_id


def _clean(text: Any, limit: int) -> str:
    """Text safe to post: no addresses, which can carry a token or a webhook's secret, and short enough to fit."""
    text = _URL.sub("[url]", str(text))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _kind(record: logging.LogRecord) -> str:
    """What makes two errors the same one: where it was logged, the exception, and the line it came from."""
    if record.exc_info and record.exc_info[1] is not None:
        frames = traceback.extract_tb(record.exc_info[2])
        place = f"{frames[-1].filename}:{frames[-1].lineno}" if frames else ""
        return f"{record.name}|{type(record.exc_info[1]).__name__}|{place}"
    return f"{record.name}|{record.msg}"


def _payload(record: logging.LogRecord, error_id: str) -> Dict[str, Any]:
    """The webhook post: the message, the traceback's end, and what was going on."""
    message = re.sub(r" \(error [0-9A-F]{8}\)$", "", _clean(record.getMessage(), 250))        # the title already says it
    summary = ""
    trace = ""
    if record.exc_info and record.exc_info[1] is not None:
        kind, value, tb = record.exc_info
        summary = _clean(f"{kind.__name__}: {value}", 300)
        trace = _clean("".join(traceback.format_exception(kind, value, tb)), 100_000)[-TRACE_CHARS:]
    description = f"**{message}**" + (f"\n{summary}" if summary else "") + (f"\n```py\n{trace}\n```" if trace else "")
    context = getattr(record, "error_context", None) or {}
    fields = [{"name": _clean(name, 60), "value": _clean(value, 1000) or "-", "inline": len(str(value)) < 40}
              for name, value in context.items() if value not in (None, "", {}, [])][:20]
    up = int(time.monotonic() - _STARTED)
    fields.append({"name": "Logged by", "value": f"`{record.name}` · {record.levelname.lower()} · up {up // 3600}h {up % 3600 // 60}m", "inline": False})
    embed = {"title": f"Error {error_id}", "description": description[:4000], "color": 0xE5484D, "fields": fields,
             "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat()}
    return {"username": USERNAME, "avatar_url": AVATAR, "embeds": [embed], "allowed_mentions": {"parse": []}}


def _enqueue(payload: Dict[str, Any]) -> None:
    try:
        _queue.put_nowait(payload)
    except queue.Full:
        global _dropped
        _dropped += 1


class ErrorWebhook(logging.Handler):
    """Every error logged anywhere in the bot, posted to RAS_ERROR_WEBHOOK under an id, the developer page's aside."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        global _dropped
        try:
            # the webhook's own trouble is logged as a warning, which this never sees, so it cannot report itself in a loop
            if not ERROR_WEBHOOK_URL or record.name.startswith(SKIPPED):
                return
            context = getattr(record, "error_context", None) or {}
            if str(context.get("Page", "")).startswith(SKIPPED_PATHS):
                return
            error_id = getattr(record, "error_id", None) or new_id()
            now = time.monotonic()
            with _guard:
                _sent[:] = [at for at in _sent if now - at < 60]
                if len(_sent) >= PER_MINUTE:
                    _dropped += 1
                    return
                _sent.append(now)
                kind = _kind(record)
                first = _seen.get(kind)
                if first and now - first[1] < REPEAT_WINDOW:
                    _seen[kind] = (first[0], first[1], first[2] + 1)
                    who = context.get("User")
                    line = (f"**Error {error_id}** · the same as {first[0]} again ({first[2] + 1} more in the last "
                            f"{int((now - first[1]) // 60) + 1} min)" + (f" · {_clean(who, 100)}" if who else ""))
                    _enqueue({"username": USERNAME, "avatar_url": AVATAR, "content": line, "allowed_mentions": {"parse": []}})
                    return
                _seen[kind] = (error_id, now, 0)
                dropped, _dropped = _dropped, 0
            payload = _payload(record, error_id)
            if dropped:
                payload["content"] = f"-# {dropped} error(s) before this one were not posted: there were too many at once"
            _enqueue(payload)
        except Exception:
            # the reporter must never be the thing that breaks: say so where the logs go, and carry on
            print("error webhook: could not report an error", file=sys.stderr)


def _post(payload: Dict[str, Any]) -> None:
    try:
        response = requests.post(ERROR_WEBHOOK_URL, json=payload, timeout=15)
        if response.status_code == 429:
            time.sleep(min(float(response.json().get("retry_after") or 2), 30))
            response = requests.post(ERROR_WEBHOOK_URL, json=payload, timeout=15)
        if response.status_code >= 300:
            logger.warning("error webhook answered %s", response.status_code)
    except (requests.RequestException, ValueError) as error:
        logger.warning("error webhook could not be reached (%s)", type(error).__name__)


def _deliver() -> None:
    while True:
        _post(_queue.get())


def install() -> None:
    """Send every error from here on to the webhook, once; does nothing without RAS_ERROR_WEBHOOK."""
    root = logging.getLogger()
    if not ERROR_WEBHOOK_URL or any(isinstance(handler, ErrorWebhook) for handler in root.handlers):
        return
    root.addHandler(ErrorWebhook())
    threading.Thread(target=_deliver, name="error-webhook", daemon=True).start()
    logger.info("errors are reported to the error webhook as %s", USERNAME)
