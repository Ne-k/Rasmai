from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Dict, Optional, Any
import re

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.engine.areas import summarise_areas
from rasmai.storage.db import load_area_progress
from rasmai.util import _json_safe
from rasmai.web.dashboard.files import _send_file


def areas_payload(user_id: str, account: Dict[str, Any], cached: Optional[CachedAnalysis]) -> Dict[str, Any]:
    """The map as last read, with the plays-to-next-reward estimate from the stored readings.

    :param user_id: The Discord user id.
    :type user_id: str
    :param account: The linked account, as stored.
    :type account: Dict[str, Any]
    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :rtype: Dict[str, Any]
    """
    analyzer = cached.analyzer if cached else None
    events = getattr(analyzer, "events_data", None) if analyzer else None
    read_at = getattr(analyzer, "events_read_at", None) if analyzer else None
    if not events or not (events.get("areaEvents") or events.get("eventAreaEvents")):
        snapshot = account.get("latestSnapshot") or {}
        events = snapshot.get("areas") or {}
        try:
            read_at = datetime.fromisoformat(str(snapshot.get("areasReadAt") or "")) if snapshot.get("areasReadAt") else None
        except ValueError:
            read_at = None
    from rasmai.scraping import wiki
    return _json_safe(summarise_areas(events, load_area_progress(user_id), read_at, resolve=wiki.area_lookup))


def area_image(handler: BaseHTTPRequestHandler, key: str) -> bool:
    """An area's cached artwork by key, or 404.

    :param handler: The request being answered.
    :type handler: BaseHTTPRequestHandler
    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: str
    :rtype: bool
    """
    from rasmai.scraping.scraper import ensure_area_image
    path = ensure_area_image(key) if re.fullmatch(r"(?:banner_)?[0-9a-f]{6,40}", key or "") else None
    if path is None:
        handler._send_json(404, {"ok": False, "error": "not_found"})
        return True
    kinds = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
    _send_file(handler, path, kinds.get(path.suffix, "image/png"))
    return True
