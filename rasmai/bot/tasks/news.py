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
    followed_news_keys, jetstream_alive, news_channel_filters, news_copy_seen, news_copy_sent, news_mark_seen, news_seen_any, news_sources, news_subscribers, news_unseen, remove_channel_webhook,
    remove_unknown_news_sources, save_jetstream_alive, news_message_gone, news_sent_messages, news_sent_moved, news_sent_recent, news_sent_root, news_sent_save,
    news_webhook,
)

logger = logging.getLogger(__name__)

POLL_EVERY = 240                    # seconds from one look at an X feed to the next, start to start, so a post is out inside five minutes
POLL_SPREAD = 0.8                   # share of that cycle the looks are spread over, one account after another, instead of every account at once
POLL_GAP_MAX = 30                   # seconds between two accounts' looks at most, so a few accounts are not left waiting out the cycle
IDLE_RECHECK = 60                   # seconds between asking whether anyone follows a Bluesky account, while nobody does
CATCH_UP = 5                        # most posts sent at once after a gap; older ones are marked seen, not sent
BURST_WINDOW = 1800                 # seconds; posts this recent are never cut by CATCH_UP, so a burst of them all goes out even when a Nitter feed lags
X_AT_ONCE = 4                       # X accounts read at the same time, so a dead one cannot hold up the rest, nor all of them crowd a Nitter instance
SEND_AT_ONCE = 10                   # channels a post is being sent to at the same time; webhooks share Discord's ~50 a second global limit, so no more
SEND_TIMEOUT = 30                   # seconds a send may take, Discord's own retries included, before it counts as a failure worth one more try
UPLOAD_BUDGET = 1 << 30             # bytes a post may upload across all its channels; above it, the link draws the media instead of every channel getting a copy
GONE_CODES = (10003, 10015, 50027)  # Discord's Unknown Channel, Unknown Webhook and Invalid Webhook Token
NO_MENTIONS = discord.AllowedMentions.none()      # on every send: whatever a post says, it cannot ping a user, a role, @everyone or @here
GAP_HOPS = 4                        # posts followed up a thread from the account's answer, looking for one that was sent: X's timeline hides the middle of a thread

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
        self._tasks: List[Optional[asyncio.Task]] = [None, None]       # the Bluesky loop and the X loop
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
        loops = (self._bluesky_loop, self._x_loop)
        # on_ready fires again after a reconnect: a loop still running must not double, and one that ended is started again
        stopped = [number for number, task in enumerate(self._tasks) if task is None or task.done()]
        if not stopped:
            return
        if len(stopped) == len(loops):
            logger.info("news: Japanese posts are translated %s",
                        f"by {news.TRANSLATE_MODEL} at {news.TRANSLATE_URL}, with Google Translate as the fallback" if news.TRANSLATE_URL
                        else "by Google Translate only: MAIMAI_TRANSLATE_URL is not set")
        for number in stopped:
            self._tasks[number] = asyncio.create_task(loops[number]())

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
            operation = commit.get("operation")
            if data.get("kind") != "commit" or operation not in ("create", "update"):
                return
            did, rkey, record = commit.get("repo"), commit.get("rkey"), commit.get("record")
            source = accounts.get(did)
            if source is None or not rkey or not isinstance(record, dict):
                return
            # a replayed post is old enough that its thread is complete; a live one is given a moment to finish
            settled = _now_us() - int(data.get("time_us") or _now_us()) > SETTLED
            uri = f"at://{did}/app.bsky.feed.post/{rkey}"
            if operation == "update":
                await self.bluesky_edit(source, uri, wait=not settled)
            else:
                await self.bluesky_post(source, record, uri, wait=not settled)
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
        updating = not await self._only_maimai(source) or news.is_maimai(str(record.get("text", "")))
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
            # the account answering a post that was sent: the answer is added to that message instead of sent on its own
            root = await asyncio.to_thread(news_sent_root, source.key, str((reply.get("parent") or {}).get("uri", ""))) if reply else None
            if root is not None and await self._bluesky_rebuild(source, root, uri) is not None:
                await asyncio.to_thread(news_mark_seen, source.key, [uri])
                return 0
            if not await self._first_copy(source, str(record.get("text", ""))):
                await asyncio.to_thread(news_mark_seen, source.key, [uri])
                return 0
            post, uris = await news.build_bluesky_post(self.session, source, record, uri)
            await asyncio.to_thread(news_mark_seen, source.key, uris)
            return await self.publish(post)

    async def bluesky_edit(self, source: Source, uri: str, wait: bool = True) -> int:
        """Edit what a sent Bluesky post became, after the account edited it or a post in its thread; returns how many were edited."""
        root = await asyncio.to_thread(news_sent_root, source.key, uri)
        if root is None:
            return 0            # never sent, or sent too long ago to follow
        if wait:
            await asyncio.sleep(news.THREAD_WAIT_SECONDS)       # the stream has the edit a moment before the public API serves it
        return await self._bluesky_rebuild(source, root) or 0

    async def _bluesky_rebuild(self, source: Source, root: str, carrying: str = "") -> Optional[int]:
        """Build a sent thread again as it reads now and edit its messages to match; returns how many were edited.

        None when the thread does not show ``carrying`` yet, or would no longer fit the message with it.
        """
        thread, _above = await news.bluesky_thread(self.session, root, source.did)
        if not thread or (carrying and carrying not in {p.get("uri") for p in thread}):
            return None
        post, covers = await news.build_bluesky_post(self.session, source, thread[0].get("record") or {}, root, media=False)
        if carrying and not post.fits():
            return None
        await asyncio.to_thread(news_sent_save, source.key, root, covers, "", [])       # a later edit or answer of any of them finds it
        return await self.revise(source.key, root, post)

    # ------------------------------------------------------------ X

    async def _x_loop(self) -> None:
        try:
            await asyncio.to_thread(remove_unknown_news_sources, SOURCES)       # a source taken out of the bot leaves its rows behind
        except Exception:
            logger.exception("news: old subscriptions could not be cleared")
        # sources read last round; at the start, every X account followed, so what was missed while the bot was down is caught up.
        # The X side of a Bluesky account only learns then: the Bluesky stream itself replays what was missed
        followed: Optional[Set[str]] = None
        turn = asyncio.Semaphore(X_AT_ONCE)
        while True:
            try:
                sources = await asyncio.to_thread(load_sources)
                wanted = await asyncio.to_thread(followed_news_keys)
                if followed is None:
                    followed = {source.key for source in sources.values() if source.platform == "X" and source.key in wanted}
                feeds = [source for source in sources.values() if source.key in wanted and source.platform == "X"] + \
                        [news.x_side(source) for source in sources.values() if source.key in wanted and source.platform != "X" and source.x_handle]
                polled: Set[str] = set()
                learned = followed
                began = time.monotonic()
                gap = min(POLL_GAP_MAX, POLL_EVERY * POLL_SPREAD / max(1, len(feeds)))

                async def read(source: Source, wait: float) -> None:
                    if wait > 0:
                        await asyncio.sleep(wait)       # the feeds are asked one after another across the cycle: a Nitter instance sees a trickle, not a burst
                    async with turn:
                        try:
                            # an account followed again after nobody did only learns: its posts in the meantime are not news to anyone
                            await self.poll(source, learn=source.key not in learned)
                            polled.add(source.key)
                        except Exception:
                            logger.exception("news: reading %s failed", source.handle)
                await asyncio.gather(*(read(source, number * gap) for number, source in enumerate(feeds)))
                followed = (followed & wanted) | polled
            except Exception:
                # a locked database must cost one round, not the loop: nothing else would start it again
                logger.exception("news: a round of reading X failed")
                began = time.monotonic()
            await asyncio.sleep(max(min(5.0, POLL_EVERY / 10), POLL_EVERY - (time.monotonic() - began)))

    async def poll(self, source: Source, learn: bool = False) -> int:
        """Send the posts of an X account that nobody has seen.

        The very first look sends none: it only learns what is already there. So does one with ``learn``.
        """
        # an added account gone private or suspended is empty on every instance, so it is not worth trying all of them each round
        items, avatar = await news.fetch_feed(self.session, source.handle, len(news.RSS_INSTANCES) if source.key in SOURCES else news.LOOKUP_TRIES)
        showing = {item.id for item in items}
        only = await self._only_maimai(source)
        items = [item for item in news.own_posts(items, source) if not only or news.is_maimai(item.text)]
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
        # the cap is for a gap, the bot down or the feeds unreadable: posts made minutes apart, as a tournament's announcements are, all go out
        recent = time.time() - BURST_WINDOW
        older = [item for item in pending[:-CATCH_UP] if (news.tweet_time(item.id) or 0) < recent]
        pending = [item for item in pending if item not in older]
        if older:
            await asyncio.to_thread(news_mark_seen, source.key, [item.id for item in older])
        sent = 0
        earlier = await asyncio.to_thread(news_sent_recent, source.key) if pending else []
        for item in pending:
            edit = news.edit_of(item.id, item.text, earlier, showing)
            if edit is not None:
                await self.x_edit(source, item, avatar, *edit, items)
                earlier = [row for row in earlier if row[0] != edit[0]]
            elif item.reply_to and await self.x_fold(source, item, avatar, items):
                pass
            elif await self._first_copy(source, item.text):
                await self.publish(await news.build_x_post(self.session, source, item, avatar))
                sent += 1
            await asyncio.to_thread(news_mark_seen, source.key, [item.id])
        return sent

    async def x_edit(self, source: Source, item: news.FeedItem, avatar: str, earlier: str, root: str, items: List[news.FeedItem]) -> int:
        """Edit what a sent X post became into its edited version, which X gave a new id; returns how many were edited."""
        await asyncio.to_thread(news_sent_moved, source.key, earlier, item.id, item.text)
        # with the answers already added to it, while the feed still shows them all; otherwise the edited post alone
        post = await self._x_whole(source, root, items, avatar)
        if post is None:
            post = await news.build_x_post(self.session, source, item, avatar, media=False)
            post.posted_at = news.tweet_time(root) or post.posted_at       # still dated when it was first posted, as X shows it
        return await self.revise(source.key, root, post)

    async def x_fold(self, source: Source, item: news.FeedItem, avatar: str, items: List[news.FeedItem]) -> bool:
        """Add the account's answer to its own sent post to the message that post became; False when it goes out as a post of its own.

        The feed shows a thread's first and last posts and hides the middle, so the answer's parent may never have been seen: the
        thread is followed up a few posts for one that was sent, and the posts between, which the feed never showed, come from the
        syndication endpoint's text and are recorded under the root so they are never sent on their own if they turn up later.
        """
        root, between, post_id = None, [], item.id     # between: (id, text) of the posts above the answer that were not sent, nearest first
        for _ in range(GAP_HOPS):
            above = await news.syndication_above(self.session, post_id, source.handle)
            root = await asyncio.to_thread(news_sent_root, source.key, above[0]) if above else None
            if above is None or root is not None:
                break
            between.append(above)
            post_id = above[0]
        if root is None:
            return False
        post = await self._x_whole(source, root, items, avatar, item.id, dict(between))
        if post is None:
            return False
        for each, text in [(item.id, item.text), *between]:
            await asyncio.to_thread(news_sent_save, source.key, root, [each], text, [])
        await asyncio.to_thread(news_mark_seen, source.key, [each for each, _text in between])
        await self.revise(source.key, root, post)
        return True

    async def _x_whole(self, source: Source, root: str, items: List[news.FeedItem], avatar: str, adding: str = "",
                       texts: Optional[Dict[str, str]] = None) -> Optional[Post]:
        """A sent X post and the account's answers to it as one message, oldest first, each an embed: from the feed, or for a post
        the feed no longer shows, from ``texts`` or the syndication endpoint, without its media.

        None when one of them cannot be read from anywhere, or ``adding`` would no longer fit the message.
        """
        covered = [post_id for post_id, under, _body in await asyncio.to_thread(news_sent_recent, source.key) if under == root]
        found = {item.id: item for item in items}
        texts = texts or {}
        ids = sorted({*covered, *texts, *([adding] if adding else [])}, key=int)
        if not ids:
            return None
        posts = []
        for i in ids:
            if i not in found:
                words = texts.get(i)
                if words is None:
                    tweet = await news.syndication_tweet(self.session, i, source.handle)
                    if tweet is None:
                        return None
                    words = news.syndication_text(tweet)
                found[i] = news.FeedItem(i, words, f"https://x.com/{source.handle}/status/{i}", "", False, source.handle)
            posts.append(await news.build_x_post(self.session, source, found[i], avatar, media=False))
        whole = posts[0]
        whole.thread = posts[1:]
        whole.posted_at = news.tweet_time(root) or whole.posted_at       # still dated when it was first posted, as X shows it
        if adding and not whole.fits():
            return None
        return whole

    async def _only_maimai(self, source: Source) -> bool:
        """Whether every channel following an account gets only its posts about maimai, so nothing else of it is worth reading."""
        filters = await asyncio.to_thread(news_channel_filters, source.key)
        return bool(filters) and all(filters.values())

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
        """Send a post to every channel following its source; returns how many it reached. A post older than MAX_AGE is not sent.

        Each message is kept under the post and every post it covers (its thread), so an edit of any of them can follow.
        """
        if post.posted_at and post.posted_at < time.time() - MAX_AGE:
            return 0
        subscribers: List[Tuple[str, str]] = await asyncio.to_thread(news_subscribers, post.source)
        if not post.about_maimai:
            filters = await asyncio.to_thread(news_channel_filters, post.source)
            subscribers = [(channel_id, url) for channel_id, url in subscribers if not filters.get(channel_id)]
        if not subscribers:
            return 0
        files = await self._files(post)
        unfurl = sum(len(data) for _name, data in files) * len(subscribers) > UPLOAD_BUDGET
        if unfurl:
            files = []          # an 8 MB video to hundreds of channels is gigabytes uploaded for one post
        gate = asyncio.Semaphore(SEND_AT_ONCE)
        kept: List[Tuple[str, str, bool]] = []

        async def one(channel_id: str, url: str) -> Optional[bool]:
            async with gate:
                return await self._deliver(channel_id, url, post, files, unfurl, kept)

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
        if kept:
            try:
                await asyncio.to_thread(news_sent_save, post.source, post.id, post.covers or [post.id], post.parts[-1] if post.parts else "", kept)
            except Exception:
                logger.exception("news: the messages a post became could not be kept, so its edits will not follow")
        return sum(result is True for result in results)

    async def revise(self, source: str, root: str, post: Post) -> int:
        """Edit every message a sent post became to say what it says now; returns how many were edited.

        shortcut: only the embeds change, its pictures and video stay the message's attachments as sent, outside the embeds, which is
        what lets an edit leave them be; re-upload them if edits that swap media turn up.
        """
        messages = await asyncio.to_thread(news_sent_messages, source, root)
        post.wanted_video = False       # whether the link draws its preview was settled when it was sent, and is kept with each message
        gate = asyncio.Semaphore(SEND_AT_ONCE)

        async def one(channel_id: str, message_id: str, unfurl: bool) -> bool:
            url = await asyncio.to_thread(news_webhook, channel_id)
            if not url:
                return False
            async with gate:
                try:
                    webhook = discord.Webhook.from_url(url, session=self.session)
                    await asyncio.wait_for(webhook.edit_message(int(message_id), content=post.link(unfurl), embeds=post.embeds(), allowed_mentions=NO_MENTIONS),
                                           SEND_TIMEOUT)
                    return True
                except (discord.NotFound, ValueError):
                    # the message was deleted, or the channel's webhook replaced since: there is nothing there to edit any more
                    await asyncio.to_thread(news_message_gone, channel_id, message_id)
                except (discord.HTTPException, aiohttp.ClientError, asyncio.TimeoutError) as error:
                    logger.warning("news: an edit failed with %s", type(error).__name__)
                return False
        results = await asyncio.gather(*(one(*message) for message in messages), return_exceptions=True)
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
                    only = (await asyncio.to_thread(news_channel_filters, key)).get(channel_id)
                    posts = await news.recent_posts(self.session, source, count, only)
                except Exception:
                    logger.exception("news: the earlier posts of %s could not be read", key)
                    continue
                for post in posts:
                    if not await self._deliver(channel_id, url, post, await self._files(post)):
                        return sent             # the webhook is gone, refused or not answering: the rest would go the same way
                    sent += 1
            return sent

    async def _deliver(self, channel_id: str, url: str, post: Post, files: List[Tuple[str, bytes]], unfurl: bool = False,
                       kept: Optional[List[Tuple[str, str, bool]]] = None) -> Optional[bool]:
        """Send a post to one channel: True when it arrived, None when it failed in a way that may pass, False when it will not.

        What arrived is added to ``kept`` as ``(channel, message, whether its link draws the preview)``.
        """
        try:
            webhook = discord.Webhook.from_url(url, session=self.session)
        except ValueError:
            await asyncio.to_thread(remove_channel_webhook, channel_id, url)
            return False
        for attach in ([True, False] if files else [False]):
            # without its pictures or video the post would show no media at all, so then the link is left to draw its preview
            unfurled = unfurl or (bool(files) and not attach)
            options: Dict[str, Any] = {"content": post.link(unfurled), "embeds": post.embeds(), "username": post.username, "allowed_mentions": NO_MENTIONS}
            if post.avatar:
                options["avatar_url"] = post.avatar
            buffers = [io.BytesIO(data) for _name, data in files] if attach else []
            if attach:
                options["files"] = [discord.File(buffer, filename=name) for buffer, (name, _data) in zip(buffers, files)]
            try:
                message = await asyncio.wait_for(webhook.send(**options, wait=True), SEND_TIMEOUT)
                if kept is not None and message is not None:
                    kept.append((channel_id, str(message.id), unfurled or (post.wanted_video and not post.videos)))
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

