from http.server import BaseHTTPRequestHandler
from pathlib import Path
import re


JACKET_DIR = Path("otoge_cache/jackets")


def _send_file(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "public, max-age=2592000, immutable")
    handler.end_headers()
    handler.wfile.write(body)


def jacket(handler: BaseHTTPRequestHandler, name: str) -> bool:
    """A song jacket from the chart-database cache, or 404.

    :param handler: The request being answered.
    :type handler: BaseHTTPRequestHandler
    :param name: The name to look up.
    :type name: str
    :rtype: bool
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        handler._send_json(404, {"ok": False, "error": "not_found"})
        return False
    stem = Path(name).stem
    for candidate in (JACKET_DIR / f"{stem}{ext}" for ext in (".webp", ".png", ".jpg")):
        if candidate.is_file():
            suffix = candidate.suffix.lower()
            _send_file(handler, candidate, {".webp": "image/webp", ".png": "image/png"}.get(suffix, "image/jpeg"))
            return True
    handler.send_response(404)
    handler.send_header("Content-Length", "0")
    handler.end_headers()
    return True
