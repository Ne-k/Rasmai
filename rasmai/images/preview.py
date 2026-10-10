from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import io
import logging
import math
import threading

from PIL import Image, ImageDraw, ImageFont

from rasmai.config import CHART_SKIN_DIR
from rasmai.engine.simai.parse import Chart, Note

logger = logging.getLogger(__name__)

BG = (14, 13, 24)
PINK, GOLD, ORANGE, BLUE, CYAN, WHITE = (255, 95, 168), (255, 210, 63), (255, 138, 61), (74, 168, 255), (70, 217, 255), (245, 242, 250)
RING, INK = (44, 42, 66), (170, 166, 196)

# How fast things come in follows MajdataView, the open simai viewer, so the preview moves as that does at the game's usual settings:
# a note is `speed` units a second, the buttons are 4.8 units from the middle, and a note first shows small, grows to full size where
# it is 1.225 out, then travels the rest of the way. Taps, holds and slides run at 7.0; touch notes at 7.5, a half step above.
NOTE_SPEED = 7.0
TOUCH_SPEED = 7.5
RING_UNITS = 4.8
PINNED = 1.225
APPEAR = 0.3            # the size a note is when it first shows, as a share of full size
FIRST_SEEN = (APPEAR - 0.51) / 0.4      # how far out it is then: just under the middle, so it takes RING_UNITS - FIRST_SEEN to cross


def approach(speed: float) -> float:
    """Seconds from a note first showing to its being struck at a speed."""
    return (RING_UNITS - FIRST_SEEN) / speed


APPROACH = approach(NOTE_SPEED)           # about 0.76 seconds at 7.0
TOUCH_APPROACH = approach(TOUCH_SPEED)    # about 0.71 at 7.5
SECONDS = 9.0
# the sizes tried in turn until the picture fits what the server lets be uploaded: (pixels across, frames a second)
ATTEMPTS: Tuple[Tuple[int, int], ...] = ((440, 20), (360, 15), (300, 12))
MAX_SKIN_PIXELS = 4_000_000      # one picture in a pack; anything bigger is not a note
BUNDLED_SKIN = Path(__file__).parent / "chart_skin"

# The pictures a pack may hold, as PNGs named for what they are. Every one is optional: a note with no picture is drawn instead, and
# a pack in CHART_SKIN_DIR replaces the bundled picture of the same name. A note struck with others or a break reads its "_each" or
# "_break" picture when there is one and the plain one when there is not; an EX note gets the "_ex" picture over the top.
#   tap  star  (a ring and a star, centred)
#   hold  (the whole hexagon, standing upright with its top cap outermost, stretched to the hold's length)
#   slide  (one chevron of a slide's track, pointing left as the Majdata set draws it)
#   touch  (a triangle with its point up; four of them close in on the place)   touch_point  touch_hold_1 .. 4  touch_hold_border
#   touch_hit (the frame as a touch is struck)   hit (the burst where a tap is struck)
#   field (the playfield with its eight buttons, edge to edge, sized to the ring)   button (one at each of the eight places)


class Skin:
    """The note pictures in one or more folders, read again whenever something in them changes and never fatal when they are bad."""

    def __init__(self, *folders: Path):
        self.folders = [Path(folder) for folder in folders]
        self._stamp: Optional[Tuple] = None
        self._raw: Dict[str, Image.Image] = {}
        self._sized: Dict[Tuple[str, int, int, int], Image.Image] = {}
        self._lock = threading.Lock()

    def refresh(self) -> None:
        """Look at the folders; read their pictures again if any was added, changed or taken away. A later folder wins a clash."""
        found: Dict[str, Path] = {}
        stamp: List[Tuple] = []
        for folder in self.folders:
            try:
                for path in sorted(folder.glob("*.png")):
                    found[path.stem.lower()] = path
                    stamp.append((str(path), path.stat().st_mtime_ns))
            except OSError:
                continue
        with self._lock:
            if tuple(stamp) == self._stamp:
                return
            raw: Dict[str, Image.Image] = {}
            for name, path in found.items():
                try:
                    with Image.open(path) as picture:
                        if picture.width * picture.height > MAX_SKIN_PIXELS:
                            logger.warning("chart skin: %s is too large to be a note picture, left out", path.name)
                            continue
                        raw[name] = picture.convert("RGBA")
                except Exception as error:      # a damaged or unreadable file leaves that one note drawn, never the preview
                    logger.warning("chart skin: %s could not be read (%s), left out", path.name, type(error).__name__)
            self._raw, self._sized, self._stamp = raw, {}, tuple(stamp)

    def pick(self, role: str, variant: str = "") -> Optional[str]:
        """The picture to use for a role, preferring the variant's own: ``tap`` with ``each`` is ``tap_each`` if the pack has it."""
        for name in (f"{role}_{variant}" if variant else "", role):
            if name and name in self._raw:
                return name
        return None

    def sprite(self, name: str, width: int, height: int = 0, angle: float = 0.0) -> Image.Image:
        """A picture at a size, turned by an angle in degrees clockwise; height 0 keeps its proportions."""
        key = (name, width, height, int(round(angle / 5.0)) * 5)
        with self._lock:
            found = self._sized.get(key)
            if found is None:
                if len(self._sized) > 800:
                    self._sized.clear()          # a stretched hold is a new size nearly every frame: do not keep them all
                raw = self._raw[name]
                found = raw.resize((max(1, width), max(1, height or round(width * raw.height / raw.width))), Image.Resampling.LANCZOS)
                if key[3]:
                    found = found.rotate(-key[3], resample=Image.Resampling.BICUBIC, expand=True)
                self._sized[key] = found
            return found


_skin = Skin(BUNDLED_SKIN, CHART_SKIN_DIR)


class Field:
    """Where things go on the picture: the ring of eight buttons, the touch areas inside it, and how big a note is."""

    def __init__(self, size: int, ss: int = 2):
        self.size, self.ss = size, ss
        self.w = size * ss
        self.cx = self.cy = self.w / 2
        self.r = self.w * 0.385
        self.nr = self.w * 0.034

    @staticmethod
    def angle(key: str) -> float:
        return math.radians(-90 + 22.5 + 45 * (int(key) - 1))      # key 1 sits just right of the top, then clockwise

    def pt(self, key: str, radius: Optional[float] = None) -> Tuple[float, float]:
        a, r = self.angle(key), self.r if radius is None else radius
        return (self.cx + r * math.cos(a), self.cy + r * math.sin(a))

    def touch(self, position: str) -> Tuple[float, float]:
        """A touch area's place: A and B follow the buttons, D and E sit between them, C is the middle."""
        if position[:1] == "C":
            return (self.cx, self.cy)
        area, number = position[:1], int(position[1:] or 1)
        on_key, between = self.angle(str(number)), math.radians(-90 + 45 * (number - 1))
        share, a = {"A": (0.80, on_key), "B": (0.42, on_key), "D": (0.95, between), "E": (0.66, between)}.get(area, (0.80, on_key))
        return (self.cx + self.r * share * math.cos(a), self.cy + self.r * share * math.sin(a))


def _mix(a: Sequence[int], b: Sequence[int], share: float) -> Tuple[int, ...]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * share)) for i in range(len(a)))


def _arc(field: Field, start: str, end: str, clockwise: bool, dip: float = 1.0, steps: int = 48) -> List[Tuple[float, float]]:
    """Along the ring from one button to another; a dip below 1 goes in towards the middle part of the way, as the loops do."""
    a0, a1 = field.angle(start), field.angle(end)
    sweep = (a1 - a0) % (2 * math.pi) if clockwise else -((a0 - a1) % (2 * math.pi))
    if abs(sweep) < 1e-6:
        sweep = 2 * math.pi if clockwise else -2 * math.pi        # back to the button it left: all the way round
    out = []
    for i in range(steps + 1):
        f = i / steps
        inward = max(0.0, min(1.0, f / 0.18, (1 - f) / 0.18))
        r = field.r * (1 - (1 - dip) * inward)
        out.append((field.cx + r * math.cos(a0 + sweep * f), field.cy + r * math.sin(a0 + sweep * f)))
    return out


def _line(points: Sequence[Tuple[float, float]], per: int = 12) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.extend((x0 + (x1 - x0) * i / per, y0 + (y1 - y0) * i / per) for i in range(per))
    out.append(points[-1])
    return out


def _one_path(field: Field, start: str, shape: str, end: str) -> List[List[Tuple[float, float]]]:
    """The track of one turn of a slide, from the button `start`: one line, or three for a wifi."""
    last = end[-1]
    if shape == "-":
        return [_line([field.pt(start), field.pt(last)])]
    if shape in ("<", ">"):
        upper = int(start) in (7, 8, 1, 2)        # a > turns clockwise from the top half of the ring and the other way from the bottom
        return [_arc(field, start, last, clockwise=(shape == ">") == upper)]
    if shape == "^":
        return [_arc(field, start, last, clockwise=(int(last) - int(start)) % 8 <= 4)]
    if shape == "v":
        return [_line([field.pt(start), (field.cx, field.cy), field.pt(last)])]
    if shape == "V" and len(end) >= 2:
        return [_line([field.pt(start), field.pt(end[0]), field.pt(end[1])])]
    if shape in ("p", "q", "pp", "qq"):
        return [_arc(field, start, last, clockwise=shape[0] == "q", dip=0.80 if len(shape) == 2 else 0.52)]
    if shape in ("s", "z"):
        # the S and the Z are approximated: out to one side, across, and back to the other
        a, b = field.pt(start), field.pt(last)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        px, py = -dy / length, dx / length
        k = 0.24 * length * (1 if shape == "s" else -1)
        return [_line([a, (a[0] + dx * .33 + px * k, a[1] + dy * .33 + py * k), (a[0] + dx * .67 - px * k, a[1] + dy * .67 - py * k), b])]
    if shape == "w":
        centre = int(last)
        return [_line([field.pt(start), field.pt(str(((centre + d - 1) % 8) + 1))]) for d in (-1, 0, 1)]
    return [_line([field.pt(start), field.pt(last)])]


def slide_paths(field: Field, note: Note) -> List[List[Tuple[float, float]]]:
    """Every track a slide's star runs along, as dots to follow. A slide that turns more than once is its turns joined end to end."""
    if not note.position.isdigit():
        return []
    turns = note.corners or ((note.shape, note.end),)
    if not turns or not turns[-1][1]:
        return []
    start, joined = note.position, None
    for shape, end in turns:
        if not end or not end[-1].isdigit():
            return []
        paths = _one_path(field, start, shape, end)
        joined = paths if joined is None else [joined[0] + paths[0][1:]]
        start = end[-1]
    return joined or []


class Track:
    """A slide's route as dots, with how far along each one is, so a star's place at any moment is a lookup and not a walk."""

    def __init__(self, points: Sequence[Tuple[float, float]]):
        self.points = list(points)
        self.marks = [0.0]
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:]):
            self.marks.append(self.marks[-1] + math.hypot(x1 - x0, y1 - y0))
        self.length = self.marks[-1]

    def at(self, share: float) -> Tuple[Tuple[float, float], float]:
        """The point a share of the way along, and which way the track is heading there."""
        goal = self.length * max(0.0, min(1.0, share))
        i = max(1, min(len(self.marks) - 1, bisect_left(self.marks, goal)))
        (x0, y0), (x1, y1) = self.points[i - 1], self.points[i]
        g = (goal - self.marks[i - 1]) / ((self.marks[i] - self.marks[i - 1]) or 1.0)
        return (x0 + (x1 - x0) * g, y0 + (y1 - y0) * g), math.atan2(y1 - y0, x1 - x0)


def busiest_start(chart: Chart, seconds: float = SECONDS) -> float:
    """Where the most is going on: the start of the stretch with the most notes, a slide or a hold counting double."""
    if chart.seconds <= seconds:
        return 0.0
    times = [n.time for n in chart.notes]
    weights = [2 if n.kind in ("slide", "hold") else 1 for n in chart.notes]
    prefix = [0]
    for w in weights:
        prefix.append(prefix[-1] + w)
    best, where, moment = -1, 0.0, 0.0
    while moment <= chart.seconds - seconds:
        weight = prefix[bisect_left(times, moment + seconds)] - prefix[bisect_left(times, moment)]
        if weight > best:
            best, where = weight, moment
        moment += 0.5
    return max(0.0, where - 0.3)


def place(t: float, hit: float, speed: float = NOTE_SPEED) -> Optional[Tuple[float, float]]:
    """Where a note is at a moment, as (how far out along its lane as a share of the way to the button, its size as a share of full).

    None before it first shows. It grows where it is 1.225 out, then travels, then waits on the button once it has been struck.
    """
    distance = (t - hit) * speed + RING_UNITS
    size = distance * 0.4 + 0.51
    if size <= APPEAR:
        return None
    return min(max(distance, PINNED), RING_UNITS) / RING_UNITS, min(1.0, size)


class _Painter:
    def __init__(self, notes: Sequence[Note], field: Field, skin: Skin):
        self.notes, self.f, self.skin = notes, field, skin
        self.paths = {id(n): [Track(path) for path in slide_paths(field, n)] for n in notes if n.kind == "slide"}
        self.label = ImageFont.load_default(size=max(10, field.size // 34))

    @staticmethod
    def tone(note: Note, base: Tuple[int, int, int]) -> Tuple[int, int, int]:
        return ORANGE if note.brk else GOLD if note.each > 1 else base

    @staticmethod
    def variant(note: Note) -> str:
        return "break" if note.brk else "each" if note.each > 1 else ""

    def put(self, img: Image.Image, name: str, xy: Tuple[float, float], width: float, angle: float = 0.0, height: float = 0.0,
            fade: float = 1.0) -> None:
        picture = self.skin.sprite(name, round(width), round(height), angle)
        if fade < 1.0:
            picture = picture.copy()
            picture.putalpha(picture.getchannel("A").point(lambda v: int(v * fade)))
        img.paste(picture, (round(xy[0] - picture.width / 2), round(xy[1] - picture.height / 2)), picture)

    def circle(self, img: Image.Image, d: ImageDraw.ImageDraw, note: Note, xy: Tuple[float, float], radius: float, base: Tuple[int, int, int]) -> None:
        name = self.skin.pick("tap", self.variant(note))
        if name:
            self.put(img, name, xy, radius * 2.6)
            if note.ex and self.skin.pick("tap_ex"):
                self.put(img, "tap_ex", xy, radius * 2.7)
            return
        d.ellipse([xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius], fill=self.tone(note, base), outline=WHITE, width=3 * self.f.ss)

    def star(self, img: Image.Image, d: ImageDraw.ImageDraw, note: Note, xy: Tuple[float, float], spin: float, size: float = 1.0) -> None:
        radius = self.f.nr * 1.05 * size
        name = self.skin.pick("star", self.variant(note))
        if name:
            self.put(img, name, xy, radius * 2.6, math.degrees(spin))
            if note.ex and self.skin.pick("star_ex"):
                self.put(img, "star_ex", xy, radius * 2.7, math.degrees(spin))
            return
        points = []
        for i in range(10):
            rr = radius if i % 2 == 0 else radius * 0.45
            a = spin + math.pi * i / 5 - math.pi / 2
            points.append((xy[0] + rr * math.cos(a), xy[1] + rr * math.sin(a)))
        d.polygon(points, fill=self.tone(note, BLUE), outline=WHITE)

    def track(self, img: Image.Image, d: ImageDraw.ImageDraw, note: Note, t: float) -> None:
        f = self.f
        progress = (t - note.time - note.wait) / max(note.duration, 0.05)
        name = self.skin.pick("slide", self.variant(note))
        for path in self.paths[id(note)]:
            count = max(2, int(path.length / (20 * f.ss * f.size / 440)))
            for i in range(count):
                share = (i + 0.5) / count
                if share < progress:
                    continue                  # the star has been past it
                (x, y), a = path.at(share)
                if name:
                    self.put(img, name, (x, y), f.nr * 0.95, math.degrees(a) + 180)        # the pack's chevron points left
                    continue
                s = 6 * f.ss * f.size / 440
                colour = _mix(BG, self.tone(note, BLUE), 0.55)
                d.line([(x - s * math.cos(a) - s * .8 * math.sin(a), y - s * math.sin(a) + s * .8 * math.cos(a)), (x, y),
                        (x - s * math.cos(a) + s * .8 * math.sin(a), y - s * math.sin(a) - s * .8 * math.cos(a))], fill=colour, width=3 * f.ss)

    def hold(self, img: Image.Image, d: ImageDraw.ImageDraw, note: Note, t: float) -> None:
        f, hit = self.f, note.time
        head = place(t, hit)
        if head is None or t > hit + note.duration + 0.05:
            return
        tail = place(t, hit + note.duration)
        a = f.pt(note.position, f.r * (tail[0] if tail else PINNED / RING_UNITS))
        b = f.pt(note.position, f.r * head[0])
        shape = self.skin.pick("hold", self.variant(note))
        if shape:
            # the whole hexagon, stretched from the tail to the head with its top cap outermost
            width = f.nr * 2.6 * head[1]
            length = math.hypot(b[0] - a[0], b[1] - a[1]) + width
            turn = math.degrees(f.angle(note.position)) + 90
            at = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            self.put(img, shape, at, width, turn, height=length)
            if note.ex and self.skin.pick("hold_ex"):
                self.put(img, "hold_ex", at, width * 1.04, turn, height=length * 1.02)
            return
        d.line([a, b], fill=_mix(BG, self.tone(note, PINK), 0.85), width=int(f.nr * 1.5))
        self.circle(img, d, note, a, f.nr * 0.75, PINK)
        self.circle(img, d, note, b, f.nr * head[1], PINK)

    def touch(self, img: Image.Image, d: ImageDraw.ImageDraw, note: Note, t: float) -> None:
        f, hit = self.f, note.time
        x, y = f.touch(note.position)
        far = (hit - t) / TOUCH_APPROACH
        held = note.kind == "touch_hold" and far < 0 and t < hit + note.duration
        if not (-0.02 <= far <= 1.0 or held):
            return
        step = f.nr * (1.15 + 2.6 * max(0.0, min(1.0, far)))
        variant = self.variant(note)
        triangle = self.skin.pick("touch", variant)
        if triangle:
            # four triangles close in on the place, each with its point to the middle: above, right, below, left
            for i, ((dx, dy), turn) in enumerate((((0, -1), 180), ((1, 0), 270), ((0, 1), 0), ((-1, 0), 90))):
                name = self.skin.pick("touch_hold", str(i + 1)) if note.kind == "touch_hold" and variant == "" else triangle
                self.put(img, name or triangle, (x + dx * step, y + dy * step), f.nr * 2.1, turn)
            point = self.skin.pick("touch_point", variant)
            if point:
                self.put(img, point, (x, y), f.nr * 0.9)
            if held and self.skin.pick("touch_hold_border"):
                self.put(img, "touch_hold_border", (x, y), f.nr * 3.6)
            return
        size = f.nr * (1.0 + 1.6 * max(0.0, far))
        colour = self.tone(note, CYAN)
        d.polygon([(x, y - size), (x + size, y), (x, y + size), (x - size, y)], outline=colour, width=3 * f.ss)
        d.polygon([(x, y - f.nr * .55), (x + f.nr * .55, y), (x, y + f.nr * .55), (x - f.nr * .55, y)], fill=colour)

    def burst(self, img: Image.Image, d: ImageDraw.ImageDraw, note: Note, t: float) -> None:
        f, since = self.f, t - note.time
        if not 0 <= since < 0.22 or note.kind == "slide":
            return
        fade = 1 - since / 0.22
        touch = note.kind in ("touch", "touch_hold")
        at = f.touch(note.position) if touch or not note.position.isdigit() else f.pt(note.position)
        size = f.nr * (1.2 + 1.6 * (1 - fade))
        name = self.skin.pick("touch_hit" if touch else "hit")
        if name:
            self.put(img, name, at, size * 2, fade=fade)
        else:
            d.ellipse([at[0] - size, at[1] - size, at[0] + size, at[1] + size], outline=_mix(BG, WHITE, fade), width=2 * f.ss)

    def frame(self, t: float, start: float, end: float) -> Image.Image:
        f = self.f
        img = Image.new("RGB", (f.w, f.w), BG)
        d = ImageDraw.Draw(img)
        field_art, button = self.skin.pick("field"), self.skin.pick("button")
        if field_art:
            self.put(img, field_art, (f.cx, f.cy), f.r * 2.1)        # the playfield picture carries its own button marks
        else:
            d.ellipse([f.cx - f.r * 1.06, f.cy - f.r * 1.06, f.cx + f.r * 1.06, f.cy + f.r * 1.06], outline=RING, width=2 * f.ss)
            d.ellipse([f.cx - f.r * .42, f.cy - f.r * .42, f.cx + f.r * .42, f.cy + f.r * .42], outline=(30, 29, 48), width=f.ss)
        for k in range(1, 9):
            x, y = f.pt(str(k))
            if button:
                self.put(img, button, (x, y), f.nr * 1.9)
            elif not field_art:
                d.ellipse([x - f.nr * .87, y - f.nr * .87, x + f.nr * .87, y + f.nr * .87], outline=(60, 58, 88), width=2 * f.ss)
        look = max(APPROACH, TOUCH_APPROACH) + 0.05
        live = [n for n in self.notes if n.time - look <= t <= n.time + n.duration + 0.5]
        for note in live:
            if note.kind == "slide" and id(note) in self.paths and t >= note.time - APPROACH * 0.8:
                self.track(img, d, note, t)
        for note in live:
            hit = note.time
            if note.kind == "hold" and note.position.isdigit():
                self.hold(img, d, note, t)
            elif note.kind == "tap" and note.position.isdigit():
                placed = place(t, hit)
                if placed is not None and t <= hit + 0.02:
                    self.circle(img, d, note, f.pt(note.position, f.r * placed[0]), f.nr * placed[1], PINK)
            elif note.kind == "slide" and note.position.isdigit():
                if t < hit:
                    placed = place(t, hit)
                    if placed is not None:
                        self.star(img, d, note, f.pt(note.position, f.r * placed[0]), t * 3.0, placed[1])
                elif id(note) in self.paths:
                    travelled = (t - hit - note.wait) / max(note.duration, 0.05)
                    if travelled < 1.0:
                        for path in self.paths[id(note)]:
                            self.star(img, d, note, path.at(travelled)[0], t * 3.0)
            elif note.kind in ("touch", "touch_hold"):
                self.touch(img, d, note, t)
            self.burst(img, d, note, t)
        img = img.reduce(f.ss)        # drawn at twice the size for smooth edges; an exact box average back down is the cheap way
        d = ImageDraw.Draw(img)
        shown = max(0.0, t)
        d.text((14, f.size - 26), f"{int(shown // 60)}:{shown % 60:04.1f}", fill=INK, font=self.label)
        left, right, top = 70, f.size - 14, f.size - 20
        d.rectangle([left, top, right, top + 4], fill=(40, 38, 62))
        d.rectangle([left, top, left + (right - left) * max(0.0, min(1.0, (t - start) / (end - start))), top + 4], fill=PINK)
        return img


@dataclass
class Preview:
    gif: bytes
    start: float          # seconds into the chart where the clip begins
    end: float
    size: int
    fps: int


def _encode(frames: List[Image.Image], fps: int) -> bytes:
    # a few frames from across the clip set the palette, with the plain colours added outright so a small note is never washed out
    width, height = frames[0].width, frames[0].height
    sheet = Image.new("RGB", (width * 6, height + 40))
    for i in range(6):
        sheet.paste(frames[(len(frames) * (i + 1)) // 7], (width * i, 0))
    swatches = ImageDraw.Draw(sheet)
    shades = [c for base in (PINK, GOLD, ORANGE, BLUE, CYAN, WHITE) for c in (base, _mix(BG, base, .55), _mix(BG, base, .8))]
    for i, colour in enumerate(shades):
        swatches.rectangle([i * 40, height + 4, i * 40 + 36, height + 36], fill=colour)
    palette = sheet.quantize(colors=240, method=Image.Quantize.MEDIANCUT)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    out = io.BytesIO()
    quantized[0].save(out, format="GIF", save_all=True, append_images=quantized[1:], duration=int(1000 / fps), loop=0, disposal=1, optimize=False)
    return out.getvalue()


def render_preview(chart: Chart, limit: int = 10 * 1024 * 1024, start: Optional[float] = None, seconds: float = SECONDS,
                   skin: Optional[Skin] = None) -> Optional[Preview]:
    """A looping picture of part of a chart: the notes coming in, slides running their tracks, as they would be played.

    Smaller and slower versions are tried until one fits `limit`; if even the smallest does not, that one is returned and the
    caller sees it is over. None when the chart has no notes to show.

    :param chart: The parsed chart.
    :type chart: Chart
    :param limit: The most bytes the picture may take, which is what the server lets be uploaded.
    :type limit: int
    :param start: Where in the chart to begin, in seconds; the busiest stretch when left out.
    :type start: Optional[float]
    :param seconds: How long a clip.
    :type seconds: float
    :param skin: The note pictures to use; the bundled ones and the folder in the settings when left out.
    :type skin: Optional[Skin]
    :rtype: Optional[Preview]
    """
    if not chart.notes:
        return None
    skin = skin or _skin
    skin.refresh()
    seconds = max(2.0, min(seconds, chart.seconds or seconds))
    begin = busiest_start(chart, seconds) if start is None else max(0.0, start)
    finish = begin + seconds
    window = [n for n in chart.notes if begin - 1 <= n.time <= finish + 1]
    result = None
    for size, fps in ATTEMPTS:
        painter = _Painter(window, Field(size), skin)
        frames = [painter.frame(begin + i / fps, begin, finish) for i in range(int(seconds * fps))]
        result = Preview(_encode(frames, fps), begin, finish, size, fps)
        if len(result.gif) <= limit:
            break
    return result
