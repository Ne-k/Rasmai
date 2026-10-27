from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple
import logging
import os
import re
import threading
import time

from rasmai.config import ASTRODX_DIR
from rasmai.engine.analysis.charts import ChartRef, loose_title
from rasmai.engine.simai.parse import Chart, parse

logger = logging.getLogger(__name__)

# An AstroDX (MajdataPlay) songs folder: anywhere under the root, one folder a song, holding maidata.txt with every difficulty
# as &inote_N= and the music beside it. The owner copies it onto the server; nothing here is downloaded.
SLOTS = {"basic": 2, "advanced": 3, "expert": 4, "master": 5, "remaster": 6, "utage": 7}
TRACKS = ("track.mp3", "track.ogg", "track.wav")
ARTS = ("bg.png", "bg.jpg", "bg.jpeg")

# a DX and a standard chart of one song are two folders, told apart by a marker in the folder name or the title
MARKER = re.compile(r"[\[(（【]\s*(DX|SD|STD)\s*[\])）】]", re.I)
FIELD = re.compile(r"^\s*&([A-Za-z_]\w*)\s*=", re.M)

# a slot whose note count is this far from the published one is probably not the chart asked for
CLOSE = 0.05
# how often the tree is walked to see whether a pack was added or changed
CHECK_EVERY = 60.0


@dataclass(frozen=True)
class Found:
    chart: Chart            # this one difficulty, its times on the audio file's clock (&first applied)
    maidata: str            # the whole maidata.txt, for the website's own reader
    slot: int               # the N of the &inote_N this difficulty is
    track: Optional[Path]
    art: Optional[Path]
    folder: Path


@dataclass(frozen=True)
class _Song:
    folder: Path
    maidata: Path
    kind: str               # "dx", "std", or "" when nothing says
    slots: FrozenSet[int]
    track: Optional[Path]
    art: Optional[Path]


_lock = threading.Lock()
_memo: Tuple[Optional[Path], float, Tuple[int, float], Dict[str, List[_Song]]] = (None, 0.0, (0, 0.0), {})
_scanning = False
_sure: Dict[Tuple[Tuple[str, str, str], int], bool] = {}      # held() for unmarked folders, which needs the notes read; forgotten on a rescan


def _read(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # older Japanese packs are written in Shift JIS
        return data.decode("cp932", errors="replace")


def _fields(text: str) -> Dict[str, str]:
    """Every &name=value in a maidata.txt, a value running to the next line that starts with &."""
    marks = list(FIELD.finditer(text))
    return {mark.group(1).lower(): text[mark.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)].strip()
            for i, mark in enumerate(marks)}


def _inside(path: Path, base: Path) -> Optional[Path]:
    # folder and file names come from an uploaded pack, so a link pointing out of the root is refused
    try:
        real = path.resolve()
    except OSError:
        return None
    return real if real.is_relative_to(base) else None


def _kind(*names: str) -> str:
    for name in names:
        marker = MARKER.search(name or "")
        if marker:
            return "dx" if marker.group(1).upper() == "DX" else "std"
    return ""


def _walk(base: Path) -> List[Tuple[Path, Dict[str, str]]]:
    """Every folder holding a maidata.txt, with its file names by their lower case; links to folders are not followed."""
    found = []
    for folder, _, names in os.walk(base):
        names_by = {name.lower(): name for name in names}
        if "maidata.txt" in names_by:
            found.append((Path(folder), names_by))
    return found


def _stamp(found: List[Tuple[Path, Dict[str, str]]]) -> Tuple[int, float]:
    latest = 0.0
    for folder, names in found:
        try:
            latest = max(latest, os.stat(folder).st_mtime, os.stat(folder / names["maidata.txt"]).st_mtime)
        except OSError:
            pass
    return len(found), latest


def _build(base: Path, found: List[Tuple[Path, Dict[str, str]]]) -> Dict[str, List[_Song]]:
    index: Dict[str, List[_Song]] = {}
    for folder, names in found:
        maidata = _inside(folder / names["maidata.txt"], base)
        if maidata is None:
            continue
        try:
            fields = _fields(_read(maidata))
        except OSError as error:
            logger.info("astrodx: could not read %s: %s", maidata, error)
            continue
        title = fields.get("title") or folder.name
        slots = frozenset(int(name[6:]) for name, value in fields.items() if re.fullmatch(r"inote_\d", name) and value)

        def beside(choices: Tuple[str, ...]) -> Optional[Path]:
            return next((path for path in (_inside(folder / names[c], base) for c in choices if c in names) if path), None)

        song = _Song(maidata.parent, maidata, _kind(title, folder.name), slots, beside(TRACKS), beside(ARTS))
        # by its title, and by its folder's name for a pack that left the title out or wrote it differently
        for key in {loose_title(MARKER.sub(" ", title)), loose_title(MARKER.sub(" ", folder.name))} - {""}:
            index.setdefault(key, []).append(song)
    return index


def _scan(root: Path) -> None:
    """Walk the tree and read it again if it changed since the last walk."""
    global _memo, _scanning
    try:
        try:
            base = root.resolve()
            found = _walk(base) if base.is_dir() else []
        except OSError:
            base, found = root, []
        fresh = _stamp(found)
        held_root, _, stamp, index = _memo
        if held_root != root or fresh != stamp:
            index = _build(base, found)
            _sure.clear()
            if found:
                logger.info("astrodx: %d song folders under %s", len(found), base)
        _memo = (root, time.monotonic(), fresh, index)
    except Exception:
        logger.exception("astrodx: could not read the songs folder")
    finally:
        _scanning = False


def _index() -> Dict[str, List[_Song]]:
    """The songs under ASTRODX_DIR by folded title, as last read; walked again at most once a minute, read again only when it changed."""
    global _scanning
    root = ASTRODX_DIR
    with _lock:
        held_root, checked, _, index = _memo
        index = index if held_root == root else {}
        if (held_root == root and time.monotonic() - checked < CHECK_EVERY) or _scanning:
            return index
        _scanning = True
    # a big pack on a shared folder takes seconds to walk, and the bot's event loop asks this, so the walk runs beside it
    threading.Thread(target=_scan, args=(root,), name="astrodx-scan", daemon=True).start()
    return index


def _candidates(ref: ChartRef) -> List[Tuple[_Song, bool]]:
    """The folders that could hold this chart, each with whether its type is certain."""
    songs = _index().get(loose_title(MARKER.sub(" ", ref.title)), [])
    mine = [song for song in songs if song.kind == ref.chart_type]
    if mine:
        return [(song, True) for song in mine]
    # an unmarked folder beside one marked as the other type is this type; alone it could be either, so the note count decides
    other = any(song.kind for song in songs)
    return [(song, other) for song in songs if not song.kind]


def _off(chart: Optional[Chart], published: int) -> float:
    if chart is None:
        return float("inf")
    return abs(len(chart.notes) - published) / published if published else 0.0


def _pick(fields: Dict[str, str], slot: int, published: int) -> Optional[Tuple[int, Chart, float]]:
    """The slot holding the chart asked for, its notes, and how far its count is from the published one."""
    body = fields.get(f"inote_{slot}")
    chart = parse(body) if body else None
    off = _off(chart, published)
    if (chart is not None and off <= CLOSE) or not published:
        return (slot, chart, off) if chart is not None else None
    # a pack that numbers its difficulties its own way: the slot whose count matches is the one asked for
    others = [(n, parse(fields[f"inote_{n}"])) for n in range(1, 8) if n != slot and fields.get(f"inote_{n}")]
    near = min(((n, other, _off(other, published)) for n, other in others), key=lambda pick: pick[2], default=None)
    if near is not None and near[2] <= CLOSE:
        return near
    return (slot, chart, off) if chart is not None else None


def find(ref: ChartRef) -> Optional[Found]:
    """This chart from the AstroDX folder, with its music and picture, or None when the folder does not have it; never raises.

    :param ref: The chart.
    :type ref: ChartRef
    :rtype: Optional[Found]
    """
    slot = SLOTS.get(ref.difficulty)
    if slot is None:
        return None
    published = int(ref.notes or 0)
    best: Optional[Tuple[float, Found]] = None
    for song, certain in _candidates(ref):
        try:
            text = _read(song.maidata)
        except OSError as error:
            logger.info("astrodx: could not read %s: %s", song.maidata, error)
            continue
        fields = _fields(text)
        picked = _pick(fields, slot, published)
        if picked is None:
            continue
        number, chart, off = picked
        if not certain and published and off > CLOSE:
            continue              # an unmarked folder whose counts do not match is the other type's chart
        if best is not None and best[0] <= off:
            continue
        # the notation counts from its first beat, which sits &first seconds into the track
        try:
            first = float(fields.get(f"first_{number}") or fields.get("first") or 0)
        except ValueError:
            first = 0.0
        for note in chart.notes:
            note.time += first
        chart.seconds += first
        best = (off, Found(chart, text, number, song.track, song.art, song.folder))
    return best[1] if best else None


def held(ref: ChartRef) -> bool:
    """Whether the AstroDX folder has a song folder with this difficulty in it, without reading its notes.

    An unmarked folder alone could be either type, so for one of those its notes are read once to say what find would.

    :param ref: The chart.
    :type ref: ChartRef
    :rtype: bool
    """
    slot = SLOTS.get(ref.difficulty)
    if slot is None:
        return False
    candidates = [(song, certain) for song, certain in _candidates(ref) if slot in song.slots]
    if any(certain for _, certain in candidates):
        return True
    if not candidates:
        return False
    # an unmarked folder alone could be either type, and only its note count says which, as find decides
    key = (ref.key, int(ref.notes or 0))
    if key not in _sure:
        _sure[key] = find(ref) is not None
    return _sure[key]
