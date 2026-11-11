from contextlib import contextmanager
from types import SimpleNamespace
import glob
import json

from tools.checks import ROOT, check
from tools.checks.stubs import stub_get

USER = "100000000000000001"

# a few songs with the title the chart database holds and the name maimai DX NET stores for them,
# which has the spaces and symbols taken out
SONGS = {
    "Oshama Scramble!": {"title": "Oshama Scramble!", "artist": "Wanko", "dx_lev_mas_i": "13.0", "dx_lev_mas": "13",
                         "dx_lev_mas_notes": "100", "lev_mas_i": "12.0", "lev_mas": "12", "lev_mas_notes": "90"},
    "Bring it on": {"title": "Bring it on", "artist": "Somebody", "dx_lev_exp_i": "10.0", "dx_lev_exp": "10",
                    "dx_lev_exp_notes": "100", "dx_lev_mas_i": "12.5", "dx_lev_mas": "12+", "dx_lev_mas_notes": "100"},
}
TIME = "2026-09-27T06:27:00+09:00"


@contextmanager
def _scratch():
    import pathlib
    import tempfile

    from rasmai.storage.db import connection as store
    was = store.DATABASE_PATH
    store.DATABASE_PATH, store._database_ready = pathlib.Path(tempfile.mkdtemp()) / "kamaitachi.sqlite3", False
    try:
        yield store
    finally:
        store.DATABASE_PATH, store._database_ready = was, False


def _index():
    from rasmai.engine.analysis import build_chart_index
    from rasmai.scraping import dxdata
    kept = dxdata.cached
    dxdata.cached = lambda: {}          # the second source is whatever is stored on this machine; the sample stands alone
    try:
        return build_chart_index(SONGS, region="intl")
    finally:
        dxdata.cached = kept


def _analyzer(index, songs, recent=()):
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import SongInfo
    a = MaimaiRatingAnalyzer()
    a._chart_index = index
    a.songs = [SongInfo(name=n, chart_type=t, difficulty_type=d, accuracy=acc, fc_status=fc, level=level)
               for n, t, d, acc, fc, level in songs]
    a.recent_songs = list(recent)
    return a


def _play(percent, fc, notes, when=TIME, title="Oshama Scramble!", kind="dx", tier="master"):
    return {"songName": title, "musicType": kind, "difficulty": tier, "achievement": int(round(percent * 10000)),
            "dxScore": 1, "maxDxScore": 300, "fc": fc, "fs": "", "track": 1, "playedAt": when,
            "judgement": {"fast": 4, "late": 2, "notes": {"tap": dict(zip(("critical", "perfect", "great", "good", "miss"), notes))}}}


def _fixture():
    songs = [("OshamaScramble!", "dx", "master", 100.9, "AP", "13"),         # a timed play says the same, so no untimed copy
             ("Bringiton", "dx", "expert", 98.5, "FC+", "10"),
             ("Bringiton", "dx", "master", 101.0, "FC", "12+"),               # 101% cannot be anything but an all perfect plus
             ("OshamaScramble!", "std", "master", 79.0, "", "12"),
             ("OshamaScramble!", "dx", "utage", 90.0, "", "13"),
             ("Nothing Like It", "dx", "master", 90.0, "", "13")]
    recent = [_play(100.9, "AP", (100, 0, 0, 0, 0)),
              _play(99.5, "AP", (0, 97, 3, 0, 0), "2026-09-27T07:00:00+09:00"),          # an all perfect with greats: one step down
              _play(101.0, "AP+", (0, 99, 1, 0, 0), "2026-09-28T07:00:00+09:00")]       # 101% with a great: nobody played that
    history = [{"key": "oshamascramble!|dx|master", "played_at": "2026-09-20T10:00:00+09:00", "achievement": 98.0, "fc": "FC", "judgement": None},
               {"key": "oshamascramble!|dx|master", "played_at": TIME, "achievement": 100.9, "fc": "AP", "judgement": None}]
    return _analyzer(_index(), songs, recent), history


def _fixed_document():
    from rasmai.bot.builders.kamaitachi import build_document
    a, history = _fixture()
    return build_document(a, history)


def _violations(document):
    """Everything wrong with a document, by Tachi's own rules."""
    from rasmai.bot.builders.kamaitachi import DIFFICULTY, LAMPS, SERVICE, broken_rule
    problems = []
    meta = document.get("meta") or {}
    if meta.get("game") != "maimaidx" or meta.get("playtype") != "Single" or not 2 <= len(str(meta.get("service"))) <= 15 or meta.get("service") != SERVICE:
        problems.append(f"the header is wrong: {meta}")
    allowed = set(DIFFICULTY.values()) | {"DX " + name for name in DIFFICULTY.values()}
    for score in document.get("scores") or []:
        percent, lamp = score.get("percent"), score.get("lamp")
        why = broken_rule(percent, lamp, score.get("judgements")) if isinstance(percent, float) and lamp in LAMPS else "unreadable percent or lamp"
        if why:
            problems.append(f"{score.get('identifier')} {percent} {lamp}: {why}")
        if score.get("matchType") != "songTitle" or score.get("difficulty") not in allowed or not str(score.get("identifier") or "").strip():
            problems.append(f"a score cannot be matched: {score}")
        if "timeAchieved" in score and (not isinstance(score["timeAchieved"], int) or score["timeAchieved"] < 10 ** 12):
            problems.append(f"the time is not unix milliseconds: {score}")
        if "judgements" in score and (sorted(score["judgements"]) != sorted(("pcrit", "perfect", "great", "good", "miss"))
                                      or set(score["optional"]) != {"fast", "slow"}):
            problems.append(f"the judgements are not what Tachi reads: {score}")
    return problems


@check("every score in a Kamaitachi file passes Tachi's own rules, for the sample and for every real export on this machine")
def _passes_validators():
    from rasmai.bot.builders.kamaitachi import build_document
    from rasmai.scraping.otoge import CachedOtogeDB
    from rasmai.storage.models import SongInfo

    problems = []
    document, _counts = _fixed_document()
    problems += [f"sample: {p}" for p in _violations(document)]
    titles = {score["identifier"] for score in document["scores"]}
    if titles != {"Oshama Scramble!", "Bring it on"}:
        problems.append(f"a score went out under the stored name instead of the chart database's title: {titles}")
    shapes = {(s["identifier"], s["difficulty"]) for s in document["scores"]}
    if ("Oshama Scramble!", "Master") not in shapes or ("Bring it on", "DX Expert") not in shapes:
        problems.append(f"standard and DX charts are not told apart: {shapes}")

    # the debug exports are the player's own and are not in the repository, so this part runs where they are
    files = sorted(glob.glob(str(ROOT / "debug" / "*.json")) + glob.glob(str(ROOT / "data" / "maimai-export-*.json")))[::10]
    database = CachedOtogeDB()
    if files and database.songs_data:
        from rasmai.engine.analysis import build_chart_index
        index = build_chart_index(database.songs_for("intl"), region="intl")
        allowed = SongInfo.__dataclass_fields__
        for path in files:
            data = json.loads(open(path, encoding="utf-8").read())
            if "player" not in data or "songs" not in data:
                continue
            a = _analyzer(index, [])
            a.songs = [SongInfo(**{k: v for k, v in row.items() if k in allowed}) for row in data["songs"]]
            a.recent_songs = data.get("recentSongsData") or []
            real, counts = build_document(a, [])
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            problems += [f"{name}: {p}" for p in _violations(real)]
            if not real["scores"] or counts["charts"] + counts["plays"] != len(real["scores"]):
                problems.append(f"{name}: the counts do not add up to the scores in the file: {counts}")
    return problems


@check("a Kamaitachi lamp is read from the fc mark, and a clear needs 80%")
def _lamps():
    from rasmai.bot.builders.kamaitachi import tachi_lamp
    table = [("AP+", 101.0, "ALL PERFECT+"), ("AP", 100.7, "ALL PERFECT"), ("FC+", 99.0, "FULL COMBO+"), ("FC", 98.0, "FULL COMBO"),
             ("ap+", 101.0, "ALL PERFECT+"), ("", 80.0, "CLEAR"), ("", 79.9999, "FAILED"), ("NONE", 90.0, "CLEAR"),
             (None, 50.0, "FAILED"), ("FDX+", 99.0, "CLEAR"), ("SYNC", 70.0, "FAILED")]
    return [f"{fc!r} at {percent} read as {tachi_lamp(fc, percent)}, not {want}" for fc, percent, want in table if tachi_lamp(fc, percent) != want]


@check("a score that would break a rule is mended where one reading is honest and left out where none is")
def _mending():
    from rasmai.bot.builders.kamaitachi import mend
    nothing = {"great": 0, "good": 0, "miss": 0}
    table = [(101.0, "FULL COMBO", None, "ALL PERFECT+"), (101.0, "ALL PERFECT+", nothing, "ALL PERFECT+"),
             (100.0, "ALL PERFECT+", None, "FULL COMBO+"), (100.7, "ALL PERFECT+", None, "ALL PERFECT"),
             (79.0, "FULL COMBO", None, "FULL COMBO"), (95.0, "FULL COMBO", None, "FULL COMBO"),
             (95.0, "ALL PERFECT", {"great": 0, "good": 0, "miss": 2}, "CLEAR"),
             (95.0, "FULL COMBO+", {"great": 1, "good": 1, "miss": 0}, "FULL COMBO"),
             (70.0, "CLEAR", None, "FAILED"), (101.0, "ALL PERFECT+", {"great": 1, "good": 0, "miss": 0}, None),
             (0.0, "CLEAR", None, None), (101.5, "ALL PERFECT+", None, None), (float("nan"), "CLEAR", None, None)]
    return [f"{p} {lamp} {j} became {mend(p, lamp, j)}, not {want}" for p, lamp, j, want in table if mend(p, lamp, j) != want]


@check("the sample file keeps timed plays, leaves out Utage and unknown charts and counts them, and never writes a contradiction")
def _sample_file():
    from rasmai.bot.builders.kamaitachi import kamaitachi_file

    problems = []
    document, counts = _fixed_document()
    want = {"charts": 3, "plays": 3, "skipped": 3, "utage": 1, "unmatched": 1, "invalid": 1, "repaired": 2}
    if counts != want:
        problems.append(f"the counts are {counts}, expected {want}")
    scores = document["scores"]
    timed = [s for s in scores if "timeAchieved" in s]
    if len(timed) != 3 or len(scores) - len(timed) != 3:
        problems.append(f"three plays and three untimed bests were expected: {len(timed)} timed of {len(scores)}")
    # the play that matches the stored best carries it, so the best is not sent again untimed
    same = [s for s in scores if s["identifier"] == "Oshama Scramble!" and s["difficulty"] == "DX Master" and s["percent"] == 100.9]
    if len(same) != 1 or "timeAchieved" not in same[0] or "judgements" not in same[0]:
        problems.append(f"the best that a timed play already says was sent twice or lost its time: {same}")
    greats = [s for s in scores if s["percent"] == 99.5]
    if len(greats) != 1 or greats[0]["lamp"] != "FULL COMBO+":
        problems.append(f"an all perfect with greats was not moved down a step: {greats}")
    if any(s["percent"] == 101.0 and "timeAchieved" in s for s in scores):
        problems.append("a 101% play with a great in it was written")
    if [s for s in scores if s["percent"] == 101.0 and s["lamp"] != "ALL PERFECT+"]:
        problems.append("101% was written without an all perfect plus")
    if any(s["identifier"] == "Nothing Like It" for s in scores):
        problems.append("a chart the database does not know was written")
    if any("utage" in s["difficulty"].lower() for s in scores):
        problems.append("an Utage chart was written")
    a, history = _fixture()
    body, name, _ = kamaitachi_file(SimpleNamespace(analyzer=a, user_id=USER))
    if not (name.startswith("rasmai-kamaitachi-") and name.endswith(".json") and len(name) == len("rasmai-kamaitachi-20260101-0000.json")):
        problems.append(f"the file name is {name}")
    if not json.loads(body).get("scores"):
        problems.append("the file holds no scores")
    return problems


class _Answer:
    def __init__(self, status=200, body=None, raw=None, location=None):
        self.status_code = status
        self._raw = raw if raw is not None else json.dumps(body).encode("utf-8")
        self.headers = {"Location": location} if location else {}
        self.closed = False

    def iter_content(self, size):
        for start in range(0, len(self._raw), size):
            yield self._raw[start:start + size]

    def close(self):
        self.closed = True


def _tachi(pbs):
    """A pbs/all answer shaped like the live API's (v3: a chart is keyed by chartID and carries its song), from
    (title, alt titles, difficulty, level, percent, lamp, time) tuples."""
    songs, charts, rows = [], [], []
    for number, (title, alts, difficulty, level, percent, lamp, when) in enumerate(pbs):
        song = {"id": f"S{number}", "title": title, "altTitles": alts, "artist": "x"}
        songs.append(song)
        charts.append({"game": "maimaidx", "chartID": f"C{number}", "song": song, "difficulty": difficulty, "level": level, "levelNum": 12.0})
        rows.append({"chartID": f"C{number}", "songID": f"S{number}", "userID": 1, "timeAchieved": when, "isPrimary": True,
                     "scoreData": {"percent": percent, "lamp": lamp, "grade": "SSS", "judgements": {"pcrit": 90, "perfect": 8, "great": 2, "good": 0, "miss": 0},
                                   "optional": {"fast": 1, "slow": 1}}})
    return {"success": True, "description": "Returned PBs.", "body": {"pbs": rows, "songs": songs, "charts": charts}}


@contextmanager
def _network(*answers):
    """requests.get answering from a list, remembering every address asked; nothing leaves the machine."""
    from rasmai.scraping import kamaitachi
    asked = []
    queue = list(answers)

    def get(url, **kwargs):
        asked.append((url, kwargs))
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    with stub_get(kamaitachi, get):
        yield asked


@check("a Kamaitachi profile is read with a checked username, one host, no redirects and a size limit")
def _client():
    import requests
    from rasmai.scraping import kamaitachi
    from rasmai.scraping.kamaitachi import KamaitachiError, fetch_pbs

    problems = []

    def kind(*answers, name="someone"):
        with _network(*answers) as asked:
            try:
                fetch_pbs(name)
            except KamaitachiError as error:
                return error.kind, str(error), asked
            return "fine", "", asked

    with _network(_Answer(body=_tachi([]))) as asked:
        for bad in ("", "a", "has space", "../x", "x" * 31, "a/b", "a?b", "名前です", None, 5):
            try:
                fetch_pbs(bad)
                problems.append(f"{bad!r} was accepted as a username")
            except KamaitachiError:
                pass
        if asked:
            problems.append(f"a refused username still made a request: {asked}")
    result, _, asked = kind(_Answer(body=_tachi([("a", [], "Master", "12", 99.0, "CLEAR", None)])), name="Some_One-9")
    if result != "fine":
        problems.append(f"a good answer was refused: {result}")
    if not asked or not all(url == "https://kamai.tachi.ac/api/v1/users/Some_One-9/games/maimaidx/pbs/all" for url, _ in asked):
        problems.append(f"the request did not go to the fixed host with the name in place: {asked}")
    for url, kwargs in asked:
        if kwargs.get("allow_redirects") is not False or not kwargs.get("timeout") or "User-Agent" not in kwargs.get("headers", {}):
            problems.append(f"the request is missing redirects off, a timeout or an agent: {kwargs}")
    if kind(_Answer(404, {"success": False, "description": "The user nobody does not exist."}))[0] != "no_such_user":
        problems.append("an unknown user was not reported as such")
    said = kind(_Answer(404, {"success": False, "description": "The user someone has not played maimaidx"}))
    if said[0] != "kamaitachi" or "no maimai DX scores" not in said[1]:
        problems.append(f"a profile without maimai DX was not told clearly: {said[:2]}")
    other = kind(_Answer(404, {"success": False, "description": "Endpoint not found"}))
    if other[0] != "kamaitachi" or len(other[2]) != 1:
        problems.append(f"a missing route should be one request and then a plain error: {other}")
    if kind(_Answer(302, {}, location="https://evil.example/"))[0] != "kamaitachi":
        problems.append("a redirect was followed or ignored")
    if kind(_Answer(200, raw=b"<html>not json"))[0] != "kamaitachi":
        problems.append("something that is not JSON was accepted")
    if kind(_Answer(200, {"success": False, "description": "no"}))[0] != "kamaitachi":
        problems.append("success: false was accepted")
    if kind(_Answer(500, {"success": False, "description": "boom"}))[0] != "kamaitachi":
        problems.append("a server error was accepted")
    if kind(requests.ConnectionError("down"))[0] != "kamaitachi":
        problems.append("a connection error was not reported")
    kept = kamaitachi.MAX_BYTES
    kamaitachi.MAX_BYTES = 100
    try:
        if kind(_Answer(200, {"success": True, "body": {"pbs": ["x" * 500]}}))[0] != "kamaitachi":
            problems.append("an answer past the size limit was read")
    finally:
        kamaitachi.MAX_BYTES = kept
    return problems


@check("personal bests from Kamaitachi are matched by title or other name, kept only when they beat what is stored, and counted")
def _import():
    from rasmai.scraping.kamaitachi import pb_rows
    from rasmai.storage.db import best_recorded_scores, load_chart_scores, record_chart_scores
    from rasmai.web.dashboard.imports import record_pbs

    problems = []
    index = _index()
    a = _analyzer(index, [])
    body = _tachi([
        ("Oshama Scramble!", [], "DX Master", "13", 100.9, "ALL PERFECT", 1790458048000),
        ("Bring it on!!", ["bring it on"], "DX Expert", "10", 98.0, "FULL COMBO", None),       # by another name, and no time
        ("Never Heard Of It", [], "DX Master", "13", 99.0, "CLEAR", None),
        ("Oshama Scramble!", [], "Master", "12", 79.0, "FAILED", 1790458048000),
        ("Oshama Scramble!", [], "WORLD'S END", "?", 90.0, "CLEAR", None),
    ])["body"]
    body["pbs"].append({"chartID": "nope", "scoreData": "broken"})
    body["pbs"].append("not even a dict")
    rows = pb_rows(body)
    if len(rows) != 4:
        problems.append(f"{len(rows)} readable bests, expected 4 (a world's end chart and two broken rows are unreadable)")
    first = rows[0] if rows else {}
    if (first.get("type"), first.get("tier"), first.get("fc"), first.get("percent")) != ("dx", "master", "AP", 100.9):
        problems.append(f"the first best was read wrong: {first}")
    with _scratch():
        record_chart_scores(USER, [("bringiton|dx|expert", "2026-09-01T10:00:00+09:00", 99.9, 2800, "FC", "", "best")])
        result = record_pbs(USER, rows, len(body["pbs"]), a, index)
        # the Oshama dx play and the std master play are new, the Bring it on best is worse than the stored 99.9, the unknown title found nothing
        want = {"bests": 0, "plays": 2, "unmatched": 4, "seen": 7}
        if result != want:
            problems.append(f"the import counted {result}, expected {want}")
        kept = best_recorded_scores(USER)
        if kept.get("bringiton|dx|expert") != 99.9:
            problems.append(f"a worse score replaced the stored one: {kept}")
        if kept.get("oshamascramble!|dx|master") != 100.9 or kept.get("oshamascramble!|std|master") != 79.0:
            problems.append(f"the scores were not stored under the names maimai DX NET gives: {sorted(kept)}")
        again = record_pbs(USER, rows, len(body["pbs"]), a, index)
        if again["bests"] or again["plays"]:
            problems.append(f"importing the same profile twice added something: {again}")
        stored = load_chart_scores(USER, ["oshamascramble!|dx|master"])
        if len(stored) != 1 or stored[0]["fc"] != "AP" or stored[0]["source"] != "play" or stored[0]["dx_score"] != 3 * 98 + 2 * 2:
            problems.append(f"the play was stored with the wrong lamp, kind or dx score: {stored}")
        fresh = record_pbs("100000000000000002", rows[1:2], 1, a, index)
        if fresh["bests"] != 1 or fresh["plays"] != 0:
            problems.append(f"a best with no time should be stored as a best: {fresh}")
    return problems


@check("exporting for Kamaitachi and importing the file back gives the same bests")
def _round_trip():
    from rasmai.scraping.kamaitachi import pb_rows
    from rasmai.storage.db import best_recorded_scores
    from rasmai.web.dashboard.imports import record_pbs

    problems = []
    a, history = _fixture()
    document, _ = _fixed_document()
    # what Kamaitachi would hold: one best per chart, the highest percent, with the lamp that goes with it
    best = {}
    for score in document["scores"]:
        key = (score["identifier"], score["difficulty"])
        if key not in best or score["percent"] > best[key]["percent"]:
            best[key] = score
    pbs = [(title, [], difficulty, "13", s["percent"], s["lamp"], s.get("timeAchieved")) for (title, difficulty), s in best.items()]
    body = _tachi(pbs)["body"]
    with _scratch():
        result = record_pbs(USER, pb_rows(body), len(body["pbs"]), a, a.chart_index)
        kept = best_recorded_scores(USER)
    want = {"oshamascramble!|dx|master": 100.9, "oshamascramble!|std|master": 79.0, "bringiton|dx|expert": 98.5, "bringiton|dx|master": 101.0}
    if kept != want:
        problems.append(f"the bests that came back are {kept}, not {want}")
    if result["unmatched"] or result["seen"] != len(pbs):
        problems.append(f"something did not match on the way back: {result}")
    return problems


@check("the Kamaitachi routes are registered, refuse a bad username before asking anyone, and limit how often a profile is read")
def _routes():
    from rasmai.bot.builders import charts as charts_package
    from rasmai.scraping.kamaitachi import KamaitachiError
    from rasmai.security import kamaitachi_limiter
    from rasmai.storage.db import upsert_connected_account
    from rasmai.web.dashboard import routes

    problems = []
    if "/internal/me/kamaitachi" not in routes.DOWNLOADS or "/internal/me/kamaitachi/import" not in routes.WRITES:
        problems.append("the download or the import is not in the route tables")

    class Handler:
        def __init__(self):
            self.sent = []

        def _send_json(self, status, body):
            self.sent.append((status, body))

    def post(user, payload):
        handler = Handler()
        routes.handle_post(handler, "/internal/me/kamaitachi/import", {"id": user}, payload)
        return handler.sent[0]

    index = _index()
    kept = charts_package.shared_index
    charts_package.shared_index = lambda: index
    kamaitachi_limiter._events.clear()
    try:
        with _scratch():
            upsert_connected_account(USER, "intl", "cookie://" + "a" * 64, {"name": "Someone", "rating": 12000})
            with _network(_Answer(body=_tachi([("Oshama Scramble!", [], "DX Master", "13", 100.9, "ALL PERFECT", None)]))) as asked:
                for bad in ({}, {"username": ""}, {"username": "no good"}, {"username": ["x"]}, None):
                    if post(USER, bad) != (400, {"ok": False, "error": "bad_username"}):
                        problems.append(f"{bad} was not refused as a bad username: {post(USER, bad)}")
                if asked:
                    problems.append("a bad username reached Kamaitachi")
                status, body = post(USER, {"username": "someone"})
                if (status, body) != (200, {"ok": True, "bests": 1, "plays": 0, "unmatched": 0, "seen": 1}):
                    problems.append(f"a good import answered {status} {body}")
            with _network(_Answer(404, {"success": False, "description": "The user nobody does not exist."})):
                if post(USER, {"username": "nobody"}) != (404, {"ok": False, "error": "no_such_user"}):
                    problems.append("an unknown user was not a 404 no_such_user")
            with _network(_Answer(500, {"success": False})):
                status, body = post(USER, {"username": "someone"})
                if status != 502 or body.get("error") != "kamaitachi" or not body.get("message"):
                    problems.append(f"a Kamaitachi failure was not a 502 with a message: {status} {body}")
            with _network(_Answer(body=_tachi([]))):
                status, body = post(USER, {"username": "someone"})
                if status != 502 or "no maimai DX scores" not in body.get("message", ""):
                    problems.append(f"a profile with no scores was not told clearly: {status} {body}")
            kamaitachi_limiter.allow(USER)          # the fifth of five
            with _network(_Answer(404, {"success": False, "description": "The user someone does not exist."})) as asked:
                status, body = post(USER, {"username": "someone"})
                if status != 429 or body.get("error") != "rate_limited" or asked:
                    problems.append(f"the sixth read in a quarter hour was not limited: {status} {body} {asked}")
                if post("100000000000000009", {"username": "someone"})[0] == 429:
                    problems.append("one person's reads used up another's")
    finally:
        charts_package.shared_index = kept
        kamaitachi_limiter._events.clear()
    if KamaitachiError("no_such_user").kind != "no_such_user":
        problems.append("the error does not carry its kind")
    return problems


@check("a public Kamaitachi profile can be all an account has, with its bests the stored scores and the rating and nothing reading maimai DX NET, "
       "or be followed beside a working maimai sign-in, which it never replaces; an expired sign-in is given up for it with every stored score kept")
def _link():
    from datetime import timedelta

    from rasmai.bot.state.snapshots import CHART_FIELDS, analyzer_from_snapshot, snapshot_charts
    from rasmai.scraping import scraper
    from rasmai.scraping.kamaitachi import REGION, KamaitachiError
    from rasmai.security import kamaitachi_limiter
    from rasmai.storage.db import best_recorded_scores, get_connected_account, mark_session_expired, quiet_reads_due, set_user_settings, upsert_connected_account
    from rasmai.storage.db.cohort import cohort_accounts
    from rasmai.web.dashboard import imports, routes

    problems = []
    if "/internal/me/kamaitachi/unfollow" not in routes.WRITES:
        problems.append("the way to stop following is not in the route table")
    index = _index()
    kept = scraper.MaimaiRatingAnalyzer
    # the builder makes its own scraper, which here must stand on the sample chart database rather than the machine's
    def sample():
        made = kept()
        made._chart_index = index
        return made
    scraper.MaimaiRatingAnalyzer = sample
    kamaitachi_limiter._events.clear()

    class Handler:
        def __init__(self):
            self.sent = []

        def _send_json(self, status, body):
            self.sent.append((status, body))

    def post(user, payload, what="import"):
        handler = Handler()
        routes.handle_post(handler, f"/internal/me/kamaitachi/{what}", {"id": user}, payload)
        return handler.sent[0]
    profile = _tachi([
        ("Oshama Scramble!", [], "DX Master", "13", 100.5, "FULL COMBO", 1790458048000),
        ("Oshama Scramble!", [], "DX Master", "13", 99.0, "CLEAR", None),              # the same chart, worse: the better one is the best
        ("Bring it on!!", ["bring it on"], "DX Expert", "10", 98.0, "FULL COMBO", None),
        ("Never Heard Of It", [], "DX Master", "13", 99.0, "CLEAR", None),
    ])
    try:
        with _scratch() as store:
            other, gone = "100000000000000002", "100000000000000005"
            connection = store.get_database_connection()
            with connection:
                # signed in on the site with nothing linked yet; `gone` is a session whose account was deleted, so it has no row at all
                connection.executemany("INSERT INTO people (user_id, created_at, terms_version, terms_accepted_at) VALUES (?, ?, ?, ?)",
                                       [(who, "2026-11-01T00:00:00", "2026-10-27", "2026-11-01T00:00:00") for who in (USER, other)])
            connection.close()
            with _network(_Answer(body=profile)) as asked:
                if post(gone, {"username": "someone"}) != (404, {"ok": False, "error": "not_found"}) or asked or get_connected_account(gone) is not None:
                    problems.append("a session that outlived its account made an account again")
            # somebody with no maimai account, which is who this is for
            with _network(_Answer(body=profile)) as asked:
                if post(USER, {"username": "no good"}) != (400, {"ok": False, "error": "bad_username"}) or asked:
                    problems.append("a bad username was not refused before Kamaitachi was asked")
                status, body = post(USER, {"username": "someone"})
            if status != 200 or not body.get("ok") or body.get("seen") != 4 or body.get("unmatched") != 1:
                problems.append(f"linking a profile answered {status} {body}")
            account = get_connected_account(USER) or {}
            charts = {(c["name"], c["chart_type"], c["difficulty_type"]): c for c in snapshot_charts(account.get("latestSnapshot"))}
            rating = int((account.get("officialProfile") or {}).get("rating") or 0)
            if account.get("region") != REGION or account.get("token") or account.get("kamaitachi") != "someone" \
                    or (account.get("officialProfile") or {}).get("name") != "someone":
                problems.append(f"the account is not kept under kamaitachi, with no sign-in, following the profile: {account.get('region')!r}, "
                                f"token {bool(account.get('token'))}, follows {account.get('kamaitachi')!r}")
            best = charts.get(("OshamaScramble!", "dx", "master")) or {}
            if len(charts) != 2 or best.get("accuracy") != 100.5 or best.get("fc_status") != "FC" or not best.get("rating"):
                problems.append(f"the stored scores are not the profile's bests, one a chart: {sorted(charts)}, {best}")
            if not rating or rating != sum(int(c["rating"]) for c in charts.values()):
                problems.append(f"the rating {rating} is not the best 50 of what the profile holds")
            # rebuilt from the store it is analysed as the international game, and nothing signs in to maimai for it
            rebuilt = analyzer_from_snapshot(USER, account)
            if rebuilt is None or rebuilt.region != "intl" or len(rebuilt.songs) != 2:
                problems.append("the stored copy does not rebuild as an analysis of the international game")
            set_user_settings(USER, {"history": True})
            if any(row["userId"] == USER for row in quiet_reads_due(timedelta(0))):
                problems.append("the daily maimai read would try to sign in for an account that has no sign-in")
            # reading it again keeps the account and adds nothing twice
            with _network(_Answer(body=profile)):
                _cached, again = imports.kamaitachi_account(USER)       # no name given: the profile it follows
            if again["bests"] or again["plays"] or (get_connected_account(USER) or {}).get("region") != REGION:
                problems.append(f"reading the profile again added {again} or changed the account")
            # a profile that is gone leaves what is stored, and one with nothing to match links nobody
            with _network(_Answer(404, {"success": False, "description": "The user someone does not exist."})):
                if post(USER, {"username": "someone"}) != (404, {"ok": False, "error": "no_such_user"}) or not snapshot_charts((get_connected_account(USER) or {}).get("latestSnapshot")):
                    problems.append("a profile that no longer exists was not a 404, or cost the stored scores")
            with _network(_Answer(body=_tachi([("Never Heard Of It", [], "DX Master", "13", 99.0, "CLEAR", None)]))):
                status, body = post(other, {"username": "someone"})
            if status != 502 or get_connected_account(other) is not None:
                problems.append(f"a profile with no chart Rasmai knows linked an account: {status} {body}")
            if post(USER, None, "unfollow") != (409, {"ok": False, "error": "only_link"}) or (get_connected_account(USER) or {}).get("kamaitachi") != "someone":
                problems.append("an account with nothing but the profile was allowed to stop following it")
            # beside a working maimai sign-in the profile is followed, not swapped in: the sign-in stays and the bests join the history
            linked = "100000000000000003"
            upsert_connected_account(linked, "intl", "cookie://" + "a" * 64, {"name": "Real", "rating": 12000})
            with _network(_Answer(body=profile)):
                status, body = post(linked, {"username": "someone"})
            held = get_connected_account(linked) or {}
            if status != 200 or held.get("region") != "intl" or not held.get("token") or held.get("kamaitachi") != "someone" \
                    or (held.get("officialProfile") or {}).get("name") != "Real" or best_recorded_scores(linked).get("oshamascramble!|dx|master") != 100.5:
                problems.append(f"following a profile beside a maimai sign-in answered {status} {body}, or cost the sign-in, or kept no scores")
            with _network(_Answer(body=profile)) as asked:
                imports.merge_followed(linked)          # what a refresh does after reading maimai
            if len(asked) != 1 or not (get_connected_account(linked) or {}).get("token"):
                problems.append("a refresh did not read the followed profile once, or it cost the sign-in")
            with _network(_Answer(500, {"success": False})):
                imports.merge_followed(linked)          # Kamaitachi down: the refresh that called this goes on
            if post(linked, None, "unfollow") != (200, {"ok": True}) or (get_connected_account(linked) or {}).get("kamaitachi"):
                problems.append("a maimai account could not stop following its profile")
            # a sign-in that expired is given up for the profile: no deletion clock, the region and every stored score kept, each chart at its better score
            expired = "100000000000000004"
            stored = {"fields": list(CHART_FIELDS), "recordedAt": "2026-11-01T10:00:00", "charts": [
                ["OshamaScramble!", "dx", "master", 99.0, 280, "13", 13.0, "", "", False, 0],       # the profile has it better
                ["Bringiton", "dx", "master", 97.0, 240, "12+", 12.5, "FC", "", False, 0],          # only maimai had this one
            ]}
            upsert_connected_account(expired, "jp", "segaid://x", {"name": "ＥＸＰ", "rating": 14000}, stored)
            mark_session_expired(expired)
            with _network(_Answer(body=profile)):
                status, body = post(expired, {"username": "someone"})
            held = get_connected_account(expired) or {}
            kept_charts = {(c["name"], c["difficulty_type"]): c["accuracy"] for c in snapshot_charts(held.get("latestSnapshot"))}
            if status != 200 or held.get("token") or held.get("sessionExpired") or held.get("region") != "jp" or held.get("kamaitachi") != "someone":
                problems.append(f"an expired account did not switch to its profile cleanly: {status} {body}, token {bool(held.get('token'))}, "
                                f"expired {held.get('sessionExpired')!r}, region {held.get('region')!r}")
            if kept_charts != {("OshamaScramble!", "master"): 100.5, ("Bringiton", "master"): 97.0, ("Bringiton", "expert"): 98.0}:
                problems.append(f"switching over did not keep the better score of each chart, or lost one maimai had: {kept_charts}")
            if (held.get("officialProfile") or {}).get("name") != "ＥＸＰ":
                problems.append("switching over renamed the player after the profile")
            if any(row[0] in (USER, expired) for row in cohort_accounts()) or not any(row[0] == linked for row in cohort_accounts()):
                problems.append("an account with no sign-in is counted in the cohort, or one with a sign-in was dropped from it")
    finally:
        scraper.MaimaiRatingAnalyzer = kept
        kamaitachi_limiter._events.clear()
    return problems
