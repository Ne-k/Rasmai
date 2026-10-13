import asyncio
import io
import logging
import pathlib
import tempfile
import types

from tools.checks import check


def _chart(text):
    from rasmai.engine.simai.parse import parse
    return parse(text)


@check("a slide keeps every turn it makes, and the fields that read it before are unchanged")
def _corners():
    problems = []
    chart = _chart("(120){4}5^2p8[8:5],")
    slide = next(n for n in chart.notes if n.kind == "slide")
    if slide.corners != (("^", "2"), ("p", "8")) or slide.shape != "^p" or slide.end != "8":
        problems.append(f"a two-turn slide was read as {slide.corners} {slide.shape!r} {slide.end!r}")
    plain = next(n for n in _chart("(120){4}1-5[4:1],").notes if n.kind == "slide")
    if plain.corners != (("-", "5"),):
        problems.append(f"a straight slide was read as {plain.corners}")
    return problems


@check("a slide's track starts on its button, ends on its last turn's, goes through every turn, and a wifi has three")
def _paths():
    import math
    from rasmai.engine.simai.parse import Note
    from rasmai.images.preview import Field, slide_paths
    problems = []
    field = Field(440)

    def near(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1]) < 2

    two = slide_paths(field, Note(0, "slide", "5", 1.0, "^p", "8", corners=(("^", "2"), ("p", "8"))))
    if len(two) != 1 or not near(two[0][0], field.pt("5")) or not near(two[0][-1], field.pt("8")):
        problems.append("a two-turn slide's track does not run from its button to its last end")
    elif not any(near(p, field.pt("2")) for p in two[0]):
        problems.append("a two-turn slide's track skips the button its first turn ends on")
    via = slide_paths(field, Note(0, "slide", "1", 1.0, "V", "73", corners=(("V", "73"),)))
    if not any(near(p, field.pt("7")) for p in via[0]) or not near(via[0][-1], field.pt("3")):
        problems.append("a V slide does not go through its middle button to its end")
    wifi = slide_paths(field, Note(0, "slide", "1", 1.0, "w", "5", corners=(("w", "5"),)))
    ends = sorted(round(math.degrees(math.atan2(p[-1][1] - field.cy, p[-1][0] - field.cx))) for p in wifi)
    if len(wifi) != 3 or len(set(ends)) != 3:
        problems.append(f"a wifi slide should fan into three tracks, got {len(wifi)}")
    if slide_paths(field, Note(0, "slide", "A1", 1.0, "-", "5", corners=(("-", "5"),))):
        problems.append("a slide that starts on a touch area was given a track")
    return problems


@check("the preview opens on the busiest stretch, not the start, and a short chart starts at nothing")
def _busiest():
    from rasmai.images.preview import busiest_start
    problems = []
    # forty quiet seconds (one comma a second at 60 BPM), then forty of four-note chords every quarter second
    sparse = "(60){4}" + "1,,,,,,,,,," * 4 + "{16}" + ",".join(["1/5", "2/6", "3/7", "4/8"] * 40) + ","
    chart = _chart(sparse)
    where = busiest_start(chart)
    dense_from = min(n.time for n in chart.notes if n.time >= 39.5)
    if not dense_from - 9 <= where <= dense_from + 1:
        problems.append(f"the busiest stretch of a chart that is quiet then dense began at {where:.1f}s, not near {dense_from:.1f}s")
    if busiest_start(_chart("(120){4}1,2,3,4,")) != 0.0:
        problems.append("a chart shorter than the clip did not start at 0")
    return problems


@check("a preview is a looping GIF of the right size, shows the notes, and tries smaller until it fits what may be uploaded")
def _gif():
    from PIL import Image
    from rasmai.images.preview import ATTEMPTS, Skin, render_preview
    problems = []
    taps = "(150){8}" + ",".join(["1", "3/6", "5", "2/7", "8-4[8:3]", "4h[4:1]", "C", "A3"] * 30) + ","
    chart = _chart(taps)
    empty = Skin(pathlib.Path(tempfile.mkdtemp()))
    made = render_preview(chart, skin=empty)
    image = Image.open(io.BytesIO(made.gif))
    if image.format != "GIF" or image.n_frames != int(9.0 * made.fps) or image.size != (made.size, made.size) or image.info.get("loop") != 0:
        problems.append(f"not a looping GIF of {int(9.0 * made.fps)} frames at {made.size}px: {image.format} {image.n_frames} {image.size} {image.info.get('loop')}")
    middle = Image.open(io.BytesIO(made.gif))
    middle.seek(60)
    if len(set(middle.convert("RGB").getdata())) < 8:
        problems.append("a frame from the middle shows nothing but the background")
    if (made.size, made.fps) != ATTEMPTS[0]:
        problems.append(f"with room to spare it should be drawn at the largest size, not {made.size}px")
    tight = render_preview(chart, limit=len(made.gif) // 3, skin=empty)
    if (tight.size, tight.fps) == ATTEMPTS[0] or len(tight.gif) >= len(made.gif):
        problems.append("a tight limit did not make a smaller picture")
    if render_preview(_chart("(120){4},,,,"), skin=empty) is not None:
        problems.append("a chart with no notes was given a preview")
    return problems


@check("a pack's pictures are used where it has them and the rest are drawn, and a damaged file, a missing folder or an oversized one costs nothing")
def _skin():
    from PIL import Image
    from rasmai.images.preview import APPROACH, Field, Skin, _Painter
    problems = []
    folder = pathlib.Path(tempfile.mkdtemp())
    chart = _chart("(120){4}1,,,,")
    note = chart.notes[0]
    field = Field(440)
    moment = note.time - APPROACH * 0.5

    def has(skin, colour):
        painter = _Painter(chart.notes, field, skin)
        pixels = painter.frame(moment, 0.0, 9.0).getdata()
        return any(p == colour for p in pixels)

    plain = Skin(folder)
    plain.refresh()
    if has(plain, (0, 255, 0)):
        problems.append("green was on the picture before any pack gave it")
    Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(folder / "tap.png")
    (folder / "star.png").write_bytes(b"this is not a picture")
    Image.new("RGBA", (5000, 5000), (255, 0, 0, 255)).save(folder / "slide.png")
    pack = Skin(folder)
    pack.refresh()
    if not has(pack, (0, 255, 0)):
        problems.append("the pack's tap picture was not used")
    if pack.pick("star") is not None or pack.pick("slide") is not None:
        problems.append("a damaged picture or an oversized one was kept")
    if pack.pick("tap", "each") != "tap" or pack.pick("tap", "break") != "tap":
        problems.append("a note with no _each or _break picture did not fall back to the plain one")
    Image.new("RGBA", (64, 64), (0, 0, 255, 255)).save(folder / "tap_each.png")
    pack.refresh()
    if pack.pick("tap", "each") != "tap_each":
        problems.append("a picture added to the folder was not picked up")
    missing = Skin(folder / "nowhere")
    missing.refresh()
    if missing.pick("tap") is not None or not _Painter(chart.notes, field, missing).frame(moment, 0.0, 9.0):
        problems.append("a folder that is not there stopped the preview")
    return problems


def _ref():
    from rasmai.engine.analysis import ChartRef
    return ChartRef("Check Song", "dx", "master", 13.0, "13", 8, "g", "a", "c.png", 26)


class _Reply:
    def __init__(self):
        self.said = []
        self.deferred = None

    async def defer(self, **kwargs):
        self.deferred = kwargs

    async def send_message(self, text, **kwargs):
        self.said.append((text, kwargs))


class _Followup:
    def __init__(self):
        self.sent = []

    async def send(self, text=None, **kwargs):
        self.sent.append((text, kwargs))


def _interaction(guild=None, ephemeral=False, user=1234):
    return types.SimpleNamespace(
        user=types.SimpleNamespace(id=user, __str__=lambda s: "u"), guild=guild, guild_id=None, channel_id=None, command=None, data={}, namespace=[],
        message=types.SimpleNamespace(flags=types.SimpleNamespace(ephemeral=ephemeral)), response=_Reply(), followup=_Followup())


@check("the Preview button is offered only for a chart whose notation is stored, and pressing it posts one GIF with the stretch it shows")
def _button():
    from rasmai.bot.builders.charts import preview as module
    from rasmai.storage.db import connection as store, sheet_put
    problems = []
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    kept = module.COOLDOWN
    try:
        ref = _ref()
        if module.preview_button(ref) is not None:
            problems.append("a chart with no stored notation was offered a Preview button")
        sheet_put("|".join(ref.key), "id1", "(150){8}" + ",".join(["1", "3/6", "5", "2/7"] * 40) + ",")
        button = module.preview_button(ref)
        if button is None or button.label != "Preview" or button.row != 4:
            problems.append("a chart with stored notation was not offered a Preview button on the last row")
        from rasmai.bot.builders.charts.views import SongView

        async def built():
            return SongView(1, ref.title, [ref], [{"played": False}], 0, last_play=3)
        view = asyncio.run(built())
        bottom = [item for item in view.children if item.row == 4]
        labels = [getattr(item, "label", "") for item in bottom]
        if "Preview" not in labels or len(bottom) > 5:
            problems.append(f"the chart page's last row should hold the Preview button in five places or fewer: {labels}")
        module._last.clear()
        module._made.clear()
        first = _interaction(ephemeral=True)
        asyncio.run(module.send_preview(first, ref))
        sent = first.followup.sent
        if first.response.deferred != {"ephemeral": True, "thinking": True}:
            problems.append(f"the press was not deferred as a thinking reply that matches the page: {first.response.deferred}")
        if len(sent) != 1 or sent[0][1].get("file") is None or sent[0][1]["file"].filename != "dx-master-preview.gif":
            problems.append(f"one GIF named for the chart was not posted: {[(t, list(k)) for t, k in sent]}")
        elif "busiest part" not in sent[0][0] or "Check Song" not in sent[0][0]:
            problems.append(f"the message does not say what is shown: {sent[0][0]}")
        again = _interaction()
        asyncio.run(module.send_preview(again, ref))
        if again.followup.sent or not again.response.said or "Easy" not in again.response.said[0][0] or not again.response.said[0][1].get("ephemeral"):
            problems.append("a second press straight away was not turned away privately")
        other = _interaction(user=999)
        asyncio.run(module.send_preview(other, ref))
        if not other.followup.sent:
            problems.append("one person's cooldown stopped somebody else")
    finally:
        store.DATABASE_PATH = was
        store._database_ready = False
        module.COOLDOWN = kept
        module._last.clear()
        module._made.clear()
    return problems


@check("a preview that cannot be drawn says so with an error ID and is reported, a chart with no notation is told so, and the server's upload limit is respected")
def _button_failures():
    from rasmai.bot.builders.charts import preview as module
    from rasmai.storage.db import connection as store, sheet_put
    problems = []
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    errors = []

    class Grab(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())

    grab = Grab()
    logging.getLogger().addHandler(grab)
    kept_draw = module._draw
    try:
        ref = _ref()
        module._last.clear()
        module._made.clear()
        nothing = _interaction()
        asyncio.run(module.send_preview(nothing, ref))
        text = nothing.followup.sent[0][0] if nothing.followup.sent else ""
        if "haven't read" not in text or not nothing.followup.sent[0][1].get("ephemeral") or module._last:
            problems.append(f"a chart with no stored notation was not told so privately and left free to try again: {text!r}")
        sheet_put("|".join(ref.key), "id1", "(150){8}" + ",".join(["1", "3/6"] * 20) + ",")

        def broken(*args):
            raise AttributeError("bug in the drawing")
        module._draw = broken
        failed = _interaction()
        asyncio.run(module.send_preview(failed, ref))
        text = failed.followup.sent[0][0] if failed.followup.sent else ""
        if "error ID" not in text or not errors or module._last:
            problems.append(f"a failed drawing was not reported with an ID and left free to try again: {text!r} {errors}")
        module._draw = kept_draw
        seen = []

        async def spy(chart_ref, limit):
            seen.append(limit)
            return None
        kept_build = module.build_preview
        module.build_preview = spy
        module._last.clear()
        asyncio.run(module.send_preview(_interaction(guild=types.SimpleNamespace(filesize_limit=50 * 1024 * 1024)), ref))
        module._last.clear()
        asyncio.run(module.send_preview(_interaction(), ref))
        module.build_preview = kept_build
        if seen != [50 * 1024 * 1024 - module.MARGIN, module.UPLOAD_LIMIT - module.MARGIN]:
            problems.append(f"the upload limit was not taken from the server, or the DM default: {seen}")
    finally:
        module._draw = kept_draw
        logging.getLogger().removeHandler(grab)
        store.DATABASE_PATH = was
        store._database_ready = False
        module._last.clear()
        module._made.clear()
    return problems


@check("notes move as MajdataView moves them at 7.0 and 7.5: first seen small about 0.76s out, a quarter of the way along, full size by 0.51s, then out to the button")
def _speed():
    from rasmai.images import preview as pv
    problems = []
    if pv.NOTE_SPEED != 7.0 or pv.TOUCH_SPEED != 7.5:
        problems.append(f"the speeds are {pv.NOTE_SPEED} and {pv.TOUCH_SPEED}, not 7.0 and 7.5")
    if not 0.755 < pv.APPROACH < 0.765 or not 0.705 < pv.TOUCH_APPROACH < 0.715:
        problems.append(f"a note is first seen {pv.APPROACH:.3f}s out and a touch {pv.TOUCH_APPROACH:.3f}s, not about 0.76 and 0.71")
    if pv.place(1.0 - pv.APPROACH - 0.01, 1.0) is not None:
        problems.append("a note was shown before it should first appear")
    seen = pv.place(1.0 - pv.APPROACH + 0.002, 1.0)
    if seen is None or abs(seen[0] - 1.225 / 4.8) > 1e-6 or seen[1] > 0.32:
        problems.append(f"a note first seen should be small and a quarter of the way out: {seen}")
    grown = pv.place(1.0 - 0.50, 1.0)
    if grown is None or grown[1] != 1.0 or not 0.25 < grown[0] < 0.4:
        problems.append(f"half a second out the note should be full size and still near the start of its travel: {grown}")
    half = pv.place(1.0 - 0.25, 1.0)
    if half is None or not 0.55 < half[0] < 0.7:
        problems.append(f"a quarter second out the note should be well over half way: {half}")
    if pv.place(1.0, 1.0) != (1.0, 1.0) or pv.place(1.1, 1.0) != (1.0, 1.0):
        problems.append("a struck note should wait on its button at full size")
    return problems


@check("the bundled note pictures all load, the folder in the settings replaces any it names, and every note of the chart can be drawn with them")
def _bundled():
    from PIL import Image
    from rasmai.images import preview as pv
    problems = []
    want = ["tap", "tap_each", "tap_break", "tap_ex", "hold", "hold_each", "hold_break", "hold_ex", "slide", "slide_each", "slide_break",
            "star", "star_each", "star_break", "star_ex", "touch", "touch_each", "touch_point", "touch_each_point", "touch_hold_1",
            "touch_hold_2", "touch_hold_3", "touch_hold_4", "touch_hold_border", "touch_hit", "field"]
    bundled = pv.Skin(pv.BUNDLED_SKIN)
    bundled.refresh()
    missing = [name for name in want if bundled.pick(name) != name]
    if missing:
        problems.append(f"the bundled pack lacks {missing}")
    folder = pathlib.Path(tempfile.mkdtemp())
    Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(folder / "tap.png")
    both = pv.Skin(pv.BUNDLED_SKIN, folder)
    both.refresh()
    if both._raw["tap"].getpixel((5, 5)) != (0, 255, 0, 255) or both.pick("star") != "star":
        problems.append("a picture in the settings folder did not replace the bundled one, or the rest of the bundled pack was lost")
    chart = _chart("(120){4}1,2h[4:1],3x,4b,5/6,7-3[4:1],8-4[4:1]*-6[4:1],C,B2h[4:1],A3,D1,E5,")
    shot = pv._Painter(chart.notes, pv.Field(440), bundled)
    for note in chart.notes:
        frame = shot.frame(note.time + 0.05 if note.duration == 0 else note.time + note.duration / 2, 0.0, 9.0)
        if not frame:
            problems.append(f"a {note.kind} could not be drawn with the bundled pack")
    return problems


@check("a hold is the pack's hexagon stretched from its tail to its head, and a slide's chevrons point the way the star goes")
def _shapes():
    import math
    from rasmai.images import preview as pv
    from rasmai.engine.simai.parse import Note
    problems = []
    skin = pv.Skin(pv.BUNDLED_SKIN)
    skin.refresh()
    field = pv.Field(440)
    hold = _chart("(120){4}1h[1:1],").notes[0]
    shot = pv._Painter([hold], field, skin)
    bare = pv._Painter([], field, skin)
    moment = hold.time + hold.duration * 0.4
    differ = sum(1 for a, b in zip(shot.frame(moment, 0.0, 9.0).getdata(), bare.frame(moment, 0.0, 9.0).getdata()) if a != b)
    if differ < 800:
        problems.append(f"a hold in progress drew only {differ} pixels more than the empty field, so it is not stretched along its lane")
    slide = Note(0.0, "slide", "7", 1.0, "-", "3", wait=0.2, corners=(("-", "3"),))
    painter = pv._Painter([slide], field, skin)
    turns = []
    original = painter.put

    def watch(img, name, xy, width, angle=0.0, **kwargs):
        if name == "slide":
            turns.append(angle)
        return original(img, name, xy, width, angle, **kwargs)
    painter.put = watch
    painter.frame(-0.1, -0.5, 9.0)
    path = pv.Track(pv.slide_paths(field, slide)[0])
    heading = math.degrees(path.at(0.5)[1])
    if not turns or any(abs(((t - (heading + 180) + 180) % 360) - 180) > 1.0 for t in turns):
        problems.append(f"a chevron was turned {turns[:2]} for a track heading {heading:.0f} degrees, when the pack's point left")
    return problems
