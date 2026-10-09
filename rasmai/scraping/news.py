from dataclasses import dataclass, field, replace
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse
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
    maimai_only: bool = False      # a channel starting to follow it gets only its posts about maimai, which it can change: an account covering other games too
    x_handle: str = ""             # a Bluesky account's own X username: both are read, and whichever copy of a post comes first is sent


# the accounts every server can pick; servers add others of their own, kept in the database
SOURCES: Dict[str, Source] = {
    "preformai": Source("preformai", "Preformai International", "Bluesky", "performaien.bsky.social", "did:plc:brwck2njp6tj43cns5t5rbdh", True, "performaien"),
    "maimai": Source("maimai", "Maimai Official", "X", "maimai_official"),
    "laundromai": Source("laundromai", "Laundromai", "X", "laundromai"),
    # not filtered: the tournament covers all three games and tags every post with all of them, so the filter cannot tell them apart
    "kop": Source("kop", "KING of Performai", "X", "kop_sega"),
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
_titles: Dict[str, str] = {}         # an X account's display name, from the title of its feed
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
    about_maimai: bool = True                        # whether it goes to a channel getting only the account's posts about maimai

    def content(self, unfurl: bool = False) -> str:
        """The message: ``unfurl`` lets the link draw its preview, for when the post's media could not be attached."""
        body = unmask("\n\n".join(p for p in self.parts if p).strip())
        if len(body) > 1500:
            body = body[:1490] + "…"
        link = self.url if unfurl or (self.wanted_video and not self.videos) else f"<{self.url}>"
        # Discord draws these in each reader's own time zone: the full date and time, then how long ago, which keeps counting
        when = f"-# Posted <t:{self.posted_at}:F> · <t:{self.posted_at}:R>\n" if self.posted_at else ""
        head = ""
        if self.follow_up:
            earlier, line = self.follow_up[0], unmask(self.follow_up[1])
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


def x_side(source: Source) -> Source:
    """The X half of an account read on both sites: the same account, posting to the same channels, read from its X feed."""
    return replace(source, platform="X", handle=source.x_handle, did="")


def copy_mark(text: str) -> str:
    """What a post says, cut down so its copy on the other site gives the same: no links, mentions, punctuation or case.

    Bluesky shortens links and writes mentions as domains where X does not, so those go. "" when too little is left
    to tell one post from another.
    """
    words = re.sub(r"https?://\S+|@\S+|\S*\w\.\w{2,}\S*", " ", text or "").lower()
    letters = "".join(re.findall(r"\w", words))[:60]
    # shortcut: a post with next to no text (a picture alone) cannot be matched, so both its copies go out; match on time if that happens often
    return "copy:" + letters if len(letters) >= 12 else ""


def first_line(text: str, limit: int = 140) -> str:
    """The start of a post on one line, to quote: markup entities undone, whitespace collapsed, cut at ``limit``."""
    line = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def trusted(url: str) -> bool:
    try:
        parts = urlparse(url)
        host = (parts.hostname or "").lower()       # raises on a malformed host such as "[x"
    except ValueError:
        return False
    return parts.scheme == "https" and (host in TRUSTED_HOSTS or host.endswith(".twimg.com"))


MAIMAI = re.compile(r"maimai|舞萌|でらっくす", re.IGNORECASE)
OTHER_GAMES = re.compile(r"chunithm|o\.?n\.?g\.?e\.?k\.?i|オンゲキ|チュウニズム|wacca|sound voltex", re.IGNORECASE)


def is_maimai(text: str) -> bool:
    """Whether a post is about maimai. Preformai International covers its sister games too, so its posts are told apart by this; the X accounts are not filtered.

    A post that names maimai is about maimai, unless another game comes first: then it is that game's post that happens to
    mention maimai, a collaboration's map for one, and is left out. Two things bring it back: the `#maimai` tag, and maimai
    named in the same sentence as the other games, as an event covering several of them does.
    """
    found = MAIMAI.search(text or "")
    if not found:
        return False
    other = OTHER_GAMES.search(text)
    if other is None or other.start() > found.start() or "#maimai" in text.lower():
        return True
    return any(MAIMAI.search(part) and OTHER_GAMES.search(part) for part in re.split(r"[\n!?。！？]+", text))


ZWSP = chr(0x200B)      # a zero-width space: "@" + this + "everyone" reads the same and pings nobody


def sanitize(text: str) -> str:
    """Text with anything that would ping somebody made inert. Sending also forbids every mention, so this is the second lock, not the first."""
    if not text:
        return text
    text = re.sub(r"@(everyone|here)", lambda m: "@" + ZWSP + m.group(1), text, flags=re.IGNORECASE)
    text = re.sub(r"<@[!&]?\d+>", lambda m: "[role]" if m.group(0).startswith("<@&") else "[user]", text)
    return re.sub(r"<#\d+>", "[channel]", text)


def unmask(text: str) -> str:
    """Post text with its ``[words](address)`` links broken, so a post cannot dress one address up as another; the bot's own links are added after."""
    return (text or "").replace("](", "]" + ZWSP + "(")


# ---------------------------------------------------------------- fetching

async def fetch_bytes(session: aiohttp.ClientSession, url: str, limit: int = MAX_FILE_BYTES) -> Optional[bytes]:
    """A file from a trusted host, followed through up to three redirects that must stay on trusted hosts; None past ``limit``."""
    for _ in range(4):
        if not trusted(url):
            return None
        try:
            async with session.get(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=20)) as response:
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
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
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


def _playlist_args(url: str, out: str) -> List[str]:
    # the playlist names its own segments and keys, and ffmpeg follows them and any redirect wherever they point: this keeps it to https,
    # and has the playlist's certificate checked, which the ffmpeg in Debian bookworm does not do unless asked, so nobody between can rewrite where it points
    return ["-protocol_whitelist", "https,tls,tcp,crypto", "-tls_verify", "1", "-headers", "User-Agent: Mozilla/5.0\r\n", "-i", url, "-c", "copy",
            "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", out]


def _video_sync(url: str) -> Optional[bytes]:
    if not shutil.which("ffmpeg") or not trusted(url):
        return None
    first, second = _temp(), _temp()
    try:
        if not _ffmpeg(_playlist_args(url, first), 180) or os.path.getsize(first) == 0:
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
                # only down the account's own chain: its answer to a fan sits under the fan's reply, and is not sent
                if isinstance(reply, dict) and ((reply.get("post") or {}).get("author") or {}).get("did") == did:
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


async def build_bluesky_post(session: aiohttp.ClientSession, source: Source, record: Dict[str, Any], uri: str) -> Tuple[Post, List[str]]:
    """The post for a thread that started at ``uri``, and the URIs of every post in it."""
    thread, above = await bluesky_thread(session, uri, source.did)
    thread = thread or [{"uri": uri, "record": record, "author": {"did": source.did}}]
    parts: List[str] = []
    images: List[str] = []
    playlists: List[str] = []
    for post in thread:
        body = post.get("record") or {}
        text = str(body.get("text", "")).strip()
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
                iso_time(str((thread[0].get("record") or {}).get("createdAt", ""))),
                # the account correcting or continuing a maimai post is about maimai too, whatever the correction says
                is_maimai("\n".join(parts)) or bool(above and is_maimai(str((above.get("record") or {}).get("text", "")))))
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
        """What was written, with its line breaks: the description's HTML keeps them, where the title runs it all into one line.

        A link is its full address where the post shows it shortened; a mention or hashtag, which Nitter links to itself, is its text.
        Without a description, the title, less Nitter's "R to @someone:" in front.
        """
        body = re.search(r"<p>(.*?)</p>", self.description, re.S)
        if not body:
            return re.sub(r"^R to @\w+:\s*", "", self.title)

        def link(match: "re.Match[str]") -> str:
            href, shown = match.group(1), match.group(2)
            return href if href.startswith(("http://", "https://")) and urlparse(href).hostname not in TRUSTED_HOSTS else shown
        written = re.sub(r"<br\s*/?>\s*", "\n", body.group(1))
        written = re.sub(r'<a [^>]*?href="([^"]*)"[^>]*>(.*?)</a>', link, written, flags=re.S)
        return html.unescape(re.sub(r"<[^>]+>", "", written)).strip()


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
    return items, twimg((root.findtext("./channel/image/url") or "").strip())


def feed_title(content: bytes) -> str:
    """The display name a Nitter feed's title gives, "Maimai Official" out of "Maimai Official / @maimai_official"; "" without one."""
    try:
        title = ET.fromstring(content).findtext("./channel/title") or ""
    except ET.ParseError:
        return ""
    return title.rsplit(" / @", 1)[0].strip() if " / @" in title else ""


async def fetch_feed(session: aiohttp.ClientSession, username: str, tries: int = len(RSS_INSTANCES)) -> Tuple[List[FeedItem], str]:
    """An account's posts from the first Nitter instance that answers with any, of the first ``tries``; ([], "") when none does."""
    first = _working.get(username)
    instances = ([first] if first else []) + [b for b in RSS_INSTANCES if b != first]
    for number, base in enumerate(instances[:tries]):
        if number:
            await asyncio.sleep(RSS_FALLBACK_DELAY)
        content = await fetch_bytes(session, f"{base}/{username}/rss", FEED_BYTES)
        items, avatar = parse_feed(content) if content else ([], "")
        if items:
            if first != base:
                logger.info("news: %s now read through %s", username, urlparse(base).hostname)
                _working[username] = base
            _titles[username.lower()] = feed_title(content)
            return items, avatar
    return [], ""


BLUESKY_LINK = re.compile(r"^(?:https?://)?(?:www\.)?bsky\.app/profile/([^/?#\s]+)", re.IGNORECASE)
X_LINK = re.compile(r"^(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})(?:[/?#]|$)", re.IGNORECASE)
X_NAME = re.compile(r"^[A-Za-z0-9_]{1,15}$")
LOOKUP_TRIES = 3            # Nitter instances asked about an account someone typed; all of them would be a minute of waiting for a typo


def _label(name: str, handle: str) -> str:
    """The name posts are sent under. Discord refuses a webhook name with "discord" or "clyde" in it, so then the handle stands in."""
    for candidate in (" ".join(str(name or "").split())[:80], handle[:80]):
        if candidate and not re.search(r"discord|clyde", candidate, re.IGNORECASE):
            return candidate
    return "News"


def parse_account(text: str) -> Tuple[str, str]:
    """Which platform an account someone typed is on, and its handle: ("Bluesky", "name.bsky.social"), ("X", "name"), or ("", "").

    A link says which itself. Otherwise a Bluesky handle is a domain, so it always has a dot, and an X username never can.
    """
    text = (text or "").strip()
    link = BLUESKY_LINK.match(text)
    if link:
        return "Bluesky", link.group(1)
    link = X_LINK.match(text)
    if link:
        return "X", link.group(1)
    text = text.lstrip("@")
    if text.startswith("did:") or "." in text:
        return ("Bluesky", text) if re.fullmatch(r"[A-Za-z0-9.:_-]{3,253}", text) else ("", "")
    return ("X", text) if X_NAME.match(text) else ("", "")


async def find_account(session: aiohttp.ClientSession, text: str) -> Optional[Source]:
    """The account someone typed, looked up so it is known to exist and under what name; None when it cannot be found.

    A Bluesky account is kept by its DID, which stays when its handle changes. An X account has to have a readable
    feed: a private one, or one Nitter cannot reach, has nothing to send.
    """
    platform, handle = parse_account(text)
    if platform == "Bluesky":
        data = await _get_json(session, f"{PUBLIC_API}/app.bsky.actor.getProfile", {"actor": handle})
        did = str(data.get("did", "")) if isinstance(data, dict) else ""
        if not did.startswith("did:"):
            return None
        handle = str(data.get("handle") or handle)
        return Source(f"bsky:{did}", _label(str(data.get("displayName") or ""), handle), "Bluesky", handle, did)
    if platform == "X":
        items, _avatar = await fetch_feed(session, handle, LOOKUP_TRIES)
        if not items:
            return None
        # the feed's own links carry the name as the account writes it
        handle = next((item.author for item in items if item.author.lower() == handle.lower()), handle)
        return Source(f"x:{handle.lower()}", _label(_titles.get(handle.lower(), ""), "@" + handle), "X", handle)
    return None


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
    """Whether a post already carries its own English, so a translation would only say it twice.

    Either it is mostly English, or it has an English sentence and at least as much English as Japanese. A sentence is four
    words in a row, three of them lowercase: a name such as "KING of Performai The 8th" is not one, and a Japanese post that
    names its event in English is still translated. Links, hashtags and mentions count for neither language.
    """
    plain = re.sub(r"https?://\S+|[#@]\w+", " ", text or "")
    japanese = len(re.findall(r"[぀-ゟ゠-ヿ一-鿿]", plain))
    english = len(re.findall(r"[A-Za-z]", plain))
    sentence = any(sum(word.islower() for word in re.findall(r"[A-Za-z][A-Za-z']+", run.group(0))) >= 3
                   for run in re.finditer(r"(?:\b[A-Za-z][A-Za-z']+\b[ ,.!?:;&]+){3,}\b[A-Za-z][A-Za-z']+\b", plain))
    return english >= 1.5 * japanese or (sentence and english >= japanese)


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
            async with session.get("https://translate.googleapis.com/translate_a/single",
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
        now = time.monotonic()
        # said once per post, with the reasons, because a post sent in Japanese is otherwise indistinguishable from one that was never meant to be translated
        logger.warning("news: a post could not be translated, so it goes out in Japanese. Local model: %s. Google: %s.",
                       "not set up (MAIMAI_TRANSLATE_URL is empty)" if not TRANSLATE_URL else ("paused after a failure" if now < _local_paused_until else "failed or answered badly"),
                       "paused after being throttled" if now < _translate_paused_until else "failed")
        return text
    _translated[clean] = result
    while len(_translated) > TRANSLATED_KEPT:
        _translated.popitem(last=False)
    return result


def twimg(url: str) -> str:
    """A picture behind a Nitter instance's own proxy as the twimg.com address it stands for, any other address as it is.

    Some instances hand out every picture through themselves, over http and from another host: the bot will not fetch
    those, and Discord will not show such an avatar, so the post went without its pictures and its sender's face.
    """
    path = urlparse(url or "").path
    if not path.startswith("/pic/"):
        return url
    inner = re.sub(r"^orig/", "", unquote(path[len("/pic/"):]))
    return inner if inner.startswith(("http://", "https://")) else f"https://pbs.twimg.com/{inner}"


def media_urls(description_html: str) -> List[str]:
    return [twimg(url) for url in re.findall(r'<img[^>]+src="([^"]+)"', description_html or "")]


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
    parts = [english] if english and english != written else []
    parts.append(written)
    follow_up = None
    if item.reply_to:
        follow_up = await syndication_parent(session, item.id, source.handle) or ("", "")
    return Post(source.key, item.id, f"https://x.com/{source.handle}/status/{item.id}", source.label, avatar, parts, images, videos, wanted_video, follow_up,
                tweet_time(item.id), is_maimai(written) or bool(follow_up and is_maimai(follow_up[1])))


async def recent_posts(session: aiohttp.ClientSession, source: Source, count: int, maimai_only: Optional[bool] = None) -> List[Post]:
    """The latest ``count`` posts of an account, oldest first, as they would be sent now.

    With ``maimai_only``, only its posts about maimai count, the same filter live ones go through; left out, the account's default.
    """
    only = source.maimai_only if maimai_only is None else maimai_only
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
            if not only or is_maimai(str(record.get("text", ""))):
                found.append((record, post["uri"]))
            if len(found) == count:
                break
        # oldest first, each site's own order kept where times are equal or missing
        picks = [(iso_time(str(record.get("createdAt", ""))) or 0, "Bluesky", copy_mark(str(record.get("text", ""))), (record, uri))
                 for record, uri in reversed(found)]
        x, avatar = x_side(source), ""
        if source.x_handle:
            # its X posts count too: some are only there, and the latest of both sites is what is shown
            items, avatar = await fetch_feed(session, x.handle)
            mine = [item for item in own_posts(items, x) if not only or is_maimai(item.text)][:count]
            picks += [(tweet_time(item.id) or 0, "X", copy_mark(item.text), item) for item in reversed(mine)]
        kept: List[Any] = []
        marks: Dict[str, set] = {"Bluesky": set(), "X": set()}
        for _when, site, mark, pick in sorted(picks, key=lambda pick: pick[0]):
            if mark and mark in marks["X" if site == "Bluesky" else "Bluesky"]:
                continue        # the later copy of a post on both sites
            marks[site].add(mark)
            kept.append(pick)
        return [await build_x_post(session, x, pick, avatar) if isinstance(pick, FeedItem) else (await build_bluesky_post(session, source, *pick))[0]
                for pick in kept[-count:]]
    items, avatar = await fetch_feed(session, source.handle)
    own = own_posts(items, source)[:count]
    return [await build_x_post(session, source, item, avatar) for item in reversed(own)]
