from typing import Any, Dict, List, Set, Tuple
import asyncio
import io
import json
import logging

import aiohttp
import discord

from rasmai.scraping import news
from rasmai.scraping.news import Post, SOURCES, Source
from rasmai.storage.db import news_mark_seen, news_seen_any, news_subscribers, news_unseen, remove_news_subscription

logger = logging.getLogger(__name__)

POLL_EVERY = 300        # seconds between looks at the X feeds
IDLE_RECHECK = 60       # seconds between asking whether anyone follows a Bluesky account, while nobody does
CATCH_UP = 5            # most posts sent at once after a gap; older ones are marked seen, not sent


def _extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"GIF8"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


class NewsWatch:
    """Posts from the maimai accounts, sent into every channel that follows them.

    Bluesky arrives over Jetstream as it is posted. X has no feed of its own to read, so it is polled
    through a public Nitter instance every few minutes. Each channel's webhook is sealed in the database
    and opened only to send.
    """

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self._tasks: List[asyncio.Task] = []
        self._running: Set[asyncio.Task] = set()

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=news.HEADERS)
        return self._session

    def start(self) -> None:
        if any(not task.done() for task in self._tasks):
            return          # on_ready fires again after a reconnect; the loops must not double
        self._tasks = [asyncio.create_task(self._bluesky_loop()), asyncio.create_task(self._x_loop())]

    def _spawn(self, work: Any) -> None:
        task = asyncio.create_task(work)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    # ------------------------------------------------------------ Bluesky

    async def _bluesky_loop(self) -> None:
        accounts = {source.did: source for source in SOURCES.values() if source.did}
        url = news.JETSTREAM_URL + "".join(f"&wantedDids={did}" for did in accounts)
        while True:
            try:
                followed = [await asyncio.to_thread(news_subscribers, source.key) for source in accounts.values()]
                if not any(followed):
                    await asyncio.sleep(IDLE_RECHECK)
                    continue
                async with self.session.ws_connect(url, heartbeat=30) as socket:
                    logger.info("news: connected to Jetstream")
                    async for message in socket:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            self._spawn(self._event(message.data, accounts))
                        elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.info("news: Jetstream dropped (%s)", type(error).__name__)
            except Exception:
                logger.exception("news: Jetstream failed")
            await asyncio.sleep(5)

    async def _event(self, raw: str, accounts: Dict[str, Source]) -> None:
        try:
            data = json.loads(raw)
            commit = data.get("commit") or {}
            if data.get("kind") != "commit" or commit.get("operation") != "create":
                return
            did, rkey, record = commit.get("repo"), commit.get("rkey"), commit.get("record")
            source = accounts.get(did)
            if source is None or not rkey or not isinstance(record, dict):
                return
            await self.bluesky_post(source, record, f"at://{did}/app.bsky.feed.post/{rkey}")
        except Exception:
            logger.exception("news: a Bluesky event could not be handled")

    async def bluesky_post(self, source: Source, record: Dict[str, Any], uri: str) -> int:
        """Send a new post if it reads like a maimai update and nobody has seen it; returns how many channels got it."""
        if not news.is_update(str(record.get("text", "")), str((record.get("embed") or {}).get("$type", ""))):
            return 0
        root = str(((record.get("reply") or {}).get("root") or {}).get("uri", ""))
        # a reply in a thread already sent was in that send, or is not an update of its own
        if (root and not await asyncio.to_thread(news_unseen, source.key, [root])) or not await asyncio.to_thread(news_unseen, source.key, [uri]):
            return 0
        if not await asyncio.to_thread(news_subscribers, source.key):
            return 0
        await asyncio.sleep(news.THREAD_WAIT_SECONDS)       # the rest of a thread is posted in the seconds after its first post
        post, uris = await news.build_bluesky_post(self.session, source, record, uri)
        if post is None:
            return 0
        await asyncio.to_thread(news_mark_seen, source.key, uris)
        return await self.publish(post)

    # ------------------------------------------------------------ X

    async def _x_loop(self) -> None:
        while True:
            for source in SOURCES.values():
                if source.platform != "X":
                    continue
                try:
                    if await asyncio.to_thread(news_subscribers, source.key):
                        await self.poll(source)
                except Exception:
                    logger.exception("news: reading %s failed", source.handle)
            await asyncio.sleep(POLL_EVERY)

    async def poll(self, source: Source) -> int:
        """Send the posts of an X account that nobody has seen. The very first look sends none: it only learns what is already there."""
        items, avatar = await news.fetch_feed(self.session, source.handle)
        items = [item for item in items if item.id and not item.retweet]
        if not items:
            return 0
        first = not await asyncio.to_thread(news_seen_any, source.key)
        unseen = await asyncio.to_thread(news_unseen, source.key, [item.id for item in items])
        if first:
            await asyncio.to_thread(news_mark_seen, source.key, [item.id for item in items])
            return 0
        pending = [item for item in reversed(items) if item.id in unseen]       # oldest first
        older, pending = pending[:-CATCH_UP], pending[-CATCH_UP:]
        if older:
            await asyncio.to_thread(news_mark_seen, source.key, [item.id for item in older])
        for item in pending:
            await self.publish(await news.build_x_post(self.session, source, item, avatar))
            await asyncio.to_thread(news_mark_seen, source.key, [item.id])
        return len(pending)

    # ------------------------------------------------------------ sending

    async def publish(self, post: Post) -> int:
        """Send a post to every channel following its source; returns how many it reached."""
        subscribers: List[Tuple[str, str]] = await asyncio.to_thread(news_subscribers, post.source)
        if not subscribers:
            return 0
        files: List[Tuple[str, bytes]] = []
        for number, url in enumerate(post.images[:10], 1):
            data = await news.fetch_bytes(self.session, url)
            if data:
                files.append((f"image_{number}.{_extension(data)}", data))
        files += [(f"video_{number}.mp4", data) for number, data in enumerate(post.videos[:5], 1)]
        files = files[:10]
        reached = 0
        for channel_id, url in subscribers:
            if await self._deliver(channel_id, url, post, files):
                reached += 1
        return reached

    async def _deliver(self, channel_id: str, url: str, post: Post, files: List[Tuple[str, bytes]]) -> bool:
        try:
            webhook = discord.Webhook.from_url(url, session=self.session)
        except ValueError:
            await asyncio.to_thread(remove_news_subscription, channel_id)
            return False
        for attach in ([True, False] if files else [False]):
            options: Dict[str, Any] = {"content": post.content(), "username": post.username, "allowed_mentions": discord.AllowedMentions.none()}
            if post.avatar:
                options["avatar_url"] = post.avatar
            if attach:
                options["files"] = [discord.File(io.BytesIO(data), filename=name) for name, data in files]
            try:
                await webhook.send(**options)
                return True
            except (discord.NotFound, discord.Forbidden):
                # somebody deleted the webhook or the channel: nothing will ever be delivered there again
                logger.info("news: a channel's webhook is gone, so its subscriptions are removed")
                await asyncio.to_thread(remove_news_subscription, channel_id)
                return False
            except discord.HTTPException as error:
                if attach and error.status == 413:
                    continue            # the attachments were too big for this server; the text and link still go
                logger.warning("news: a webhook send failed with %s", error.status)
                return False
        return False
