from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
import html
import json
import logging
import re
import threading
import time
import urllib.parse

import requests

from rasmai.config import USER_AGENT
from rasmai.engine.analysis import loose_title
from rasmai.romaji import has_kana, loanword, romanize, skeleton
from rasmai.storage.db import source_state_get, source_state_set

logger = logging.getLogger(__name__)


# SilentBlue is the RemyWiki sister site for SEGA's rhythm games. Its API and index.php
# sit behind a bot challenge, but plain page views and category listings are served, and
# every song page ends with a Videos section of YouTube embeds, one per chart.
WIKI = "https://silentblue.remywiki.com"


CATEGORY = "Category:maimai_Songs"


TIMEOUT = 12


TITLES_SOURCE = "silentblue_titles"


TITLES_TTL = timedelta(days=7)        # the song list changes with each version


FOUND_TTL = timedelta(days=30)        # a page may gain videos later


MISSING_TTL = timedelta(days=7)       # a song may get a page later


_lock = threading.Lock()              # one crawl of the category at a time


_next_request = 0.0                   # one request a second, across threads


_pace = threading.Lock()


_CATEGORY_LINK = re.compile(r'<li><a href="/[^"]*" title="([^"]*)"')


_PAGEFROM = re.compile(r'pagefrom=([^"&#]*)')


DIFFICULTIES = {"basic": "basic", "advanced": "advanced", "expert": "expert", "master": "master", "remaster": "remaster"}


def _get(url: str) -> Optional[str]:
    """One polite GET: identified, paced, and never raising.

    :param url: The address to fetch.
    :type url: str
    :rtype: Optional[str]
    """
    global _next_request
    with _pace:
        now = time.monotonic()
        start = max(now, _next_request)
        _next_request = start + 1.0
    if start > now:
        time.sleep(start - now)
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"}, timeout=TIMEOUT)
    except requests.RequestException as error:
        logger.info("wiki fetch failed for %s: %s", url, error)
        return None
    if response.status_code != 200 or "Just a moment" in response.text[:2000]:
        logger.info("wiki refused %s (%s)", url, response.status_code)
        return None
    return response.text


def page_url(title: str) -> str:
    return f"{WIKI}/{urllib.parse.quote(title.replace(' ', '_'), safe='!()~*:,')}"


def crawl_titles() -> List[str]:
    """Every page in the maimai songs category, walking the listing 200 at a time.

    :rtype: List[str]
    """
    titles: List[str] = []
    seen_from = set()
    url = f"{WIKI}/{CATEGORY}"
    for _page in range(40):
        text = _get(url)
        if text is None:
            break
        titles.extend(html.unescape(t) for t in _CATEGORY_LINK.findall(text) if not t.startswith("Category:"))
        nexts = [n for n in _PAGEFROM.findall(text) if n not in seen_from]
        if not nexts:
            break
        seen_from.add(nexts[0])
        url = f"{WIKI}/{CATEGORY}?pagefrom={nexts[0]}"
    return sorted(set(titles))


def wiki_titles(refresh: bool = False) -> List[str]:
    """The cached title list, crawled when missing or older than a week.

    :param refresh: Whether to fetch again rather than use the stored copy.
    :type refresh: bool
    :rtype: List[str]
    """
    state = source_state_get(TITLES_SOURCE)
    if state and state.get("payload") and not refresh:
        try:
            checked = datetime.fromisoformat(state["checked_at"])
            if datetime.now() - checked < TITLES_TTL:
                return json.loads(state["payload"])
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    with _lock:
        state = source_state_get(TITLES_SOURCE)
        if state and state.get("payload") and not refresh:
            try:
                if datetime.now() - datetime.fromisoformat(state["checked_at"]) < TITLES_TTL:
                    return json.loads(state["payload"])
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
        titles = crawl_titles()
        if titles:
            source_state_set(TITLES_SOURCE, payload=json.dumps(titles, ensure_ascii=False))
            logger.info("wiki title list: %d maimai songs", len(titles))
        elif state and state.get("payload"):
            return json.loads(state["payload"])   # a failed crawl keeps the stale list
        return titles


_titles_memo: Tuple[float, List[str]] = (0.0, [])


def cached_titles() -> List[str]:
    """The wiki's song list if a crawl has already stored it; never crawls. Re-read from the database at most every five minutes.

    :rtype: List[str]
    """
    global _titles_memo
    checked, titles = _titles_memo
    if titles or time.monotonic() - checked < 300:
        return titles
    state = source_state_get(TITLES_SOURCE)
    found: List[str] = []
    if state and state.get("payload"):
        try:
            found = list(json.loads(state["payload"]))
        except (ValueError, json.JSONDecodeError):
            found = []
    _titles_memo = (time.monotonic(), found)
    return found


class AliasIndex:
    """Wiki page titles keyed the way `match_title` matches them, for finding thousands of aliases at once."""

    def __init__(self, titles: Sequence[str]):
        self.by_loose: Dict[str, List[str]] = {}
        self.by_skeleton: Dict[str, List[str]] = {}
        self.by_loanword: Dict[str, List[str]] = {}
        for title in titles:
            self.by_loose.setdefault(loose_title(title), []).append(title)
            self.by_skeleton.setdefault(skeleton(title), []).append(title)
            bones = loanword(title)
            if len(bones) >= 4:
                self.by_loanword.setdefault(bones, []).append(title)

    def find(self, title: str, reading: str) -> Optional[str]:
        exact = self.by_loose.get(loose_title(title), [])
        if len(exact) == 1:
            return exact[0]
        japanese = has_kana(title) or bool(re.search(r"[一-鿿]", title))
        keys = {skeleton(romanize(title))} if japanese else set()
        if reading:
            keys.add(skeleton(romanize(reading)))
        keys.discard("")
        hits = {t for key in keys for t in self.by_skeleton.get(key, [])}
        if len(hits) == 1:
            return hits.pop()
        # the wiki writes katakana loanwords as the English word (モニタリング is "Monitoring"): meet on the loanword skeleton
        if japanese:
            bones = {loanword(title)} | ({loanword(reading)} if reading else set())
            hits = {t for key in bones if len(key) >= 4 for t in self.by_loanword.get(key, [])}
            if len(hits) == 1:
                return hits.pop()
        return None


def match_title(title: str, reading: str, titles: Sequence[str]) -> Optional[str]:
    """The wiki page for a database title: exact first, then the romanised skeleton of the title or its reading.

    The wiki names Japanese songs in Hepburn romaji; the database carries a katakana
    reading for sorting, which `skeleton` folds onto the same letters.

    :param title: The song title.
    :type title: str
    :param reading: The song's title as it is read.
    :type reading: str
    :param titles: The wiki's page titles.
    :type titles: Sequence[str]
    :rtype: Optional[str]
    """
    wanted = loose_title(title)
    exact = [t for t in titles if loose_title(t) == wanted]
    if len(exact) == 1:
        return exact[0]
    keys = {skeleton(romanize(title))} if has_kana(title) or re.search(r"[一-鿿]", title) else set()
    if reading:
        keys.add(skeleton(romanize(reading)))
    keys.discard("")
    if not keys:
        return None
    hits = [t for t in titles if skeleton(t) in keys]
    return hits[0] if len(hits) == 1 else None
