from pathlib import Path
from typing import Optional, Set
from urllib.parse import urlparse
import hashlib
import logging
import re
import threading

import requests

from rasmai.config import BROWSER_USER_AGENT, DATABASE_PATH, MAIMAI_BASE_URLS
from rasmai.scraping.scraper.area_images import _image_suffix

logger = logging.getLogger(__name__)


NAMEPLATE_DIR = DATABASE_PATH.parent / "nameplates"


NAMEPLATE_KEY = re.compile(r"[0-9a-f]{40}")


# a plate is a 720x116 picture, tens of kilobytes; anything far past that is not one
_MAX_BYTES = 1024 * 1024


_HOSTS = {urlparse(base).hostname for base in MAIMAI_BASE_URLS.values()}


# ponytail: one lock for every plate and failures remembered until restart; plates are fetched once each
_lock = threading.Lock()
_failed: Set[str] = set()


def nameplate_key(image_url: str) -> str:
    """The key a plate is cached under, or "" when the address is not a maimai DX NET name plate.

    :param image_url: The address the plate is served from.
    :type image_url: str
    :rtype: str
    """
    parts = urlparse(image_url or "")
    if parts.scheme != "https" or parts.hostname not in _HOSTS or "/img/NamePlate/" not in parts.path:
        return ""
    return hashlib.sha1(f"{parts.hostname}{parts.path}".encode("utf-8")).hexdigest()


def nameplate_path(key: str) -> Optional[Path]:
    """The cached plate by its key, or None.

    :param key: The key from ``nameplate_key``.
    :type key: str
    :rtype: Optional[Path]
    """
    if not NAMEPLATE_KEY.fullmatch(key or ""):
        return None
    for suffix in (".png", ".jpg", ".webp", ".gif"):
        candidate = NAMEPLATE_DIR / f"{key}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def cache_nameplate(image_url: str, cookies: str = "") -> str:
    """Fetch a name plate from maimai DX NET once and keep it under data/; returns its key, or "".

    Tried bare first, as the site's pictures are served without a session, and with the
    saved sign-in only when that fails. Redirects are refused so the host check holds.

    :param image_url: The address the plate is served from.
    :type image_url: str
    :param cookies: The cookie header to send.
    :type cookies: str
    :rtype: str
    """
    key = nameplate_key(image_url)
    if not key:
        return ""
    with _lock:
        if nameplate_path(key) is not None:
            return key
        if key in _failed and not cookies:
            return ""
        for attempt in ({}, {"Cookie": cookies}) if cookies else ({},):
            try:
                response = requests.get(image_url, headers={"User-Agent": BROWSER_USER_AGENT, **attempt},
                                        timeout=15, allow_redirects=False, stream=True)
                body = response.raw.read(_MAX_BYTES + 1, decode_content=True) if response.status_code == 200 else b""
                response.close()
            except Exception as error:
                logger.info(f"Name plate fetch failed: {error}")
                break
            kind = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            suffix = _image_suffix(body, kind) if 0 < len(body) <= _MAX_BYTES else ""
            if suffix:
                try:
                    NAMEPLATE_DIR.mkdir(parents=True, exist_ok=True)
                    (NAMEPLATE_DIR / f"{key}{suffix}").write_bytes(body)
                except OSError as error:
                    logger.info(f"Name plate could not be saved: {error}")
                    break
                _failed.discard(key)
                return key
            logger.info(f"Name plate {image_url} answered {response.status_code} {kind or '?'} ({len(body)} bytes)")
        _failed.add(key)
        return ""
