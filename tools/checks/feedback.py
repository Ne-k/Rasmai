import json
import pathlib
import tempfile
import threading
import urllib.error
import urllib.request

from tools.checks import check


def _fresh_database():
    from rasmai.storage.db import connection as store
    was = store.DATABASE_PATH
    store.DATABASE_PATH = pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    return store, was


@check("the feedback form keeps a rating from 1 to 5 with answers cleaned and cut, refuses anything else, newest first, and counts what was said")
def _storage():
    from rasmai.storage.db import feedback
    problems = []
    store, was = _fresh_database()
    kept = feedback.FORM_MAX_ROWS
    try:
        first = feedback.add_form_feedback(5, "the best-50\x00 image\nand picks", "slow\x07 images", "  more stats  ", "me@example.com")
        for bad in ("x", 0, 6, -1, None, ""):
            if feedback.add_form_feedback(bad) is not None:
                problems.append(f"a rating of {bad!r} was kept")
        feedback.add_form_feedback(3, "a" * 5000, wish="b" * 5000, contact="c" * 5000)
        rows = feedback.form_feedback()
        if first is None or len(rows) != 2:
            problems.append(f"expected two kept answers, found {len(rows)}")
            return problems
        newest, oldest = rows
        if newest["id"] < oldest["id"]:
            problems.append("the newest answer was not listed first")
        if oldest["liked"] != "the best-50 image\nand picks" or oldest["annoyed"] != "slow images" or oldest["wish"] != "more stats":
            problems.append(f"an answer was not cleaned (control characters out, line breaks kept, ends trimmed): {oldest}")
        if (len(newest["liked"]), len(newest["wish"]), len(newest["contact"])) != (1000, 1000, 200):
            problems.append(f"long answers were not cut to 1000, 1000 and 200: {(len(newest['liked']), len(newest['wish']), len(newest['contact']))}")
        summary = feedback.form_feedback_summary()
        if summary != {"total": 2, "average": 4.0, "stars": {"1": 0, "2": 0, "3": 1, "4": 0, "5": 1}}:
            problems.append(f"the summary is wrong: {summary}")
        feedback.FORM_MAX_ROWS = 2
        if feedback.add_form_feedback(5) is not None:
            problems.append("a form that already holds as many answers as it takes kept another")
        feedback.FORM_MAX_ROWS = kept
    finally:
        feedback.FORM_MAX_ROWS = kept
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("the bot takes a feedback answer from the website only with the secret, refuses a bad rating, keeps nothing that is not text, says so when full, and the developer page lists it")
def _route():
    from rasmai.storage.db import feedback
    from rasmai.web import web_server
    from rasmai.web.dashboard import admin
    problems = []
    store, was = _fresh_database()
    kept_secret, kept_max = web_server.INTERNAL_API_SECRET, feedback.FORM_MAX_ROWS
    web_server.INTERNAL_API_SECRET = "check-only-secret"
    server = web_server.InternalApiServer(host="127.0.0.1", port=0)
    try:
        server.start()
        port = server.httpd.server_address[1]

        def post(body, secret="check-only-secret"):
            headers = {"Content-Type": "application/json"}
            if secret:
                headers["X-Rasmai-Internal"] = secret
            request = urllib.request.Request(f"http://127.0.0.1:{port}/internal/feedback", data=json.dumps(body).encode(), headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as answer:
                    return answer.status, json.loads(answer.read() or b"{}")
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read() or b"{}")

        status, body = post({"rating": 4, "liked": "the picks", "annoyed": "", "wish": "dark mode", "contact": "me#1"})
        if status != 200 or not body.get("ok"):
            problems.append(f"a good answer was refused: {status} {body}")
        for bad in ({}, {"rating": 0}, {"rating": 6}, {"rating": "lots"}, {"rating": None}, {"liked": "no rating"}):
            status, body = post(bad)
            if status != 400 or body.get("error") != "invalid_rating":
                problems.append(f"{bad} answered {status} {body}, expected 400 invalid_rating")
        status, _ = post({"rating": 3}, secret="")
        if status != 401:
            problems.append(f"an answer with no secret answered {status}, expected 401")
        status, _ = post({"rating": 3, "liked": {"a": 1}, "annoyed": ["x"], "wish": 7, "contact": None})
        rows = feedback.form_feedback()
        odd = rows[0] if rows else {}
        if status != 200 or any(odd.get(key) for key in ("liked", "annoyed", "wish", "contact")):
            problems.append(f"answers that are not text were kept as something: {status} {odd}")
        feedback.FORM_MAX_ROWS = 2
        status, body = post({"rating": 5})
        if status != 503 or body.get("error") != "full":
            problems.append(f"a full form answered {status} {body}, expected 503 full")
        feedback.FORM_MAX_ROWS = kept_max
        payload = admin.admin_payload()
        if payload.get("feedbackSummary", {}).get("total") != 2 or len(payload.get("feedback", [])) != 2:
            problems.append(f"the developer page does not list the answers: {payload.get('feedbackSummary')} {len(payload.get('feedback', []))}")
        elif payload["feedback"][1]["wish"] != "dark mode" or payload["feedback"][1]["contact"] != "me#1":
            problems.append("an answer reached the developer page without its text")
    finally:
        feedback.FORM_MAX_ROWS = kept_max
        web_server.INTERNAL_API_SECRET = kept_secret
        try:
            server.httpd.shutdown()
        except Exception:
            pass
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems


@check("a fake answer to the feedback form can be removed by the developer account only, a missing or bad id is refused, and the page's numbers follow")
def _remove():
    from rasmai.storage.db import feedback
    from rasmai.web import web_server
    from rasmai.web.dashboard import admin
    from rasmai.config import ADMIN_USER_ID
    problems = []
    store, was = _fresh_database()
    kept_secret = web_server.INTERNAL_API_SECRET
    web_server.INTERNAL_API_SECRET = "check-only-secret"
    server = web_server.InternalApiServer(host="127.0.0.1", port=0)
    try:
        server.start()
        port = server.httpd.server_address[1]
        ids = [feedback.add_form_feedback(5, "good"), feedback.add_form_feedback(1, "buy followers at spam.example"), feedback.add_form_feedback(3)]

        def remove(body, user=ADMIN_USER_ID):
            headers = {"Content-Type": "application/json", "X-Rasmai-Internal": "check-only-secret"}
            if user:
                headers["X-Rasmai-User"] = json.dumps({"id": user, "name": "x", "handle": "x", "avatar": ""})
            request = urllib.request.Request(f"http://127.0.0.1:{port}/internal/me/admin/delete-feedback", data=json.dumps(body).encode(), headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as answer:
                    return answer.status, json.loads(answer.read() or b"{}")
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read() or b"{}")

        status, _ = remove({"id": ids[1]}, user="100000000000000099")
        if status != 404 or len(feedback.form_feedback()) != 3:
            problems.append(f"somebody who is not the developer account answered {status} and left {len(feedback.form_feedback())} answers, expected 404 and 3")
        status, _ = remove({"id": ids[1]}, user="")
        if status != 401 or len(feedback.form_feedback()) != 3:
            problems.append(f"a call with no signed-in user answered {status}, expected 401")
        status, body = remove({"id": ids[1]})
        left = [row["id"] for row in feedback.form_feedback()]
        if status != 200 or not body.get("ok") or ids[1] in left or len(left) != 2:
            problems.append(f"the developer account could not remove an answer: {status} {body} {left}")
        status, body = remove({"id": ids[1]})
        if status != 404 or body.get("error") != "no_such_answer":
            problems.append(f"removing the same answer twice answered {status} {body}, expected 404 no_such_answer")
        for bad in ({}, {"id": None}, {"id": "x"}, {"id": []}, {"id": 99999}):
            status, _ = remove(bad)
            if status != 404 or len(feedback.form_feedback()) != 2:
                problems.append(f"{bad} answered {status} or removed something")
        payload = admin.admin_payload()
        if payload["feedbackSummary"]["total"] != 2 or payload["feedbackSummary"]["average"] != 4.0 or len(payload["feedback"]) != 2:
            problems.append(f"the developer page's numbers did not follow the removal: {payload['feedbackSummary']}")
        # a removed answer frees its place under the cap
        kept_max = feedback.FORM_MAX_ROWS
        feedback.FORM_MAX_ROWS = 2
        refused = feedback.add_form_feedback(4)
        remove({"id": ids[0]})
        accepted = feedback.add_form_feedback(4)
        feedback.FORM_MAX_ROWS = kept_max
        if refused is not None or accepted is None:
            problems.append("a removed answer did not free its place under the cap")
    finally:
        web_server.INTERNAL_API_SECRET = kept_secret
        try:
            server.httpd.shutdown()
        except Exception:
            pass
        store.DATABASE_PATH = was
        store._database_ready = False
    return problems
