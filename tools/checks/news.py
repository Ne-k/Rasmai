from contextlib import contextmanager
import asyncio
import logging
import pathlib
import tempfile
import time

from tools.checks import check

URL = "https://discord.com/api/webhooks/123456789012345678/SECRETTOKEN-abcdefghijklmnopqrstuvwxyz"


@contextmanager
def _no_session():
    """The watch makes its HTTP session on first use, and a check has no loop to keep one in: nothing here sends over a real one."""
    from rasmai.bot.tasks.news import NewsWatch
    kept = NewsWatch.session
    NewsWatch.session = property(lambda self: None)
    try:
        yield
    finally:
        NewsWatch.session = kept


@contextmanager
def _scratch():
    from rasmai.storage.db import connection as store
    was = store.DATABASE_PATH
    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "news.sqlite3", False
    try:
        yield store
    finally:
        store.DATABASE_PATH, store._database_ready = was, False


@check("a webhook URL is sealed in the database, opens only for its own channel, and a restart sends nothing twice")
def _storage():
    from rasmai.storage import db
    from rasmai.storage.db import news as news_db

    problems = []
    with _scratch() as store:
        db.add_news_subscription("g1", "c1", "maimai", URL)
        db.add_news_subscription("g1", "c1", "laundromai", URL)
        db.add_news_subscription("g2", "c2", "maimai", URL + "2")
        raw = pathlib.Path(store.DATABASE_PATH).read_bytes()
        if b"SECRETTOKEN" in raw or b"discord.com/api/webhooks" in raw:
            problems.append("a webhook URL is readable in the database file")
        connection = db.get_database_connection()
        stored = [row["webhook"] for row in connection.execute("SELECT webhook FROM news_subscriptions")]
        connection.close()
        if any(URL in value or "SECRETTOKEN" in value for value in stored) or len(set(stored)) != len(stored):
            problems.append("a stored webhook is plain text, or two rows were sealed the same")
        if sorted(db.news_subscribers("maimai")) != [("c1", URL), ("c2", URL + "2")] or db.news_subscribers("laundromai") != [("c1", URL)]:
            problems.append(f"subscribers came back as {db.news_subscribers('maimai')}")
        if db.news_webhook("c1") != URL or db.news_webhook("nowhere") is not None:
            problems.append("a channel's webhook did not come back, or an unknown channel had one")
        if db.channel_sources("c1") != ["laundromai", "maimai"] or db.news_subscription_count("g1") != 2:
            problems.append("the channel's sources or the server's count is wrong")
        # a row copied to another channel must not open there
        connection = db.get_database_connection()
        with connection:
            connection.execute("UPDATE news_subscriptions SET channel_id = 'c3' WHERE channel_id = 'c2'")
        connection.close()
        if db.news_subscribers("maimai") != [("c1", URL)] or db.news_webhook("c3") is not None:
            problems.append("a webhook sealed for one channel opened under another")
        db.replace_channel_webhook("c1", URL + "new")
        if db.news_webhook("c1") != URL + "new" or db.news_subscribers("laundromai") != [("c1", URL + "new")]:
            problems.append("replacing a channel's webhook did not reach every source in it")
        if db.remove_news_subscription("c1", "maimai") != 1 or db.channel_sources("c1") != ["laundromai"]:
            problems.append("removing one source took the wrong rows")
        if db.remove_news_subscription("c1") != 1 or db.remove_guild_news("g2") != 1 or db.news_subscription_count("g1") != 0:
            problems.append("removing a channel, or a server, left rows behind")

        if db.news_seen_any("maimai") or db.news_unseen("maimai", ["1", "2", ""]) != {"1", "2"}:
            problems.append("an empty source claimed to have seen posts")
        db.news_mark_seen("maimai", ["1", "2"])
        if not db.news_seen_any("maimai") or db.news_seen_any("laundromai") or db.news_unseen("maimai", ["1", "2", "3"]) != {"3"}:
            problems.append("seen posts were not remembered per source")
        was = news_db.SEEN_KEPT
        news_db.SEEN_KEPT = 3
        try:
            db.news_mark_seen("maimai", ["3", "4", "5", "6"])
            kept = db.news_unseen("maimai", ["1", "2", "3", "4", "5", "6"])
        finally:
            news_db.SEEN_KEPT = was
        if kept != {"1", "2", "3"}:
            problems.append(f"the oldest records were not the ones dropped: unseen {sorted(kept)}")
    return problems


@check("posts are filtered, stripped of pings and read from feeds, and the bot only ever fetches from trusted https hosts")
def _reading():
    import aiohttp
    from rasmai.scraping import news

    problems = []
    clean = news.sanitize("@everyone <@123> <@&9> <#7> @here hi")
    if "@everyone" in clean or "<@" in clean or "<#" in clean or "@here" in clean:
        problems.append(f"a ping survived: {clean!r}")

    feed = b"""<rss><channel><image><url>https://pbs.twimg.com/profile_images/1/a.png</url></image>
      <item><title>RT by someone</title><link>https://n/x/status/3#m</link><description></description></item>
      <item><title>new song</title><link>https://n/maimai_official/status/2#m</link><description>&lt;img src="https://pbs.twimg.com/m.jpg"&gt;&lt;img src="/pic/a"&gt;</description></item>
      <item><title>\xe3\x83\xaa\xe3\x83\x84\xe3\x82\xa4\xe3\x83\xbc\xe3\x83\x88 x</title><link>https://n/x/status/1#m</link><description></description></item></channel></rss>"""
    items, avatar = news.parse_feed(feed)
    if [(i.id, i.retweet) for i in items] != [("3", True), ("2", False), ("1", True)] or avatar != "https://pbs.twimg.com/profile_images/1/a.png":
        problems.append(f"the feed read as {[(i.id, i.retweet) for i in items]}, {avatar!r}")
    # a relative /pic/ address is the instance's own proxy of a twimg.com picture, so it is read as that
    if news.media_urls(items[1].description) != ["https://pbs.twimg.com/m.jpg", "https://pbs.twimg.com/a"]:
        problems.append(f"the pictures read as {news.media_urls(items[1].description)}")
    if news.parse_feed(b"not xml") != ([], ""):
        problems.append("something that is not a feed gave items")

    record = {"embed": {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": "bafyA"}}}, {"image": {"ref": {"$link": "bafyB"}}}]}}
    images, videos = news.bluesky_media(record, "did:plc:x")
    if images != [f"{news.IMG_CDN}/did:plc:x/bafyA", f"{news.IMG_CDN}/did:plc:x/bafyB"] or videos:
        problems.append(f"Bluesky pictures read as {images}")
    _images, videos = news.bluesky_media({"embed": {"$type": "app.bsky.embed.video", "video": {"ref": {"$link": "bafyV"}}}}, "did:plc:x")
    if videos != [f"{news.VID_CDN}/did%3Aplc%3Ax/bafyV/playlist.m3u8"]:
        problems.append(f"a Bluesky video read as {videos}")

    for url, ok in (("https://cdn.bsky.app/a.jpg", True), ("https://pbs.twimg.com/a.jpg", True), ("https://video.twimg.com/a.mp4", True),
                    ("http://cdn.bsky.app/a.jpg", False), ("https://127.0.0.1/a", False), ("https://169.254.169.254/latest", False),
                    ("https://evil.example/a.jpg", False), ("https://cdn.bsky.app.evil.example/a", False), ("file:///etc/passwd", False)):
        if news.trusted(url) != ok:
            problems.append(f"{url} trusted={news.trusted(url)}, expected {ok}")

    async def untrusted():
        async with aiohttp.ClientSession() as session:
            return await news.fetch_bytes(session, "https://127.0.0.1:1/x"), await news.fetch_bytes(session, "http://localhost/x")
    if asyncio.run(untrusted()) != (None, None):
        problems.append("a file was fetched from an address that is not trusted")

    post = news.Post("maimai", "1", "https://x.com/maimai_official/status/1", "Maimai Official", parts=["a" * 3000])
    text = post.content()
    if len(text) > 2000 or not text.endswith("<https://x.com/maimai_official/status/1>\n\n---"):
        problems.append("a long post is over Discord's limit or its link is not held back from unfurling")
    post = news.Post("maimai", "1", "https://x.com/m/status/1", "n", parts=["t"], wanted_video=True)
    if "<https" in post.content():
        problems.append("a post whose video could not be attached still hid its link")
    post.videos.append(b"v")
    if "<https" not in post.content():
        problems.append("a post with its video attached left its link to unfurl")
    return problems


@check("the account answering itself is sent with a quote of what it answers, an answer to anybody else is not, the feed's own order is not trusted, and a post already in two languages is not translated again")
def _followups():
    from rasmai.scraping import news

    problems = []
    source = news.SOURCES["maimai"]
    me, someone = source.handle, "somebody"

    def item(n, title, author=me, retweet=False):
        reply = title.split(":")[0][len("R to @"):] if title.startswith("R to @") else ""
        return news.FeedItem(str(n), title, f"https://n/{author}/status/{n}#m", "", retweet, author, reply)
    feed = [item(30, "own post"), item(40, f"R to @{me}: the fix"), item(50, f"R to @{someone}: hello"), item(10, "older own post"),
            item(60, f"RT by @{me}: theirs", author=someone, retweet=True), item(70, "quoted elsewhere", author=someone), item(20, f"R to @{me.upper()}: shouting")]
    if [i.id for i in news.own_posts(feed, source)] != ["40", "30", "20", "10"]:
        problems.append(f"the account's own posts came out as {[i.id for i in news.own_posts(feed, source)]}: replies to itself in, retweets, others' pages and replies to others out, newest first by id")
    if feed[1].text != "the fix" or feed[0].text != "own post":
        problems.append("the reply marker was not taken off the text")
    xml = (b'<rss><channel><item><title>R to @maimai_official: x</title><link>https://n/maimai_official/status/5#m</link></item>'
           b'<item><title>RT by @maimai_official: y</title><link>https://n/other/status/6#m</link></item></channel></rss>')
    parsed, _ = news.parse_feed(xml)
    if [(i.author, i.reply_to) for i in parsed] != [("maimai_official", "maimai_official"), ("other", "")]:
        problems.append(f"the feed gave author and reply as {[(i.author, i.reply_to) for i in parsed]}")

    for written, both in (("新曲定数です! Here's the constants for the new songs! #maimai", True), ("Sorry, I forgot to post level 8+!", True),
                          ("【WEC2026決勝楽曲が登場！】「WEC2026」maimai でらっくす（舞萌 DX）部門 最終決勝戦の課題曲に、世界最速公開の新曲が登場！ Music：igel Movie：いそにん https://x.co/a", False),
                          # KOP's posts name the event in English, which is not English of their own
                          ("『KING of Performai The 8th』 maimai でらっくすのオンライン予選課題曲はコチラ！ WEC2026でお披露目された新曲「魔法仕掛けのファンタジア」が課題曲として登場！", False),
                          ("ADVANCED Lv.6の定数の修正です。 Fix for ADVANCED Lv.6 constants: Energy: 6.4 → 6.3", True),
                          # an English sign-off on a Japanese post, and a name about as long as the Japanese around it
                          ("【KOP7th ダイジェストムービー】『KING of Performai The 7th』全国決勝大会の模様を収めた、特別なダイジェストムービーを公開！！ 会場や配信で応援してくださった皆さま、ありがとうございました！ See you next time", False),
                          ("KING of Performai The 8th、本日より国内版エントリー開始です！", False),
                          ("#maimai #WEC2026 @maimai_official 新曲", False)):
        if news.has_english(written) != both:
            problems.append(f"{written!r} said to have its own English: {news.has_english(written)}")

    translated = []

    async def fake_translate(session, written):
        translated.append(written)
        return "English"

    async def fake_json(session, url, params=None):
        parent = {"id_str": "99", "text": "first &amp; line\nsecond line " + "x" * 200, "user": {"screen_name": parent_author["name"]}}
        return {"parent": parent}
    parent_author = {"name": me}
    kept = news.translate, news._get_json
    news.translate, news._get_json = fake_translate, fake_json
    try:
        async def build(entry):
            return await news.build_x_post(None, source, entry, "https://av/a.png")
        both = asyncio.run(build(item(41, f"R to @{me}: 新曲です! Here is the fix for the constants of two songs")))
        if translated or both.parts != ["新曲です! Here is the fix for the constants of two songs"] or both.follow_up is None:
            problems.append(f"a post already in two languages was translated, or kept its reply marker: {both.parts}, translated {translated}")
        only = asyncio.run(build(item(42, "新曲です")))
        if translated != ["新曲です"] or only.parts != ["English", "新曲です"] or only.follow_up is not None:
            problems.append(f"a Japanese-only post came out as {only.parts}")
        if both.follow_up[0] != f"https://x.com/{me}/status/99" or not both.follow_up[1].startswith("first & line second line") or len(both.follow_up[1]) > 140 or "\n" in both.follow_up[1]:
            problems.append(f"the earlier post was quoted as {both.follow_up}")
        shown = both.content()
        if not shown.startswith(news.FOLLOW_UP_MARK + f" **Follow-up to [their earlier post](<https://x.com/{me}/status/99>)**\n> first & line"):
            problems.append(f"the follow-up reads {shown!r}")
        parent_author["name"] = someone
        elsewhere = asyncio.run(build(item(43, f"R to @{me}: odd")))
        if elsewhere.follow_up != ("", "") or "their earlier post**\n" not in elsewhere.content() or "[" in elsewhere.content().split("\n")[0]:
            problems.append("an answer whose parent could not be shown as the account's own was not given the plain header")
    finally:
        news.translate, news._get_json = kept

    # Bluesky: the post above comes from the thread, and only the account's own is quoted
    did = news.SOURCES["preformai"].did
    bsky = news.SOURCES["preformai"]
    above = {"uri": f"at://{did}/app.bsky.feed.post/abc", "author": {"did": did}, "record": {"text": "the update"}}
    mine = {"uri": f"at://{did}/app.bsky.feed.post/def", "author": {"did": did}, "record": {"text": "Fix: 6.4 to 6.3", "reply": {"parent": {"uri": above["uri"]}},
                                                                                         "createdAt": "2026-10-01T00:00:00Z"}}

    async def fake_thread(session, uri, owner):
        return [mine], above

    async def fake_avatar(session, handle):
        return ""
    kept_thread, kept_avatar = news.bluesky_thread, news.bluesky_avatar
    news.bluesky_thread, news.bluesky_avatar = fake_thread, fake_avatar
    try:
        built, uris = asyncio.run(news.build_bluesky_post(None, bsky, mine["record"], mine["uri"]))
        if built.follow_up != (f"https://bsky.app/profile/{bsky.handle}/post/abc", "the update") or uris != [mine["uri"]]:
            problems.append(f"a Bluesky follow-up quoted {built.follow_up}")
        alone, _ = asyncio.run(news.build_bluesky_post(None, bsky, {"text": "plain"}, mine["uri"]))
        if alone.follow_up is not None:
            problems.append("a post that answers nothing was given a follow-up header")
    finally:
        news.bluesky_thread, news.bluesky_avatar = kept_thread, kept_avatar

    # Google's free endpoint throttles: one refusal pauses it, and the post goes out as written
    calls = []

    class Throttled:
        def get(self, url, **kwargs):
            calls.append(url)

            class Response:
                status = 429

                async def __aenter__(inner):
                    return inner

                async def __aexit__(inner, *exc):
                    return False
            return Response()
    kept_pause, kept_url = news._translate_paused_until, news.TRANSLATE_URL
    news._translate_paused_until, news.TRANSLATE_URL = 0.0, ""
    try:
        if asyncio.run(news.translate(Throttled(), "新曲です")) != "新曲です" or asyncio.run(news.translate(Throttled(), "新曲です")) != "新曲です" or len(calls) != 1:
            problems.append(f"a throttled translation asked {len(calls)} times, not once and then paused")
    finally:
        news._translate_paused_until, news.TRANSLATE_URL = kept_pause, kept_url
        news._translated.clear()
    return problems


@check("a Japanese post is translated by the local model with Google's own prompt, one at a time and kept, and anything wrong with the model falls back to Google and then to the post as written")
def _translation():
    import aiohttp
    from aiohttp import web
    from rasmai.scraping import news

    problems = []
    seen, state = [], {"mode": "ok", "busy": 0, "most": 0}

    async def chat(request):
        body = await request.json()
        seen.append(body)
        state["busy"] += 1
        state["most"] = max(state["most"], state["busy"])
        await asyncio.sleep(0.05)
        state["busy"] -= 1
        if state["mode"] == "missing":
            return web.json_response({"error": "model not found"}, status=404)
        said = {"ok": "The final song is out!", "runaway": "x" * 5000, "japanese": "新曲が登場しました", "empty": "  "}[state["mode"]]
        return web.json_response({"message": {"role": "assistant", "content": said}})

    async def run():
        app = web.Application()
        app.router.add_post("/api/chat", chat)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        google = []

        async def fake_google(session, clean):
            google.append(clean)
            return "from Google"
        kept = news.TRANSLATE_URL, news.TRANSLATE_MODEL, news.TRANSLATE_KEEP_ALIVE, news._translate_google
        news.TRANSLATE_URL, news.TRANSLATE_MODEL, news.TRANSLATE_KEEP_ALIVE, news._translate_google = f"http://127.0.0.1:{port}", "translategemma:12b", "2m", fake_google

        def reset(mode):
            state.update(mode=mode, busy=0, most=0)
            news._local_paused_until = 0.0
            news._translated.clear()
            seen.clear()
            google.clear()
        try:
            async with aiohttp.ClientSession() as session:
                reset("ok")
                got = await news.translate(session, "新曲が登場！ https://example.com/a")
                if got != "The final song is out!" or google:
                    problems.append(f"the local model's answer was {got!r}, Google asked {len(google)} times")
                body = seen[0]
                if body["model"] != "translategemma:12b" or body["stream"] is not False or body["keep_alive"] != "2m" or body["options"]["temperature"] != 0:
                    problems.append(f"the request carried {body}")
                prompt = body["messages"][0]["content"]
                if not prompt.startswith("You are a professional Japanese (ja) to English (en) translator.") or not prompt.endswith("into English:\n\n\n新曲が登場！"):
                    problems.append(f"the prompt is not Google's, with two blank lines and then only the text, links left out: {prompt[-80:]!r}")
                if await news.translate(session, "新曲が登場！ https://example.com/a") != got or len(seen) != 1:
                    problems.append("the same post was translated twice")
                # two at once are sent to the model one after the other
                reset("ok")
                await asyncio.gather(news.translate(session, "一つ目"), news.translate(session, "二つ目"), news.translate(session, "三つ目"))
                if state["most"] != 1 or len(seen) != 3:
                    problems.append(f"{state['most']} translations ran on the model at once, from {len(seen)} requests")
                # an answer that cannot be the translation is not used, and Google is asked for that post
                for mode in ("runaway", "japanese", "empty"):
                    reset(mode)
                    if await news.translate(session, "新曲が登場！") != "from Google" or len(google) != 1:
                        problems.append(f"a {mode} answer from the model was used or Google was not asked")
                # the model not pulled: Google, and the model is left alone for a while rather than asked for every post
                reset("missing")
                if await news.translate(session, "一つ") != "from Google" or await news.translate(session, "二つ") != "from Google" or len(seen) != 1 or len(google) != 2:
                    problems.append(f"a missing model was asked {len(seen)} times instead of once and then paused")
                # once the pause is over it is tried again
                news._local_paused_until = 0.0
                state["mode"] = "ok"
                if await news.translate(session, "三つ") != "The final song is out!":
                    problems.append("the model was not used again after its pause")
                # Google failing too: the post as written
                async def nothing(session, clean):
                    return None
                news._translate_google = nothing
                reset("missing")
                if await news.translate(session, "四つ") != "四つ":
                    problems.append("with every translator failing the post was not left as written")
                # nobody home
                await runner.cleanup()
                news._translate_google = fake_google
                reset("ok")
                if await news.translate(session, "五つ") != "from Google" or news._local_paused_until <= 0:
                    problems.append("an unreachable model was not fallen back from, or not paused")
                # not set up at all: the model is never asked
                news.TRANSLATE_URL = ""
                reset("ok")
                if await news.translate(session, "六つ") != "from Google" or seen:
                    problems.append("with no model set up one was still asked for")
                # a link on its own has nothing to translate
                if await news.translate(session, "https://example.com/a") != "https://example.com/a":
                    problems.append("a post of only a link was sent for translation")
        finally:
            news.TRANSLATE_URL, news.TRANSLATE_MODEL, news.TRANSLATE_KEEP_ALIVE, news._translate_google = kept
            news._local_paused_until = 0.0
            news._translated.clear()
    asyncio.run(run())
    return problems


@check("Bluesky posts are sent only when they are about maimai while X posts are never filtered, and every post says when it was made in Discord's own time format")
def _maimai_and_time():
    import datetime
    from rasmai.scraping import news

    problems = []
    for words, expected in (("The final WEC2026 #maimai DX track was revealed!", True), ("First WEC2026 original maimai song", True), ("舞萌 DX 新曲", True),
                            ("maimai でらっくす の新曲", True), ("MAIMAI", True),
                            ("Gekimai collaboration coming to #CHUNITHM on 10/08!\n\nPart 2 of the maimai DX map will be available!\n2 songs will be added:\nO.N.G.E.K.I. Chapter 7 will be available!", False),
                            ("🏆 KING of Performai The 8th has been announced!\nLike always, the event will feature competitions for O.N.G.E.K.I., CHUNITHM and maimai DX, as well as both int. versions!", True),
                            ("Collaboration in #CHUNITHM today! Part 2 of the map is in #maimai DX.", True),
                            ("A new song is in maimai DX! It also comes to CHUNITHM on 10/08.", True),
                            ("CHUNITHM and maimai DX share this campaign!", True),
                            ("A new Irodorimidori song will be added in #CHUNITHM on 10/01.", False), ("The monthly login bonuses are available in #CHUNITHM!", False),
                            ("good morning", False), ("", False),
                            # SEGA's pages for every game are under maimai.sega.jp, so a link names maimai without the post being about it
                            ("『KING of Performai The 8th』 CHUNITHMのオンライン予選課題コースはコチラ！ https://maimai.sega.jp/kop8th/chunithm/", False),
                            ("⬇️ KOP8th Official Site (JP) maimai.sega.jp/kop8th/", False),
                            ("maimai でらっくすのオンライン予選課題曲はコチラ！ https://maimai.sega.jp/kop8th/maimai/", True)):
        if news.is_maimai(words) is not expected:
            problems.append(f"{words!r} was judged about maimai: {news.is_maimai(words)}")
    source = news.SOURCES["maimai"]
    off_topic = news.FeedItem("30", "FEAT contest is open", "https://n/maimai_official/status/30#m", "", False, "maimai_official")
    if [i.id for i in news.own_posts([off_topic], source)] != ["30"]:
        problems.append("an X post that says nothing about maimai was filtered out, and X accounts are not filtered")

    def utc(*when):
        return int(datetime.datetime(*when, tzinfo=datetime.timezone.utc).timestamp())
    if news.tweet_time("2105787186885063025") != utc(2026, 10, 1, 22, 29, 23) or news.tweet_time("2107308619469611079") != utc(2026, 10, 6, 3, 15, 1) or news.tweet_time("x") is not None:
        problems.append("a tweet's time was not read from its id, or a bad id was not refused")
    if news.iso_time("2026-10-07T06:20:28.788Z") != utc(2026, 10, 7, 6, 20, 28) or news.iso_time("garbage") is not None:
        problems.append("a Bluesky post's time was not read, or garbage was not refused")
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    if not now - 5 <= news.iso_time("2999-01-01T00:00:00Z") <= now + 5:
        problems.append("a post claiming to be from the future was believed")

    stamp = 1790000000
    shown = news.Post("maimai", "1", "https://x.com/a/status/1", "n", parts=["hello"], posted_at=stamp).content()
    if f"-# Posted <t:{stamp}:F> · <t:{stamp}:R>\n" not in shown or shown.index("Posted") > shown.index("<https://x.com"):
        problems.append(f"the time is not shown as a full date and a relative one before the link: {shown!r}")
    if "Posted" in news.Post("maimai", "1", "https://x.com/a/status/1", "n", parts=["hello"]).content():
        problems.append("a post of unknown time was given a time")
    follow = news.Post("maimai", "1", "https://x.com/a/status/1", "n", parts=["fix"], follow_up=("https://x.com/a/status/0", "line"), posted_at=stamp).content()
    if f"<t:{stamp}:R>" not in follow or not follow.startswith(news.FOLLOW_UP_MARK):
        problems.append("a follow-up lost its time, or its header")

    async def build_x():
        return await news.build_x_post(None, source, news.FeedItem("2105787186885063025", "plain english words", "https://n/maimai_official/status/2105787186885063025#m", "", False, "maimai_official"), "")
    if asyncio.run(build_x()).posted_at != utc(2026, 10, 1, 22, 29, 23):
        problems.append("an X post was not given the time in its id")

    did = news.SOURCES["preformai"].did
    bsky = news.SOURCES["preformai"]
    first = {"uri": f"at://{did}/app.bsky.feed.post/a", "author": {"did": did}, "record": {"text": "maimai first", "createdAt": "2026-10-07T06:20:28.788Z"}}
    second = {"uri": f"at://{did}/app.bsky.feed.post/b", "author": {"did": did}, "record": {"text": "and more", "createdAt": "2026-10-07T06:20:40.000Z"}}

    async def fake_thread(session, uri, owner):
        return [first, second], None

    async def fake_avatar(session, handle):
        return ""
    kept = news.bluesky_thread, news.bluesky_avatar
    news.bluesky_thread, news.bluesky_avatar = fake_thread, fake_avatar
    try:
        built, _ = asyncio.run(news.build_bluesky_post(None, bsky, first["record"], first["uri"]))
        if built.posted_at != utc(2026, 10, 7, 6, 20, 28):
            problems.append(f"a Bluesky thread was timed {built.posted_at}, not when it began")
    finally:
        news.bluesky_thread, news.bluesky_avatar = kept
    return problems


class _Webhook:
    """Stands in for a Discord webhook: records what is sent, or fails the way a given scenario says."""

    def __init__(self, url, sent, behave):
        self.url, self.sent, self.behave = url, sent, behave

    async def send(self, **options):
        import discord
        outcome = self.behave(self.url, options)
        answers = {"gone": (discord.NotFound, 404, {"code": 10015, "message": "Unknown Webhook"}), "denied": (discord.Forbidden, 403, {"code": 50013, "message": "Missing Permissions"}),
                   "edge403": (discord.Forbidden, 403, "<html>Cloudflare</html>"), "edge404": (discord.NotFound, 404, "<html>not here</html>"),
                   "broken": (discord.DiscordServerError, 500, {"message": "oops"}), "bad": (discord.HTTPException, 400, {"code": 50035, "message": "Invalid Form Body"})}
        if outcome in answers:
            kind, status, message = answers[outcome]
            raise kind(type("R", (), {"status": status, "reason": outcome})(), message)
        if outcome == "big":
            raise discord.HTTPException(type("R", (), {"status": 413, "reason": "big"})(), "big")
        if outcome == "network":
            import aiohttp
            raise aiohttp.ClientConnectionError("reset")
        if outcome == "boom":
            raise RuntimeError("something nobody foresaw")
        if outcome == "slow":
            await asyncio.sleep(1)
        self.sent.append((self.url, options))


@contextmanager
def _webhooks(behave=lambda url, options: None):
    import discord
    sent = []
    kept = discord.Webhook.from_url
    discord.Webhook.from_url = staticmethod(lambda url, session=None: _Webhook(url, sent, behave))
    try:
        yield sent
    finally:
        discord.Webhook.from_url = kept


@check("each channel following a source gets a post once, with no pings, and a channel whose webhook is gone stops being sent to")
def _delivery():
    from rasmai.bot.tasks.news import NewsWatch
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    watch = NewsWatch()
    session = _no_session()
    session.__enter__()

    async def fake_bytes(session, url, limit=0):
        return b"\x89PNG" + b"0" * 10 if "cdn.bsky.app" in url else None
    kept = news.fetch_bytes
    news.fetch_bytes = fake_bytes
    seen_logs = []

    class Collect(logging.Handler):
        def emit(self, record):
            seen_logs.append(record.getMessage())
    handler, root = Collect(), logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        with _scratch():
            db.add_news_subscription("g1", "c1", "preformai", URL + "1", maimai_only=True)
            db.add_news_subscription("g2", "c2", "preformai", URL + "2", maimai_only=True)
            db.add_news_subscription("g2", "c2", "maimai", URL + "2")
            post = news.Post("preformai", "at://x/y/1", "https://bsky.app/profile/p/post/1", "Preformai International", "https://av/a.png",
                             ["@everyone hello"], [f"{news.IMG_CDN}/d/a"], [b"video"])

            async def run(post):
                return await watch.publish(post)
            with _webhooks() as sent:
                if asyncio.run(run(post)) != 2 or sorted(url for url, _ in sent) != [URL + "1", URL + "2"]:
                    problems.append(f"a post reached {[u[-1] for u, _ in sent]}, not both channels following it")
                options = sent[0][1]
                if options["username"] != "Preformai International" or options["avatar_url"] != "https://av/a.png":
                    problems.append("the post was not sent under the source's name and picture")
                if options["allowed_mentions"].to_dict() != {"parse": []}:
                    problems.append("a post could ping somebody")
                if [file.filename for file in options["files"]] != ["image_1.png", "video_1.mp4"]:
                    problems.append(f"attachments were {[file.filename for file in options['files']]}")
            # a source nobody follows is sent nowhere
            with _webhooks() as sent:
                if asyncio.run(run(news.Post("laundromai", "1", "https://x.com/l/status/1", "L", parts=["t"]))) != 0 or sent:
                    problems.append("a source nobody follows was sent somewhere")
            # too big for the server: the text and link still go
            with _webhooks(lambda url, options: "big" if "files" in options else None) as sent:
                if asyncio.run(run(post)) != 2 or any("files" in options for _, options in sent) or len(sent) != 2:
                    problems.append("a 413 did not fall back to sending without the attachments")
            # one webhook deleted: only that channel loses its subscriptions, the other still gets the post
            with _webhooks(lambda url, options: "gone" if url.endswith("1") else None) as sent:
                if asyncio.run(run(post)) != 1 or [url for url, _ in sent] != [URL + "2"]:
                    problems.append("a deleted webhook stopped the other channels getting the post")
            if db.channel_sources("c1") or db.channel_sources("c2") != ["maimai", "preformai"]:
                problems.append("a deleted webhook's channel was not unsubscribed, or another channel was")
            # a stored value that is not a webhook URL at all
            db.add_news_subscription("g3", "c3", "preformai", "not a webhook", maimai_only=True)
            if asyncio.run(NewsWatch()._deliver("c3", "not a webhook", post, [])) or db.channel_sources("c3"):
                problems.append("a stored value that is no webhook was kept")
    finally:
        session.__exit__(None, None, None)
        news.fetch_bytes = kept
        root.removeHandler(handler)
        root.setLevel(previous)
    if any("SECRETTOKEN" in line or "discord.com/api" in line for line in seen_logs):
        problems.append("a webhook URL was logged")
    return problems


@check("the first look at an X account sends nothing, later looks send what is new, oldest first and capped, and retweets are skipped")
def _polling():
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    source = news.SOURCES["maimai"]

    def item(n, retweet=False):
        return news.FeedItem(str(n), f"post {n}", f"https://n/{source.handle}/status/{n}", "", retweet, source.handle)
    feed = {"items": [item(5), item(4), item(3, retweet=True), item(2), item(1)]}

    async def fake_feed(session, username, tries=0):
        return feed["items"], "https://av/a.png"

    async def fake_post(session, src, entry, avatar):
        return news.Post(src.key, entry.id, entry.link, src.label, avatar, [entry.title])
    kept = news.fetch_feed, news.build_x_post
    news.fetch_feed, news.build_x_post = fake_feed, fake_post
    watch = tasks.NewsWatch()
    published = []

    async def record(post):
        published.append(post.id)
        return 1
    watch.publish = record
    kept_age = tasks.MAX_AGE
    tasks.MAX_AGE = 10 ** 12        # these ids are tiny, so by their own time they are from 2010
    try:
        with _scratch(), _no_session():
            db.add_news_subscription("g", "c", "maimai", URL)
            if asyncio.run(watch.poll(source)) != 0 or published:
                problems.append("the first look at an account sent its old posts")
            if db.news_unseen("maimai", ["1", "2", "4", "5"]) or db.news_unseen("maimai", ["3"]) != {"3"}:
                problems.append("the first look did not record the posts that were there, or recorded a retweet")
            if asyncio.run(watch.poll(source)) != 0 or published:
                problems.append("a look with nothing new sent something")
            feed["items"] = [item(8), item(7), item(6)] + feed["items"]
            if asyncio.run(watch.poll(source)) != 3 or published != ["6", "7", "8"]:
                problems.append(f"new posts went out as {published}, not oldest first")
            published.clear()
            feed["items"] = [item(n) for n in range(30, 8, -1)] + feed["items"]
            if asyncio.run(watch.poll(source)) != tasks.CATCH_UP or published != [str(n) for n in range(26, 31)]:
                problems.append(f"a long gap sent {published}, not just the newest {tasks.CATCH_UP}")
            if db.news_unseen("maimai", [str(n) for n in range(9, 31)]):
                problems.append("the older posts of a long gap were not marked seen, so they would be sent next look")
            published.clear()
            feed["items"] = []
            if asyncio.run(watch.poll(source)) != 0:
                problems.append("an unreachable feed sent something")

            # a post that turns up unseen but is days old, after downtime or a gap with nobody following, is marked seen and never sent
            tasks.MAX_AGE = kept_age

            def made(seconds_ago, n=0):
                return str(((int((time.time() - seconds_ago) * 1000) - news.TWITTER_EPOCH_MS) << 22) + n)
            old, fresh = made(3 * 86400), made(60)
            feed["items"] = [item(fresh), item(old)] + [item(n) for n in range(30, 0, -1)]
            if asyncio.run(watch.poll(source)) != 1 or published != [fresh]:
                problems.append(f"a three-day-old post and a fresh one arriving together sent {published}, not just the fresh one")
            if db.news_unseen("maimai", [old]):
                problems.append("a post too old to send was not marked seen")
            # Bluesky's createdAt goes the same way: whatever path a post takes, one days old is never sent live
            with _webhooks() as sent:
                now = int(time.time())
                for age in (3 * 86400, 60):
                    asyncio.run(tasks.NewsWatch().publish(news.Post("maimai", str(age), "https://x.com/a/status/1", "n", parts=["hi"], posted_at=now - age)))
            if len(sent) != 1:
                problems.append(f"a days-old post and a fresh one handed to publish made {len(sent)} sends, not 1")
    finally:
        news.fetch_feed, news.build_x_post = kept
        tasks.MAX_AGE = kept_age
    return problems


@check("a Bluesky update is sent once, its replies and reposts of it are not, and nothing is built for a source nobody follows")
def _bluesky():
    from rasmai.bot.tasks.news import NewsWatch
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    source = news.SOURCES["preformai"]
    built = []

    async def fake_build(session, src, record, uri):
        built.append(uri)
        return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=[record["text"]]), [uri, uri + "-b"]
    kept_build, kept_wait = news.build_bluesky_post, news.THREAD_WAIT_SECONDS
    news.build_bluesky_post, news.THREAD_WAIT_SECONDS = fake_build, 0
    watch = NewsWatch()
    published = []

    async def record(post):
        published.append(post.id)
        return 1
    watch.publish = record
    update = {"text": "#maimai new song added 🎵 event 12/1", "embed": {"$type": "app.bsky.embed.images"}}
    try:
        with _scratch(), _no_session():
            if asyncio.run(watch.bluesky_post(source, update, "at://d/p/1")) != 0 or built:
                problems.append("a post was built for a source nobody follows")
            db.add_news_subscription("g", "c", "preformai", URL, maimai_only=True)
            if asyncio.run(watch.bluesky_post(source, {"text": "good morning"}, "at://d/p/0")) != 0 or built:
                problems.append("a post that is not about maimai was built")
            if asyncio.run(watch.bluesky_post(source, {"text": "A new song will be added in #CHUNITHM on 10/01. update available event"}, "at://d/p/00")) != 0 or built:
                problems.append("a CHUNITHM post was sent, however much it reads like an update")
            if asyncio.run(watch.bluesky_post(source, update, "at://d/p/1")) != 1 or published != ["at://d/p/1"]:
                problems.append("an update was not sent")
            if asyncio.run(watch.bluesky_post(source, update, "at://d/p/1")) != 0:
                problems.append("the same update was sent twice")
            did = source.did
            mine, theirs = {"uri": f"at://{did}/app.bsky.feed.post/x"}, {"uri": "at://did:plc:somebodyelse/app.bsky.feed.post/x"}
            # what was part of a send is recorded as seen, so it is not sent again
            if asyncio.run(watch.bluesky_post(source, {**update, "reply": {"root": {"uri": "at://d/p/1"}, "parent": mine}}, "at://d/p/1-b")) != 0:
                problems.append("a post that was already part of a sent thread was sent again")
            # the account correcting or continuing itself later is sent, whatever the answer says, because what it answers was sent
            fix = {"text": "Fix: Energy 6.4 to 6.3", "reply": {"root": {"uri": "at://d/p/1"}, "parent": mine}}
            if asyncio.run(watch.bluesky_post(source, fix, "at://d/p/2")) != 1 or published[-1] != "at://d/p/2":
                problems.append("the account answering its own sent post was not sent")
            # but not an answer in a thread that was never sent, unless it reads like an update on its own
            stray = {"text": "ok thanks", "reply": {"root": {"uri": "at://d/p/50"}, "parent": mine}}
            if asyncio.run(watch.bluesky_post(source, stray, "at://d/p/51")) != 0:
                problems.append("a chatty answer in a thread that was never sent was sent")
            if asyncio.run(watch.bluesky_post(source, {**update, "reply": {"root": {"uri": "at://d/p/50"}, "parent": mine}}, "at://d/p/52")) != 1:
                problems.append("an answer that reads like an update was dropped because its thread was not sent")
            # never an answer to somebody else, however much it reads like an update
            if asyncio.run(watch.bluesky_post(source, {**update, "reply": {"root": {"uri": "at://d/p/1"}, "parent": theirs}}, "at://d/p/60")) != 0 \
                    or asyncio.run(watch.bluesky_post(source, {"text": "thanks!", "reply": {"root": {"uri": "at://d/p/1"}, "parent": theirs}}, "at://d/p/61")) != 0:
                problems.append("the account's answer to somebody else was sent")
    finally:
        news.build_bluesky_post, news.THREAD_WAIT_SECONDS = kept_build, kept_wait
    return problems


@check("earlier posts come oldest first, only update posts on Bluesky and only originals on X, go to the one channel that asked, and change nothing live")
def _history():
    from rasmai.bot.tasks.news import NewsWatch
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    bsky, maimai = news.SOURCES["preformai"], news.SOURCES["maimai"]

    def entry(n, text, did=bsky.did, repost=False):
        out = {"post": {"uri": f"at://d/p/{n}", "author": {"did": did}, "record": {"text": text}}}
        if repost:
            out["reason"] = {"$type": "reason"}
        return out
    update = "#maimai new song added \U0001f3b5 event 12/1"
    feed = {"feed": [entry(10, "The monthly bonuses are now available in #CHUNITHM!"), entry(9, update), entry(8, "good morning"), entry(7, update, repost=True), entry(6, update, did="did:other"),
                     entry(5, update), entry(4, update), entry(3, update)]}

    async def fake_json(session, url, params=None):
        return feed

    async def fake_build(session, src, record, uri):
        return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=[uri[-1]]), [uri]
    items = [news.FeedItem(str(n), f"post {n}", f"https://n/m/status/{n}", "", retweet=(n == 4), author=maimai.handle) for n in (5, 4, 3, 2, 1)]

    async def fake_feed(session, username, tries=0):
        return items, "https://av/a.png"

    async def fake_x(session, src, item, avatar):
        return news.Post(src.key, item.id, item.link, src.label, avatar, [item.title])
    kept = news._get_json, news.build_bluesky_post, news.fetch_feed, news.build_x_post
    news._get_json, news.build_bluesky_post, news.fetch_feed, news.build_x_post = fake_json, fake_build, fake_feed, fake_x
    try:
        if asyncio.run(news.recent_posts(None, bsky, 0)) != []:
            problems.append("asking for none gave posts")
        got = [p.id[-1] for p in asyncio.run(news.recent_posts(None, bsky, 3))]
        if got != ["4", "5", "9"]:
            problems.append(f"three earlier Bluesky posts were {got}: they must be update posts only, oldest first, no reposts and nobody else's")
        if [p.id for p in asyncio.run(news.recent_posts(None, maimai, 3))] != ["2", "3", "5"]:
            problems.append("earlier X posts were not the newest originals, oldest first, retweets left out")
        if len(asyncio.run(news.recent_posts(None, maimai, 1))) != 1:
            problems.append("asking for one X post gave another number")

        watch = NewsWatch()
        sent = []

        async def deliver(channel_id, url, post, files):
            sent.append((channel_id, post.source, post.id))
            return channel_id != "gone" or len(sent) < 2
        watch._deliver = deliver

        async def no_files(post):
            return []
        watch._files = no_files
        with _scratch(), _no_session():
            db.add_news_subscription("g", "other", "maimai", URL)
            if asyncio.run(watch.history("c1", URL, ["maimai", "preformai"], 2)) != 4 or sent != [
                    ("c1", "maimai", "3"), ("c1", "maimai", "5"), ("c1", "preformai", "at://d/p/5"), ("c1", "preformai", "at://d/p/9")]:
                problems.append(f"earlier posts were sent as {sent}")
            if any(channel == "other" for channel, _s, _i in sent):
                problems.append("earlier posts reached a channel that did not ask")
            if db.news_seen_any("maimai") or db.news_seen_any("preformai"):
                problems.append("sending earlier posts recorded them as seen, which would change what is sent live")
            sent.clear()
            if asyncio.run(watch.history("gone", URL, ["maimai", "preformai"], 2)) != 1 or len(sent) != 2:
                problems.append("a channel that stopped accepting posts was still sent the rest")
    finally:
        news._get_json, news.build_bluesky_post, news.fetch_feed, news.build_x_post = kept
    return problems


class _Socket:
    """A Jetstream connection that says what a script tells it to."""

    def __init__(self, script):
        self.script = list(script)

    async def receive(self, timeout=None):
        step = self.script.pop(0)
        if step == "quiet":
            raise asyncio.TimeoutError
        return step


@check("a Jetstream reconnect asks for what it missed, a quiet stretch is noted as alive, and a post replayed from the past is not waited on")
def _jetstream():
    import aiohttp
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    accounts = {s.did: s for s in news.SOURCES.values() if s.did}
    now = 1_800_000_000 * 1_000_000
    if "cursor" in tasks.jetstream_url(accounts, None, now):
        problems.append("a first ever connection asked to replay")
    asked = int(tasks.jetstream_url(accounts, now - 3600 * 1_000_000, now).split("cursor=")[1])
    if asked != now - 3600 * 1_000_000 - tasks.REWIND:
        problems.append(f"a reconnect an hour later asked from {now - asked} microseconds ago, not from just before the last moment it was alive")
    if int(tasks.jetstream_url(accounts, now - 10 * 24 * 3600 * 1_000_000, now).split("cursor=")[1]) != now - tasks.REPLAY_LIMIT:
        problems.append("a break of days asked for all of it instead of the limit")
    if "wantedDids=" + news.SOURCES["preformai"].did not in tasks.jetstream_url(accounts, None, now) or "wantedCollections=app.bsky.feed.post" not in tasks.jetstream_url(accounts, None, now):
        problems.append("the stream was not asked for the account's posts")

    watch = tasks.NewsWatch()
    handled = []

    async def record(source, record, uri, wait=True):
        handled.append((uri, wait))
        return 1
    watch.bluesky_post = record
    did = news.SOURCES["preformai"].did

    def event(rkey, age_seconds):
        stamp = tasks._now_us() - age_seconds * 1_000_000
        return aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, json_text(rkey, stamp), None)

    def json_stamp(data):
        import json
        return json.loads(data)["time_us"]

    def json_text(rkey, stamp):
        import json
        return json.dumps({"did": did, "time_us": stamp, "kind": "commit",
                           "commit": {"operation": "create", "repo": did, "rkey": rkey, "record": {"text": "x"}}})
    closed = aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None)
    kept_alive, kept_done = tasks.ALIVE_EVERY, tasks.REPLAY_DONE
    try:
        with _scratch(), _no_session():
            if db.jetstream_alive() is not None:
                problems.append("a new database already had a moment the stream was alive")
            # while a reconnect's replay may still be arriving, only what has arrived counts: a drop half way through asks for the rest again
            tasks.ALIVE_EVERY, tasks.REPLAY_DONE = 0, 10 ** 6
            replay = [event("r1", 7200), event("r2", 5400), event("r3", 3600)]
            stamps = [json_stamp(m.data) for m in replay]
            asyncio.run(watch.read(_Socket(["quiet"] + replay + [closed]), accounts))
            if db.jetstream_alive() != stamps[-1]:
                problems.append(f"part way through a replay the stream was noted alive at {db.jetstream_alive()}, not at the newest event received {stamps[-1]}")
            handled.clear()
            db.save_jetstream_alive(0)
            asyncio.run(watch.read(_Socket(["quiet", closed]), accounts))
            if db.jetstream_alive() not in (0, None):
                problems.append("a connection that had received nothing yet was noted alive at the clock, skipping whatever its replay held")
            # once the replay has had its time, a quiet stretch is noted alive at the clock
            tasks.REPLAY_DONE = 0
            before = tasks._now_us()
            asyncio.run(watch.read(_Socket(["quiet", closed]), accounts))
            first = db.jetstream_alive()
            if first is None or not before - tasks.ALIVE_LAG - 5_000_000 <= first <= tasks._now_us() - tasks.ALIVE_LAG + 5_000_000:
                problems.append(f"a quiet connection did not note when it was alive: {first}")
            tasks.ALIVE_EVERY = kept_alive

            async def run_events():
                await watch.read(_Socket([event("live", 1), event("replayed", 3600), closed]), accounts)
                await asyncio.sleep(0.2)
            asyncio.run(run_events())
            if dict(handled) != {f"at://{did}/app.bsky.feed.post/live": True, f"at://{did}/app.bsky.feed.post/replayed": False}:
                problems.append(f"a live post and a replayed one were handled as {handled}: only the live one is waited on for its thread")
            # the noted moment moves on, so a second drop replays from later than the first
            tasks.ALIVE_EVERY = 0
            asyncio.run(watch.read(_Socket(["quiet", closed]), accounts))
            if not (db.jetstream_alive() or 0) >= (first or 0):
                problems.append("the moment the stream was alive went backwards")
    finally:
        tasks.ALIVE_EVERY, tasks.REPLAY_DONE = kept_alive, kept_done

    # the loop itself: while nobody follows, the noted moment keeps up with the clock, so the first follower is not sent days of old posts;
    # once somebody does, the connection asks from the moment noted
    class Stop(BaseException):      # not an Exception, so the loop's own error handler lets it through
        pass
    urls = []

    class Session:
        closed = False

        def ws_connect(self, url, heartbeat=None):
            urls.append(url)

            class Context:
                async def __aenter__(inner):
                    return _Socket([closed])

                async def __aexit__(inner, *exc):
                    return False
            return Context()
    kept_sleep = tasks.asyncio.sleep
    calls = {"n": 0, "limit": 2}

    async def fake_sleep(seconds):
        calls["n"] += 1
        if calls["n"] >= calls["limit"]:
            raise Stop

    async def loop_once():
        watch = tasks.NewsWatch()
        watch._session = Session()
        try:
            await watch._bluesky_loop()
        except Stop:
            pass
    tasks.asyncio.sleep = fake_sleep
    try:
        with _scratch():
            asyncio.run(loop_once())
            idle = db.jetstream_alive()
            if urls or idle is None or abs(idle - tasks._now_us()) > 30_000_000:
                problems.append("with nobody following, the loop connected, or did not note that it was alive")
            db.add_news_subscription("g", "c", "preformai", URL, maimai_only=True)
            db.save_jetstream_alive(tasks._now_us() - 120 * 1_000_000)
            calls["n"], calls["limit"] = 0, 1
            asyncio.run(loop_once())
            if len(urls) != 1 or "cursor=" not in urls[0]:
                problems.append(f"a reconnect with a follower connected as {urls}, without asking for what it missed")
    finally:
        tasks.asyncio.sleep = kept_sleep
    return problems


@check("nothing the bot sends can ping: every post forbids all mentions, and every kind of ping in a post is made inert")
def _mentions():
    from rasmai.bot.tasks.news import NO_MENTIONS, NewsWatch
    from rasmai.scraping import news

    problems = []
    if NO_MENTIONS.to_dict() != {"parse": []}:
        problems.append(f"the mentions allowed on a send are {NO_MENTIONS.to_dict()}")
    attack = "@everyone @EVERYONE @here <@123> <@!456> <@&789> hi <#42>"
    for parts, video in (([attack], False), ([attack, attack], True)):
        content = news.Post("maimai", "1", "https://x.com/a/status/1", "Maimai Official", parts=parts, wanted_video=video).content()
        if "@everyone" in content.lower() or "@here" in content.lower() or "<@" in content or "<#" in content:
            problems.append(f"a ping form survived in {content!r}")
        if content.replace(chr(0x200B), "").lower().count("@everyone") != 2 * len(parts) or "[user]" not in content or "[role]" not in content:
            problems.append(f"the post's own words were not kept readable: {content!r}")

    quoted = news.Post("maimai", "1", "https://x.com/a/status/1", "Maimai Official", parts=["fix"], follow_up=("https://x.com/a/status/0", attack)).content()
    if "@everyone" in quoted.lower() or "@here" in quoted.lower() or "<@" in quoted:
        problems.append(f"a ping in the post being answered survived in the quote: {quoted!r}")

    watch = NewsWatch()
    post = news.Post("maimai", "1", "https://x.com/a/status/1", "Maimai Official", "https://av/a.png", [attack], [], [b"video"])
    with _no_session(), _webhooks(lambda url, options: "big" if "files" in options else None) as sent:
        asyncio.run(watch._deliver("c", URL, post, [("video_1.mp4", b"video")]))       # first with its attachment, which is refused as too big, then without
        asyncio.run(watch._deliver("c", URL, post, []))
    if len(sent) != 2 or any(o.get("allowed_mentions") is None or o["allowed_mentions"].to_dict() != {"parse": []} for _u, o in sent):
        problems.append("a webhook send, with or without attachments, did not forbid every mention")
    if any("@everyone" in o["content"].lower() or "<@" in o["content"] for _u, o in sent):
        problems.append("a webhook was sent a raw ping")
    return problems


async def _and_let_tasks_run(work):
    """Await a command, then give anything it started in the background a moment, since the loop is closed as soon as the command returns."""
    result = await work
    await asyncio.sleep(0.05)
    return result


def aiohttp_closed():
    import aiohttp
    return aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None)


@check("one connection, one feed read, one build, one translation and one set of attachments serve every channel following an account, and a replayed or threaded post is sent once")
def _once():
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    channels = [f"c{n}" for n in range(6)]
    source = news.SOURCES["maimai"]
    counts = {"feed": 0, "build": 0, "bytes": 0}

    def item(n):
        return news.FeedItem(str(n), f"post {n}", f"https://n/{source.handle}/status/{n}", "", False, source.handle)
    feed = {"items": [item(1)]}

    async def fake_feed(session, username, tries=0):
        counts["feed"] += 1
        return feed["items"], "https://av/a.png"

    async def fake_build(session, src, entry, avatar):
        counts["build"] += 1
        return news.Post(src.key, entry.id, entry.link, src.label, avatar, [entry.title], ["https://cdn.bsky.app/a.jpg", "https://cdn.bsky.app/b.jpg"])

    async def fake_bytes(session, url, limit=0):
        counts["bytes"] += 1
        return b"\x89PNG" + b"0" * 10
    kept = news.fetch_feed, news.build_x_post, news.fetch_bytes
    news.fetch_feed, news.build_x_post, news.fetch_bytes = fake_feed, fake_build, fake_bytes
    kept_age = tasks.MAX_AGE
    tasks.MAX_AGE = 10 ** 12        # ids 1 and 2 are from 2010 by their own time
    try:
        with _scratch(), _no_session():
            for number, channel in enumerate(channels):
                db.add_news_subscription(f"g{number}", channel, "maimai", URL + str(number))
            watch = tasks.NewsWatch()
            with _webhooks() as sent:
                asyncio.run(watch.poll(source))
                feed["items"] = [item(2), item(1)]
                asyncio.run(watch.poll(source))
            if counts != {"feed": 2, "build": 1, "bytes": 2} or sorted(url for url, _ in sent) != sorted(URL + str(n) for n in range(6)):
                problems.append(f"six channels followed one account and it cost {counts} for {len(sent)} sends: the feed once a look, the post built once, each picture fetched once, and one send each")

            # the loops look at an account only while somebody follows it, once a round however many do
            looked = []

            async def poll(src, learn=False):
                looked.append(src.key)
                return 0

            class Stop(BaseException):
                pass
            rounds = {"n": 0}
            kept_sleep = tasks.asyncio.sleep

            async def fake_sleep(seconds):
                rounds["n"] += 1
                if rounds["n"] >= 2:
                    raise Stop
            watch.poll = poll
            tasks.asyncio.sleep = fake_sleep
            try:
                try:
                    asyncio.run(watch._x_loop())
                except Stop:
                    pass
            finally:
                tasks.asyncio.sleep = kept_sleep
            if looked != ["maimai", "maimai"]:
                problems.append(f"two rounds of the X loop looked at {looked}: once a round for the one account anybody follows, not once a channel and not for the ones nobody does")

            # Bluesky: the same post arriving twice while it is being waited on, as a reconnect's replay does, and a reply arriving while its thread's first post waits
            bsky = news.SOURCES["preformai"]
            did = bsky.did
            built, published = [], []

            async def fake_thread_build(session, src, record, uri):
                built.append(uri)
                await asyncio.sleep(0.02)
                return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=[record["text"]]), [uri]

            async def record_publish(post):
                published.append(post.id)
                return 1
            kept_build, kept_wait = news.build_bluesky_post, news.THREAD_WAIT_SECONDS
            news.build_bluesky_post, news.THREAD_WAIT_SECONDS = fake_thread_build, 0
            db.add_news_subscription("g", "b", "preformai", URL + "b", maimai_only=True)
            watch = tasks.NewsWatch()
            watch.publish = record_publish
            first = {"text": "maimai news"}
            reply = {"text": "maimai more", "reply": {"root": {"uri": f"at://{did}/app.bsky.feed.post/1"}, "parent": {"uri": f"at://{did}/app.bsky.feed.post/1"}}}
            try:
                async def together():
                    return await asyncio.gather(
                        watch.bluesky_post(bsky, first, f"at://{did}/app.bsky.feed.post/1"), watch.bluesky_post(bsky, first, f"at://{did}/app.bsky.feed.post/1"),
                        watch.bluesky_post(bsky, reply, f"at://{did}/app.bsky.feed.post/2"))
                asyncio.run(together())
            finally:
                news.build_bluesky_post, news.THREAD_WAIT_SECONDS = kept_build, kept_wait
            if built != [f"at://{did}/app.bsky.feed.post/1"] or published != [f"at://{did}/app.bsky.feed.post/1"]:
                problems.append(f"a post replayed during its own wait, and a reply to it, built {built} and sent {published}")
            if watch._inflight:
                problems.append("a post stayed marked as being handled after it was done")

            # one Jetstream connection however many channels follow
            urls = []

            class Session:
                closed = False

                def ws_connect(self, url, heartbeat=None):
                    urls.append(url)

                    class Context:
                        async def __aenter__(inner):
                            return _Socket([aiohttp_closed()])

                        async def __aexit__(inner, *exc):
                            return False
                    return Context()
            for number in range(5):
                db.add_news_subscription(f"h{number}", f"d{number}", "preformai", URL + f"d{number}", maimai_only=True)
            rounds["n"] = 1          # stop at the first pause, after the one connection closes: a second would be a reconnect, not a second connection
            tasks.asyncio.sleep = fake_sleep
            watch = tasks.NewsWatch()
            kept_property = tasks.NewsWatch.session
            tasks.NewsWatch.session = property(lambda self: Session())
            try:
                try:
                    asyncio.run(watch._bluesky_loop())
                except Stop:
                    pass
            finally:
                tasks.asyncio.sleep = kept_sleep
                tasks.NewsWatch.session = kept_property
            if len(urls) != 1 or urls[0].count("wantedDids=") != 1:
                problems.append(f"six channels following Bluesky opened {len(urls)} connections, {urls}")
    finally:
        news.fetch_feed, news.build_x_post, news.fetch_bytes = kept
        tasks.MAX_AGE = kept_age
    return problems


class _Perms:
    def __init__(self, webhooks):
        self.manage_webhooks = webhooks


class _Me:
    def __init__(self):
        import discord
        self.guild_permissions = discord.Permissions(send_messages=True, embed_links=True)


class _Guild:
    def __init__(self, guild_id=77, channels=()):
        self.id, self.me = guild_id, _Me()
        self.channels = {c.id: c for c in channels}

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        import discord
        if cid not in self.channels:
            raise discord.NotFound(type("R", (), {"status": 404, "reason": "Not Found"})(), "Unknown Channel")
        return self.channels[cid]


class _Channel:
    def __init__(self, cid, user_ok=True, bot_ok=True, guild_id=77):
        self.id, self.mention, self.user_ok, self.bot_ok = cid, f"<#{cid}>", user_ok, bot_ok
        self.name = f"chan{cid}"
        self.created = 0
        self.guild = _Guild(guild_id)

    def permissions_for(self, who):
        return _Perms(self.bot_ok if who is self.guild.me else self.user_ok)

    async def create_webhook(self, name, reason=None):
        self.created += 1
        return type("W", (), {"url": f"{URL}-made{self.id}-{self.created}"})()


class _Interaction:
    def __init__(self, guild_id=77, guild=None):
        self.user, self.guild_id, self.said, self.sent, self.drawn = type("U", (), {"id": 1})(), guild_id, [], [], []
        self.guild = guild
        self.client = type("C", (), {"application_id": 4242})()
        outer, state = self, {"done": False}

        class Response:
            async def send_message(self, text=None, **options):
                state["done"] = True
                outer.said.append(text or "")
                outer.sent.append(options)

            async def send_modal(self, modal):
                state["done"] = True
                outer.modal = modal

            async def defer(self, ephemeral=False):
                state["done"] = True

            async def edit_message(self, **options):
                state["done"] = True
                outer.drawn.append(options)

            def is_done(self):
                return state["done"]

        class Followup:
            async def send(self, text, **options):
                outer.said.append(text)
                outer.sent.append(options)
        self.response, self.followup = Response(), Followup()

    async def edit_original_response(self, **options):
        self.drawn.append(options)

    async def original_response(self):
        return None


@check("/news subscribe is a menu of a channel, its accounts and Save that also switches accounts off, /news unsubscribe lists what each channel gets, and both need Manage Webhooks, keep one webhook per channel, cap a server and clean up after themselves")
def _command():
    from urllib.parse import parse_qs, urlparse

    import discord
    from rasmai.bot.commands import news as command
    from rasmai.bot.tasks.news import NewsWatch
    from rasmai.scraping.news import SOURCES
    from rasmai.storage import db

    problems = []
    group = command.news
    names = {c.name: c for c in group.commands}
    sent = group.to_dict(__import__("rasmai.bot.core", fromlist=["bot"]).bot.tree)
    if set(names) != {"subscribe", "unsubscribe", "manage"} or sent["contexts"] != [0] or sent["integration_types"] != [0, 1]:
        problems.append(f"the group has {sorted(names)}, contexts {sent['contexts']}, installs {sent['integration_types']}: it must be for servers only, installed to a server or an account")
    if sent["default_member_permissions"] != discord.Permissions(manage_webhooks=True).value:
        problems.append("the picker is not limited to people who can manage webhooks")
    subscribe, unsubscribe, manage = names.get("subscribe"), names.get("unsubscribe"), names.get("manage")
    options = {p.name: p for p in subscribe.parameters}
    if set(options) != {"previous"} or options["previous"].required or options["previous"].default != 0 \
            or (options["previous"].min_value, options["previous"].max_value) != (0, command.MAX_HISTORY):
        problems.append(f"subscribe takes {sorted(options)}: only the earlier posts, optional, 0 by default within 0 to {command.MAX_HISTORY}; the channel and accounts are picked in its menu")
    if [p.name for p in unsubscribe.parameters]:
        problems.append("unsubscribe takes options; it shows what is followed and the channels are picked there")
    if {s.handle for s in SOURCES.values()} != {"performaien.bsky.social", "maimai_official", "laundromai", "kop_sega"}:
        problems.append("the accounts are not Preformai International, Maimai Official, Laundromai and KING of Performai")

    from rasmai.bot import core
    kept_application = core.bot._connection.application_id
    core.bot._connection.application_id = 4242
    kept = discord.Webhook.from_url
    fetched = []

    class Live:
        def __init__(self, url):
            self.url = url

        async def fetch(self):
            fetched.append(self.url)
            return type("H", (), {"channel_id": 5})()

        async def delete(self):
            fetched.append(("deleted", self.url))
    discord.Webhook.from_url = staticmethod(lambda url, session=None: Live(url))
    asked = []
    kept_history = NewsWatch.history

    async def history(self, channel_id, url, keys, count):
        asked.append((channel_id, list(keys), count))
        return 0
    NewsWatch.history = history
    command._history_at.clear()
    save = command.save_channel
    every = list(SOURCES)
    try:
        with _scratch(), _no_session():
            # who may do it
            said = _Interaction()
            asyncio.run(save(said, _Channel(5, user_ok=False), every))
            if "You need" not in said.said[0] or db.channel_sources("5"):
                problems.append(f"somebody without Manage Webhooks was told {said.said}")
            # the bot lacks it: a fresh invite link for this server, or the permission by hand, and nothing is made
            channel, said = _Channel(5, bot_ok=False), _Interaction()
            asyncio.run(save(said, channel, every))
            view = said.sent[0].get("view")
            link = view.children[0].url if view is not None and view.children else ""
            query = parse_qs(urlparse(link).query)
            granted = int(query.get("permissions", ["0"])[0])
            if "I need" not in said.said[0] or "Manage Server" not in said.said[0] or "Server Settings" not in said.said[0]:
                problems.append(f"the permission message did not give both ways out: {said.said[0]!r}")
            if (query.get("client_id") != ["4242"] or query.get("guild_id") != ["77"] or query.get("disable_guild_select") != ["true"]
                    or "applications.commands" not in query.get("scope", [""])[0]):
                problems.append(f"the invite link is not for this bot and this server only: {link}")
            have = discord.Permissions(send_messages=True, embed_links=True).value
            if not granted & discord.Permissions(manage_webhooks=True).value or granted & have != have:
                problems.append("the invite link does not ask for Manage Webhooks on top of what the bot already has")
            if db.channel_sources("5") or channel.created:
                problems.append("something was stored or made though the bot had no permission")
            # everything, into a channel
            channel, said = _Channel(5), _Interaction()
            done = asyncio.run(save(said, channel, every))
            if sorted(db.channel_sources("5")) != sorted(SOURCES) or channel.created != 1 or asked or "now gets" not in (done or ""):
                problems.append(f"following all three made {db.channel_sources('5')} with {channel.created} webhook(s), said {done!r}, or sent earlier posts unasked")
            url = db.news_webhook("5")
            if not url or url not in [u for _c, u in db.news_subscribers("maimai")]:
                problems.append("the webhook was not stored")
            if "SECRETTOKEN" in (done or "") or url in (done or "") or any("SECRETTOKEN" in line for line in said.said):
                problems.append("the reply showed the webhook URL")
            # the same again: nothing changes, nothing is made
            done = asyncio.run(save(_Interaction(), channel, every))
            if "Nothing changed" not in (done or "") or channel.created != 1:
                problems.append(f"saving what is already followed said {done!r}")
            # unticking one stops only it, and the webhook stays for the rest
            done = asyncio.run(save(_Interaction(), channel, ["maimai", "preformai"]))
            if sorted(db.channel_sources("5")) != ["maimai", "preformai"] or "Laundromai" not in (done or "").split("no longer gets")[-1] or ("deleted", url) in fetched:
                problems.append(f"unticking one account left {db.channel_sources('5')}, said {done!r}, or deleted the webhook")
            # ticking it again reuses the channel's webhook, after checking it still works
            done = asyncio.run(save(_Interaction(), channel, every))
            if channel.created != 1 or db.news_webhook("5") != url or fetched != [url] or "now gets Laundromai" not in (done or ""):
                problems.append(f"ticking an account again made a new webhook ({channel.created}) or did not check the old: {done!r}")
            # unticking everything stops the channel and deletes its webhook
            done = asyncio.run(save(_Interaction(), channel, []))
            if db.channel_sources("5") or ("deleted", url) not in fetched:
                problems.append(f"unticking every account left {db.channel_sources('5')} or the webhook behind")
            # earlier posts: only for what is newly ticked, once in a while per server
            channel, said = _Channel(8), _Interaction()
            done = asyncio.run(_and_let_tasks_run(save(said, channel, ["maimai"], 3)))
            if asked != [("8", ["maimai"], 3)] or "last 3 post" not in (done or ""):
                problems.append(f"earlier posts were asked for as {asked}, said {done!r}")
            again, other = _Interaction(), _Channel(9)
            asyncio.run(save(again, other, ["laundromai"], 2))
            if "a moment ago" not in again.said[0] or db.channel_sources("9") or len(asked) != 1:
                problems.append(f"a second request for earlier posts straight away was allowed: {again.said}")
            asyncio.run(save(_Interaction(), other, ["laundromai"], 0))
            if db.channel_sources("9") != ["laundromai"] or len(asked) != 1:
                problems.append("a plain subscribe was held up by the earlier-posts limit")
            # the cap, counting what this save unticks
            full = _Interaction(guild_id=99)
            for n in range(9):
                db.add_news_subscription("99", f"x{n}", "maimai", URL)
            crowded = _Channel(6, guild_id=99)
            db.add_news_subscription("99", "6", "maimai", URL)
            asyncio.run(save(full, crowded, ["laundromai", "preformai"]))
            if "up to 10" not in full.said[0] or db.channel_sources("6") != ["maimai"]:
                problems.append(f"a full server was told {full.said} and its subscriptions became {db.channel_sources('6')}")
            done = asyncio.run(save(_Interaction(guild_id=99), crowded, ["laundromai"]))
            if db.channel_sources("6") != ["laundromai"]:
                problems.append(f"swapping one account for another in a full server was refused: {done!r}")
            # a channel of another server, however it was picked
            elsewhere = _Interaction()
            asyncio.run(save(elsewhere, _Channel(66, guild_id=55), ["laundromai"]))
            if "this server" not in elsewhere.said[0] or db.channel_sources("66"):
                problems.append(f"a channel in another server was subscribed from this one: {elsewhere.said}")

            # the subscribe menu: a channel picker, the accounts ticked, and Save, which waits for a channel
            said = _Interaction()
            asyncio.run(subscribe.callback(said, 0))
            menu = said.sent[0].get("view") if said.sent else None
            if not isinstance(menu, command.SubscribeMenu) or said.sent[0].get("ephemeral") is not True or "embed" not in said.sent[0]:
                problems.append("/news subscribe did not answer privately with an embed and its menu")
            else:
                kinds = [type(item).__name__ for item in menu.children]
                if kinds != ["ChannelSelect", "Select", "Button", "Button", "Button", "Select", "Select"] or not menu.save.disabled or not menu.test.disabled \
                        or menu.which.max_values != len(SOURCES) or menu.which.min_values != 0:
                    problems.append(f"the menu is {kinds}, Save and the test {'off' if menu.save.disabled else 'on'} before a channel: a channel picker, the accounts, Save and a test post")
                field = said.sent[0]["embed"].fields[0] if said.sent[0]["embed"].fields else None
                if field is None or field.name != "Getting news now" or "<#9>: Laundromai" not in field.value:
                    problems.append(f"the menu did not list the channels getting news: {field}")
                # picking a channel that follows some ticks just those, and shows them
                followed = _Channel(12)
                db.add_news_subscription("77", "12", "laundromai", URL)
                guild = _Guild(77, [followed])
                followed.guild = guild
                menu.where._values = [type("Picked", (), {"id": 12, "mention": "<#12>"})()]
                pick = _Interaction(guild=guild)
                asyncio.run(menu.pick_channel(pick))
                if menu.ticked != ["laundromai"] or menu.save.disabled or menu.test.disabled or not pick.drawn or "doesn't get" in pick.drawn[0]["embed"].description:
                    problems.append(f"picking a channel that follows Laundromai ticked {menu.ticked} and drew {pick.drawn}")
                # ticking more and saving changes that channel
                menu.which._values = ["laundromai", "maimai"]
                asyncio.run(menu.pick_accounts(_Interaction(guild=guild)))
                saved = _Interaction(guild=guild)
                asyncio.run(menu.submit(saved))
                if sorted(db.channel_sources("12")) != ["laundromai", "maimai"] or not saved.drawn or "now gets Maimai Official" not in saved.drawn[-1]["embed"].description:
                    problems.append(f"saving the menu left {db.channel_sources('12')} and drew {saved.drawn}")
                listed_now = saved.drawn[-1]["embed"].fields[0].value if saved.drawn and saved.drawn[-1]["embed"].fields else ""
                if "<#12>:" not in listed_now or "Maimai Official" not in listed_now.split("<#12>:")[1].split("\n")[0]:
                    problems.append(f"the list of channels was not brought up to date by saving: {listed_now!r}")
                # one order everywhere, the picker's, and what the channel gets is said once, not again above the list
                said_now = saved.drawn[-1]["embed"].description if saved.drawn else ""
                if "currently gets" in said_now or "Maimai Official, Laundromai" not in listed_now:
                    problems.append(f"after saving the menu said {said_now!r} over {listed_now!r}")
                # a test post: the latest post of the account picked, any of them, through the channel's webhook, once in a while
                if [option.value for option in menu.test.options] != list(SOURCES):
                    problems.append(f"the test picker listed {[option.value for option in menu.test.options]}, not every account")
                menu.test._values = ["preformai"]      # one the channel does not get
                if menu.test.disabled:
                    problems.append("the test post stayed off for a channel that gets news")
                command._history_at.clear()
                asked.clear()
                # picking an account asks how many of its posts to send
                opened = _Interaction(guild=guild)
                asyncio.run(menu.pick_test(opened))
                box = getattr(opened, "modal", None)
                if not isinstance(box, command.TestPosts) or box.key != "preformai" or box.count.default != "1":
                    problems.append(f"picking a test account opened {box!r}")
                    box = command.TestPosts(menu, "preformai")
                for typed in ("abc", "0", str(command.MAX_HISTORY + 1)):
                    wrong = _Interaction(guild=guild)
                    box.count._value = typed
                    asyncio.run(box.on_submit(wrong))
                    if asked or "Type a number" not in (wrong.said[0] if wrong.said else ""):
                        problems.append(f"{typed!r} test posts asked for {asked} and said {wrong.said}")
                tried = _Interaction(guild=guild)
                box.count._value = "3"
                asyncio.run(_and_let_tasks_run(box.on_submit(tried)))
                if asked != [("12", ["preformai"], 3)] or "Sending the latest 3 Preformai International posts" not in (tried.said[0] if tried.said else "") or not tried.drawn:
                    problems.append(f"three test posts asked for {asked} and said {tried.said}")
                again = _Interaction(guild=guild)
                asyncio.run(menu.send_test(again, "maimai"))
                if len(asked) != 1 or "a moment ago" not in (again.said[0] if again.said else ""):
                    problems.append(f"a second test post straight away was allowed: {again.said}")
                command._history_at.clear()
                # a channel the bot cannot see is explained, with the button that adds it
                menu.where._values = [type("Picked", (), {"id": 404, "mention": "<#404>"})()]
                blind = _Interaction(guild=guild)
                asyncio.run(menu.pick_channel(blind))
                if not blind.said or "<#404>" not in blind.said[0] or menu.channel is not followed:
                    problems.append(f"a channel the bot cannot see was answered with {blind.said}, or replaced the one picked before")

            # the unsubscribe menu: every channel and what it follows, and stopping the ones picked
            db.add_news_subscription("77", "13", "maimai", URL + "13")
            listed = _Interaction(guild=_Guild(77, [_Channel(12), _Channel(13), _Channel(14, user_ok=False)]))
            db.add_news_subscription("77", "14", "maimai", URL + "14")
            asyncio.run(unsubscribe.callback(listed))
            menu = listed.sent[0].get("view") if listed.sent else None
            shown = listed.sent[0]["embed"].description if listed.sent and "embed" in listed.sent[0] else ""
            if not isinstance(menu, command.UnsubscribeMenu) or "<#12>: Laundromai, Maimai Official" not in shown and "<#12>: Maimai Official, Laundromai" not in shown or "<#13>: Maimai Official" not in shown:
                problems.append(f"/news unsubscribe showed {shown!r}")
            else:
                menu.which._values = ["13", "14"]
                asyncio.run(menu.pick(_Interaction()))
                done = _Interaction()
                asyncio.run(menu.submit(done))
                note = done.drawn[-1]["embed"].description if done.drawn else ""
                if db.channel_sources("13") or db.channel_sources("14") != ["maimai"] or ("deleted", URL + "13") not in fetched or "Manage Webhooks" not in note:
                    problems.append(f"stopping two channels, one the person may not manage, left {db.channel_sources('13')}, {db.channel_sources('14')} and said {note!r}")
                if "13" in [option.value for option in menu.which.options]:
                    problems.append("a stopped channel stayed in the picker")
            nothing = _Interaction(guild_id=4040, guild=_Guild(4040))
            asyncio.run(unsubscribe.callback(nothing))
            if "No channels here" not in (nothing.said[0] if nothing.said else ""):
                problems.append(f"a server following nothing was told {nothing.said}")
        # every command checks the person themselves: a server may open the commands to everyone in its settings
        for command_ in (subscribe, unsubscribe, manage):
            for allowed in (False, True):
                said = _Interaction()
                said.permissions = discord.Permissions(send_messages=True, manage_webhooks=allowed)
                try:
                    passed = all([asyncio.run(c(said)) if asyncio.iscoroutinefunction(c) else c(said) for c in command_.checks])
                except discord.app_commands.MissingPermissions as error:
                    passed = False
                    asyncio.run(core.on_app_command_error(said, error))
                    if not said.said or "**Manage Webhooks**" not in said.said[0] or said.sent[0].get("ephemeral") is not True:
                        problems.append(f"somebody without Manage Webhooks running /news {command_.name} was told {said.said}")
                if passed is not allowed:
                    problems.append(f"/news {command_.name} {'refused' if allowed else 'let in'} somebody {'with' if allowed else 'without'} Manage Webhooks")
        said = _Interaction()
        asyncio.run(core.on_app_command_error(said, discord.app_commands.MissingPermissions(["manage_guild"])))
        if "**Manage Server**" not in said.said[0]:
            problems.append(f"a missing Manage Server was named as {said.said}")
        # a channel option the bot cannot see, on any command, is explained the same way
        hidden = type("Hidden", (), {"mention": "<#31337>", "__str__": lambda self: "logs"})()
        error = discord.app_commands.TransformerError(hidden, discord.AppCommandOptionType.channel,
                                                      discord.app_commands.transformers.BaseChannelTransformer(discord.TextChannel))
        needed = discord.Permissions(view_channel=True, send_messages=True, embed_links=True, attach_files=True, read_message_history=True,
                                     use_external_emojis=True, manage_webhooks=True).value
        kept_guild = core.bot.get_guild
        try:
            for member, expect in ((True, "give me **View Channel**"), (False, "I'm not in this server")):
                core.bot.get_guild = lambda guild_id, member=member: object() if member else None
                said = _Interaction()
                asyncio.run(core.on_app_command_error(said, error))
                view = said.sent[0].get("view") if said.sent else None
                link = view.children[0].url if view is not None and view.children else ""
                query = parse_qs(urlparse(link).query)
                if len(said.said) != 1 or "<#31337>" not in said.said[0] or expect.lower() not in said.said[0].lower() or "went wrong" in said.said[0]:
                    problems.append(f"a channel the bot cannot see ({'member' if member else 'only installed to an account'}) was answered with {said.said}")
                if (query.get("guild_id") != ["77"] or query.get("client_id") != ["4242"] or query.get("disable_guild_select") != ["true"]
                        or int(query.get("permissions", ["0"])[0]) & needed != needed or "applications.commands" not in query.get("scope", [""])[0]):
                    problems.append(f"the link to add the bot ({'member' if member else 'only installed to an account'}) was not for this server with everything it needs: {link}")
        finally:
            core.bot.get_guild = kept_guild
    finally:
        core.bot._connection.application_id = kept_application
        discord.Webhook.from_url = kept
        NewsWatch.history = kept_history
        command._history_at.clear()
    return problems


@check("the account's answer to somebody else is never carried in a thread, one channel's network failure leaves the rest sent, and a gone webhook removes only its own rows")
def _review():
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    did = news.SOURCES["preformai"].did

    def node(uri, author, replies=()):
        return {"$type": "app.bsky.feed.defs#threadViewPost", "post": {"uri": uri, "author": {"did": author}, "record": {"text": uri, "createdAt": uri}},
                "replies": list(replies)}
    thread = node("1", did, [node("2", "fan", [node("3", did)]), node("4", did, [node("5", did)])])

    async def fake_json(session, url, params=None):
        return {"thread": thread}
    kept_json = news._get_json
    news._get_json = fake_json
    try:
        found, _ = asyncio.run(news.bluesky_thread(None, "1", did))
    finally:
        news._get_json = kept_json
    if [p["uri"] for p in found] != ["1", "4", "5"]:
        problems.append(f"a thread carried {[p['uri'] for p in found]}: the account answering a fan is not the account continuing its post")

    if news.trusted("https://[x/a.jpg") or news.trusted("https://[::1]@cdn.bsky.app/a.jpg") or not news.trusted("https://cdn.bsky.app/a.jpg"):
        problems.append("a malformed address was trusted, or raised, or a good one was refused")

    with _scratch(), _no_session():
        # one channel's connection fails: the others still get the post, and nothing is removed
        for n in range(4):
            db.add_news_subscription("g", f"c{n}", "maimai", URL + str(n))
        with _webhooks(lambda url, options: "network" if url.endswith("1") else None) as sent:
            reached = asyncio.run(tasks.NewsWatch().publish(news.Post("maimai", "p", "https://x.com/a/status/1", "n", parts=["hi"])))
        if reached != 3 or len(sent) != 3 or len(db.news_subscribers("maimai")) != 4:
            problems.append(f"one channel's network failure reached {reached} of 4 and left {len(db.news_subscribers('maimai'))} subscribed")

        # too big to attach: the text goes with its link free to draw the preview, as nothing else shows the media
        with _webhooks(lambda url, options: "big" if options.get("files") else None) as sent:
            post = news.Post("maimai", "p", "https://x.com/a/status/1", "n", parts=["hi"], images=["https://cdn.bsky.app/a.jpg"])
            asyncio.run(tasks.NewsWatch()._deliver("c0", URL + "0", post, [("a.png", b"x")]))
        if len(sent) != 1 or "<https://x.com/a/status/1>" in sent[0][1]["content"] or "https://x.com/a/status/1" not in sent[0][1]["content"]:
            problems.append("a post sent without its too-big media still hid its link preview")

        # the webhook a send failed on is gone; a newer one the channel moved to in the meantime stays
        db.add_news_subscription("g", "m", "maimai", URL + "old")
        db.add_news_subscription("g", "m", "laundromai", URL + "new")
        with _webhooks(lambda url, options: "gone") as sent:
            asyncio.run(tasks.NewsWatch()._deliver("m", URL + "old", news.Post("maimai", "p", "u", "n", parts=["hi"]), []))
        if db.channel_sources("m") != ["laundromai"]:
            problems.append(f"a gone webhook removed {db.channel_sources('m')} left, not just its own row")

        # a source the bot no longer has stops counting against the server
        db.add_news_subscription("g", "s", "search", URL)
        db.remove_unknown_news_sources(news.SOURCES)
        if db.channel_sources("s") or not db.channel_sources("c0"):
            problems.append("a removed source's rows were kept, or a real one went with them")

    # an account nobody followed for a while is only learned when somebody follows it again
    source = news.SOURCES["maimai"]

    def made(seconds_ago, n=0):
        return str(((int((time.time() - seconds_ago) * 1000) - news.TWITTER_EPOCH_MS) << 22) + n)
    items = {"now": [news.FeedItem(made(3600), "a", "https://n/maimai_official/status/1", "", False, source.handle)]}

    async def fake_feed(session, username, tries=0):
        return items["now"], ""

    async def fake_build(session, src, entry, avatar):
        return news.Post(src.key, entry.id, entry.link, src.label, parts=[entry.title], posted_at=news.tweet_time(entry.id))
    kept = news.fetch_feed, news.build_x_post
    news.fetch_feed, news.build_x_post = fake_feed, fake_build
    try:
        with _scratch(), _no_session():
            watch = tasks.NewsWatch()
            sent_ids = []

            async def record(post):
                sent_ids.append(post.id)
                return 1
            watch.publish = record
            db.add_news_subscription("g", "c", "maimai", URL)
            asyncio.run(watch.poll(source))                    # the first look learns
            items["now"] = [news.FeedItem(made(1800, 1), "b", "https://n/maimai_official/status/2", "", False, source.handle)] + items["now"]
            if asyncio.run(watch.poll(source, learn=True)) or sent_ids or db.news_unseen("maimai", [items["now"][0].id]):
                problems.append(f"a look that only learns sent {sent_ids}, or did not record what it saw")
    finally:
        news.fetch_feed, news.build_x_post = kept

    # A was sent long ago; B answers it and C answers B a moment later. B's thread carries C, so C is not sent again on its own
    bsky = news.SOURCES["preformai"]
    a, b, c = (f"at://{did}/app.bsky.feed.post/{k}" for k in "abc")
    published = []

    async def thread_build(session, src, record, uri):
        await asyncio.sleep(0.02)
        carried = [b, c] if uri == b else [uri]
        return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=[record["text"]]), carried

    async def record_publish(post):
        published.append(post.id)
        return 1
    kept_build, kept_wait = news.build_bluesky_post, news.THREAD_WAIT_SECONDS
    news.build_bluesky_post, news.THREAD_WAIT_SECONDS = thread_build, 0
    try:
        with _scratch(), _no_session():
            db.add_news_subscription("g", "b", "preformai", URL, maimai_only=True)
            db.news_mark_seen("preformai", [a])
            watch = tasks.NewsWatch()
            watch.publish = record_publish
            to_b = {"text": "and more", "reply": {"root": {"uri": a}, "parent": {"uri": a}}}
            to_c = {"text": "and more still", "reply": {"root": {"uri": a}, "parent": {"uri": b}}}

            async def together():
                await asyncio.gather(watch.bluesky_post(bsky, to_b, b), watch.bluesky_post(bsky, to_c, c))
            asyncio.run(together())
    finally:
        news.build_bluesky_post, news.THREAD_WAIT_SECONDS = kept_build, kept_wait
    if published != [b]:
        problems.append(f"a reply and a reply to it arriving together sent {published}, not the first carrying both")
    return problems


@check("a post cannot hide one link behind another, and ffmpeg reading a video playlist can only fetch over https")
def _disguises():
    from rasmai.scraping import news

    problems = []
    disguised = "[x.com/maimai_official](https://evil.example)"
    post = news.Post("maimai", "1", "https://x.com/a/status/1", "n", parts=[disguised], follow_up=("https://x.com/a/status/0", disguised))
    shown = post.content()
    if "](" in shown.replace("[their earlier post](<https://x.com/a/status/0>)", ""):
        problems.append(f"a masked link in a post or in the post it answers still draws as a link: {shown!r}")
    if "[their earlier post](<https://x.com/a/status/0>)" not in shown or shown.replace(news.ZWSP, "").count(disguised) != 2:
        problems.append(f"the follow-up's own link or the post's words were lost: {shown!r}")

    args = news._playlist_args("https://video.bsky.app/a/playlist.m3u8", "out.mp4")
    allowed = args[args.index("-protocol_whitelist") + 1].split(",") if "-protocol_whitelist" in args else []
    if not allowed or args.index("-protocol_whitelist") > args.index("-i") or {"file", "http"} & set(allowed) or "https" not in allowed:
        problems.append(f"ffmpeg is not held to https before it opens the playlist: {args}")
    if "-tls_verify" not in args or args[args.index("-tls_verify") + 1] != "1" or args.index("-tls_verify") > args.index("-i"):
        problems.append(f"ffmpeg does not check the playlist's certificate: {args}")
    return problems


@check("a post to hundreds of channels frees each upload, retries only what may pass, never drops a channel over an answer Discord did not give, keeps Bluesky in order and sends earlier posts one request at a time")
def _scale():
    from collections import Counter
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    seen_logs = []

    class Collect(logging.Handler):
        def emit(self, record):
            seen_logs.append(record.getMessage())
    handler, logger = Collect(), logging.getLogger(tasks.__name__)
    logger.addHandler(handler)

    async def fake_bytes(session, url, limit=0):
        return b"\x89PNG" + b"0" * 10
    kept = news.fetch_bytes, news.recent_posts, news.build_bluesky_post, news.THREAD_WAIT_SECONDS, tasks.SEND_TIMEOUT, tasks.UPLOAD_BUDGET
    news.fetch_bytes = fake_bytes
    post = news.Post("maimai", "p", "https://x.com/a/status/1", "n", parts=["hi"], images=["https://cdn.bsky.app/a.jpg"], videos=[b"video"])

    def channels(count, source="maimai"):
        for n in range(count):
            db.add_news_subscription("g", f"c{n}", source, URL + str(n))

    def publish(post, behave):
        attempts = Counter()

        def counted(url, options):
            attempts[url[-1]] += 1
            return behave(url[-1], attempts[url[-1]])
        with _webhooks(counted) as sent:
            started = time.monotonic()
            reached = asyncio.run(tasks.NewsWatch().publish(post))
        return reached, sent, attempts, time.monotonic() - started
    try:
        with _no_session():
            # every upload's buffer is closed once sent: discord.py keeps it open, and aiohttp's copy of it lives until a full collection
            with _scratch():
                channels(2)
                _r, sent, _a, _t = publish(post, lambda n, tries: None)
                if not sent or not all(file.fp.closed for _u, options in sent for file in options["files"]):
                    problems.append("an attachment's buffer was left open after its send")

            # a 403 or 404 with no Discord code came from in front of Discord: it says nothing about the webhook
            with _scratch():
                channels(4)
                outcomes = {"0": "edge403", "1": "edge404", "2": "denied", "3": "gone"}
                publish(post, lambda n, tries: outcomes[n])
                following = [db.channel_sources(f"c{n}") for n in range(4)]
                if following != [["maimai"], ["maimai"], [], []]:
                    problems.append(f"after a Cloudflare 403, a Cloudflare 404, Missing Permissions and Unknown Webhook the channels follow {following}")

            # a send that hangs is given up on, so it cannot hold a slot for long
            with _scratch():
                channels(2)
                tasks.SEND_TIMEOUT = 0.05
                reached, _s, attempts, took = publish(post, lambda n, tries: "slow" if n == "0" else None)
                tasks.SEND_TIMEOUT = kept[4]
                if tasks.SEND_AT_ONCE != 10 or reached != 1 or took > 0.8:
                    problems.append(f"a hung send was not cut off ({reached} reached in {took:.2f}s), or {tasks.SEND_AT_ONCE} sends run at once, not 10")

            # too many bytes for every channel: the link draws the media instead
            with _scratch():
                channels(2)
                tasks.UPLOAD_BUDGET = 20
                reached, sent, _a, _t = publish(post, lambda n, tries: None)
                tasks.UPLOAD_BUDGET = kept[5]
                if reached != 2 or any("files" in options or "<https://x.com/a/status/1>" in options["content"] for _u, options in sent):
                    problems.append("media over the upload budget was still attached to every channel, or its link was not left to unfurl")

            # one send failing in a way nobody foresaw does not stop the rest, and the post counts as sent where it arrived
            with _scratch():
                channels(2)
                try:
                    reached, _s, _a, _t = publish(post, lambda n, tries: "boom" if n == "0" else None)
                    if reached != 1:
                        problems.append(f"an unexpected failure in one channel left {reached} reached, not 1")
                except RuntimeError:
                    problems.append("an unexpected failure in one channel stopped the post, so it would be sent to every channel again")

            # a dropped connection is tried once more; a refusal is not, nor a 5xx, which discord.py has already tried five times
            with _scratch():
                channels(4)
                outcomes = {"0": lambda tries: "network" if tries == 1 else None, "1": lambda tries: "broken", "2": lambda tries: "bad", "3": lambda tries: None}
                reached, _s, attempts, _t = publish(post, lambda n, tries: outcomes[n](tries))
                if reached != 2 or dict(attempts) != {"0": 2, "1": 1, "2": 1, "3": 1}:
                    problems.append(f"a passing failure was not retried once, or a refusal was: reached {reached}, attempts {dict(attempts)}")

            # earlier posts for many servers go one request at a time
            with _scratch():
                state = {"busy": 0, "most": 0}

                async def two(session, source, count, only=None):
                    return [news.Post(source.key, str(n), "https://x.com/a/status/1", "n", parts=["hi"]) for n in range(2)]
                news.recent_posts = two
                watch = tasks.NewsWatch()

                async def deliver(channel_id, url, post, files):
                    state["busy"] += 1
                    state["most"] = max(state["most"], state["busy"])
                    await asyncio.sleep(0.02)
                    state["busy"] -= 1
                    return True
                watch._deliver = deliver

                async def both():
                    return await asyncio.gather(watch.history("a", URL, ["maimai"], 2), watch.history("b", URL, ["maimai"], 2))
                if asyncio.run(both()) != [2, 2] or state["most"] != 1:
                    problems.append(f"two servers' earlier posts were sent {state['most']} at a time, not one")

            # a video post and a text post right after it: the video's slower build does not let the text overtake it
            with _scratch():
                bsky = news.SOURCES["preformai"]
                channels(1, "preformai")
                published = []

                async def build(session, src, record, uri):
                    await asyncio.sleep(0.3 if uri.endswith("v") else 0)
                    return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=[record["text"]]), [uri]
                news.build_bluesky_post, news.THREAD_WAIT_SECONDS = build, 0
                watch = tasks.NewsWatch()

                async def record(post):
                    published.append(post.id[-1])
                    return 1
                watch.publish = record

                async def arrive():
                    async def later():
                        await asyncio.sleep(0.1)
                        await watch.bluesky_post(bsky, {"text": "maimai text"}, f"at://{bsky.did}/app.bsky.feed.post/t")
                    await asyncio.gather(watch.bluesky_post(bsky, {"text": "maimai video"}, f"at://{bsky.did}/app.bsky.feed.post/v"), later())
                asyncio.run(arrive())
                if published != ["v", "t"]:
                    problems.append(f"a video post and a text post after it went out as {published}")
    finally:
        news.fetch_bytes, news.recent_posts, news.build_bluesky_post, news.THREAD_WAIT_SECONDS, tasks.SEND_TIMEOUT, tasks.UPLOAD_BUDGET = kept
        logger.removeHandler(handler)
    if any("SECRETTOKEN" in line or "discord.com/api" in line for line in seen_logs):
        problems.append("a webhook URL was logged")
    return problems


@check("a server can add its own Bluesky or X account by handle or link: it is looked up, listed under its own name, read without the maimai filter, picked up by both loops, and forgotten once no channel follows it")
def _added():
    from rasmai.bot.commands import news as command
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    for text, expect in (("someone.bsky.social", ("Bluesky", "someone.bsky.social")), ("@someone", ("X", "someone")), ("some_one", ("X", "some_one")),
                         ("https://bsky.app/profile/a.example.com/post/3k", ("Bluesky", "a.example.com")),
                         ("https://x.com/Laundromai/status/1", ("X", "Laundromai")), ("twitter.com/maimai_official", ("X", "maimai_official")),
                         ("did:plc:abc123", ("Bluesky", "did:plc:abc123")), ("way_too_long_for_an_x_name", ("", "")),
                         ("has space", ("", "")), ("", ("", ""))):
        if news.parse_account(text) != expect:
            problems.append(f"{text!r} was read as {news.parse_account(text)}, not {expect}")
    if news.feed_title(b"<rss><channel><title>Laundromai / @laundromai</title></channel></rss>") != "Laundromai" or news.feed_title(b"nope") != "":
        problems.append("an X account's name was not read from its feed's title")
    if news._label("Discord News", "dn.bsky.social") != "dn.bsky.social" or news._label("", "@x") != "@x":
        problems.append("a name Discord refuses for a webhook was used, or an empty one was")

    async def fake_json(session, url, params=None):
        return {"did": "did:plc:zz", "handle": "fan.bsky.social", "displayName": "Fan Page"} if (params or {}).get("actor") == "fan.bsky.social" else None

    async def fake_feed(session, username, tries=0):
        if username.lower() != "fanx":
            return [], ""
        news._titles["fanx"] = "Fan X"
        return [news.FeedItem("1", "hi", "https://n/FanX/status/1", "", False, "FanX")], ""
    kept = news._get_json, news.fetch_feed
    news._get_json, news.fetch_feed = fake_json, fake_feed
    try:
        found = [asyncio.run(news.find_account(None, text)) for text in ("@fan.bsky.social", "https://x.com/fanx", "nobody.bsky.social", "@nobody")]
    finally:
        news._get_json, news.fetch_feed = kept
    fan = news.Source("bsky:did:plc:zz", "Fan Page", "Bluesky", "fan.bsky.social", "did:plc:zz")
    fanx = news.Source("x:fanx", "Fan X", "X", "FanX")
    if found != [fan, fanx, None, None]:
        problems.append(f"looking accounts up gave {found}")

    async def fake_find(session, text):
        return {"fan": fan, "fanx": fanx, "maimai_official": news.Source("x:maimai_official", "Maimai Official", "X", "maimai_official")}.get(text)
    kept_find = news.find_account
    news.find_account = fake_find
    try:
        with _scratch(), _no_session():
            tasks.load_sources()
            menu = command.SubscribeMenu(1, 77, {}, 0)
            asyncio.run(menu.add_account(_Interaction(), "fan"))
            labels = {option.value: option.label for option in menu.which.options}
            if labels.get(fan.key) != "Fan Page" or fan.key not in menu.ticked:
                problems.append(f"an added account was not listed under its name and ticked: {labels}, ticked {menu.ticked}")
            if any("(" in label for label in labels.values()):
                problems.append(f"the accounts still say where they come from: {list(labels.values())}")
            command._lookup_at.clear()
            asyncio.run(menu.add_account(_Interaction(), "maimai_official"))
            if "x:maimai_official" in [option.value for option in menu.which.options] or len(menu.which.options) != len(news.SOURCES) + 1 or "maimai" in menu.added:
                problems.append("a built-in account typed in again was listed twice")
            command._lookup_at.clear()
            nope = _Interaction()
            asyncio.run(menu.add_account(nope, "zzz"))
            if not nope.said or "Couldn't find" not in nope.said[0]:
                problems.append(f"an account that could not be found was answered with {nope.said}")
            # saving keeps the account and follows it, under its name
            menu.channel = _Channel(40)
            saved = _Interaction()
            asyncio.run(menu.submit(saved))
            if fan.key not in db.channel_sources("40") or tasks.all_sources().get(fan.key) != fan:
                problems.append(f"saving did not keep the added account: {db.channel_sources('40')}")
            if not saved.drawn or "Fan Page" not in saved.drawn[-1]["embed"].description or "Fan Page" not in saved.drawn[-1]["embed"].fields[0].value:
                problems.append(f"the saved account was not shown by name: {saved.drawn[-1]['embed'].description if saved.drawn else None}")
            # the Bluesky stream is asked for it, and its posts go out whatever they are about; Preformai's still need to be about maimai
            if "did:plc:zz" not in asyncio.run(tasks.NewsWatch()._followed_bluesky()):
                problems.append("the Bluesky stream would not be asked for an added account")
            built = []

            async def fake_build(session, src, record, uri):
                built.append(src.key)
                return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=["x"]), [uri]

            async def fake_publish(post):
                return 1
            kept_build, kept_wait = news.build_bluesky_post, news.THREAD_WAIT_SECONDS
            news.build_bluesky_post, news.THREAD_WAIT_SECONDS = fake_build, 0
            try:
                watch = tasks.NewsWatch()
                watch.publish = fake_publish
                db.add_news_subscription("77", "41", "preformai", URL, maimai_only=True)
                preformai = news.SOURCES["preformai"]
                asyncio.run(watch.bluesky_post(fan, {"text": "lunch photo"}, "at://did:plc:zz/app.bsky.feed.post/1"))
                asyncio.run(watch.bluesky_post(preformai, {"text": "A new song in #CHUNITHM"}, f"at://{preformai.did}/app.bsky.feed.post/2"))
            finally:
                news.build_bluesky_post, news.THREAD_WAIT_SECONDS = kept_build, kept_wait
            if built != [fan.key]:
                problems.append(f"posts were built for {built}: an added account sends everything, Preformai only its maimai posts")
            # the open stream is closed for a new set of accounts, so it can be opened again asking for them
            kept_every = tasks.ALIVE_EVERY
            tasks.ALIVE_EVERY = 0

            async def changed():
                return True
            try:
                asyncio.run(tasks.NewsWatch().read(_Socket(["quiet"]), {}, changed))
            except IndexError:
                problems.append("a Jetstream connection kept reading after the accounts to follow changed")
            finally:
                tasks.ALIVE_EVERY = kept_every
            # the X loop reads an added X account
            db.add_news_source(fanx.key, "X", fanx.handle, "", fanx.label)
            db.add_news_subscription("77", "42", fanx.key, URL)
            looked = []

            async def poll(src, learn=False):
                looked.append(src.key)
                return 0

            class Stop(BaseException):
                pass

            async def stop(seconds):
                raise Stop
            watch = tasks.NewsWatch()
            watch.poll = poll
            kept_sleep = tasks.asyncio.sleep
            tasks.asyncio.sleep = stop
            kept_gap, tasks.POLL_GAP_MAX = tasks.POLL_GAP_MAX, 0         # no staggering: this check counts rounds by the sleep between them
            try:
                asyncio.run(watch._x_loop())
            except Stop:
                pass
            finally:
                tasks.asyncio.sleep = kept_sleep
                tasks.POLL_GAP_MAX = kept_gap
            if fanx.key not in looked:
                problems.append(f"the X loop looked at {looked}, not the added X account")
            # forgotten once no channel follows it; one still followed stays, with its subscription
            db.remove_news_subscription("40")
            db.news_mark_seen("maimai", ["9"])
            db.news_mark_seen(fanx.key, ["9"])
            db.remove_unknown_news_sources(news.SOURCES)
            if db.news_seen_any(fan.key) or not db.news_seen_any("maimai") or not db.news_seen_any(fanx.key):
                problems.append("the sweep kept the seen posts of a forgotten account, or dropped those of one still read")
            tasks.load_sources()
            if fan.key in tasks.all_sources() or fanx.key not in tasks.all_sources() or db.channel_sources("42") != [fanx.key]:
                problems.append(f"after the sweep the added accounts were {[k for k in tasks.all_sources() if ':' in k]}")
            # removing an added account stops it in every channel here the person may manage, and a channel left with nothing loses its webhook
            for cid in ("43", "44", "45"):
                db.add_news_subscription("77", cid, fanx.key, URL + cid)
            db.add_news_subscription("77", "43", "maimai", URL + "43")
            dropped = []

            async def drop(url):
                dropped.append(url)
            kept_drop = command._drop_webhook
            command._drop_webhook = drop
            try:
                menu = command.SubscribeMenu(1, 77, db.guild_news("77"), 0)
                if [option.value for option in menu.drop.options] != [fanx.key] or menu.drop.disabled:
                    problems.append(f"the remove picker listed {[option.label for option in menu.drop.options]}, not just the added account")
                db.add_news_subscription("77", "46", fanx.key, URL + "46")      # after the menu opened
                menu.drop._values = [fanx.key]
                gone = _Interaction(guild=_Guild(77, [_Channel(42), _Channel(43), _Channel(45, user_ok=False)]))
                asyncio.run(menu.remove_account(gone))
                # one typed in and never saved just leaves the list
                menu.added[fan.key] = fan
                menu._fill(set())
                menu.drop._values = [fan.key]
                asyncio.run(menu.remove_account(_Interaction()))
            finally:
                command._drop_webhook = kept_drop
            note = gone.drawn[-1]["embed"].description if gone.drawn else ""
            left = {cid: db.channel_sources(cid) for cid in ("42", "43", "44", "45", "46")}
            shown = gone.drawn[-1]["embed"].fields[0].value if gone.drawn else ""
            if left != {"42": [], "43": ["maimai"], "44": [], "45": [fanx.key], "46": []} or sorted(dropped) != [URL, URL + "44", URL + "46"] \
                    or "Removed **Fan X** from" not in note or "Manage Webhooks" not in note or "<#41>" in note or "<#44>" in shown:
                problems.append(f"removing an added account left {left}, deleted {len(dropped)} webhook(s) and said {note!r}")
            if fan.key in menu.added or fan.key in [option.value for option in menu.which.options + menu.drop.options]:
                problems.append("an unsaved account stayed listed after it was removed")
    finally:
        news.find_account = kept_find
        tasks._added = {}
    return problems


@check("an added account cannot hold up the others: a busy Bluesky one is capped, X accounts are read side by side and a dead one is tried on few instances, the cap on added accounts holds on Save, and an account's own name cannot pose as a link")
def _added_limits():
    from rasmai.bot.commands import news as command
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    fan = news.Source("bsky:did:plc:zz", "[Verify](https://evil.example)", "Bluesky", "fan.bsky.social", "did:plc:zz")
    fanx = news.Source("x:fanx", "Fan X", "X", "FanX")
    preformai, maimai = news.SOURCES["preformai"], news.SOURCES["maimai"]
    with _scratch(), _no_session():
        db.add_news_source(fan.key, "Bluesky", fan.handle, fan.did, fan.label)
        db.add_news_source(fanx.key, "X", fanx.handle, "", fanx.label)
        for cid, key in (("50", fan.key), ("51", fanx.key), ("52", "maimai"), ("53", "preformai")):
            db.add_news_subscription("77", cid, key, URL)
        tasks.load_sources()
        try:
            if db.followed_news_keys() != {fan.key, fanx.key, "maimai", "preformai"}:
                problems.append(f"the followed accounts were read as {db.followed_news_keys()}")
            # a burst from an added Bluesky account: only CATCH_UP are built, the rest are marked seen; a built-in one is never cut
            built = []

            async def fake_build(session, src, record, uri):
                built.append(src.key)
                return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=["x"]), [uri]

            async def fake_publish(post):
                return 1

            async def burst(source, text):
                watch = tasks.NewsWatch()
                watch.publish = fake_publish
                await asyncio.gather(*(watch.bluesky_post(source, {"text": text}, f"at://{source.did}/app.bsky.feed.post/{n}") for n in range(tasks.CATCH_UP + 3)))
                await watch.bluesky_post(source, {"text": text}, f"at://{source.did}/app.bsky.feed.post/later")      # the burst over, it sends again
            kept_build, kept_wait = news.build_bluesky_post, news.THREAD_WAIT_SECONDS
            news.build_bluesky_post, news.THREAD_WAIT_SECONDS = fake_build, 0
            try:
                asyncio.run(burst(fan, "lunch"))
                asyncio.run(burst(preformai, "maimai news"))
            finally:
                news.build_bluesky_post, news.THREAD_WAIT_SECONDS = kept_build, kept_wait
            if built.count(fan.key) != tasks.CATCH_UP + 1 or built.count("preformai") != tasks.CATCH_UP + 4:
                problems.append(f"a burst built {built.count(fan.key)} posts of an added account and {built.count('preformai')} of Preformai")
            if db.news_unseen(fan.key, [f"at://{fan.did}/app.bsky.feed.post/{n}" for n in range(tasks.CATCH_UP + 3)]):
                problems.append("the posts of a burst that were not built were not marked seen, so a reconnect would send them")
            # the X loop reads accounts side by side: the first waits on one read after it, which a loop reading one at a time never reaches
            gate, done = asyncio.Event(), []

            async def poll(src, learn=False):
                if src.key == "maimai":
                    await asyncio.wait_for(gate.wait(), 2)
                else:
                    gate.set()
                done.append(src.key)

            class Stop(BaseException):
                pass

            async def stop(seconds):
                raise Stop
            watch = tasks.NewsWatch()
            watch.poll = poll
            kept_sleep = tasks.asyncio.sleep
            tasks.asyncio.sleep = stop
            kept_gap, tasks.POLL_GAP_MAX = tasks.POLL_GAP_MAX, 0         # no staggering: this check counts rounds by the sleep between them
            try:
                asyncio.run(watch._x_loop())
            except Stop:
                pass
            finally:
                tasks.asyncio.sleep = kept_sleep
                tasks.POLL_GAP_MAX = kept_gap
            if sorted(done) != sorted(["maimai", "preformai", fanx.key]):      # Preformai is read on X as well
                problems.append(f"the X loop finished {done}: it reads one account at a time, or skipped one")
            # an added X account is tried on few instances, a built-in one on all
            tries = []

            async def counting_feed(session, username, tries_left=0):
                tries.append((username, tries_left))
                return [], ""
            kept_feed = news.fetch_feed
            news.fetch_feed = counting_feed
            try:
                asyncio.run(tasks.NewsWatch().poll(fanx))
                asyncio.run(tasks.NewsWatch().poll(maimai))
            finally:
                news.fetch_feed = kept_feed
            if tries != [("FanX", news.LOOKUP_TRIES), ("maimai_official", len(news.RSS_INSTANCES))]:
                problems.append(f"the X accounts were read with {tries}")
            # an account's own name is escaped where markdown is drawn, and left as it is in a picker
            if not command._name(fan.key).startswith("\\[") or command._names([fan.key], plain=True) != fan.label:
                problems.append(f"an account's name was shown as {command._name(fan.key)!r}")
            # the cap on added accounts is checked again on Save
            kept_max = command.MAX_ADDED
            command.MAX_ADDED = db.followed_news_source_count()
            try:
                late = news.Source("x:late", "Late", "X", "late")
                said = _Interaction()
                done_text = asyncio.run(command.save_channel(said, _Channel(54), [late.key], added={late.key: late}))
            finally:
                command.MAX_ADDED = kept_max
            if done_text is not None or db.channel_sources("54") or not said.said or said.said[0] != command.ADDED_FULL:
                problems.append(f"saving an account past the cap gave {done_text!r}, said {said.said} and left {db.channel_sources('54')}")
        finally:
            tasks._added = {}
    return problems


@check("Preformai is read on Bluesky and on X and each post is sent once, from whichever site has it first, while the same words said twice on one site are both sent, X posts of other games are not, and the X side only learns at a start")
def _both_sites():
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    preformai = news.SOURCES["preformai"]
    x = news.x_side(preformai)
    if (x.key, x.platform, x.handle, x.did, x.maimai_only) != ("preformai", "X", "performaien", "", True):
        problems.append(f"Preformai's X side is {x}")
    # the same post as each site gives it: Bluesky shortens the link and writes the mention as a domain
    sky = "New song in #maimai DX!\n\npreformai.com/news/2026… @performaien.bsky.social"
    tweet = "New song in #maimai DX! https://preformai.com/news/2026/10/08 @performaien"
    if news.copy_mark(sky) != news.copy_mark(tweet) or not news.copy_mark(sky) or news.copy_mark("Image") != "":
        problems.append(f"the two copies of a post were marked {news.copy_mark(sky)!r} and {news.copy_mark(tweet)!r}")

    def tweet_id(seconds_ago=60):
        return str(((int(time.time()) - seconds_ago) * 1000 - news.TWITTER_EPOCH_MS) << 22)
    feed = []

    async def fake_feed(session, username, tries=0):
        return list(feed), ""

    async def fake_x(session, src, item, avatar):
        return news.Post(src.key, item.id, f"https://x.com/{src.handle}/status/{item.id}", src.label, parts=[item.text])

    async def fake_build(session, src, record, uri):
        return news.Post(src.key, uri, "https://bsky.app/x", src.label, parts=[record.get("text", "")]), [uri]
    sent = []

    async def publish(post):
        sent.append(post.url)
        return 1
    kept = news.fetch_feed, news.build_x_post, news.build_bluesky_post, news.THREAD_WAIT_SECONDS
    news.fetch_feed, news.build_x_post, news.build_bluesky_post, news.THREAD_WAIT_SECONDS = fake_feed, fake_x, fake_build, 0
    try:
        with _scratch(), _no_session():
            db.add_news_subscription("77", "60", "preformai", URL, maimai_only=True)
            db.news_mark_seen("preformai", ["an earlier post"])        # not a first look
            watch = tasks.NewsWatch()
            watch.publish = publish

            def item(text, seconds_ago=60):
                tid = tweet_id(seconds_ago)
                return news.FeedItem(tid, text, f"https://n/performaien/status/{tid}", "", False, "performaien")
            # X first: its copy is sent, the Bluesky one that follows is not, and is recorded as seen
            feed[:] = [item(tweet)]
            asyncio.run(watch.poll(x))
            asyncio.run(watch.bluesky_post(preformai, {"text": sky}, f"at://{preformai.did}/app.bsky.feed.post/a"))
            if len(sent) != 1 or "x.com" not in sent[0] or db.news_unseen("preformai", [f"at://{preformai.did}/app.bsky.feed.post/a"]):
                problems.append(f"with X first, {sent} were sent")
            # Bluesky first: the X copy read later is not sent, and is recorded as seen
            sent.clear()
            later = "A new #maimai DX song arrives on 10/15, the second WEC2026 track"
            asyncio.run(watch.bluesky_post(preformai, {"text": later}, f"at://{preformai.did}/app.bsky.feed.post/b"))
            feed[:] = [item(later, 30)]
            asyncio.run(watch.poll(x))
            if sent != ["https://bsky.app/x"] or db.news_unseen("preformai", [feed[0].id]):
                problems.append(f"with Bluesky first, {sent} were sent")
            if db.news_copy_seen("preformai", news.copy_mark(later) + ":Bluesky", -3600):
                problems.append("a copy sent just now was counted as sent within a window that ended an hour ago")
            # the same words twice on one site are two posts, not copies
            sent.clear()
            for n in ("c", "d"):
                asyncio.run(watch.bluesky_post(preformai, {"text": "The #maimai DX daily bonus is back for this weekend"}, f"at://{preformai.did}/app.bsky.feed.post/{n}"))
            if len(sent) != 2:
                problems.append(f"the same words posted twice on Bluesky were sent {len(sent)} time(s)")
            # a post only on X goes out; one about another game does not, as on Bluesky
            sent.clear()
            feed[:] = [item("About #CHUNITHM KOP8TH: registration opens on 22 October 2026", 20), item("WEC2026 recap: thank you for cheering on #maimai DX", 10)]
            asyncio.run(watch.poll(x))
            if len(sent) != 1:
                problems.append(f"of an X-only maimai post and a CHUNITHM one, {len(sent)} were sent")
            # a test post or earlier posts take the latest of both sites: a post only on X counts, and a post on both comes once
            def made(seconds_ago):
                return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - seconds_ago))
            both = "New song in #maimai DX! Details on the site"
            sky_feed = {"feed": [{"post": {"uri": f"at://{preformai.did}/app.bsky.feed.post/{n}", "author": {"did": preformai.did},
                                           "record": {"text": text, "createdAt": made(ago)}}}
                                 for n, text, ago in (("both", both, 100), ("old", "A #maimai event arrives on 12/1, see you there", 500))]}

            async def fake_json(session, url, params=None):
                return sky_feed
            kept_json = news._get_json
            news._get_json = fake_json
            feed[:] = [item("About #CHUNITHM KOP8TH: registration opens on 22 October 2026", 5), item("KOP The 8th is open! Register in maimai DX-NET", 10),
                       item(both, 130)]
            try:
                latest = asyncio.run(news.recent_posts(None, preformai, 3))
            finally:
                news._get_json = kept_json
            shown = [post.parts[-1][:12] for post in latest]
            if shown != ["A #maimai ev", "New song in ", "KOP The 8th "] or "x.com" not in latest[1].url:
                problems.append(f"Preformai's latest three were {[(post.url, post.parts[-1][:20]) for post in latest]}")
            # the X side is read with the X accounts, and only learns on the first round after a start
            looked = []

            async def poll(src, learn=False):
                looked.append((src.key, src.handle, learn))

            class Stop(BaseException):
                pass
            rounds = {"n": 0}

            async def stop(seconds):
                rounds["n"] += 1
                if rounds["n"] >= 2:
                    raise Stop
            db.add_news_subscription("77", "61", "maimai", URL)
            loop = tasks.NewsWatch()
            loop.poll = poll
            kept_sleep = tasks.asyncio.sleep
            tasks.asyncio.sleep = stop
            kept_gap, tasks.POLL_GAP_MAX = tasks.POLL_GAP_MAX, 0         # no staggering: this check counts rounds by the sleep between them
            try:
                asyncio.run(loop._x_loop())
            except Stop:
                pass
            finally:
                tasks.asyncio.sleep = kept_sleep
                tasks.POLL_GAP_MAX = kept_gap
            wanted = [("maimai", "maimai_official", False), ("preformai", "performaien", True), ("maimai", "maimai_official", False), ("preformai", "performaien", False)]
            if sorted(looked) != sorted(wanted):
                problems.append(f"two rounds of the X loop read {looked}")
    finally:
        news.fetch_feed, news.build_x_post, news.build_bluesky_post, news.THREAD_WAIT_SECONDS = kept
    return problems


@check("an X post keeps its line breaks, its links are their full address, and its mentions and hashtags read as written")
def _x_text():
    from rasmai.scraping import news

    problems = []
    described = ('<p>And its here....<br><br>🔷Registration Period:<br>\nAsk <a href="/performai">@performai</a> &amp; '
                 '<a href="/search?q=%23maimai">#maimai</a><br>\n<a href="https://maimai.sega.jp/kop8th/maimai/">maimai.sega.jp/kop8th/maimai…</a></p>\n'
                 '<img src="https://pbs.twimg.com/media/a.jpg" />')
    item = news.FeedItem("1", "And its here.... 🔷Registration Period: Ask @performai & #maimai maimai.sega.jp/kop8th/maimai…", "", described, False)
    wanted = "And its here....\n\n🔷Registration Period:\nAsk @performai & #maimai\nhttps://maimai.sega.jp/kop8th/maimai/"
    if item.text != wanted:
        problems.append(f"an X post read as {item.text!r}")
    nitter = news.RSS_INSTANCES[0]
    linked = news.FeedItem("2", "x", "", f'<p>see <a href="{nitter}/someone/status/9">this post</a></p>', False)
    if linked.text != "see this post" or news.FeedItem("3", "R to @me: plain title", "", "", False).text != "plain title":
        problems.append(f"a Nitter link or a post without a description read as {linked.text!r}")
    # an instance that hands out its pictures through its own proxy, over http from another host, as x.n0g.xyz does
    proxied = (b'<rss><channel><image><url>http://pics.example/pic/https%3A%2F%2Fpbs.twimg.com%2Fprofile_images%2F1%2Fa_400x400.jpg</url></image>'
               b'<item><title>t</title><link>https://n/me/status/5</link><description>&lt;p&gt;t&lt;/p&gt;'
               b'&lt;img src="http://pics.example/pic/media%2FHUK.jpg" /&gt;&lt;img src="/pic/orig/media%2FHUL.jpg" /&gt;</description></item></channel></rss>')
    items, avatar = news.parse_feed(proxied)
    if avatar != "https://pbs.twimg.com/profile_images/1/a_400x400.jpg" or not items \
            or news.media_urls(items[0].description) != ["https://pbs.twimg.com/media/HUK.jpg", "https://pbs.twimg.com/media/HUL.jpg"]:
        problems.append(f"a proxied avatar and pictures read as {avatar!r} and {news.media_urls(items[0].description) if items else None}")
    return problems


@check("posts made minutes apart all go out, oldest first, however many land in one look, while a backlog after a gap is still cut to the newest few")
def _burst():
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news

    from rasmai.storage import db

    problems = []
    kop = news.SOURCES["kop"]
    if (kop.platform, kop.handle, kop.maimai_only) != ("X", "kop_sega", False):
        problems.append(f"KING of Performai is {kop}")

    def item(seconds_ago):
        tid = str(((int(time.time()) - seconds_ago) * 1000 - news.TWITTER_EPOCH_MS) << 22)
        return news.FeedItem(tid, f"post {seconds_ago}", f"https://n/kop_sega/status/{tid}", "", False, "kop_sega")
    feed = []

    async def fake_feed(session, username, tries=0):
        return list(reversed(feed)), ""         # newest first, as a feed lists them

    async def fake_x(session, src, it, avatar):
        return news.Post(src.key, it.id, it.link, src.label, parts=[it.text])
    sent = []

    async def publish(post):
        sent.append(post.parts[0])
        return 1
    kept = news.fetch_feed, news.build_x_post
    news.fetch_feed, news.build_x_post = fake_feed, fake_x
    try:
        with _scratch(), _no_session():
            db.add_news_subscription("77", "70", "kop", URL)
            db.news_mark_seen("kop", ["an earlier post"])        # not a first look
            watch = tasks.NewsWatch()
            watch.publish = publish
            # six announcements in four minutes, as KOP8th's were, all seen in one look
            feed[:] = [item(seconds) for seconds in (240, 200, 170, 150, 120, 60)]
            asyncio.run(watch.poll(kop))
            if sent != [f"post {seconds}" for seconds in (240, 200, 170, 150, 120, 60)]:
                problems.append(f"a burst of six posts sent {sent}")
            # hours of posts missed while the bot was down, then two new ones: the old ones are cut to make the newest few
            sent.clear()
            feed[:] = [item(seconds) for seconds in range(3 * 3600, 2 * 3600, -600)] + [item(90), item(30)]
            asyncio.run(watch.poll(kop))
            if len(sent) != tasks.CATCH_UP or sent[-2:] != ["post 90", "post 30"]:
                problems.append(f"a backlog of {len(feed) - 2} old posts and two new ones sent {sent}")
            if db.news_unseen("kop", [it.id for it in feed]):
                problems.append("the posts cut from a backlog were not marked seen")
    finally:
        news.fetch_feed, news.build_x_post = kept
    return problems


@check("/news manage lists only the channels that get news, opens one to change or test it, stops one the person may manage, and clears a deleted one")
def _manage():
    from rasmai.bot.commands import news as command
    from rasmai.storage import db

    problems = []
    dropped = []

    async def drop(url):
        dropped.append(url)
    kept = command._drop_webhook
    command._drop_webhook = drop
    try:
        with _scratch(), _no_session():
            db.add_news_subscription("77", "80", "maimai", URL + "80")
            db.add_news_subscription("77", "80", "laundromai", URL + "80")
            db.add_news_subscription("77", "81", "preformai", URL + "81", maimai_only=True)
            db.add_news_subscription("77", "82", "kop", URL + "82")       # its channel was deleted
            guild = _Guild(77, [_Channel(80), _Channel(81, user_ok=False)])
            opened = _Interaction(guild=guild)
            asyncio.run(command.manage.callback(opened))
            menu = opened.sent[0].get("view") if opened.sent else None
            if not isinstance(menu, command.ManageMenu):
                return [f"/news manage answered {opened.said}"]
            listed = [(option.value, option.label, option.description) for option in menu.where.options]
            if listed != [("80", "#chan80", "Maimai Official, Laundromai"), ("81", "#chan81", "Preformai International"), ("82", "A deleted channel", "KING of Performai")]:
                problems.append(f"the channels listed were {listed}")
            # opening one ticks what it gets; unticking one and saving stops only that one
            menu.where._values = ["80"]
            asyncio.run(menu.pick_channel(_Interaction(guild=guild)))
            if menu.channel is None or menu.channel.id != 80 or menu.ticked != ["maimai", "laundromai"] or menu.stop_here.disabled or menu.save.disabled:
                problems.append(f"opening a channel ticked {menu.ticked} with stop {'off' if menu.stop_here.disabled else 'on'}")
            menu.which._values = ["maimai"]
            asyncio.run(menu.pick_accounts(_Interaction(guild=guild)))
            asyncio.run(menu.submit(_Interaction(guild=guild)))
            if db.channel_sources("80") != ["maimai"]:
                problems.append(f"saving a managed channel left {db.channel_sources('80')}")
            # stopping it removes its news and its webhook, and it leaves the list
            stopped = _Interaction(guild=guild)
            asyncio.run(menu.stop_news(stopped))
            if db.channel_sources("80") or [url for url in dropped if url] != [URL + "80"] or "80" in [option.value for option in menu.where.options] or menu.channel is not None:
                problems.append(f"stopping a channel left {db.channel_sources('80')}, deleted {dropped}, and listed {[option.value for option in menu.where.options]}")
            # one the person may not manage stays
            menu.where._values = ["81"]
            asyncio.run(menu.pick_channel(_Interaction(guild=guild)))
            refused = _Interaction(guild=guild)
            asyncio.run(menu.stop_news(refused))
            if db.channel_sources("81") != ["preformai"] or not refused.said or "Manage Webhooks" not in refused.said[0]:
                problems.append(f"stopping a channel the person may not manage left {db.channel_sources('81')} and said {refused.said}")
            # a deleted one has nobody to ask, so picking it clears it
            menu.where._values = ["82"]
            gone = _Interaction(guild=guild)
            asyncio.run(menu.pick_channel(gone))
            if db.channel_sources("82") or not gone.drawn or "deleted" not in gone.drawn[-1]["embed"].description:
                problems.append(f"picking a deleted channel left {db.channel_sources('82')}")
            nothing = _Interaction(guild_id=4040, guild=_Guild(4040))
            asyncio.run(command.manage.callback(nothing))
            if "No channels here" not in (nothing.said[0] if nothing.said else ""):
                problems.append(f"a server with no news was told {nothing.said}")
    finally:
        command._drop_webhook = kept
    return problems


@check("each channel chooses which accounts send it only their maimai posts: Preformai starts that way and keeps it from before, a post goes only where it may, and an account is read in full while any channel wants all of it")
def _maimai_choice():
    import sqlite3

    from rasmai.bot.commands import news as command
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    from rasmai.storage import db

    problems = []
    with _scratch() as store:
        # a database from before the choice: Preformai's channels keep the filter they always had, the others get everything
        old = sqlite3.connect(store.DATABASE_PATH)
        old.execute("CREATE TABLE news_subscriptions (channel_id TEXT NOT NULL, source TEXT NOT NULL, guild_id TEXT NOT NULL, webhook TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (channel_id, source))")
        old.executemany("INSERT INTO news_subscriptions VALUES (?, ?, '77', 'x', 'then')", [("1", "preformai"), ("1", "maimai")])
        old.commit()
        old.close()
        if db.news_channel_filters("preformai") != {"1": True} or db.news_channel_filters("maimai") != {"1": False}:
            problems.append(f"after the upgrade the filters were {db.news_channel_filters('preformai')} and {db.news_channel_filters('maimai')}")
    with _scratch(), _no_session():
        # a channel that starts following an account gets its default
        asyncio.run(command.save_channel(_Interaction(), _Channel(2), ["preformai", "maimai", "kop"]))
        if db.guild_maimai_only("77") != {"2": {"preformai"}}:
            problems.append(f"a new channel's filters were {db.guild_maimai_only('77')}")
        # two channels following Maimai Official, one of them only for maimai posts
        db.add_news_subscription("77", "3", "maimai", URL + "3")
        db.add_news_subscription("77", "4", "maimai", URL + "4")
        db.set_channel_maimai_only("3", ["maimai"])
        if db.news_channel_filters("maimai") != {"2": False, "3": True, "4": False}:
            problems.append(f"setting a channel's filter gave {db.news_channel_filters('maimai')}")
        reached = []

        async def deliver(channel_id, url, post, files, unfurl=False):
            reached.append((post.id, channel_id))
            return True
        watch = tasks.NewsWatch()
        watch._deliver = deliver
        for post_id, about in (("chunithm", False), ("maimai", True)):
            asyncio.run(watch.publish(news.Post("maimai", post_id, "https://x.com/m/status/1", "Maimai Official", about_maimai=about)))
        if sorted(reached) != [("chunithm", "2"), ("chunithm", "4"), ("maimai", "2"), ("maimai", "3"), ("maimai", "4")]:
            problems.append(f"posts reached {sorted(reached)}")
        # the account is read in full while one channel wants all of it, and only for maimai once every channel filters
        if asyncio.run(watch._only_maimai(news.SOURCES["maimai"])):
            problems.append("Maimai Official was read for maimai posts only while two channels want all of it")
        db.set_channel_maimai_only("2", ["preformai", "maimai"])
        db.set_channel_maimai_only("4", ["maimai"])
        if not asyncio.run(watch._only_maimai(news.SOURCES["maimai"])) or asyncio.run(watch._only_maimai(news.SOURCES["laundromai"])):
            problems.append("an account every channel filters was read in full, or one nobody follows was taken as filtered")
        # earlier posts follow the channel's own choice
        asked = []

        async def recent(session, source, count, only=None):
            asked.append(only)
            return []
        kept = news.recent_posts
        news.recent_posts = recent
        try:
            db.set_channel_maimai_only("4", [])
            asyncio.run(watch.history("3", URL, ["maimai"], 1))
            asyncio.run(watch.history("4", URL, ["maimai"], 1))
        finally:
            news.recent_posts = kept
        if asked != [True, False]:
            problems.append(f"earlier posts were read with the maimai filter {asked}")
        # the menu: a button opens the choice, picking applies it, and the list marks it
        menu = command.SubscribeMenu(1, 77, db.guild_news("77"), 0)
        guild = _Guild(77, [_Channel(4), _Channel(5, user_ok=False)])
        menu.where._values = [type("Picked", (), {"id": 4, "mention": "<#4>"})()]
        asyncio.run(menu.pick_channel(_Interaction(guild=guild)))
        opened = _Interaction(guild=guild)
        asyncio.run(menu.open_only(opened))
        choice = opened.sent[0].get("view") if opened.sent else None
        if menu.only.disabled or not isinstance(choice, command.MaimaiOnly) or [option.value for option in choice.pick.options] != ["maimai"]:
            problems.append(f"the maimai-only button opened {choice!r}")
        else:
            choice.pick._values = ["maimai"]
            chose = _Interaction(guild=guild)
            asyncio.run(choice.choose(chose))
            listed = menu.embed().fields[0].value
            if db.news_channel_filters("maimai").get("4") is not True or "<#4>: Maimai Official (maimai only)" not in listed or not chose.drawn:
                problems.append(f"choosing maimai only for a channel left {db.news_channel_filters('maimai')} and listed {listed!r}")
            menu.channel = _Channel(5, user_ok=False)
            refused = _Interaction(guild=guild)
            asyncio.run(choice.choose(refused))
            if "Manage Webhooks" not in (refused.said[0] if refused.said else ""):
                problems.append(f"somebody without Manage Webhooks choosing a filter was told {refused.said}")

    # whether a built post is about maimai: its own words, or for a follow-up, the post it continues
    async def parent(session, post_id, handle):
        return ("https://x.com/m/status/1", "A new #maimai DX song is out")
    kept_parent = news.syndication_parent
    news.syndication_parent = parent
    try:
        about = [asyncio.run(news.build_x_post(None, news.SOURCES["maimai"], news.FeedItem("1", text, "", "", False, "maimai_official", reply), "")).about_maimai
                 for text, reply in (("A #CHUNITHM event this weekend", ""), ("A #maimai event this weekend", ""), ("Fix: the level is 13+", "maimai_official"))]
    finally:
        news.syndication_parent = kept_parent
    if about != [False, True, True]:
        problems.append(f"X posts were taken as about maimai: {about}")
    # earlier posts and test posts from an account only on X follow the filter too, and a link to SEGA's site is not maimai
    kop = news.SOURCES["kop"]
    feed = [news.FeedItem(str(n), text, f"https://n/kop_sega/status/{n}", "", False, "kop_sega") for n, text in
            ((3, "The CHUNITHM course is here! https://maimai.sega.jp/kop8th/chunithm/"), (2, "The maimai DX song is here! https://maimai.sega.jp/kop8th/maimai/"),
             (1, "The ONGEKI songs are here! https://maimai.sega.jp/kop8th/ongeki/"))]

    async def fake_feed(session, username, tries=0):
        return feed, ""
    kept_feed = news.fetch_feed
    news.fetch_feed = fake_feed
    try:
        filtered = [post.id for post in asyncio.run(news.recent_posts(None, kop, 3, True))]
        everything = [post.id for post in asyncio.run(news.recent_posts(None, kop, 3, False))]
    finally:
        news.fetch_feed = kept_feed
    if filtered != ["2"] or everything != ["1", "2", "3"]:
        problems.append(f"KOP's earlier posts were {filtered} with the maimai filter and {everything} without")
    return problems


@check("a post fits Discord's 2000 characters however many pings are made inert in it, a feed's pictures and a record's blobs can only point at the places trusted, and a dead webhook's token counts as gone")
def _limits():
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping import news
    problems = []
    quote = "q" * 140
    post = news.Post("maimai", "1", "https://x.com/a/status/1", "Maimai", parts=["@everyone " * 400], posted_at=1_800_000_000, follow_up=("https://x.com/a/status/0", quote))
    text = post.content()
    if len(text) > 2000 or "@everyone" in text.replace("@" + news.ZWSP + "everyone", ""):
        problems.append(f"a long post of pings came out {len(text)} characters, or with a live ping")
    short = news.Post("maimai", "1", "https://x.com/a/status/1", "Maimai", parts=["hello"]).content()
    if "hello" not in short or "…" in short:
        problems.append(f"a short post was cut: {short!r}")
    for blob in ("../../x", "abc?d=1", "a/b", 5, None, ""):
        images, videos = news.bluesky_media({"embed": {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": blob}}}]}}, "did:plc:x")
        more, clips = news.bluesky_media({"embed": {"$type": "app.bsky.embed.video", "video": {"ref": {"$link": blob}}}}, "did:plc:x")
        if images or videos or more or clips:
            problems.append(f"a blob {blob!r} was put into an address")
    images, _ = news.bluesky_media({"embed": {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": "bafkreih" + "a" * 40}}}]}}, "did:plc:x")
    if len(images) != 1:
        problems.append("a real content id was refused")
    feed = b"<rss><channel><image><url>%s</url></image><item><title>t</title><link>https://n/a/status/1</link></item></channel></rss>"
    for address, kept in (("https://pbs.twimg.com/profile_images/1/a.jpg", True), ("https://evil.example/a.png", False), ("http://pbs.twimg.com/a.jpg", False)):
        _items, avatar = news.parse_feed(feed % address.encode())
        if bool(avatar) != kept:
            problems.append(f"a feed's picture at {address} was {'dropped' if kept else 'kept'}")
    if 50027 not in tasks.GONE_CODES:
        problems.append("a webhook answering Invalid Webhook Token is kept and tried on every post")
    if len(news.FeedItem("1", "t", "", "<p>" + "<a " * 100000 + "</p>", False).text) > 20000:
        problems.append("a feed's description was read whole")
    return problems


@check("the X loop outlives a database that fails for a moment, and starting the news again restarts a loop that ended without doubling the one running")
def _loops():
    from rasmai.bot.tasks import news as tasks
    problems = []
    calls = []

    def keys():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is locked")
        return set()
    kept = tasks.followed_news_keys, tasks.load_sources, tasks.POLL_EVERY, tasks.remove_unknown_news_sources
    tasks.followed_news_keys, tasks.load_sources, tasks.POLL_EVERY, tasks.remove_unknown_news_sources = keys, lambda: {}, 0.01, lambda sources: None

    async def run():
        watch = tasks.NewsWatch()
        loop = asyncio.create_task(watch._x_loop())
        await asyncio.sleep(0.3)
        alive = not loop.done()
        loop.cancel()
        return alive, len(calls)

    async def restart():
        watch = tasks.NewsWatch()
        started = []

        async def forever(name):
            started.append(name)
            await asyncio.sleep(60)
        watch._bluesky_loop, watch._x_loop = (lambda: forever("bluesky")), (lambda: forever("x"))
        watch.start()
        await asyncio.sleep(0)
        watch.start()
        await asyncio.sleep(0)
        watch._tasks[1].cancel()
        await asyncio.sleep(0.01)
        watch.start()
        await asyncio.sleep(0)
        for task in watch._tasks:
            task.cancel()
        return started
    try:
        alive, seen = asyncio.run(run())
        if not alive or seen < 3:
            problems.append(f"one failed read of the database ended the X loop (alive {alive}, {seen} reads)")
        started = asyncio.run(restart())
        if started != ["bluesky", "x", "x"]:
            problems.append(f"starting the news again started {started}, not just the loop that had ended")
    finally:
        tasks.followed_news_keys, tasks.load_sources, tasks.POLL_EVERY, tasks.remove_unknown_news_sources = kept
    return problems


@check("a channel the bot cannot see is only changed by someone with Manage Webhooks across the server, a deleted one by anybody who may use the command, and adding accounts is spaced out and capped per server")
def _unseen():
    import discord
    import time
    import types
    from rasmai.bot.commands import news as command
    from rasmai.scraping.news import Source
    problems = []

    class Hidden(_Guild):
        async def fetch_channel(self, cid):
            raise discord.Forbidden(type("R", (), {"status": 403, "reason": "Forbidden"})(), "Missing Access")

    def person(server_wide):
        who = _Interaction().user
        who.guild_permissions = _Perms(server_wide)
        return types.SimpleNamespace(user=who, guild_id=77)

    async def ask(guild, server_wide, channel=None):
        return await command._refusal_for(person(server_wide), guild, channel, "5")
    if asyncio.run(ask(_Guild(), False)):
        problems.append("a deleted channel's news could not be cleared by someone who may use the command")
    if not asyncio.run(ask(Hidden(), False)) or asyncio.run(ask(Hidden(), True)):
        problems.append("a channel the bot cannot see was open to someone with Manage Webhooks in only another channel, or shut to someone with it everywhere")
    if not asyncio.run(ask(_Guild(), False, _Channel(5, user_ok=False))):
        problems.append("a channel the person cannot manage was not refused")

    with _scratch():
        menu = command.SubscribeMenu(1, 77, {}, 0)
        command._lookup_at[1] = time.monotonic()
        wait = _Interaction()
        asyncio.run(menu.add_account(wait, "fan"))
        if not wait.said or "One lookup at a time" not in wait.said[0]:
            problems.append(f"a second lookup straight away was answered with {wait.said}")
        command._lookup_at.clear()

        from rasmai.storage import db
        extras = {f"x:fan{n}": Source(f"x:fan{n}", f"Fan {n}", "X", f"fan{n}") for n in range(command.MAX_EXTRA_PER_SERVER + 1)}
        guild = _Guild(77)
        channel = _Channel(5)
        channel.guild = guild
        guild.channels[5] = channel
        refused = _Interaction(guild=guild)
        result = asyncio.run(command.save_channel(refused, channel, list(extras), 0, extras))
        if result is not None or not refused.said or "of its own choosing" not in refused.said[0]:
            problems.append(f"a server following {len(extras)} accounts of its own choosing was told {refused.said}")
        allowed = _Interaction(guild=guild)
        asyncio.run(command.save_channel(allowed, channel, list(extras)[:command.MAX_EXTRA_PER_SERVER], 0, extras))
        if db.guild_news("77").get("5", []) != list(extras)[:command.MAX_EXTRA_PER_SERVER]:
            problems.append(f"{command.MAX_EXTRA_PER_SERVER} accounts of its own choosing were not allowed: {db.guild_news('77')}")
    return problems


@check("X accounts are read one after another across the cycle, not all at once, and each is read again one cycle after its last look began")
def _spread():
    import time
    from rasmai.bot.tasks import news as tasks
    from rasmai.scraping.news import Source
    problems = []
    accounts = {f"x:a{n}": Source(f"x:a{n}", f"A{n}", "X", f"a{n}") for n in range(5)}
    looks = []
    kept = tasks.followed_news_keys, tasks.load_sources, tasks.POLL_EVERY, tasks.remove_unknown_news_sources
    tasks.followed_news_keys, tasks.load_sources, tasks.POLL_EVERY, tasks.remove_unknown_news_sources = lambda: set(accounts), lambda: accounts, 1.0, lambda sources: None
    tasks.POLL_GAP_MAX = 30

    async def run():
        watch = tasks.NewsWatch()

        async def poll(source, learn=False):
            looks.append((source.key, time.monotonic()))
            await asyncio.sleep(0.05)       # a look takes a moment; the next cycle must still start on time
            return 0
        watch.poll = poll
        loop = asyncio.create_task(watch._x_loop())
        await asyncio.sleep(2.3)
        loop.cancel()
    try:
        asyncio.run(run())
    finally:
        tasks.followed_news_keys, tasks.load_sources, tasks.POLL_EVERY, tasks.remove_unknown_news_sources = kept
        tasks.POLL_GAP_MAX = 30
    first = sorted(at for key, at in looks if key in accounts)[:5]
    if len(first) < 5 or first[-1] - first[0] < 0.4:
        problems.append(f"the first five looks began within {first[-1] - first[0] if first else 0:.2f}s of each other, all at once")
    own = sorted(at for key, at in looks if key == "x:a0")
    if len(own) < 2 or not 0.9 < own[1] - own[0] < 1.1:
        problems.append(f"an account was looked at again {own[1] - own[0] if len(own) > 1 else 0:.2f}s later, not one cycle after its look began")
    return problems


@check("a database that already holds a news table of another shape is mended instead of failing every read, with the old rows kept under another name")
def _old_tables():
    import sqlite3
    from rasmai.storage import db
    from rasmai.bot.tasks import news as tasks
    problems = []
    with _scratch() as store:
        old = sqlite3.connect(store.DATABASE_PATH)
        old.execute("CREATE TABLE news_subscriptions (channel_id TEXT, guild_id TEXT, webhook TEXT)")
        old.execute("INSERT INTO news_subscriptions VALUES ('c0', 'g0', 'sealed')")
        old.execute("CREATE TABLE news_seen (post_id TEXT)")
        old.commit()
        old.close()
        try:
            db.add_news_subscription("g1", "c1", "maimai", URL)
            keys = db.followed_news_keys()
            db.remove_unknown_news_sources(tasks.SOURCES)
        except sqlite3.OperationalError as error:
            problems.append(f"a news table of an older shape still broke the queries: {error}")
            return problems
        if keys != {"maimai"}:
            problems.append(f"the subscription made after the repair was read back as {keys}")
        connection = db.get_database_connection()
        names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'news_%unfit%'")]
        kept = [row[0] for name in names if name.startswith("news_subscriptions") for row in connection.execute(f"SELECT channel_id FROM {name}")]
        connection.close()
        if len(names) != 2 or kept != ["c0"]:
            problems.append(f"the old tables were {names} holding {kept}, not set aside with their rows")
    return problems


@check("/news is offered in servers the app is only installed to an account in, where picking a channel hands out the link that adds the bot, and never in a DM")
def _installs():
    from rasmai.bot.commands import news as command
    problems = []
    group = command.news
    if not (group.allowed_installs.guild and group.allowed_installs.user):
        problems.append("/news is hidden where the app is only installed to an account, so those servers never see it")
    if group.allowed_contexts.dm_channel or group.allowed_contexts.private_channel or not group.allowed_contexts.guild:
        problems.append("/news can be run outside a server, where a webhook has no channel")
    return problems


@check("/invite offers the app install and a server install that asks for every permission the bot needs and lets the person pick any server, wherever it is run")
def _invite_buttons():
    from urllib.parse import parse_qs, urlparse
    from rasmai.bot import core
    from rasmai.bot.commands import account
    problems = []
    kept = core.bot._connection.application_id, account.DISCORD_BOT_INVITE
    core.bot._connection.application_id, account.DISCORD_BOT_INVITE = 4242, "https://discord.com/oauth2/authorize?client_id=4242&scope=bot"
    try:
        for guild_id in (77, None):
            asked = _Interaction(guild_id=guild_id)
            asyncio.run(account.invite.callback(asked))
            labels = {item.label: item.url for item in asked.sent[0]["view"].children}
            link = labels.get("Invite (Server)", "")
            query = parse_qs(urlparse(link).query)
            if "Invite (App Install)" not in labels or not link:
                problems.append(f"/invite in {guild_id or 'a DM'} offered {sorted(labels)}")
            if query.get("guild_id") or query.get("disable_guild_select") or int(query.get("permissions", ["0"])[0]) & core.BOT_PERMISSIONS.value != core.BOT_PERMISSIONS.value:
                problems.append(f"the server link from {guild_id or 'a DM'} was {link}")
    finally:
        core.bot._connection.application_id, account.DISCORD_BOT_INVITE = kept
    return problems
