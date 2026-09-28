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


@check("a dashboard opening six requests at once builds its analysis once, and a cached one never waits")
def _coalesced_builds():
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

    held = (A.analyzer_from_snapshot, A.resolve_unknown_later)
    A.analyzer_from_snapshot, A.resolve_unknown_later = slow_build, lambda cached, loop=None: False
    try:
        # one person, six requests at once, nothing cached: one build and six answers
        person = "coalesce-check-0"
        answers = []
        threads = [threading.Thread(target=lambda: answers.append(A.analysis_for_user(person, {})))
                   for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if running["built"] != 1:
            problems.append(f"one dashboard opening built its analysis {running['built']} times; k6 counted "
                            f"six, and a burst of fifty visitors queued three hundred of them")
        if len(answers) != 6 or any(a is None for a in answers):
            problems.append("a request that waited for somebody else's build came back with nothing")

        # many different people at once: never more building together than the cap allows
        running.update(now=0, most=0, built=0)
        threads = [threading.Thread(target=A.analysis_for_user, args=(f"coalesce-check-{n}", {}))
                   for n in range(1, 4 * ANALYSIS_BUILDS + 2)]
        for t in threads:
            t.start()
        # and somebody already cached is answered straight away, however full the queue is
        time.sleep(0.05)
        started = time.perf_counter()
        A.analysis_for_user(person, {})
        waited = time.perf_counter() - started
        for t in threads:
            t.join()
        if running["most"] > ANALYSIS_BUILDS:
            problems.append(f"{running['most']} analyses were built at once against a cap of {ANALYSIS_BUILDS}, "
                            f"and more at once is slower: 2.9 a second one at a time, 1.5 eight at a time")
        if waited > 0.1:
            problems.append(f"a cached dashboard waited {waited:.2f}s behind other people's builds")
    finally:
        A.analyzer_from_snapshot, A.resolve_unknown_later = held
        from rasmai.bot.state import cache
        for key in [k for k in list(getattr(cache, "_analysis_cache", {})) if str(k).startswith("coalesce-check")]:
            cache._analysis_cache.pop(key, None)
    if ANALYSIS_BUILDS < 1:
        problems.append("a cap below one would let nothing build at all")
    return problems
