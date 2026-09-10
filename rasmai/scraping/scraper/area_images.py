from datetime import datetime
from typing import List, Dict, Optional
import re
import requests
import threading
import hashlib
from pathlib import Path
import logging

from rasmai.config import BROWSER_USER_AGENT, DATABASE_PATH

logger = logging.getLogger(__name__)


AREA_IMAGE_DIR = DATABASE_PATH.parent / "area_images"


_IMAGE_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8", ".jpg"), (b"GIF8", ".gif"), (b"RIFF", ".webp"))


def _image_suffix(content: bytes, content_type: str) -> str:
    """The file suffix for a picture, from its first bytes; the server's content type only when the bytes say nothing.

    :rtype: str
    """
    for magic, suffix in _IMAGE_MAGIC:
        if content.startswith(magic):
            return suffix
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}.get(content_type, "")


# the site names each picture by a hex stem: areas at /img/Map/Body/<stem>.png, event banners at /img/EventMap/Banner/<stem>.png
_AREA_IMAGE_STEM = re.compile(r"/img/(Map/Body|EventMap/Banner)/([0-9a-f]{6,40})\.(?:png|jpg|jpeg|webp|gif)(?:\?.*)?$", re.I)


_AREA_IMAGE_HOSTS = ("https://maimaidx-eng.com", "https://maimaidx.jp")


AREA_IMAGE_KEY = re.compile(r"(?:banner_)?[0-9a-f]{6,40}")


def area_image_key(image_url: str) -> str:
    """The key a picture is cached under: the site's own file stem (banners prefixed) when the address has one, else a hash.

    A stem key can be turned back into the address, so a picture missing from the cache
    can be fetched when it is first asked for.

    :param image_url: The address the picture is served from.
    :type image_url: str
    :rtype: str
    """
    if not image_url:
        return ""
    match = _AREA_IMAGE_STEM.search(image_url)
    if match:
        return ("banner_" if match.group(1).lower().startswith("eventmap") else "") + match.group(2).lower()
    return hashlib.sha1(image_url.split("?")[0].encode("utf-8")).hexdigest()


def _period_bounds(text: str) -> Optional[List[int]]:
    """[start, end] in milliseconds since the epoch from "YYYY/MM/DD HH:MM～YYYY/MM/DD HH:MM" anywhere in `text`, JST.

    :param text: The text to work on.
    :type text: str
    :rtype: Optional[List[int]]
    """
    match = re.search(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*～\s*(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})", text or "")
    if not match:
        return None
    sy, sm, sd, sh, smin, ey, em, ed, eh, emin = match.groups()
    start = datetime.fromisoformat(f"{sy}-{sm}-{sd}T{sh}:{smin}:00+09:00")
    end = datetime.fromisoformat(f"{ey}-{em}-{ed}T{eh}:{emin}:00+09:00")
    return [int(start.timestamp() * 1000), int(end.timestamp() * 1000)]


# one registry for the whole process: a picture found on disk is remembered, and a picture being
# fetched holds a lock so a second asker (another user's read, the site, the bot) waits instead of fetching too
_area_images_known: Dict[str, Path] = {}


_area_images_lock = threading.Lock()


_area_image_fetching: Dict[str, threading.Lock] = {}


def area_image_path(key: str) -> Optional[Path]:
    """The cached picture of an area by its key, or None.

    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: str
    :rtype: Optional[Path]
    """
    if not AREA_IMAGE_KEY.fullmatch(key or ""):
        return None
    with _area_images_lock:
        known = _area_images_known.get(key)
    if known is not None and known.exists():
        return known
    for suffix in (".png", ".jpg", ".webp", ".gif"):
        candidate = AREA_IMAGE_DIR / f"{key}{suffix}"
        if candidate.exists():
            with _area_images_lock:
                _area_images_known[key] = candidate
            return candidate
    return None


def _fetch_lock(key: str) -> threading.Lock:
    with _area_images_lock:
        return _area_image_fetching.setdefault(key, threading.Lock())


def ensure_area_image(key: str) -> Optional[Path]:
    """The cached picture, fetching it by its stem from the site when it is not there yet; None when it cannot be had.

    :param key: The chart, as ``(title, chart type, difficulty)``.
    :type key: str
    :rtype: Optional[Path]
    """
    path = area_image_path(key)
    if path is not None or not AREA_IMAGE_KEY.fullmatch(key or "") or len(key) == 40:
        return path
    folder, stem = ("EventMap/Banner", key[len("banner_"):]) if key.startswith("banner_") else ("Map/Body", key)
    for host in _AREA_IMAGE_HOSTS:
        if cache_area_image(f"{host}/maimai-mobile/img/{folder}/{stem}.png"):
            return area_image_path(key)
    return None


def cache_area_image(image_url: str, cookies: str = "") -> str:
    """Fetch an area's picture from maimai DX NET once and keep it under data/; returns its key, or "".

    The pictures are the same artwork the cabinet shows. They are served without
    a session, so the first try goes bare and the saved sign-in is only sent when that fails.

    :param image_url: The address the picture is served from.
    :type image_url: str
    :param cookies: The cookie header to send.
    :type cookies: str
    :rtype: str
    """
    if not image_url:
        return ""
    key = area_image_key(image_url)
    if area_image_path(key) is not None:
        return key
    with _fetch_lock(key):
        if area_image_path(key) is not None:      # fetched by whoever held the lock first
            return key
        return _fetch_area_image(image_url, key, cookies)


def _fetch_area_image(image_url: str, key: str, cookies: str) -> str:
    headers = {"User-Agent": BROWSER_USER_AGENT}
    for attempt in ({}, {"Cookie": cookies}) if cookies else ({},):
        try:
            response = requests.get(image_url, headers={**headers, **attempt}, timeout=30)
        except Exception as error:
            logger.info(f"Area image fetch failed: {error}")
            return ""
        kind = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        suffix = _image_suffix(response.content or b"", kind) if response.status_code == 200 else ""
        if not suffix:
            logger.info(f"Area image {image_url} answered {response.status_code} {kind or '?'} ({len(response.content or b'')} bytes)"
                        f"{' with the session' if attempt else ' without a session'}")
        if suffix:
            try:
                AREA_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                target = AREA_IMAGE_DIR / f"{key}{suffix}"
                target.write_bytes(response.content)
            except OSError as error:
                logger.info(f"Area image could not be saved: {error}")
                return ""
            with _area_images_lock:
                _area_images_known[key] = target
            logger.info(f"Area picture {key} cached ({len(response.content):,} bytes), shared by every account")
            return key
    return ""
