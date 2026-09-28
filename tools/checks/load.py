from tools.checks import check


@check("the internal API queues a page's worth of requests instead of refusing the sixth")
def _backlog():
    import pathlib

    from rasmai.web import web_server

    problems = []
    queue = getattr(getattr(web_server, "_QueueingServer", None), "request_queue_size", 5)
    # the stdlib default is five, and a dashboard opens with six requests at once: two people
    # opening theirs together refused 89% of requests under k6, every one of them in 0ms
    if queue < 64:
        problems.append(f"the internal API listens with a backlog of {queue}, so a couple of dashboards "
                        f"opening at once are refused rather than queued")
    source = pathlib.Path(web_server.__file__).read_text(encoding="utf-8")
    if "= ThreadingHTTPServer((" in source:
        problems.append("the internal API is built on the bare stdlib server again, with its backlog of five")
    return problems


@check("a thread keeps its database connection, and never carries it to another database or another caller's work")
def _kept_connections():
    import pathlib
    import tempfile
    import threading

    from rasmai.storage.db import connection as store

    problems = []
    was = store.DATABASE_PATH
    first = pathlib.Path(tempfile.mkdtemp()) / "a.sqlite3"
    second = pathlib.Path(tempfile.mkdtemp()) / "b.sqlite3"
    try:
        for path in (first, second):
            store.DATABASE_PATH, store._database_ready = path, False
            c = store.get_database_connection()
            c.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
            c.commit()
            c.close()

        store.DATABASE_PATH = first
        c = store.get_database_connection()
        if store.get_database_connection() is not c:
            problems.append("a second call on the same thread opened a new connection, which is the "
                            "cost this exists to avoid: nine of them were most of the overview's time")
        c.execute("INSERT INTO t VALUES ('left uncommitted')")
        c.close()
        c = store.get_database_connection()
        if c.execute("SELECT COUNT(*) FROM t").fetchone()[0]:
            problems.append("a caller's uncommitted write survived its close and reached the next caller")
        c.close()

        # the sweep swaps the database path back and forth all the time, and a kept connection that
        # ignored the swap would write a check's rows into the real database
        store.DATABASE_PATH = second
        c = store.get_database_connection()
        c.execute("INSERT INTO t VALUES ('second only')")
        c.commit()
        c.close()
        store.DATABASE_PATH = first
        c = store.get_database_connection()
        if c.execute("SELECT COUNT(*) FROM t").fetchone()[0]:
            problems.append("a row written after the database path moved landed in the one it moved away from")
        c.close()

        other = []
        worker = threading.Thread(target=lambda: other.append(store.get_database_connection()))
        worker.start()
        worker.join()
        if other and other[0] is store.get_database_connection():
            problems.append("two threads were handed the same connection")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("a dashboard's six requests build one analysis, a crowd queues without holding threads, and a cached one never waits")
def _queued_builds():
    import threading
    import time
    import types

    from rasmai.config import ANALYSIS_BUILDS
    from rasmai.web.dashboard import analysis as A

    problems = []
    running = {"now": 0, "most": 0, "built": 0}
    guard = threading.Lock()

    def slow_build(user_id, account):
        with guard:
            running["now"] += 1
            running["built"] += 1
            running["most"] = max(running["most"], running["now"])
        time.sleep(0.15)
        with guard:
            running["now"] -= 1
        return types.SimpleNamespace(region="intl", generate_recommendations=lambda: ([], []))

    places = []

    def ask(person, into):
        started = time.perf_counter()
        try:
            into.append(("ok", A.analysis_for_user(person), time.perf_counter() - started))
        except A.StillBuilding as wait:
            into.append(("wait", wait.seconds, time.perf_counter() - started))
            places.append(wait.position)

    held = (A.analyzer_from_snapshot, A.resolve_unknown_later, A.get_connected_account)
    A.analyzer_from_snapshot, A.resolve_unknown_later = slow_build, lambda cached, loop=None: False
    A.get_connected_account = lambda user_id: {}
    try:
        # one person, six requests at once, nothing cached: one build and six answers
        person = "coalesce-check-0"
        answers = []
        threads = [threading.Thread(target=ask, args=(person, answers)) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if running["built"] != 1:
            problems.append(f"one dashboard opening built its analysis {running['built']} times; k6 counted "
                            f"six, and a burst of fifty visitors queued three hundred of them")
        if len(answers) != 6 or any(kind != "ok" or value is None for kind, value, _ in answers):
            problems.append(f"a request that waited for its own build came back without it: {answers}")

        # a crowd of new people at once: never more building together than the cap, and the ones
        # queued behind are told to come back rather than held
        running.update(now=0, most=0, built=0)
        crowd = [f"coalesce-check-{n}" for n in range(1, 4 * ANALYSIS_BUILDS + 2)]
        answers = []
        threads = [threading.Thread(target=ask, args=(p, answers)) for p in crowd]
        for t in threads:
            t.start()
        # and somebody already cached is answered straight away, however full the queue is
        time.sleep(0.05)
        started = time.perf_counter()
        A.analysis_for_user(person)
        waited = time.perf_counter() - started
        for t in threads:
            t.join()
        told = [a for a in answers if a[0] == "wait"]
        if not told:
            problems.append(f"{len(crowd)} people queued behind a cap of {ANALYSIS_BUILDS} and every request "
                            f"waited out its build: a thousand did that under k6 and held 7,700 threads")
        if any(took > 0.1 for _, _, took in told):
            problems.append(f"a request queued behind others was held {max(t for _, _, t in told):.2f}s before being told to come back")
        if any(not 2 <= seconds <= 30 for _, seconds, _ in told):
            problems.append(f"the page was told to come back after {[s for _, s, _ in told]}s, outside 2-30")
        if told and (min(places) < 2 or len(set(places)) < 2):
            problems.append(f"people queued behind others were told their places were {sorted(places)}; "
                            f"each should see where they stand, and not all the same place")
        deadline = time.monotonic() + 10
        while A._pending and time.monotonic() < deadline:
            time.sleep(0.02)
        missing = [p for p in crowd if A.cache_get(p) is None]
        if missing:
            problems.append(f"{len(missing)} queued analyses were never built")
        if running["most"] > ANALYSIS_BUILDS:
            problems.append(f"{running['most']} analyses were built at once against a cap of {ANALYSIS_BUILDS}, "
                            f"and more at once is slower: 2.9 a second one at a time, 1.5 eight at a time")
        if waited > 0.1:
            problems.append(f"a cached dashboard waited {waited:.2f}s behind other people's builds")

        # somebody with nothing to build from is answered from memory when the page asks again,
        # not sent to the back of the line each time, which in a crowd was forty trips of thirty seconds
        empty = {"builds": 0}

        def nothing(user_id, account):
            empty["builds"] += 1

        A.analyzer_from_snapshot = nothing
        for _ in range(3):
            A.analysis_for_user("coalesce-check-empty")
        if empty["builds"] != 1:
            problems.append(f"an account with nothing to build was built {empty['builds']} times in a row")
    finally:
        A._finished.pop("coalesce-check-empty", None)
        A.analyzer_from_snapshot, A.resolve_unknown_later, A.get_connected_account = held
        from rasmai.bot.state import cache
        for key in [k for k in list(getattr(cache, "_analysis_cache", {})) if str(k).startswith("coalesce-check")]:
            cache._analysis_cache.pop(key, None)
    if ANALYSIS_BUILDS < 1:
        problems.append("a cap below one would let nothing build at all")
    return problems


@check("the internal API answers from a fixed set of threads, so a crowd queues instead of being refused")
def _pooled_answers():
    import http.client
    import threading
    from http.server import BaseHTTPRequestHandler

    from rasmai.web import web_server

    problems = []
    answered_on = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            answered_on.append(threading.current_thread().name)
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = web_server._QueueingServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def ask():
            c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            c.request("GET", "/")
            c.getresponse().read()
            c.close()

        askers = [threading.Thread(target=ask) for _ in range(200)]
        for t in askers:
            t.start()
        for t in askers:
            t.join()
        strays = sorted({name for name in answered_on if name != "internal-api"})
        if strays:
            problems.append(f"requests were answered on threads started for them ({strays[:3]}...): starting one "
                            f"per connection is what stopped connections being taken, 40% refused at a thousand people")
        if len(answered_on) != 200:
            problems.append(f"{200 - len(answered_on)} of 200 requests at once went unanswered")
    finally:
        server.shutdown()
        server.server_close()
    return problems


@check("somebody waiting is built before the warm-ups, and a warmed person who asks moves to the front")
def _warm_then_asked():
    import threading
    import time
    import types

    from rasmai.config import ANALYSIS_BUILDS
    from rasmai.web.dashboard import analysis as A

    problems = []
    order = []
    guard = threading.Lock()

    def slow_build(user_id, account):
        with guard:
            order.append(user_id)
        time.sleep(0.05)
        return types.SimpleNamespace(region="intl", generate_recommendations=lambda: ([], []))

    held = (A.analyzer_from_snapshot, A.resolve_unknown_later, A.get_connected_account)
    A.analyzer_from_snapshot, A.resolve_unknown_later = slow_build, lambda cached, loop=None: False
    A.get_connected_account = lambda user_id: {}
    warmed = [f"warm-check-{n}" for n in range(12)]
    try:
        A.warm(warmed)
        time.sleep(0.01)
        asker = threading.Thread(target=lambda: A.analysis_for_user("warm-check-asker", patient=True))
        promoted = threading.Thread(target=lambda: A.analysis_for_user(warmed[-1], patient=True))
        asker.start()
        promoted.start()
        asker.join()
        promoted.join()
        deadline = time.monotonic() + 10
        while A._pending and time.monotonic() < deadline:
            time.sleep(0.02)
        # at most one warm-up per worker can already be under way when they ask; then it is their turn
        for who in ("warm-check-asker", warmed[-1]):
            if who not in order or order.index(who) > 2 * ANALYSIS_BUILDS + 1:
                problems.append(f"{who} was built {order.index(who) + 1 if who in order else 'never'} of {len(order)}, "
                                f"behind warm-ups nobody was waiting for")
        if sorted(order) != sorted(warmed + ["warm-check-asker"]):
            problems.append(f"built {len(order)} analyses for {len(warmed) + 1} people: a promoted warm-up ran twice or not at all")
    finally:
        A.analyzer_from_snapshot, A.resolve_unknown_later, A.get_connected_account = held
        from rasmai.bot.state import cache
        for key in [k for k in list(getattr(cache, "_analysis_cache", {})) if str(k).startswith("warm-check")]:
            cache._analysis_cache.pop(key, None)
    return problems
