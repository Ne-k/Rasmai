from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import html
import json
import logging
import re
import threading
import time


from rasmai.storage.db import source_state_get, source_state_set
from rasmai.scraping.wiki.client import WIKI, _get, _lock

logger = logging.getLogger(__name__)


# The wiki keeps one page of areas per game version (maimai_DX:<version>/Areas): each area is a
# heading with its Japanese name, a line of facts ("English translation: ...", "Chinese name: ...",
# "Date added: ... (Asia)") and a table of rewards by total distance. The English names are the
# wiki's own; the game only ever transliterates them.
AREAS_SOURCE = "silentblue_areas_v2"     # bumped when the parser changes, so a stored crawl is redone


AREAS_TTL = timedelta(days=7)


_AREA_PAGE = re.compile(r'href="/maimai_DX:([^/"]+)/Areas"')


_AREA_HEADING = re.compile(r"<h3[^>]*>([\s\S]*?)</h3>")


_H2 = re.compile(r"<h2[^>]*>([\s\S]*?)</h2>")


_TAGS = re.compile(r"<[^>]+>")


_NAME_DECORATION = re.compile(r"[\s\u3000「」『』【】\[\]()（）・･:：\-−—～~!！?？.,、。]")


def area_key(name: str) -> str:
    """A name as it is matched: NFKC-folded, without spaces or brackets, so the site's and the wiki's spellings meet.

    :param name: The name to look up.
    :type name: str
    :rtype: str
    """
    import unicodedata
    folded = unicodedata.normalize("NFKC", str(name or ""))
    return _NAME_DECORATION.sub("", folded).replace("\u4e00", "\u30fc").casefold()   # the wiki sometimes types 一 for ー


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", _TAGS.sub(" ", fragment))).strip()


_TASK_TRACK = re.compile(r"^\(\s*(.+?)\s*Task Track\s*\)$", re.I)


def parse_reward_table(table: str) -> List[Dict[str, Any]]:
    """The reward ladder of one area table, read by its header row.

    Tables come in several shapes: the usual "No. | Distance(km) | Total(km) | Reward", the Splash
    era's with both units side by side ("... | Distance(m) | Total(m) | Reward"), and the first
    versions' in metres only. The km total is taken where there is one, a metres-only table is
    left out (the site counts in km today), and "Reward" spans two cells: its kind and its name.
    A "none ( X Task Track)" row is the task track that unlocks at that distance.

    :rtype: List[Dict[str, Any]]
    """
    rows = re.findall(r"<tr[\s\S]*?</tr>", table)
    if not rows:
        return []
    header = [_text(c) for c in re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", rows[0])]
    total_index = next((i for i, h in enumerate(header) if re.match(r"Total\s*\(?km\)?", h, re.I)), None)
    reward_index = next((i for i, h in enumerate(header) if re.match(r"Reward", h, re.I)), None)
    if total_index is None or reward_index is None:
        return []
    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        cells = [_text(c) for c in re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", row)]
        if len(cells) <= reward_index or not cells[total_index].isdigit():
            continue
        kind = cells[reward_index]
        name = cells[reward_index + 1] if len(cells) > reward_index + 1 else ""
        task = _TASK_TRACK.match(name)
        if task and kind.lower() in ("none", "", "-"):
            kind, name = "Task Track", task.group(1)
        if kind in ("-", "") and name in ("-", ""):
            continue
        out.append({"total": int(cells[total_index]), "kind": kind, "name": name})
    return out


def parse_areas(page: str, version: str) -> List[Dict[str, Any]]:
    """Every area on one version page: name, English and Chinese names, the Asia release date, the reward ladder.

    :param page: Which page to show, counting from zero.
    :type page: str
    :rtype: List[Dict[str, Any]]
    """
    start = page.find('id="mw-content-text"')
    if start < 0:
        return []
    body = page[start:]
    out: List[Dict[str, Any]] = []
    limited = False
    pieces = re.split(r"(<h[23][^>]*>[\s\S]*?</h[23]>)", body)
    for index in range(1, len(pieces) - 1, 2):
        heading, block = pieces[index], pieces[index + 1]
        if heading.startswith("<h2"):
            limited = "limited" in _text(heading).lower()
            continue
        name = _text(heading)
        if not name or "ちほー" not in name and "ちほ一" not in name and "Area" not in name:
            continue
        table = re.search(r"<table[\s\S]*?</table>", block)
        facts = _text(block[: table.start()] if table else block)
        stop = r"(?:Chinese name:|Dates? (?:added|available):|Additional|This Area|Completing|$)"
        english = re.search(rf"English translation:\s*(.*?)\s*{stop}", facts)
        chinese = re.search(rf"Chinese name:\s*(.*?)\s*{stop}", facts)
        # "2024/4/2 (Asia)" for a regular area, "2024/01/18 ~ 24/03/29 (Asia)" for a limited one: the first date is the release
        asia = re.search(r"(\d{4}/\d{1,2}/\d{1,2})(?:\s*~\s*\d{2,4}/\d{1,2}/\d{1,2})?\s*\(Asia\)", facts)
        japan = re.search(r"(\d{4}/\d{1,2}/\d{1,2})(?:\s*~\s*\d{2,4}/\d{1,2}/\d{1,2})?\s*\(Japan\)", facts)
        rewards = parse_reward_table(table.group(0)) if table else []
        out.append({
            "name": name, "key": area_key(name), "english": (english.group(1) if english else "").strip(),
            "chinese": (chinese.group(1) if chinese else "").strip(), "version": version, "limited": limited,
            "addedAsia": asia.group(1) if asia else "", "addedJapan": japan.group(1) if japan else "",
            "rewards": rewards, "perfectChallenge": "Perfect Challenge" in facts,
        })
    return out


def crawl_areas() -> List[Dict[str, Any]]:
    """Every area the wiki lists, one request per version page, a second apart.

    :rtype: List[Dict[str, Any]]
    """
    index = _get(f"{WIKI}/maimai_DX:Area")
    if not index:
        return []
    versions: List[str] = []
    for slug in _AREA_PAGE.findall(index):
        slug = html.unescape(slug)
        if slug not in versions:
            versions.append(slug)
    areas: List[Dict[str, Any]] = []
    for slug in versions:
        page = _get(f"{WIKI}/maimai_DX:{slug}/Areas")
        if page:
            areas.extend(parse_areas(page, slug.replace("_", " ")))
    return fill_english(areas)


_NUMBERED = re.compile(r"^(.*?)(\d+)$")


def fill_english(areas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Give an area the wiki left without an English name the name of its numbered siblings, or its own Latin one.

    "BLACK ROSEちほー9" has no translation line on the wiki; "BLACK ROSEちほー" is "Black Rose Area",
    so the ninth becomes "Black Rose Area 9". A name that is already Latin before ちほー needs no wiki.

    :param areas: The areas to show.
    :type areas: List[Dict[str, Any]]
    :rtype: List[Dict[str, Any]]
    """
    by_base: Dict[str, str] = {}
    for area in areas:
        english = str(area.get("english") or "").strip()
        if not english:
            continue
        base = _NUMBERED.sub(r"\1", area["name"]).strip()
        by_base.setdefault(base, _NUMBERED.sub(r"\1", english).strip())
    for area in areas:
        if str(area.get("english") or "").strip():
            continue
        match = _NUMBERED.match(area["name"])
        base, number = (match.group(1).strip(), match.group(2)) if match else (area["name"], "")
        stem = by_base.get(base)
        if stem is None:
            latin = re.sub(r"ちほ[ー一]$", "", base).strip()
            if latin and latin.isascii():
                stem = f"{latin} Area"
        if stem:
            area["english"] = f"{stem} {number}".strip()
    return areas


def wiki_areas(refresh: bool = False) -> List[Dict[str, Any]]:
    """The cached area list, crawled when missing or older than a week.

    :param refresh: Whether to fetch again rather than use the stored copy.
    :type refresh: bool
    :rtype: List[Dict[str, Any]]
    """
    state = source_state_get(AREAS_SOURCE)
    if state and state.get("payload") and not refresh:
        try:
            if datetime.now() - datetime.fromisoformat(state["checked_at"]) < AREAS_TTL:
                return json.loads(state["payload"])
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    with _lock:
        areas = crawl_areas()
        if areas:
            source_state_set(AREAS_SOURCE, payload=json.dumps(areas, ensure_ascii=False))
            logger.info("wiki area list: %d areas", len(areas))
        elif state and state.get("payload"):
            return json.loads(state["payload"])   # a failed crawl keeps the stale list
        return areas


_areas_memo: Tuple[float, Dict[str, Dict[str, Any]]] = (0.0, {})


def cached_areas() -> Dict[str, Dict[str, Any]]:
    """The wiki's areas keyed by `area_key`, if a crawl has stored them; never crawls. Re-read at most every five minutes.

    :rtype: Dict[str, Dict[str, Any]]
    """
    global _areas_memo
    checked, areas = _areas_memo
    if areas or time.monotonic() - checked < 300:
        return areas
    state = source_state_get(AREAS_SOURCE)
    found: Dict[str, Dict[str, Any]] = {}
    if state and state.get("payload"):
        try:
            for area in json.loads(state["payload"]):
                found.setdefault(str(area.get("key") or area_key(area.get("name", ""))), area)
        except (ValueError, json.JSONDecodeError):
            found = {}
    _areas_memo = (time.monotonic(), found)
    if not found and not state:
        _crawl_areas_soon()
    return found


_areas_crawl_started = False


def _crawl_areas_soon() -> None:
    """One background crawl of the area pages, the first time anything asks and nothing is stored."""
    global _areas_crawl_started
    if _areas_crawl_started:
        return
    _areas_crawl_started = True

    def run() -> None:
        try:
            wiki_areas()
        except Exception:
            logger.exception("wiki area crawl failed")
    threading.Thread(target=run, name="wiki-areas", daemon=True).start()


def area_lookup(name: str) -> Optional[Dict[str, Any]]:
    """The wiki's entry for an area by name, or a name-only entry derived from its numbered siblings.

    A new version's areas reach the site before the wiki writes them up; "スカイストリートちほー7" still
    gets "Sky Street Area 7" from "スカイストリートちほー", with no reward ladder.

    :param name: The name to look up.
    :type name: str
    :rtype: Optional[Dict[str, Any]]
    """
    areas = cached_areas()
    key = area_key(name)
    if key in areas:
        return areas[key]
    match = _NUMBERED.match(str(name or "").strip())
    if not match:
        return None
    base_key, number = area_key(match.group(1)), match.group(2)
    for area in areas.values():
        english = str(area.get("english") or "")
        if english and area_key(_NUMBERED.sub(r"\1", area["name"])) == base_key:
            return {"name": name, "key": key, "english": f"{_NUMBERED.sub(r'\1', english).strip()} {number}", "chinese": "",
                    "version": "", "limited": bool(area.get("limited")), "addedAsia": "", "addedJapan": "", "rewards": [], "derived": True}
    return None

