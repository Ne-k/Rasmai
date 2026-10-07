from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse
import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import aiohttp

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    key: str
    label: str         # the name its posts are sent under
    platform: str      # "Bluesky" or "X"
    handle: str
    did: str = ""      # Bluesky only: the account the Jetstream is asked for


SOURCES: Dict[str, Source] = {
    "preformai": Source("preformai", "Preformai International", "Bluesky", "performaien.bsky.social", "did:plc:brwck2njp6tj43cns5t5rbdh"),
    "maimai": Source("maimai", "Maimai Official", "X", "maimai_official"),
    "laundromai": Source("laundromai", "Laundromai", "X", "laundromai"),
}

JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
IMG_CDN = "https://cdn.bsky.app/img/feed_fullsize/plain"
VID_CDN = "https://video.bsky.app/watch"
PUBLIC_API = "https://public.api.bsky.app/xrpc"

THREAD_WAIT_SECONDS = 8
MAX_FILE_BYTES = 8 * 1024 * 1024        # what one attachment may be; a bigger video is re-encoded down to it
FEED_BYTES = 2 * 1024 * 1024
TARGET_BITRATE = "900k"
AUDIO_BITRATE = "96k"
RSS_FALLBACK_DELAY = 5                  # seconds between one Nitter instance failing and the next being tried
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RasmaiNews/1.0)"}

# public Nitter instances, tried in turn; the one that last answered is tried first
RSS_INSTANCES = [
    "https://shitter.thepixora.com",
    "https://nitter.meowing.monster",
    "https://nitter.netbub.com",
    "https://nitter.kareem.one",
    "https://shi.meowing.de",
    "https://nitter.jaydenha.uk",
    "https://nitter.click",
    "https://nitter.xitter.cc",
    "https://x.n0g.xyz",
    "https://tw.eir-nya.gay",
    "https://xcopy.uk",
]
# the only places a feed, a post or a file is allowed to point the bot at, so a hostile one cannot aim it at an address inside the network
TRUSTED_HOSTS = {urlparse(base).hostname for base in RSS_INSTANCES} | {"cdn.bsky.app", "video.bsky.app", "public.api.bsky.app"}

_working: Dict[str, str] = {}
_avatars: Dict[str, str] = {}


@dataclass
class Post:
    source: str
    id: str
    url: str
    username: str
    avatar: str = ""
    parts: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    videos: List[bytes] = field(default_factory=list)
    wanted_video: bool = False       # it has a video; if none could be attached the link is left to unfurl

    def content(self) -> str:
        body = "\n\n".join(p for p in self.parts if p).strip()
        if len(body) > 1700:
            body = body[:1690] + "…"
        link = self.url if self.wanted_video and not self.videos else f"<{self.url}>"
        return f"{body}\n\n{link}\n\n---".strip()


def trusted(url: str) -> bool:
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host in TRUSTED_HOSTS or host.endswith(".twimg.com"))


def is_update(text: str, embed_type: str = "") -> bool:
    """Whether a Bluesky post reads like a maimai update, by a few cheap signs adding up to two."""
    if not text:
        return False
    low = text.lower()
    score = 0
    if "#maimai" in low or "#chunithm" in low:
        score += 2
    if "maimai" in low or "chunithm" in low:
        score += 1
    if "🎵" in text:
        score += 1
    if "「" in text and "」" in text:
        score += 1
    if re.search(r"\d{1,2}/\d{1,2}", text) or "later today" in low:
        score += 1
    if any(word in low for word in [
        "added", "available", "collaboration", "new song", "event", "chart", "map", "returning", "will be added",
        "coming to", "receive an", "obtainable", "update", "releases", "will receive",
    ]):
        score += 1
    if "images" in embed_type or "video" in embed_type:
        score += 1
    return score >= 2


def sanitize(text: str) -> str:
    """Post text with anything that would ping somebody made inert."""
    if not text:
        return text
    text = re.sub(r"@everyone", "@​everyone", text, flags=re.IGNORECASE)
    text = re.sub(r"@here", "@​here", text, flags=re.IGNORECASE)
    text = re.sub(r"<@!?\d+>", "[user]", text)
    text = re.sub(r"<@&\d+>", "[role]", text)
    return re.sub(r"<#\d+>", "[channel]", text)


# ---------------------------------------------------------------- fetching

async def fetch_bytes(session: aiohttp.ClientSession, url: str, limit: int = MAX_FILE_BYTES) -> Optional[bytes]:
    """A file from a trusted host, followed through up to three redirects that must stay on trusted hosts; None past ``limit``."""
    for _ in range(4):
        if not trusted(url):
            return None
        try:
            async with session.get(url, allow_redirects=False, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status in (301, 302, 303, 307, 308) and response.headers.get("Location"):
                    url = urljoin(str(response.url), response.headers["Location"])
                    continue
                if response.status != 200:
                    return None
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data += chunk
                    if len(data) > limit:
                        return None
                return bytes(data)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None
    return None


async def _get_json(session: aiohttp.ClientSession, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        async with session.get(url, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status != 200:
                return None
            return await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None


def _temp() -> str:
    handle, path = tempfile.mkstemp(suffix=".mp4")
    os.close(handle)
    return path


def _ffmpeg(args: List[str], timeout: int) -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _video_sync(url: str) -> Optional[bytes]:
    if not shutil.which("ffmpeg") or not trusted(url):
        return None
    first, second = _temp(), _temp()
    try:
        if not _ffmpeg(["-headers", "User-Agent: Mozilla/5.0\r\n", "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc",
                        "-movflags", "+faststart", first], 180) or os.path.getsize(first) == 0:
            return None
        final = first
        if os.path.getsize(first) > MAX_FILE_BYTES:
            if _ffmpeg(["-i", first, "-c:v", "libx264", "-preset", "veryfast", "-b:v", TARGET_BITRATE, "-maxrate", TARGET_BITRATE,
                        "-bufsize", "2M", "-vf", "scale=-2:720", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-movflags", "+faststart", second], 600):
                final = second
            if os.path.getsize(final) > MAX_FILE_BYTES:
                return None
        with open(final, "rb") as f:
            return f.read()
    except OSError:
        return None
    finally:
        for path in (first, second):
            try:
                os.remove(path)
            except OSError:
                pass


async def video_bytes(url: str) -> Optional[bytes]:
    """A video remuxed to mp4 and, when over the size limit, re-encoded under it; None without ffmpeg or when it cannot be made small enough."""
    return await asyncio.to_thread(_video_sync, url)


# ---------------------------------------------------------------- Bluesky

def bluesky_media(record: Dict[str, Any], did: str) -> Tuple[List[str], List[str]]:
    """The image URLs and video playlist URLs a post's embed points at."""
    images: List[str] = []
    videos: List[str] = []
    embed = record.get("embed") or {}
    kind = str(embed.get("$type", ""))
    if "images" in kind:
        for item in embed.get("images", []):
            blob = ((item.get("image") or {}).get("ref") or {}).get("$link")
            if blob:
                images.append(f"{IMG_CDN}/{did}/{blob}")
    elif "video" in kind:
        blob = ((embed.get("video") or {}).get("ref") or {}).get("$link")
        if blob:
            videos.append(f"{VID_CDN}/{quote(did, safe='')}/{blob}/playlist.m3u8")
    return images, videos


async def bluesky_thread(session: aiohttp.ClientSession, uri: str, did: str) -> List[Dict[str, Any]]:
    """Every post by the same author in a thread, oldest first."""
    data = await _get_json(session, f"{PUBLIC_API}/app.bsky.feed.getPostThread", {"uri": uri, "depth": 10})
    if not isinstance(data, dict):
        return []
    found: Dict[str, Dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("$type") == "app.bsky.feed.defs#threadViewPost":
            post = node.get("post") or {}
            if (post.get("author") or {}).get("did") == did and post.get("uri"):
                found[post["uri"]] = post
            for reply in node.get("replies") or []:
                walk(reply)

    walk(data.get("thread"))
    return sorted(found.values(), key=lambda p: (p.get("record") or {}).get("createdAt", ""))


async def bluesky_avatar(session: aiohttp.ClientSession, handle: str) -> str:
    if handle not in _avatars:
        data = await _get_json(session, f"{PUBLIC_API}/app.bsky.actor.getProfile", {"actor": handle})
        avatar = str(data.get("avatar", "")) if isinstance(data, dict) else ""
        if avatar:
            _avatars[handle] = avatar
        return avatar
    return _avatars[handle]


async def build_bluesky_post(session: aiohttp.ClientSession, source: Source, record: Dict[str, Any], uri: str) -> Tuple[Optional[Post], List[str]]:
    """The post for a thread that started at ``uri``, and the URIs of every post in it; None when it holds nothing of the author's."""
    thread = await bluesky_thread(session, uri, source.did) or [{"uri": uri, "record": record, "author": {"did": source.did}}]
    thread = [p for p in thread if (p.get("author") or {}).get("did") == source.did]
    if not thread:
        return None, []
    parts: List[str] = []
    images: List[str] = []
    playlists: List[str] = []
    for post in thread:
        body = post.get("record") or {}
        text = sanitize(str(body.get("text", "")).strip())
        if text:
            parts.append(text)
        more_images, more_videos = bluesky_media(body, source.did)
        images += more_images
        playlists += more_videos
    images = list(dict.fromkeys(images))
    playlists = list(dict.fromkeys(playlists))
    videos = [data for data in [await video_bytes(url) for url in playlists[:5]] if data]
    post = Post(source.key, uri, f"https://bsky.app/profile/{source.handle}/post/{uri.split('/')[-1]}", source.label,
                await bluesky_avatar(session, source.handle), parts, images, videos, bool(playlists))
    return post, [p["uri"] for p in thread]


# ---------------------------------------------------------------- X, through Nitter's RSS

@dataclass
class FeedItem:
    id: str
    title: str
    link: str
    description: str
    retweet: bool


def tweet_id(link: str) -> str:
    match = re.search(r"/status/(\d+)", link or "")
    return match.group(1) if match else ""


def parse_feed(content: bytes) -> Tuple[List[FeedItem], str]:
    """The posts in a Nitter feed, newest first as it lists them, and the account's picture; ([], "") when it is not a feed."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return [], ""
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = item.findtext("link") or ""
        items.append(FeedItem(tweet_id(link), title, link, item.findtext("description") or "",
                              bool(re.match(r"^(?:RT\b|リツイート\b)", title, flags=re.IGNORECASE))))
    return items, (root.findtext("./channel/image/url") or "").strip()


async def fetch_feed(session: aiohttp.ClientSession, username: str) -> Tuple[List[FeedItem], str]:
    """An account's posts from the first Nitter instance that answers with any; ([], "") when none does."""
    first = _working.get(username)
    for number, base in enumerate(([first] if first else []) + [b for b in RSS_INSTANCES if b != first]):
        if number:
            await asyncio.sleep(RSS_FALLBACK_DELAY)
        content = await fetch_bytes(session, f"{base}/{username}/rss", FEED_BYTES)
        items, avatar = parse_feed(content) if content else ([], "")
        if items:
            if first != base:
                logger.info("news: %s now read through %s", username, urlparse(base).hostname)
                _working[username] = base
            return items, avatar
    return [], ""


def has_japanese(text: str) -> bool:
    return bool(text and re.search(r"[぀-ゟ゠-ヿ一-鿿]", text))


async def translate(session: aiohttp.ClientSession, text: str) -> str:
    """Japanese text in English through Google's free endpoint; the text itself when that fails."""
    clean = re.sub(r"https?://\S+", "", text or "").strip()
    if not clean:
        return text
    data = await _get_json(session, "https://translate.googleapis.com/translate_a/single",
                           {"client": "gtx", "sl": "ja", "tl": "en", "dt": "t", "q": clean})
    try:
        return "".join(segment[0] for segment in data[0] if segment and segment[0]) or text
    except (TypeError, IndexError, KeyError):
        return text


def media_urls(description_html: str) -> List[str]:
    return [url for url in re.findall(r'<img[^>]+src="([^"]+)"', description_html or "") if not url.startswith("/")]


async def syndication_video(session: aiohttp.ClientSession, post_id: str) -> List[str]:
    """The mp4 files of a post's video, best first, from Twitter's syndication endpoint."""
    if not post_id:
        return []
    for params in ({"id": post_id, "lang": "en"}, {"id": post_id, "lang": "en", "token": "a"}):
        data = await _get_json(session, "https://cdn.syndication.twimg.com/tweet-result", params)
        variants = []
        for media in (data.get("mediaDetails") or []) if isinstance(data, dict) else []:
            for variant in (media.get("video_info") or {}).get("variants", []) or []:
                if variant.get("content_type") == "video/mp4" and trusted(str(variant.get("url", ""))):
                    variants.append((variant.get("bitrate", 0) or 0, variant["url"]))
        if variants:
            return [url for _bitrate, url in sorted(variants, reverse=True)]
    return []


async def build_x_post(session: aiohttp.ClientSession, source: Source, item: FeedItem, avatar: str) -> Post:
    """A Nitter post as one to send: its text with a translation, its pictures, and its video when it has one."""
    images = [url for url in media_urls(item.description) if trusted(url)]
    videos: List[bytes] = []
    wanted_video = any("amplify_video_thumb" in url or "/tweet_video_thumb/" in url for url in images)
    if wanted_video:
        mp4 = await syndication_video(session, item.id)
        data = await video_bytes(mp4[0]) if mp4 else None
        if data:
            videos.append(data)
            images = []
    english = await translate(session, item.title) if has_japanese(item.title) else ""
    parts = [sanitize(english)] if english and english != item.title else []
    parts.append(sanitize(item.title))
    return Post(source.key, item.id, f"https://x.com/{source.handle}/status/{item.id}", source.label, avatar, parts, images, videos, wanted_video)
