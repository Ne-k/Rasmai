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


def _probe(data):
    """An MP4's codec, width, height and frame count, and one frame from its middle, as ffprobe and ffmpeg read them."""
    import shutil
    import subprocess
    from PIL import Image
    path = pathlib.Path(tempfile.mkdtemp()) / "clip.mp4"
    path.write_bytes(data)
    found = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=codec_name,width,height,nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    codec, width, height, frames = found.strip().split(",")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    return codec, int(width), int(height), int(frames), Image.frombytes("RGB", (int(width), int(height)), raw)


@check("a preview is an H.264 MP4 that starts playing before it has all loaded where ffmpeg is installed and a looping GIF where it is not; "
       "either is the right size and length, shows the notes, and tries smaller until it fits what may be uploaded")
def _clip():
    import shutil
    from unittest import mock
    from PIL import Image
    from rasmai.images import preview as pv
    problems = []
    taps = "(150){8}" + ",".join(["1", "3/6", "5", "2/7", "8-4[8:3]", "4h[4:1]", "C", "A3"] * 30) + ","
    chart = _chart(taps)
    empty = pv.Skin(pathlib.Path(tempfile.mkdtemp()))
    if shutil.which("ffmpeg"):
        made = pv.render_preview(chart, seconds=4.0, skin=empty)
        codec, width, height, frames, middle = _probe(made.data)
        if made.kind != "mp4" or codec != "h264" or (width, height) != (made.size, made.size) or frames != int(4.0 * made.fps):
            problems.append(f"not an H.264 MP4 of {int(4.0 * made.fps)} frames at {made.size}px: {made.kind} {codec} {width}x{height} {frames}")
        if made.data[4:8] != b"ftyp" or not 0 < made.data.find(b"moov") < made.data.find(b"mdat"):
            problems.append("the MP4's index is not at the front, so it cannot start playing before it has all loaded")
        if len(set(middle.getdata())) < 8:
            problems.append("a frame from the middle of the MP4 shows nothing but the background")
        if (made.size, made.fps) != pv.ATTEMPTS[0]:
            problems.append(f"with room to spare the MP4 should be drawn at the largest size, not {made.size}px")
        tight = pv.render_preview(chart, limit=len(made.data) // 3, seconds=4.0, skin=empty)
        if (tight.size, tight.fps) == pv.ATTEMPTS[0] or len(tight.data) >= len(made.data):
            problems.append("a tight limit did not make a smaller MP4")
    with mock.patch.object(pv.shutil, "which", return_value=None):
        made = pv.render_preview(chart, skin=empty)
        image = Image.open(io.BytesIO(made.data))
        frames = int(pv.SECONDS * made.fps)
        if made.kind != "gif" or image.format != "GIF" or image.n_frames != frames or image.size != (made.size, made.size) or image.info.get("loop") != 0:
            problems.append(f"without ffmpeg, not a looping GIF of {frames} frames at {made.size}px: {made.kind} {image.format} {image.n_frames} {image.size}")
        image.seek(60)
        if len(set(image.convert("RGB").getdata())) < 8:
            problems.append("a frame from the middle of the GIF shows nothing but the background")
        if (made.size, made.fps) != pv.GIF_ATTEMPTS[0]:
            problems.append(f"with room to spare the GIF should be drawn at the largest size, not {made.size}px")
        tight = pv.render_preview(chart, limit=len(made.data) // 3, skin=empty)
        if (tight.size, tight.fps) == pv.GIF_ATTEMPTS[0] or len(tight.data) >= len(made.data):
            problems.append("a tight limit did not make a smaller GIF")
    if pv.render_preview(_chart("(120){4},,,,"), skin=empty) is not None:
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


def _astrodx(found=None, held=False):
    """A stand-in for the chart folder reader, started and stopped by the check, so no check looks at real folders."""
    from unittest import mock
    fake = types.ModuleType("rasmai.scraping.astrodx")
    fake.find = lambda ref: found
    fake.held = lambda ref: held
    return mock.patch.dict("sys.modules", {"rasmai.scraping.astrodx": fake})


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
    taken_down = []

    async def delete_original_response():
        taken_down.append(True)
    return types.SimpleNamespace(
        taken_down=taken_down, delete_original_response=delete_original_response,
        user=types.SimpleNamespace(id=user, __str__=lambda s: "u"), guild=guild, guild_id=None, channel_id=None, command=None, data={}, namespace=[],
        message=types.SimpleNamespace(flags=types.SimpleNamespace(ephemeral=ephemeral)), response=_Reply(), followup=_Followup())


@check("the Preview button is offered only for a chart whose notation is stored, and pressing it posts one clip with the stretch it shows, an MP4 where ffmpeg is installed")
def _button():
    import shutil
    from rasmai.bot.builders.charts import preview as module
    from rasmai.storage.db import connection as store, sheet_put
    problems = []
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    kept = module.COOLDOWN
    folders = _astrodx()
    folders.start()
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
        # Preview is switched off on the chart page until it is tested; when it goes back, it must fit the row with the rest
        if "Preview" in labels or len(bottom) > 5:
            problems.append(f"the chart page offers Preview while it is off, or its last row is over five places: {labels}")
        module._last.clear()
        module._made.clear()
        first = _interaction(ephemeral=True)
        asyncio.run(module.send_preview(first, ref))
        sent = first.followup.sent
        if first.response.deferred != {"ephemeral": True, "thinking": True}:
            problems.append(f"the press was not deferred as a thinking reply that matches the page: {first.response.deferred}")
        kind = "mp4" if shutil.which("ffmpeg") else "gif"
        if len(sent) != 1 or sent[0][1].get("file") is None or sent[0][1]["file"].filename != f"dx-master-preview.{kind}":
            problems.append(f"one {kind} named for the chart was not posted: {[(t, list(k)) for t, k in sent]}")
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
        folders.stop()
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
    folders = _astrodx()
    folders.start()
    try:
        ref = _ref()
        module._last.clear()
        module._made.clear()
        nothing = _interaction()
        asyncio.run(module.send_preview(nothing, ref))
        text = nothing.followup.sent[0][0] if nothing.followup.sent else ""
        if "haven't read" not in text or not nothing.followup.sent[0][1].get("ephemeral") or module._last:
            problems.append(f"a chart with no stored notation was not told so privately and left free to try again: {text!r}")
        if not nothing.taken_down:
            problems.append("the public wait was left in the channel under a refusal meant only for the person who asked")
        private = _interaction(ephemeral=True)
        module._last.clear()
        asyncio.run(module.send_preview(private, ref))
        if private.taken_down or not private.followup.sent:
            problems.append("a refusal on a message only its owner sees took down a reply that was already private, or went unsaid")
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
        folders.stop()
        logging.getLogger().removeHandler(grab)
        store.DATABASE_PATH = was
        store._database_ready = False
        module._last.clear()
        module._made.clear()
    return problems


@check("notes move as the site's player moves them (web/lib/chart/rules.mjs) at the game's option IDs: grown over four beats at speed / 60 BPM, "
       "then four more out to the button; 4.50 is the default")
def _speed():
    from rasmai.images import preview as pv
    problems = []
    if (pv.NOTE_SPEED, pv.TOUCH_SPEED) != (550, 350):
        problems.append(f"the default speeds are {pv.NOTE_SPEED} and {pv.TOUCH_SPEED}, not the game's 550 and 350 (both 4.50)")
    # rules.mjs: a note shows 2 * 240000 / speed ms + NoteBase.GetMaiBugAdjustMSec before it is struck, a touch 1.25 * 240000 / speed
    for speed, seen in ((200, 2.3967), (550, 0.8630), (1100, 0.4248)):
        if abs(pv.approach(speed) - seen) > 0.0005:
            problems.append(f"at note speed {speed} a note shows {pv.approach(speed):.4f}s before it is struck, not {seen}")
    for speed, seen in ((175, 1.7143), (350, 0.8571), (900, 0.3333)):
        if abs(pv.touch_approach(speed) - seen) > 0.0005:
            problems.append(f"at touch speed {speed} a touch shows {pv.touch_approach(speed):.4f}s before it is struck, not {seen}")
    if pv.approach(5000) > 0.1:
        problems.append("Sonic is not near instant")
    out = 1.0 - pv.approach(550)
    if pv.place(out - 0.01, 1.0) is not None:
        problems.append("a note was shown before it should first appear")
    seen = pv.place(out + 0.002, 1.0)
    if seen is None or seen[0] != 0.25 or seen[1] > 0.05:
        problems.append(f"a note first seen should be tiny and a quarter of the way out: {seen}")
    grown = pv.place(1.0 - pv.span(550) + 0.01, 1.0)
    if grown is None or grown[1] != 1.0 or not 0.2 < grown[0] < 0.3:
        problems.append(f"once grown the note should be full size and just setting off: {grown}")
    half = pv.place(1.0 - pv.span(550) / 2, 1.0)
    if half is None or not 0.55 < half[0] < 0.65:
        problems.append(f"half its travel out the note should be about half way along: {half}")
    if pv.place(1.1, 1.0) != (1.0, 1.0) or pv.place(1.0, 1.0)[0] < 0.97:
        problems.append("a struck note should be at its button and wait there at full size")
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


def _wav(seconds):
    """A quiet tone, stereo at 44.1 kHz, so the soundtrack is resampled as a real song's would be."""
    import wave
    import numpy as np
    path = pathlib.Path(tempfile.mkdtemp()) / "song.wav"
    tone = (np.sin(2 * np.pi * 330 * np.arange(int(44100 * seconds)) / 44100) * 8000).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes(np.repeat(tone, 2).tobytes())
    return path


@check("a chart's Video is the whole of it as an H.264 MP4 with the song and a tap a note in AAC, as long as the chart and under the limit")
def _video():
    import json
    import shutil
    import subprocess
    import numpy as np
    from unittest import mock
    from rasmai.images import preview as pv
    problems = []
    chart = _chart("(120){4}1,2h[8:1],3-7[8:1],C,4b,")
    track = _wav(3.0)
    with mock.patch.object(pv.shutil, "which", return_value=None):
        if pv.render_video(chart, track) is not None:
            problems.append("a video was made with no ffmpeg to encode it")
    tap = np.ones(10, np.float32)
    mixed = pv.soundtrack(chart.notes, None, 0.0, 3.0, tap)
    plain, brk = (mixed[int(round(n.time * 48000)), 0] for n in (chart.notes[0], chart.notes[-1]))
    if mixed.shape != (144000, 2) or not 0 < plain < brk or abs(mixed).max() > 1.0:
        problems.append(f"the taps are not one a note with breaks louder: {mixed.shape} {plain} {brk}")
    if abs(pv.soundtrack(chart.notes, np.full((144000, 2), 2.0, np.float32), 0.0, 3.0, tap)).max() > 1.0:
        problems.append("a loud song with the taps on it clips")
    if not shutil.which("ffmpeg"):
        return problems
    limit = 2 * 1024 * 1024
    made = pv.render_video(chart, track, limit, speed=800, touch_speed=500)
    path = pathlib.Path(tempfile.mkdtemp()) / "video.mp4"
    path.write_bytes(made.data)
    found = json.loads(subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,duration",
                                       "-of", "json", str(path)], capture_output=True, text=True).stdout)["streams"]
    streams = {s["codec_type"]: (s["codec_name"], float(s["duration"])) for s in found}
    last = max(n.time + n.wait + n.duration for n in chart.notes)
    if made.start != 0.0 or abs(made.end - (last + 1.5)) > 1e-6:
        problems.append(f"the video runs {made.start:.2f}s to {made.end:.2f}s, not from the start to 1.5s past the last note at {last:.2f}s")
    for kind, codec in (("video", "h264"), ("audio", "aac")):
        if streams.get(kind, ("", 0))[0] != codec or abs(streams[kind][1] - (made.end - made.start)) > 0.15:
            problems.append(f"no {codec} {kind} as long as the video: {streams}")
    if len(made.data) > limit or made.data[4:8] != b"ftyp":
        problems.append(f"the video is {len(made.data)} bytes against a limit of {limit}, or not an MP4")
    return problems


@check("the Video button is offered only for a chart whose folder is held, and a press posts the whole chart at the presser's saved speeds")
def _video_button():
    import shutil
    from rasmai.bot.builders.charts import preview as module
    from rasmai.bot.state.prefs import update_prefs
    from rasmai.storage.db import connection as store
    problems = []
    was, store.DATABASE_PATH = store.DATABASE_PATH, pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3"
    store._database_ready = False
    ref = _ref()
    held = types.SimpleNamespace(chart=_chart("(120){4}1,2,3,4,"), track=_wav(3.0), maidata="", slot=5, art=None, folder=pathlib.Path("."))
    folders = _astrodx()
    folders.start()
    try:
        if module.full_video_button(ref) is not None:
            problems.append("a chart with no folder held was offered a Video button")
        folders.stop()
        folders = _astrodx(held, True)
        folders.start()
        button = module.full_video_button(ref)
        if button is None or button.label != "Video" or button.row != 3:
            problems.append("a chart with its folder held was not offered a Video button on row 3")
        module._made.clear()
        if module.preview_button(ref) is None or asyncio.run(module.build_preview(ref, 10 * 1024 * 1024)) is None:
            problems.append("a chart with no stored notation but its folder held was not given a Preview drawn from the folder")
        from rasmai.bot.builders.charts.views import SongView

        async def built():
            return SongView(1, ref.title, [ref], [{"played": False}], 0, last_play=3)
        rows = [(getattr(item, "label", ""), item.row) for item in asyncio.run(built()).children]
        if ("Video", 3) not in rows or sum(1 for _, row in rows if row == 4) > 5:
            problems.append(f"the chart page does not offer Video on row 3, or its last row is over five places: {rows}")
        if not shutil.which("ffmpeg"):
            return problems
        update_prefs("1234", note_speed=800, touch_speed=500)
        module._video_last.clear()
        module._videos.clear()
        first = _interaction()
        asyncio.run(module.send_video(first, ref))
        sent = first.followup.sent
        if len(sent) != 1 or sent[0][1].get("file") is None or sent[0][1]["file"].filename != "dx-master-video.mp4":
            problems.append(f"one MP4 named for the chart was not posted: {[(t, list(k)) for t, k in sent]}")
        elif "note speed 7.00, touch speed 6.00" not in sent[0][0] or "whole chart" not in sent[0][0]:
            problems.append(f"the message does not say what is shown at which speeds: {sent[0][0]}")
        if [key[1:3] for key in module._videos] != [(800, 500)]:
            problems.append(f"the video was not made at the saved speeds: {list(module._videos)}")
        again = _interaction()
        asyncio.run(module.send_video(again, ref))
        if again.followup.sent or not again.response.said or "120 seconds" not in again.response.said[0][0]:
            problems.append("a second press straight away was not turned away for two minutes")
        module._video_last.clear()
        module._videos_waiting = module.VIDEOS_QUEUED
        busy = _interaction(user=998)
        asyncio.run(module.send_video(busy, ref))
        module._videos_waiting = 0
        text = busy.followup.sent[0][0] if busy.followup.sent else ""
        if "other videos right now" not in text or module._video_last:
            problems.append(f"a press with the queue full was not turned away and left free to try again: {text!r}")
        folders.stop()
        folders = _astrodx()
        folders.start()
        module._video_last.clear()
        module._videos.clear()
        gone = _interaction(user=999)
        asyncio.run(module.send_video(gone, ref))
        text = gone.followup.sent[0][0] if gone.followup.sent else ""
        if "don't have that chart's files" not in text or module._video_last:
            problems.append(f"a chart whose folder went was not told so and left free to try again: {text!r}")
    finally:
        folders.stop()
        store.DATABASE_PATH = was
        store._database_ready = False
        module._video_last.clear()
        module._videos.clear()
        module._made.clear()
    return problems
