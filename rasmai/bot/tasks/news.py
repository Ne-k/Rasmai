from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional, Set, Tuple
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
    followed_news_keys, jetstream_alive, news_copy_seen, news_copy_sent, news_mark_seen, news_seen_any, news_sources, news_subscribers, news_unseen, remove_channel_webhook,
    remove_unknown_news_sources, save_jetstream_alive,
)

logger = logging.getLogger(__name__)

POLL_EVERY = 300                    # seconds between looks at the X feeds
IDLE_RECHECK = 60                   # seconds between asking whether anyone follows a Bluesky account, while nobody does
CATCH_UP = 5                        # most posts sent at once after a gap; older ones are marked seen, not sent
X_AT_ONCE = 4                       # X accounts read at the same time, so a dead one cannot hold up the rest, nor all of them crowd a Nitter instance
SEND_AT_ONCE = 10                   # channels a post is being sent to at the same time; webhooks share Discord's ~50 a second global limit, so no more
SEND_TIMEOUT = 30                   # seconds a send may take, Discord's own retries included, before it counts as a failure worth one more try
UPLOAD_BUDGET = 1 << 30             # bytes a post may upload across all its channels; above it, the link draws the media instead of every channel getting a copy
GONE_CODES = (10003, 10015)         # Discord's Unknown Channel and Unknown Webhook
NO_MENTIONS = discord.AllowedMentions.none()      # on every send: whatever a post says, it cannot ping a user, a role, @everyone or @here

ALIVE_EVERY = 60                    # seconds between noting that the Jetstream connection is still up
ALIVE_LAG = 60 * 1_000_000          # the moment noted is this far in the past, so a post still being processed when the bot dies is asked for again
REWIND = 10 * 1_000_000             # and a reconnect asks from this much earlier still: the server's clock is not ours, and a repeat is dropped as seen
MAX_AGE = 6 * 3600                  # seconds; a post older than this is marked seen, never sent live, however it turns up
REPLAY_LIMIT = MAX_AGE * 1_000_000  # so a longer gap is not replayed either: everything in it would only be dropped
SETTLED = 60 * 1_000_000            # a post older than this has its whole thread already, so there is nothing to wait for
REPLAY_DONE = 120                   # seconds after connecting by which the replay of a gap has arrived; until then only what has arrived counts as received


def _now_us() -> int:
    return int(time.time() * 1_000_000)


_added: Dict[str, Source] = {}      # the accounts servers added, as last read from the database


def load_sources() -> Dict[str, Source]:
    """Every source, the built-in ones and the accounts servers added, read fresh. It reads the database, so not on the event loop."""
    global _added
    _added = {row["key"]: Source(row["key"], row["label"], row["platform"], row["handle"], row["did"]) for row in news_sources()}
    return all_sources()


def all_sources() -> Dict[str, Source]:
    """Every source as last read: the built-in ones, then the accounts servers added."""
    return {**SOURCES, **_added}


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

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._tasks: List[asyncio.Task] = []
        self._running: Set[asyncio.Task] = set()
        self._inflight: Set[str] = set()        # Bluesky posts being waited on, built or sent right now
        self._queued: Dict[str, int] = {}       # of those, how many each account has
        self._copy_turn = asyncio.Lock()        # the two copies of a post, on Bluesky and on X, are decided one after the other
        self._bluesky_turn = asyncio.Lock()     # Bluesky posts are built and sent one at a time, in the order they finish waiting
        self._history_turn = asyncio.Semaphore(1)       # one /news subscribe previous: at a time, however many servers ask

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=news.HEADERS)
        return self._session

    def start(self) -> None:
        if any(not task.done() for task in self._tasks):
            return          # on_ready fires again after a reconnect; the loops must not double
        logger.info("news: Japanese posts are translated %s",
                    f"by {news.TRANSLATE_MODEL} at {news.TRANSLATE_URL}, with Google Translate as the fallback" if news.TRANSLATE_URL
                    else "by Google Translate only: MAIMAI_TRANSLATE_URL is not set")
        self._tasks = [asyncio.create_task(self._bluesky_loop()), asyncio.create_task(self._x_loop())]

    def spawn(self, work: Coroutine[Any, Any, Any]) -> None:
        """Run something in the background, kept referenced until it ends."""
        task = asyncio.create_task(work)
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    # ------------------------------------------------------------ Bluesky

    async def _followed_bluesky(self) -> Dict[str, Source]:
        """The Bluesky accounts some channel follows, by DID: the ones the stream is asked for."""
        sources = await asyncio.to_thread(load_sources)
        followed = await asyncio.to_thread(followed_news_keys)
        return {source.did: source for source in sources.values() if source.did and source.key in followed}

    async def _bluesky_loop(self) -> None:
        while True:
            try:
                accounts = await self._followed_bluesky()
                if not accounts:
                    # nobody to send to, so nothing is missed: note that, or the first follower would be sent days of old posts
                    await asyncio.to_thread(save_jetstream_alive, _now_us())
                    await asyncio.sleep(IDLE_RECHECK)
                    continue
                alive = await asyncio.to_thread(jetstream_alive)
                url = jetstream_url(accounts, alive, _now_us())

                async def changed() -> bool:
                    return set(await self._followed_bluesky()) != set(accounts)
                async with self.session.ws_connect(url, heartbeat=30) as socket:
                    logger.info("news: connected to Jetstream for %d account(s)%s", len(accounts),
                                f", asking for what it missed since {int((_now_us() - alive) / 1e6)}s ago" if alive else "")
                    await self.read(socket, accounts, changed)
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                logger.info("news: Jetstream dropped (%s)", type(error).__name__)
            except Exception:
                logger.exception("news: Jetstream failed")
            await asyncio.sleep(5)

    async def read(self, socket: Any, accounts: Dict[str, Source], changed: Optional[Callable[[], Awaitable[bool]]] = None) -> None:
        """Handle a connection's messages until it closes, noting every minute how far it has been received.

        A reconnect first replays the gap, oldest first. Until that has had time to arrive, the mark is the newest event
        received rather than the clock, or a drop part way through the replay would lose the rest of the gap.
        It also returns when ``changed`` says the accounts to follow are no longer these: the stream is asked for a set of
        accounts when it opens, so a channel following a new one means opening it again, from the mark just noted.
        """
        connected = noted = time.monotonic()
        newest = 0
        while True:
            try:
                message = await socket.receive(timeout=ALIVE_EVERY)
            except asyncio.TimeoutError:
                message = None          # a quiet stretch: the account posts rarely, and that is the usual case
            data: Any = None
            if message is not None and message.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(message.data)
                    newest = max(newest, int(data.get("time_us") or 0))
                except (ValueError, TypeError, AttributeError):
                    pass
            if time.monotonic() - noted >= ALIVE_EVERY:
                mark = _now_us() - ALIVE_LAG if time.monotonic() - connected >= REPLAY_DONE else newest
                if mark:
                    await asyncio.to_thread(save_jetstream_alive, mark)
                noted = time.monotonic()
                if changed is not None and await changed():
                    return
            if message is None:
                continue
            if message.type == aiohttp.WSMsgType.TEXT:
                if isinstance(data, dict):
                    self.spawn(self._event(data, accounts))
            elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                return

    async def _event(self, data: Dict[str, Any], accounts: Dict[str, Source]) -> None:
        try:
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
        """``_bluesky_post``, once per post at a time.

        A post is only recorded as seen when it is sent, which is after the wait for its thread. A reconnect asks the stream
        for a little before where it left off, so the same post can arrive again during that wait: it would pass the seen
        check and be sent twice.
        """
        if uri in self._inflight:
            return 0
        if source.key not in SOURCES and self._queued.get(source.key, 0) >= CATCH_UP:
            # an added account posting faster than posts are built would hold up everyone's, the maimai news too, until too old to send
            await asyncio.to_thread(news_mark_seen, source.key, [uri])
            return 0
        self._inflight.add(uri)
        self._queued[source.key] = self._queued.get(source.key, 0) + 1
        try:
            return await self._bluesky_post(source, record, uri, wait)
        finally:
            self._inflight.discard(uri)
            self._queued[source.key] -= 1

    async def _bluesky_post(self, source: Source, record: Dict[str, Any], uri: str, wait: bool) -> int:
        """Send a new post if it is one to send and nobody has seen it; returns how many channels got it.

        A post is sent unless the account covers other games too, as Preformai International does with CHUNITHM: then only
        its posts about maimai are. The account answering itself is sent as well, since that is how it corrects or continues
        a post, even when the answer never says maimai, provided what it answers was sent. An answer to somebody else is not sent.
        """
        updating = not source.maimai_only or news.is_maimai(str(record.get("text", "")))
        reply = record.get("reply") or {}
        if reply:
            if str((reply.get("parent") or {}).get("uri", "")).split("/")[2:3] != [source.did]:
                return 0            # an answer to somebody else
            root = str((reply.get("root") or {}).get("uri", ""))
            if root in self._inflight or str((reply.get("parent") or {}).get("uri", "")) in self._inflight:
                return 0            # a post above it in the thread is still waiting for its replies, and will carry this one
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
        # every post waits the same, so they reach the lock in the order they arrived, and it lets them through in that order;
        # the build is held too, since that is the slow part: a video post fetches its video, and a text post after it would overtake
        async with self._bluesky_turn:
            if not await self._first_copy(source, str(record.get("text", ""))):
                await asyncio.to_thread(news_mark_seen, source.key, [uri])
                return 0
            post, uris = await news.build_bluesky_post(self.session, source, record, uri)
            await asyncio.to_thread(news_mark_seen, source.key, uris)
            return await self.publish(post)

    # ------------------------------------------------------------ X

    async def _x_loop(self) -> None:
        try:
            await asyncio.to_thread(remove_unknown_news_sources, SOURCES)       # a source taken out of the bot leaves its rows behind
        except Exception:
            logger.exception("news: old subscriptions could not be cleared")
        # sources read last round; at the start, every X account followed, so what was missed while the bot was down is caught up.
        # The X side of a Bluesky account only learns then: the Bluesky stream itself replays what was missed
        keys = await asyncio.to_thread(followed_news_keys)
        followed = {source.key for source in (await asyncio.to_thread(load_sources)).values() if source.platform == "X" and source.key in keys}
        turn = asyncio.Semaphore(X_AT_ONCE)
        while True:
            sources = await asyncio.to_thread(load_sources)
            wanted = await asyncio.to_thread(followed_news_keys)
            feeds = [source for source in sources.values() if source.key in wanted and source.platform == "X"] + \
                    [news.x_side(source) for source in sources.values() if source.key in wanted and source.platform != "X" and source.x_handle]
            polled: Set[str] = set()

            async def read(source: Source) -> None:
                async with turn:
                    try:
                        # an account followed again after nobody did only learns: its posts in the meantime are not news to anyone
                        await self.poll(source, learn=source.key not in followed)
                        polled.add(source.key)
                    except Exception:
                        logger.exception("news: reading %s failed", source.handle)
            await asyncio.gather(*(read(source) for source in feeds))
            followed = (followed & wanted) | polled
            await asyncio.sleep(POLL_EVERY)

    async def poll(self, source: Source, learn: bool = False) -> int:
        """Send the posts of an X account that nobody has seen.

        The very first look sends none: it only learns what is already there. So does one with ``learn``.
        """
        # an added account gone private or suspended is empty on every instance, so it is not worth trying all of them each round
        items, avatar = await news.fetch_feed(self.session, source.handle, len(news.RSS_INSTANCES) if source.key in SOURCES else news.LOOKUP_TRIES)
        items = [item for item in news.own_posts(items, source) if not source.maimai_only or news.is_maimai(item.text)]
        if not items:
            return 0
        first = learn or not await asyncio.to_thread(news_seen_any, source.key)
        unseen = await asyncio.to_thread(news_unseen, source.key, [item.id for item in items])
        if first:
            await asyncio.to_thread(news_mark_seen, source.key, [item.id for item in items])
            return 0
        cutoff = time.time() - MAX_AGE
        stale = [item.id for item in items if item.id in unseen and (news.tweet_time(item.id) or 0) < cutoff]
        if stale:
            await asyncio.to_thread(news_mark_seen, source.key, stale)
        pending = [item for item in reversed(items) if item.id in unseen and item.id not in stale]       # oldest first
        older, pending = pending[:-CATCH_UP], pending[-CATCH_UP:]
        if older:
            await asyncio.to_thread(news_mark_seen, source.key, [item.id for item in older])
        sent = 0
        for item in pending:
            if await self._first_copy(source, item.text):
                await self.publish(await news.build_x_post(self.session, source, item, avatar))
                sent += 1
            await asyncio.to_thread(news_mark_seen, source.key, [item.id])
        return sent

    async def _first_copy(self, source: Source, text: str) -> bool:
        """Whether to send this post: always, unless the account posts on both sites and its copy on the other one went first.

        Only the other site's copies count, so the account saying the same thing twice on one site still sends both. Older than
        MAX_AGE they do not count either: a post that old is not sent, so it cannot be the copy of one being sent now.
        """
        mark = news.copy_mark(text) if source.x_handle else ""
        if not mark:
            return True
        other = "Bluesky" if source.platform == "X" else "X"
        async with self._copy_turn:
            if await asyncio.to_thread(news_copy_seen, source.key, f"{mark}:{other}", MAX_AGE):
                return False
            await asyncio.to_thread(news_copy_sent, source.key, f"{mark}:{source.platform}")
            return True

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
        """Send a post to every channel following its source; returns how many it reached. A post older than MAX_AGE is not sent."""
        if post.posted_at and post.posted_at < time.time() - MAX_AGE:
            return 0
        subscribers: List[Tuple[str, str]] = await asyncio.to_thread(news_subscribers, post.source)
        if not subscribers:
            return 0
        files = await self._files(post)
        unfurl = sum(len(data) for _name, data in files) * len(subscribers) > UPLOAD_BUDGET
        if unfurl:
            files = []          # an 8 MB video to hundreds of channels is gigabytes uploaded for one post
        gate = asyncio.Semaphore(SEND_AT_ONCE)

        async def one(channel_id: str, url: str) -> Optional[bool]:
            async with gate:
                return await self._deliver(channel_id, url, post, files, unfurl)

        async def every(channels: List[Tuple[str, str]]) -> List[Any]:
            # one send going wrong in a way nobody foresaw must not stop the rest, or the post would be sent to them all again
            results = await asyncio.gather(*(one(channel_id, url) for channel_id, url in channels), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    logger.warning("news: a webhook send failed unexpectedly with %s", type(result).__name__)
            return results
        results = await every(subscribers)
        # a dropped connection, a timeout or Discord's own trouble is usually over by now, so those channels get one more try
        again = [channel for channel, result in zip(subscribers, results) if result is None]
        if again:
            results += await every(again)
        return sum(result is True for result in results)

    async def history(self, channel_id: str, url: str, keys: List[str], count: int) -> int:
        """Send one channel the latest ``count`` posts of each of these sources, oldest first, and nobody else. Returns how many arrived.

        Nothing here is recorded as seen: these are old posts being shown, not new ones being handled, so live sending is unaffected.
        """
        async with self._history_turn:          # many servers asking at once would crowd out the posts being sent live
            sent = 0
            for key in keys:
                source = (await asyncio.to_thread(load_sources)).get(key)
                if source is None:
                    continue
                try:
                    posts = await news.recent_posts(self.session, source, count)
                except Exception:
                    logger.exception("news: the earlier posts of %s could not be read", key)
                    continue
                for post in posts:
                    if not await self._deliver(channel_id, url, post, await self._files(post)):
                        return sent             # the webhook is gone, refused or not answering: the rest would go the same way
                    sent += 1
            return sent

    async def _deliver(self, channel_id: str, url: str, post: Post, files: List[Tuple[str, bytes]], unfurl: bool = False) -> Optional[bool]:
        """Send a post to one channel: True when it arrived, None when it failed in a way that may pass, False when it will not."""
        try:
            webhook = discord.Webhook.from_url(url, session=self.session)
        except ValueError:
            await asyncio.to_thread(remove_channel_webhook, channel_id, url)
            return False
        for attach in ([True, False] if files else [False]):
            # without its pictures or video the post would show no media at all, so then the link is left to draw its preview
            options: Dict[str, Any] = {"content": post.content(unfurl=unfurl or (bool(files) and not attach)), "username": post.username,
                                       "allowed_mentions": NO_MENTIONS}
            if post.avatar:
                options["avatar_url"] = post.avatar
            buffers = [io.BytesIO(data) for _name, data in files] if attach else []
            if attach:
                options["files"] = [discord.File(buffer, filename=name) for buffer, (name, _data) in zip(buffers, files)]
            try:
                await asyncio.wait_for(webhook.send(**options), SEND_TIMEOUT)
                return True
            except discord.HTTPException as error:
                if error.code in GONE_CODES or (error.status == 403 and error.code):
                    # somebody deleted the webhook or the channel, or took the bot's access: nothing will ever be delivered there again
                    logger.info("news: a channel's webhook is gone, so its subscriptions are removed")
                    await asyncio.to_thread(remove_channel_webhook, channel_id, url)
                    return False
                if attach and error.status == 413:
                    continue            # the attachments were too big for this server; the text and link still go
                logger.warning("news: a webhook send failed with %s, code %s", error.status, error.code)
                # no Discord code means the answer came from in front of Discord, such as Cloudflare, and says nothing about the webhook;
                # a 5xx is not tried again here, as discord.py has already tried it five times over half a minute
                return None if not error.code and error.status < 500 else False
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                # a network failure for one channel must not stop the others, or the post would be sent to them all again
                logger.warning("news: a webhook send failed with %s", type(error).__name__)
                return None
            finally:
                for buffer in buffers:
                    # discord.File keeps its file from closing, and aiohttp leaves a copy of it that only a full collection frees: a video per channel
                    io.BytesIO.close(buffer)
        return False

