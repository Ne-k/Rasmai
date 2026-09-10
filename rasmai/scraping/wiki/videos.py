from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Sequence, Tuple
import html
import re


from rasmai.storage.db import chart_videos_get, chart_videos_set
from rasmai.scraping.wiki.client import DIFFICULTIES, FOUND_TTL, MISSING_TTL, _get, match_title, page_url, wiki_titles


def parse_videos(page: str) -> Dict[Tuple[str, str], str]:
    """YouTube ids keyed by (chart type, difficulty) from a song page's Videos section.

    'official' under ('', 'official') is the song's own video. A maimai video block with no
    chart-type heading is keyed with chart type '' for the caller to resolve.

    :param page: Which page to show, counting from zero.
    :type page: str
    :rtype: Dict[Tuple[str, str], str]
    """
    start = page.find('id="Videos"')
    if start < 0:
        return {}
    end = page.find('class="printfooter"', start)
    section = page[start:end if end > 0 else None]
    out: Dict[Tuple[str, str], str] = {}
    game, chart_type, label = "", "", ""
    for match in re.finditer(r'<h([234])[^>]*\bid="([^"]*)"|line-height:1\.6;">\s*([^<]*?)\s*<|youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{6,})', section):
        level, heading, text, video = match.groups()
        if level == "3":
            game = "maimai" if heading.lower().startswith("maimai") else heading
            chart_type = ""
        elif level == "4":
            low = heading.lower()
            chart_type = "std" if low.startswith("standard") else "dx" if low.startswith("dx") else "utage" if "utage" in low or "宴" in heading else low
        elif level == "2":
            game = ""
        elif text is not None:
            label = text
        elif video:
            key = re.sub(r"[^a-z]", "", html.unescape(label).lower())
            if not game and key.startswith("official"):
                out.setdefault(("", "official"), video)
            elif game == "maimai" and chart_type != "utage" and key in DIFFICULTIES:
                out.setdefault((chart_type, DIFFICULTIES[key]), video)
    return out


def _resolve_untyped(videos: Dict[Tuple[str, str], str], chart_types: Sequence[str]) -> Dict[Tuple[str, str], str]:
    """A page with one maimai section and no Standard/DX heading covers whichever chart type the song has.

    :param videos: A video per chart, keyed by type and difficulty.
    :type videos: Dict[Tuple[str, str], str]
    :param chart_types: Which chart types the song has.
    :type chart_types: Sequence[str]
    :rtype: Dict[Tuple[str, str], str]
    """
    only = [ct for ct in dict.fromkeys(chart_types)]
    fallback = only[0] if len(only) == 1 else "std"
    return {(ct if ct or diff == "official" else fallback, diff): vid for (ct, diff), vid in videos.items()}


# the Trivia section is one bullet list for every game the song is in; a bullet names its
# game, and follow-ups ("In the Asian version, ...") belong to the game named before them
_OTHER_GAMES = re.compile(r"CHUNITHM|中二节奏|オンゲキ|O\.N\.G\.E\.K\.I|ONGEKI|音击|GROOVE COASTER|Taiko|太鼓|jubeat|pop'n|SOUND VOLTEX|WACCA|Arcaea|"
                          r"Cytus|Deemo|Project DIVA|DanceDance|beatmania|GITADORA|Nostalgia|DANCERUSH|CROSS×BEATS|Lanota|Phigros", re.I)


_MAIMAI = re.compile(r"maimai|舞萌|でらっくす", re.I)


_CHINESE_ONLY = re.compile(r"^\s*In the Chinese version", re.I)


# a bullet counts as an unlock note when it says the song is (or was) unlockable, how, or that it is available by default;
# "no one unlocked it on day one" and "the LEGEND boss song" are trivia and stay out
_UNLOCK_WORDS = re.compile(r"\b(?:is|are|was|were|be|been|became|can be|could be|needed to be|need to be|must be)\s+unlock|unlockable|"
                           r"available by default|by default|as an? [^.]{0,60}?reward|"
                           r"by (?:using|spending|clearing|reaching|filling|getting|completing|scoring|playing|purchasing|defeating)|"
                           r"music tickets?|Stamp Card|Item Exchange|conducted to", re.I)


class _Bullets(HTMLParser):
    """Top-level bullets of a list, each with the text of its nested bullets folded in."""

    def __init__(self) -> None:
        super().__init__()
        self.items: List[List[str]] = []
        self.depth = 0
        self.stack: List[List[str]] = []      # open <li> elements, each collecting text pieces

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "ul":
            self.depth += 1
        elif tag == "li":
            piece: List[str] = []
            if self.depth <= 1:
                self.items.append(piece)
            elif self.stack:
                self.stack[0].append("\n")     # a sub-bullet starts a new line of its top-level bullet
            self.stack.append(piece if self.depth <= 1 else self.stack[0])

    def handle_endtag(self, tag: str) -> None:
        if tag == "ul":
            self.depth = max(0, self.depth - 1)
        elif tag == "li" and self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1].append(data)


def parse_unlock(page: str) -> List[str]:
    """The maimai bullets of a song page's Trivia that say how the song or its charts are unlocked.

    Each bullet is one line, with its sub-bullets folded in; bullets about other games and
    the Chinese version are left out, and a bullet with no game named belongs to the game of
    the bullet before it, which is how the wiki writes its "In the Asian version" follow-ups.

    :param page: Which page to show, counting from zero.
    :type page: str
    :rtype: List[str]
    """
    start = page.find('id="Trivia"')
    if start < 0:
        return []
    end = page.find("<h2", start + 10)
    parser = _Bullets()
    try:
        parser.feed(page[start:end if end > 0 else None])
    except Exception:            # a malformed page is worth no notes, not an error
        return []
    out: List[str] = []
    game = ""
    for pieces in parser.items:
        text = html.unescape("".join(pieces))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text).strip()
        if not text:
            continue
        head = text.split("\n", 1)[0]
        ours = _MAIMAI.search(head)
        theirs = _OTHER_GAMES.search(head)
        if ours and (not theirs or ours.start() < theirs.start()):
            game = "maimai"          # a bullet about another game may still mention maimai further on
        elif theirs:
            game = "other"
        if game != "maimai":
            continue
        lines = [line for line in text.split("\n") if line and not _CHINESE_ONLY.match(line) and not _OTHER_GAMES.search(line)]
        if not lines or not any(_UNLOCK_WORDS.search(line) for line in lines):
            continue
        out.append(" ".join(lines)[:500])
        if len(out) >= 4:
            break
    return out


def lookup_page(title: str, reading: str, chart_types: Sequence[str]) -> Dict[str, Any]:
    """What the wiki holds for a song: {"page": page title or "", "videos": {(type, difficulty): id}, "unlock": [lines]}.

    From the cache when fresh, else from the wiki. Blocking; run in a thread.

    :param title: The song title.
    :type title: str
    :param reading: The song's title as it is read.
    :type reading: str
    :param chart_types: Which chart types the song has.
    :type chart_types: Sequence[str]
    :rtype: Dict[str, Any]
    """
    cached = chart_videos_get(title)
    if cached is not None and cached.get("unlock") is not None:
        fetched = datetime.fromisoformat(cached["fetched_at"])
        ttl = FOUND_TTL if cached["page"] else MISSING_TTL
        if datetime.now() - fetched < ttl:
            return {"page": cached["page"], "unlock": cached["unlock"],
                    "videos": {tuple(k.split("|", 1)): v for k, v in cached["videos"].items()}}
    titles = wiki_titles()
    page_title = match_title(title, reading, titles) if titles else None
    videos: Dict[Tuple[str, str], str] = {}
    unlock: List[str] = []
    if page_title:
        text = _get(page_url(page_title))
        if text is None:
            return {"page": "", "videos": {}, "unlock": []}      # transient: try again next time, nothing cached
        videos = _resolve_untyped(parse_videos(text), chart_types)
        unlock = parse_unlock(text)
    chart_videos_set(title, page_title or "", {f"{ct}|{diff}": vid for (ct, diff), vid in videos.items()}, unlock)
    return {"page": page_title or "", "videos": videos, "unlock": unlock}


def video_url(video_id: str) -> str:
    return f"https://youtu.be/{video_id}"


def wiki_url(page_title: str) -> str:
    return page_url(page_title)
