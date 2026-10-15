import json
import pathlib
import pickle
import tempfile

from tools.checks import check


def _song(title, artist="A", **charts):
    song = {"title": title, "artist": artist, "version": "24000", "deleted": False, "intl": "1"}
    for tier in ("bas", "adv", "exp", "mas", "remas"):
        for prefix in ("", "dx_"):
            for suffix in ("", "_i", "_notes", "_designer"):
                song[f"{prefix}lev_{tier}{suffix}"] = ""
    song.update(charts)
    return song


@check("an otoge-db fetch reports what changed in the charts to its webhook: songs added and removed, levels, constants, notes and designers, once, and never with a ping")
def _changes():
    import requests
    from rasmai.scraping.otoge import changes

    problems = []
    kept = (changes.OTOGE_WEBHOOK_URL, requests.post, changes.threading.Thread)
    posts = []

    class Answer:
        status_code = 204

    def fake_post(url, json=None, data=None, files=None, timeout=None):
        posts.append({"url": url, "json": json, "data": data, "files": files})
        return Answer()

    class Now:          # the post runs in the background in the bot; here it runs straight away so it can be looked at
        def __init__(self, target, args=(), daemon=None, name=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    old = {"song": _song("Song", dx_lev_mas="13", dx_lev_mas_i="13.4", dx_lev_mas_notes="800"),
           "ソング": None, "gone": _song("Gone"), "kept": _song("Kept", lev_exp="9")}
    old["ソング"] = old["song"]        # the same song under its reading, which must not count twice
    new = {"song": _song("Song", dx_lev_mas="13+", dx_lev_mas_i="13.7", dx_lev_mas_notes="812", dx_lev_remas="14", dx_lev_remas_i="14.2"),
           "kept": _song("Kept", lev_exp="9", lev_exp_notes="300", lev_exp_designer="someone", deleted=True),
           "fresh": _song("@everyone Fresh", "B", dx_lev_bas="2", dx_lev_mas="12+", dx_lev_mas_i="12.8")}
    report = changes.diff(old, new)
    added, removed, changed = report["added"], report["removed"], report["changed"]
    if len(added) != 1 or "Fresh" not in added[0] or "DX 2 / 12+ (12.8)" not in added[0]:
        problems.append(f"a new song was reported as {added}")
    if removed != ["**Gone** - A"]:
        problems.append(f"a song gone from the database was reported as {removed}")
    text = " ".join(changed)
    for expect in ("level 13 → 13+", "constant 13.4 → 13.7", "notes 800 → 812", "DX Re:MASTER added: 14 (14.2)", "removed from the game", "note counts filled in and designers filled in"):
        if expect not in text:
            problems.append(f"the changes did not say {expect!r}: {changed}")
    if len(changed) != 2:
        problems.append(f"{len(changed)} songs were reported as changed, not 2, so the reading counted twice or a song was missed")
    if changes.describe([("Japan", old, old)]) or changes.describe([("International", {}, new)]):
        problems.append("nothing changing, or nothing to compare with, still made a report")

    changes.OTOGE_WEBHOOK_URL = "https://discord.com/api/webhooks/1/x"
    requests.post, changes.threading.Thread = fake_post, Now
    try:
        changes.announce([("Japan", old, new), ("International", old, old)])
        if len(posts) != 1:
            problems.append(f"one fetch with changes posted {len(posts)} times")
        else:
            sent = posts[0]["json"]
            if sent["username"] != "Rasmai · Chart updates" or not sent["avatar_url"].endswith("/app/icon-512.png"):
                problems.append(f"the post came as {sent['username']!r} with {sent['avatar_url']!r}, not Rasmai's chart updates with its icon")
            if sent["allowed_mentions"] != {"parse": []} or "## Japan" not in sent["content"] or "International" in sent["content"]:
                problems.append(f"the post could ping, or named a region that did not change: {sent}")
        # a big update goes in a file, with the start of it in the message
        posts.clear()
        many = {f"t{n}": _song(f"Title number {n}", dx_lev_mas="13") for n in range(300)}
        changes.announce([("Japan", old, {**new, **many})])
        sent = posts[0] if posts else {}
        payload = json.loads(sent.get("data", {}).get("payload_json", "{}")) if sent.get("data") else {}
        if not sent.get("files") or len(payload.get("content", "")) > 2000 or payload.get("allowed_mentions") != {"parse": []}:
            problems.append("a long report was not cut to fit with the whole of it attached, or could ping")
        # no webhook, or no earlier copy: nothing is sent
        posts.clear()
        changes.OTOGE_WEBHOOK_URL = ""
        changes.announce([("Japan", old, new)])
        changes.OTOGE_WEBHOOK_URL = "https://discord.com/api/webhooks/1/x"
        changes.announce([("Japan", {}, new)])
        if posts:
            problems.append("a report was posted with no webhook set, or with nothing to compare with")
    finally:
        changes.OTOGE_WEBHOOK_URL, requests.post, changes.threading.Thread = kept

    # the copy compared with is the saved one, which every process shares
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder) / "songs_cache.pkl"
        with open(path, "wb") as f:
            pickle.dump({"songs": old, "songs_intl": new}, f)
        if changes.held(path) != (old, new) or changes.held(pathlib.Path(folder) / "missing.pkl") != ({}, {}):
            problems.append("the saved copy was not read back, or a missing one was not taken as empty")
    return problems


@check("a chart only Japan's file lists yet is borrowed into the international table, finds its constant, stays out of picks and out of the change report")
def _borrowed_charts():
    import copy
    from rasmai.engine.analysis.charts import build_chart_index
    from rasmai.scraping.otoge import changes
    from rasmai.scraping.otoge.loader import _borrow_charts

    problems = []
    japan = {"marisa": _song("Marisa", lev_adv="7+", lev_adv_i="7.9", lev_mas="13", lev_mas_i="13.3", dx_lev_mas="13+", dx_lev_mas_i="13.6", version="26000")}
    abroad = {"marisa": _song("Marisa", lev_adv="7", lev_adv_i="7.2", lev_mas="13", lev_mas_i="13.3", version="26000")}
    before = copy.deepcopy(abroad)
    _borrow_charts(abroad, japan)
    if abroad["marisa"].get("jp_only") != ["dx_lev_mas"] or japan["marisa"].get("jp_only"):
        problems.append(f"the borrowed charts were not named on the international song alone: {abroad['marisa'].get('jp_only')}")
    index = build_chart_index(abroad, region="intl")
    index.current_version = 26
    dx = index.get(("Marisa", "dx", "master"))
    if dx is None or dx.constant != 13.6:
        problems.append(f"a score on the borrowed DX MASTER found no constant: {dx}")
    elif index.playable(dx):
        problems.append("a borrowed chart with nothing saying it is out abroad was offered in picks")
    std = index.get(("Marisa", "std", "advanced"))
    if std is None or std.constant != 7.2 or not index.playable(std):
        problems.append(f"the international file's own chart lost its constant or its place in picks: {std}")
    if any(changes.diff(before, abroad).values()):
        problems.append(f"borrowing showed up as news in the international report: {changes.diff(before, abroad)}")
    return problems
