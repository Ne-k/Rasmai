import pathlib
import tempfile

from tools.checks import check


def _ref(title, chart_type, difficulty, notes):
    from rasmai.engine.analysis.charts import ChartRef
    return ChartRef(title, chart_type, difficulty, 13.0, "13", notes, "g", "a", "c.png", 26)


def _song(folder, maidata, encoding="utf-8-sig", files=("track.mp3", "bg.png")):
    folder.mkdir(parents=True)
    (folder / "maidata.txt").write_bytes(maidata.encode(encoding))
    for name in files:
        (folder / name).write_bytes(b"x")


@check("an AstroDX folder is matched by title and type, picks the slot whose count matches, applies &first, and a missing one is nothing")
def _astrodx():
    from rasmai.scraping import astrodx
    problems = []
    root = pathlib.Path(tempfile.mkdtemp())
    four, six, eight = "(120){4}1,2,3,4,E", "(120){4}1,2,3,4,5,6,E", "(120){8}1,2,3,4,5,6,7,8,E"
    # one song as a standard folder with no marker and a DX folder beside it, and one unmarked song in Shift JIS whose
    # pack put the Master in the Re:Master's slot
    _song(root / "levels" / "pops" / "Check Alpha", f"&title=Check Alpha\n&first=1.5\n&lv_5=13\n&inote_4={eight}\n&inote_5={four}\n")
    _song(root / "levels" / "pops" / "Check Alpha [DX]", f"&title=Check Alpha [DX]\n&inote_5=\n{six}\n", files=("track.ogg", "bg.jpg"))
    _song(root / "levels" / "game" / "beta", f"&title=チェック・ベータ\n&inote_5={four}\n&inote_6={eight}\n", encoding="cp932", files=())
    kept, astrodx.ASTRODX_DIR, astrodx._memo = astrodx.ASTRODX_DIR, root, (None, 0.0, (0, 0.0), {})
    try:
        assert astrodx.find(_ref("Check Alpha", "std", "master", 4)) is None, "a lookup waited for the folder to be walked"
        astrodx._scan(root)
        std = astrodx.find(_ref("ＣＨＥＣＫ　alpha", "std", "master", 4))
        assert std is not None, "the standard chart of a song with a DX folder beside it was not found"
        assert std.slot == 5 and len(std.chart.notes) == 4, f"standard Master read as slot {std.slot}, {len(std.chart.notes)} notes"
        assert abs(std.chart.notes[0].time - 1.5) < 1e-6 and abs(std.chart.notes[-1].time - 3.0) < 1e-6, "&first was not applied"
        assert std.folder.name == "Check Alpha" and std.track == std.folder / "track.mp3" and std.art == std.folder / "bg.png"
        assert "&first=1.5" in std.maidata
        dx = astrodx.find(_ref("Check Alpha", "dx", "master", 6))
        assert dx is not None and dx.folder.name == "Check Alpha [DX]" and len(dx.chart.notes) == 6, "the DX folder was not picked"
        assert dx.chart.notes[0].time == 0.0 and dx.track.name == "track.ogg" and dx.art.name == "bg.jpg"
        assert astrodx.held(_ref("Check Alpha", "dx", "master", 0)) and not astrodx.held(_ref("Check Alpha", "dx", "remaster", 0))
        assert astrodx.held(_ref("Check Alpha", "std", "expert", 0)) and not astrodx.held(_ref("Missing Song", "std", "master", 0))
        moved = astrodx.find(_ref("チェック・ベータ", "std", "master", 8))
        assert moved is not None and moved.slot == 6, "a Master the pack filed in another slot was not found by its note count"
        assert moved.track is None and moved.art is None
        assert astrodx.find(_ref("チェック・ベータ", "dx", "master", 4)).slot == 5
        assert astrodx.find(_ref("チェック・ベータ", "dx", "master", 300)) is None, "an unmarked folder whose counts match nothing was taken"
        assert astrodx.find(_ref("チェック・ベータ", "dx", "basic", 0)) is None
        assert astrodx.held(_ref("チェック・ベータ", "dx", "master", 4)), "an unmarked folder whose count matches was not held"
        assert not astrodx.held(_ref("チェック・ベータ", "dx", "master", 300)), "held offered a chart find would not give"
        astrodx.ASTRODX_DIR = root / "missing"
        assert astrodx.find(_ref("Check Alpha", "std", "master", 4)) is None and not astrodx.held(_ref("Check Alpha", "std", "master", 4))
    except AssertionError as error:
        problems.append(str(error) or "an AstroDX lookup came out wrong")
    finally:
        astrodx.ASTRODX_DIR, astrodx._memo = kept, (None, 0.0, (0, 0.0), {})
    return problems


@check("the chart text the site's viewer is sent builds in the site's own reader, to as many notes as the bot reads")
def _viewer_text():
    import json
    import shutil
    import subprocess
    from rasmai.scraping import astrodx
    node = shutil.which("node")
    if node is None:
        return []           # shortcut: no Node on this machine to run the site's own code with; the site's build covers it where there is one
    problems = []
    viewer = (pathlib.Path("web/components/play/Viewer.tsx")).read_text(encoding="utf-8")
    if "buildChart(parseMaidata(" not in viewer:
        problems.append("the viewer hands buildChart the raw maidata.txt, which it reads as already parsed")
    root = pathlib.Path(tempfile.mkdtemp())
    _song(root / "Check Gamma", "&title=Check Gamma\n&first=0.5\n&wholebpm=150\n&inote_5=(150){8}1,2h[4:1],3-7[4:1],4,B1,C,5,6/7,E\n")
    kept, astrodx.ASTRODX_DIR, astrodx._memo = astrodx.ASTRODX_DIR, root, (None, 0.0, (0, 0.0), {})
    try:
        astrodx._scan(root)
        found = astrodx.find(_ref("Check Gamma", "std", "master", 0))
        if found is None:
            return problems + ["the check's own folder was not found"]
        lib = (pathlib.Path("web/lib/chart").resolve().as_uri()) + "/"
        script = (f"const {{ parseMaidata }} = await import({json.dumps(lib + 'chart.mjs')});"
                  f"const {{ buildChart }} = await import({json.dumps(lib + 'build.mjs')});"
                  "const [text, slot] = JSON.parse(process.argv[1]);"
                  "const c = buildChart(parseMaidata(text), slot);"
                  "console.log(JSON.stringify({ notes: c.notes.length, first: c.notes[0].t }));")
        done = subprocess.run([node, "--input-type=module", "-e", script, json.dumps([found.maidata, found.slot])],
                              capture_output=True, text=True, timeout=60)
        if done.returncode:
            return problems + [f"the site could not build the chart it is sent: {done.stderr.strip()[-300:]}"]
        built = json.loads(done.stdout)
        if built["notes"] != len(found.chart.notes):
            problems.append(f"the site reads {built['notes']} notes where the bot reads {len(found.chart.notes)}")
        if abs(built["first"] / 1000 - found.chart.notes[0].time) > 0.002:
            problems.append(f"the site starts the chart at {built['first']} ms, the bot at {found.chart.notes[0].time:.3f} s")
    finally:
        astrodx.ASTRODX_DIR, astrodx._memo = kept, (None, 0.0, (0, 0.0), {})
    return problems
