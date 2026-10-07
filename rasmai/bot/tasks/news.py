from typing import Any, Coroutine, Dict, List, Optional, Set, Tuple
import asyncio
import io
import json
import logging
import time

import aiohttp
import discord

from rasmai.scraping import news
from rasmai.scraping.news import Post, SOURCES, Source
from rasmai.storage.db import (
    jetstream_alive, news_mark_seen, news_seen_any, news_subscribers, news_unseen, remove_news_subscription,
    save_jetstream_alive,
)

logger = logging.getLogger(__name__)

POLL_EVERY = 300                    # seconds between looks at the X feeds
IDLE_RECHECK = 60                   # seconds between asking whether anyone follows a Bluesky account, while nobody does
CATCH_UP = 5                        # most posts sent at once after a gap; older ones are marked seen, not sent
SEND_AT_ONCE = 5                    # channels a post is being sent to at the same time
NO_MENTIONS = discord.AllowedMentions.none()      # on every send: whatever a post says, it cannot ping a user, a role, @everyone or @here

ALIVE_EVERY = 60                    # seconds between noting that the Jetstream connection is still up
ALIVE_LAG = 60 * 1_000_000          # the moment noted is this far in the past, so a post still being processed when the bot dies is asked for again
REWIND = 10 * 1_000_000             # and a reconnect asks from this much earlier still: the server's clock is not ours, and a repeat is dropped as seen
REPLAY_LIMIT = 48 * 3600 * 1_000_000        # a gap longer than this is not replayed; the server keeps only a few days anyway
SETTLED = 60 * 1_000_000            # a post older than this has its whole thread already, so there is nothing to wait for


def _now_us() -> int:
    return int(time.time() * 1_000_000)


def jetstream_url(accounts: Dict[str, Source], alive: Optional[int], now: int) -> str:
    """The Jetstream address for these accounts, asking to start from just before ``alive`` when there is such a moment."""
    url = news.JETSTREAM_URL + "".join(f"&wantedDids={did}" for did in accounts)
    if alive:
        url += f"&cursor={max(alive - REWIND, now - REPLAY_LIMIT)}"
    return url


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

    Bluesky arrives over Jetstream as it is posted, and after any break in the connection, or a restart, the
    stream is asked for everything since the connection was last known to be up. X has no feed of its own to
    read, so it is polled through a public Nitter instance every few minutes. Each channel's webhook is sealed
    in the database and opened only to send.
    """

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
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

    def spawn(self, work: Coroutine[Any, Any, Any]) -> None:
        """Run something in the background, kept referenced until it ends."""
        task = asyncio.create_task(work)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    # ------------------------------------------------------------ Bluesky

    async def _bluesky_loop(self) -> None:
        accounts = {source.did: source for source in SOURCES.values() if source.did}
        while True:
            try:
                followed = [await asyncio.to_thread(news_subscribers, source.key) for source in accounts.values()]
                if not any(followed):
                    # nobody to send to, so nothing is missed: note that, or the first follower would be sent days of old posts
                    await asyncio.to_thread(save_jetstream_alive, _now_us())
                    await asyncio.sleep(IDLE_RECHECK)
                    continue
                alive = await asyncio.to_thread(jetstream_alive)
                url = jetstream_url(accounts, alive, _now_us())
                async with self.session.ws_connect(url, heartbeat=30) as socket:
                    logger.info("news: connected to Jetstream%s", f", asking for what it missed since {int((_now_us() - alive) / 1e6)}s ago" if alive else "")
                    await self.read(socket, accounts)
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.info("news: Jetstream dropped (%s)", type(error).__name__)
            except Exception:
                logger.exception("news: Jetstream failed")
            await asyncio.sleep(5)

    async def read(self, socket: Any, accounts: Dict[str, Source]) -> None:
        """Handle a connection's messages until it closes, noting every minute that it is still up."""
        noted = float("-inf")
        while True:
            try:
                message = await socket.receive(timeout=ALIVE_EVERY)
            except asyncio.TimeoutError:
                message = None          # a quiet stretch: the account posts rarely, and that is the usual case
            if time.monotonic() - noted >= ALIVE_EVERY:
                await asyncio.to_thread(save_jetstream_alive, _now_us() - ALIVE_LAG)
                noted = time.monotonic()
            if message is None:
                continue
            if message.type == aiohttp.WSMsgType.TEXT:
                self.spawn(self._event(message.data, accounts))
            elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                return

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
            # a replayed post is old enough that its thread is complete; a live one is given a moment to finish
            settled = _now_us() - int(data.get("time_us") or _now_us()) > SETTLED
            await self.bluesky_post(source, record, f"at://{did}/app.bsky.feed.post/{rkey}", wait=not settled)
        except Exception:
            logger.exception("news: a Bluesky event could not be handled")

    async def bluesky_post(self, source: Source, record: Dict[str, Any], uri: str, wait: bool = True) -> int:
        """Send a new post if it is one to send and nobody has seen it; returns how many channels got it.

        A post is sent when it reads like an update. The account answering itself is sent too, since that is how it
        corrects or continues a post, even when the answer says nothing like an update does, provided what it answers
        was sent. An answer to somebody else is not sent.
        """
        updating = news.is_update(str(record.get("text", "")), str((record.get("embed") or {}).get("$type", "")))
        reply = record.get("reply") or {}
        if reply:
            if str((reply.get("parent") or {}).get("uri", "")).split("/")[2:3] != [source.did]:
                return 0            # an answer to somebody else
            root = str((reply.get("root") or {}).get("uri", ""))
            if not updating and (not root or await asyncio.to_thread(news_unseen, source.key, [root])):
                return 0            # an answer in a thread that was never sent
        elif not updating:
            return 0
        # what was already sent in a thread is recorded as seen, so only the new post of a thread goes out
        if not await asyncio.to_thread(news_unseen, source.key, [uri]):
            return 0
        if not await asyncio.to_thread(news_subscribers, source.key):
            return 0
        if wait:
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
        items = news.own_posts(items, source)
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

    async def _files(self, post: Post) -> List[Tuple[str, bytes]]:
        """The post's pictures, fetched, and its videos, as ``(file name, bytes)``; at most ten, which is all a message may carry."""
        files: List[Tuple[str, bytes]] = []
        for number, url in enumerate(post.images[:10], 1):
            data = await news.fetch_bytes(self.session, url)
            if data:
                files.append((f"image_{number}.{_extension(data)}", data))
        files += [(f"video_{number}.mp4", data) for number, data in enumerate(post.videos[:5], 1)]
        return files[:10]

    async def publish(self, post: Post) -> int:
        """Send a post to every channel following its source; returns how many it reached."""
        subscribers: List[Tuple[str, str]] = await asyncio.to_thread(news_subscribers, post.source)
        if not subscribers:
            return 0
        files = await self._files(post)
        gate = asyncio.Semaphore(SEND_AT_ONCE)

        async def one(channel_id: str, url: str) -> bool:
            async with gate:
                return await self._deliver(channel_id, url, post, files)
        return sum(await asyncio.gather(*(one(channel_id, url) for channel_id, url in subscribers)))

    async def history(self, channel_id: str, url: str, keys: List[str], count: int) -> int:
        """Send one channel the latest ``count`` posts of each of these sources, oldest first, and nobody else. Returns how many arrived.

        Nothing here is recorded as seen: these are old posts being shown, not new ones being handled, so live sending is unaffected.
        """
        sent = 0
        for key in keys:
            try:
                posts = await news.recent_posts(self.session, SOURCES[key], count)
            except Exception:
                logger.exception("news: the earlier posts of %s could not be read", key)
                continue
            for post in posts:
                if not await self._deliver(channel_id, url, post, await self._files(post)):
                    return sent             # the webhook is gone, or refused: the rest would go the same way
                sent += 1
        return sent

    async def _deliver(self, channel_id: str, url: str, post: Post, files: List[Tuple[str, bytes]]) -> bool:
        try:
            webhook = discord.Webhook.from_url(url, session=self.session)
        except ValueError:
            await asyncio.to_thread(remove_news_subscription, channel_id)
            return False
        for attach in ([True, False] if files else [False]):
            options: Dict[str, Any] = {"content": post.content(), "username": post.username, "allowed_mentions": NO_MENTIONS}
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

