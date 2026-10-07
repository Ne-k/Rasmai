from dataclasses import dataclass, field
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse
import asyncio
import html
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

import aiohttp

from rasmai.config import TRANSLATE_KEEP_ALIVE, TRANSLATE_MODEL, TRANSLATE_URL

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
_translate_paused_until = 0.0        # Google's free endpoint throttles; after a refusal it is left alone for a while
FOLLOW_UP_MARK = chr(0x21A9) + chr(0xFE0F)      # the return arrow as an emoji, spelled out so no invisible character sits in the source


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
    follow_up: Optional[Tuple[str, str]] = None      # the account answering its own earlier post: that post's address and its first line
    posted_at: Optional[int] = None                  # when it was made, in seconds since 1970

    def content(self) -> str:
        body = "\n\n".join(p for p in self.parts if p).strip()
        if len(body) > 1500:
            body = body[:1490] + "…"
        link = self.url if self.wanted_video and not self.videos else f"<{self.url}>"
        # Discord draws these in each reader's own time zone: the full date and time, then how long ago, which keeps counting
        when = f"-# Posted <t:{self.posted_at}:F> · <t:{self.posted_at}:R>\n" if self.posted_at else ""
        head = ""
        if self.follow_up:
            earlier, line = self.follow_up
            head = FOLLOW_UP_MARK + " **Follow-up to " + (f"[their earlier post](<{earlier}>)" if earlier else "their earlier post") + "**\n" + (f"> {line}\n\n" if line else "\n")
        return sanitize(f"{head}{body}\n\n{when}{link}\n\n---".strip())


TWITTER_EPOCH_MS = 1288834974657


def tweet_time(post_id: str) -> Optional[int]:
    """When an X post was made, in seconds: a status id carries its own creation time, so the feed's date is not needed."""
    try:
        return ((int(post_id) >> 22) + TWITTER_EPOCH_MS) // 1000
    except ValueError:
        return None


def iso_time(stamp: str) -> Optional[int]:
    """A Bluesky post's ``createdAt`` in seconds. The author writes it, so one claiming to be from the future is taken as now."""
    try:
        made = int(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None
    return min(made, int(datetime.now(timezone.utc).timestamp()))


def first_line(text: str, limit: int = 140) -> str:
    """The start of a post on one line, to quote: markup entities undone, whitespace collapsed, cut at ``limit``."""
    line = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def trusted(url: str) -> bool:
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host in TRUSTED_HOSTS or host.endswith(".twimg.com"))


MAIMAI = re.compile(r"maimai|舞萌|でらっくす", re.IGNORECASE)


def is_maimai(text: str) -> bool:
    """Whether a post is about maimai. Preformai International covers CHUNITHM as well, so its posts are told apart by this; the X accounts are not filtered."""
    return bool(MAIMAI.search(text or ""))


ZWSP = chr(0x200B)      # a zero-width space: "@" + this + "everyone" reads the same and pings nobody


def sanitize(text: str) -> str:
    """Text with anything that would ping somebody made inert. Sending also forbids every mention, so this is the second lock, not the first."""
    if not text:
        return text
    text = re.sub(r"@(everyone|here)", lambda m: "@" + ZWSP + m.group(1), text, flags=re.IGNORECASE)
    text = re.sub(r"<@[!&]?\d+>", lambda m: "[role]" if m.group(0).startswith("<@&") else "[user]", text)
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


_video_slots = asyncio.Semaphore(2)


async def video_bytes(url: str) -> Optional[bytes]:
    """A video remuxed to mp4 and, when over the size limit, re-encoded under it; None without ffmpeg or when it cannot be made small enough."""
    async with _video_slots:
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


async def bluesky_thread(session: aiohttp.ClientSession, uri: str, did: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Every post by the same author in a thread from ``uri`` down, oldest first, and the post above it if the author wrote that too."""
    data = await _get_json(session, f"{PUBLIC_API}/app.bsky.feed.getPostThread", {"uri": uri, "depth": 10, "parentHeight": 1})
    if not isinstance(data, dict):
        return [], None
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
    above = ((data.get("thread") or {}).get("parent") or {}).get("post")
    if not isinstance(above, dict) or (above.get("author") or {}).get("did") != did:
        above = None
    return sorted(found.values(), key=lambda p: (p.get("record") or {}).get("createdAt", "")), above


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
    thread, above = await bluesky_thread(session, uri, source.did)
    thread = thread or [{"uri": uri, "record": record, "author": {"did": source.did}}]
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
    follow_up = None
    if record.get("reply"):
        follow_up = ("", "")
        if above:
            follow_up = (f"https://bsky.app/profile/{source.handle}/post/{str(above.get('uri', '')).split('/')[-1]}",
                         first_line(str((above.get("record") or {}).get("text", ""))))
    post = Post(source.key, uri, f"https://bsky.app/profile/{source.handle}/post/{uri.split('/')[-1]}", source.label,
                await bluesky_avatar(session, source.handle), parts, images, videos, bool(playlists), follow_up,
                iso_time(str((thread[0].get("record") or {}).get("createdAt", ""))))
    return post, [p["uri"] for p in thread]


# ---------------------------------------------------------------- X, through Nitter's RSS

@dataclass
class FeedItem:
    id: str
    title: str
    link: str
    description: str
    retweet: bool
    author: str = ""         # whose status page the link is on: a retweet's is somebody else's
    reply_to: str = ""       # the account a reply answers; empty for a post that is not a reply

    @property
    def text(self) -> str:
        """What was written, without Nitter's "R to @someone:" in front."""
        return re.sub(r"^R to @\w+:\s*", "", self.title)


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
        author = re.search(r"/([A-Za-z0-9_]+)/status/", link)
        reply = re.match(r"^R to @(\w+):", title)
        items.append(FeedItem(tweet_id(link), title, link, item.findtext("description") or "",
                              bool(re.match(r"^(?:RT\b|リツイート\b)", title, flags=re.IGNORECASE)),
                              author.group(1) if author else "", reply.group(1) if reply else ""))
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


def own_posts(items: List[FeedItem], source: Source) -> List[FeedItem]:
    """The account's own posts, newest first: what it wrote, and what it wrote in answer to itself, which is how it corrects or continues one.

    Left out are retweets and anything on somebody else's status page, and replies to other people. The feed is
    not in time order, but a status id grows with time, so that is what orders it.
    """
    handle = source.handle.lower()
    own = [item for item in items if item.id and not item.retweet and item.author.lower() == handle
           and (not item.reply_to or item.reply_to.lower() == handle)]
    return sorted(own, key=lambda item: int(item.id), reverse=True)


def has_english(text: str) -> bool:
    """Whether a post already carries its own English: a run of four English words in a row, which names and hashtags do not make."""
    plain = re.sub(r"https?://\S+|[#@]\w+", " ", text or "")
    return bool(re.search(r"(?:\b[A-Za-z][A-Za-z']+\b[ ,.!?:;&]+){4,}", plain))


def has_japanese(text: str) -> bool:
    return bool(text and re.search(r"[぀-ゟ゠-ヿ一-鿿]", text))


TRANSLATE_PAUSE = 300            # how long Google's free endpoint is left alone after it refuses
LOCAL_PAUSE = 60                 # and how long the local model is, after it was unreachable or refused: the first post after a restart waits for it to load, none after that for it to fail
LOCAL_TIMEOUT = 150              # seconds a translation may take; loading an 8 GB model into memory is most of it the first time
TRANSLATED_KEPT = 200

# Google's prompt for TranslateGemma, word for word, down to the two blank lines before the text: the model was trained on exactly this
LOCAL_PROMPT = (
    "You are a professional Japanese (ja) to English (en) translator. Your goal is to accurately convey the meaning and nuances of the original "
    "Japanese text while adhering to English grammar, vocabulary, and cultural sensitivities.\n"
    "Produce only the English translation, without any additional explanations or commentary. Please translate the following Japanese text into English:\n\n\n")

_local_paused_until = 0.0
_local_slot = asyncio.Semaphore(1)      # one translation at a time: two at once on a 16 GB machine are slower than one after the other
_translated: "OrderedDict[str, str]" = OrderedDict()


def _acceptable(source: str, result: str) -> bool:
    """Whether a model's answer can be trusted to be the translation: something, not a runaway, and not still mostly Japanese."""
    if not result or len(result) > 4 * len(source) + 200:
        return False
    letters = [c for c in result if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if has_japanese(c)) / len(letters) < 0.3


async def _translate_local(session: aiohttp.ClientSession, clean: str) -> Optional[str]:
    """The text in English from the local model; None when none is set up, it is paused, it could not be reached or what it said cannot be used."""
    global _local_paused_until
    if not TRANSLATE_URL or time.monotonic() < _local_paused_until:
        return None
    body = {"model": TRANSLATE_MODEL, "stream": False, "keep_alive": TRANSLATE_KEEP_ALIVE,
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 1024},
            "messages": [{"role": "user", "content": LOCAL_PROMPT + clean}]}
    try:
        async with _local_slot:
            async with session.post(f"{TRANSLATE_URL}/api/chat", json=body, timeout=aiohttp.ClientTimeout(total=LOCAL_TIMEOUT)) as response:
                if response.status != 200:
                    _local_paused_until = time.monotonic() + LOCAL_PAUSE
                    logger.warning("news: the translation model answered %s%s", response.status,
                                   f"; has it been pulled? ollama pull {TRANSLATE_MODEL}" if response.status == 404 else "")
                    return None
                data = await response.json(content_type=None)
        result = str((data.get("message") or {}).get("content", "")).strip()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, AttributeError) as error:
        _local_paused_until = time.monotonic() + LOCAL_PAUSE
        logger.warning("news: the translation model could not be reached (%s), so Google Translate is used for a minute", type(error).__name__)
        return None
    if not _acceptable(clean, result):
        logger.warning("news: the translation model's answer was not usable, so Google Translate is used for this post")
        return None
    return result


async def _translate_google(session: aiohttp.ClientSession, clean: str) -> Optional[str]:
    """Google's free endpoint; None when it fails. A refusal for going too fast pauses it for a few minutes rather than asking again on every post."""
    global _translate_paused_until
    if time.monotonic() < _translate_paused_until:
        return None
    for attempt in range(2):
        try:
            async with session.get("https://translate.googleapis.com/translate_a/single", headers=HEADERS,
                                   params={"client": "gtx", "sl": "ja", "tl": "en", "dt": "t", "q": clean},
                                   timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 429:
                    _translate_paused_until = time.monotonic() + TRANSLATE_PAUSE
                    logger.info("news: translation is throttled, so posts go out untranslated for %d minutes", TRANSLATE_PAUSE // 60)
                    return None
                if response.status == 200:
                    data = await response.json(content_type=None)
                    return "".join(segment[0] for segment in data[0] if segment and segment[0]) or None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, IndexError):
            pass
        if attempt == 0:
            await asyncio.sleep(1)
    return None


async def translate(session: aiohttp.ClientSession, text: str) -> str:
    """Japanese text in English: from the local model when there is one, else Google's free endpoint, else the text itself, which sends the post as written.

    Links are left out of what is translated. A translation is kept for a while, so the same post is not translated twice.
    """
    clean = re.sub(r"https?://\S+", "", text or "").strip()
    if not clean:
        return text
    if clean in _translated:
        _translated.move_to_end(clean)
        return _translated[clean]
    result = await _translate_local(session, clean) or await _translate_google(session, clean)
    if not result:
        return text
    _translated[clean] = result
    while len(_translated) > TRANSLATED_KEPT:
        _translated.popitem(last=False)
    return result


def media_urls(description_html: str) -> List[str]:
    return [url for url in re.findall(r'<img[^>]+src="([^"]+)"', description_html or "") if not url.startswith("/")]


async def syndication_parent(session: aiohttp.ClientSession, post_id: str, handle: str) -> Optional[Tuple[str, str]]:
    """The address and first line of the post this one answers, when it is the same account's own; None otherwise or when it cannot be read."""
    for params in ({"id": post_id, "lang": "en", "token": "a"}, {"id": post_id, "lang": "en"}):
        data = await _get_json(session, "https://cdn.syndication.twimg.com/tweet-result", params)
        parent = data.get("parent") if isinstance(data, dict) else None
        if isinstance(parent, dict) and parent.get("id_str"):
            if str((parent.get("user") or {}).get("screen_name", "")).lower() != handle.lower():
                return None
            return f"https://x.com/{handle}/status/{parent['id_str']}", first_line(str(parent.get("text", "")))
    return None


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
    written = item.text
    # some accounts write both languages themselves, and a translation of that would only say it twice
    english = await translate(session, written) if has_japanese(written) and not has_english(written) else ""
    parts = [sanitize(english)] if english and english != written else []
    parts.append(sanitize(written))
    follow_up = None
    if item.reply_to:
        follow_up = await syndication_parent(session, item.id, source.handle) or ("", "")
    return Post(source.key, item.id, f"https://x.com/{source.handle}/status/{item.id}", source.label, avatar, parts, images, videos, wanted_video, follow_up,
                tweet_time(item.id))


async def recent_posts(session: aiohttp.ClientSession, source: Source, count: int) -> List[Post]:
    """The latest ``count`` posts of an account, oldest first, as they would be sent now.

    Bluesky counts only posts about maimai, the same filter live ones go through; X counts every original post.
    """
    if count <= 0:
        return []
    if source.platform == "Bluesky":
        data = await _get_json(session, f"{PUBLIC_API}/app.bsky.feed.getAuthorFeed",
                               {"actor": source.handle, "filter": "posts_no_replies", "limit": 50})
        found = []
        for entry in (data.get("feed") or []) if isinstance(data, dict) else []:
            post = entry.get("post") or {}
            record = post.get("record") or {}
            if entry.get("reason") or (post.get("author") or {}).get("did") != source.did or not post.get("uri"):
                continue          # a repost, or somebody else's
            if is_maimai(str(record.get("text", ""))):
                found.append((record, post["uri"]))
            if len(found) == count:
                break
        built = [(await build_bluesky_post(session, source, record, uri))[0] for record, uri in found]
        return [post for post in reversed(built) if post is not None]
    items, avatar = await fetch_feed(session, source.handle)
    own = own_posts(items, source)[:count]
    return [await build_x_post(session, source, item, avatar) for item in reversed(own)]
