from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional, Any
import re
import logging

from rasmai.config import get_maimai_base_url
from rasmai.scraping.scraper.session import cookie_jar_to_header
from rasmai.scraping.scraper.area_images import _period_bounds, cache_area_image

logger = logging.getLogger(__name__)


class AreaPages:
    """Reading the area travel map, its events and the ones that have ended."""

    def _parse_official_event_data(self, html: str, region: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        base_url = get_maimai_base_url(region)

        def parse_period(period_str: Optional[str]) -> Optional[List[int]]:
            if not period_str:
                return None
            match = re.search(
                r"Event period：(?P<sy>\d{4})/(?P<sm>\d{2})/(?P<sd>\d{2})\s+(?P<sh>\d{2}):(?P<smin>\d{2})～(?P<ey>\d{4})/(?P<em>\d{2})/(?P<ed>\d{2})\s+(?P<eh>\d{2}):(?P<emin>\d{2})",
                period_str,
            )
            if not match:
                return None
            start = datetime.fromisoformat(f"{match.group('sy')}-{match.group('sm')}-{match.group('sd')}T{match.group('sh')}:{match.group('smin')}:00+09:00")
            end = datetime.fromisoformat(f"{match.group('ey')}-{match.group('em')}-{match.group('ed')}T{match.group('eh')}:{match.group('emin')}:00+09:00")
            return [int(start.timestamp() * 1000), int(end.timestamp() * 1000)]

        area_events: List[Dict[str, Any]] = []
        for block in soup.select(".m_10.m_t_0.f_0"):
            name_element = block.select_one(".map_name_block_inner")
            basic_block = block.select_one(".basic_block")
            image_element = block.select_one("img.w_180")
            if not name_element or not basic_block or not image_element:
                continue

            image_src = image_element.get("src", "")
            image_url = image_src if image_src.startswith("http") else f"{base_url}{image_src}"
            # the small line under the distance: "NEXT REWARD <n> Km" while travelling, "--" once every reward is
            # taken, a first-play gift note before the first play, and nothing at all on the area being travelled
            # when the site shows its running total instead
            note_element = block.select_one(".f_11")
            reward_element = note_element.select_one(".f_14") if note_element else None
            reward_text = reward_element.get_text(" ", strip=True) if reward_element else ""
            state = "in_progress"
            next_reward_distance: Optional[int] = None
            if note_element is not None and reward_element is None:
                state = "not_started"
            elif reward_text == "--":
                state = "completed"
            elif reward_element is not None:
                digits = re.sub(r"[^\d]", "", reward_text)
                next_reward_distance = int(digits) if digits else None    # 0 means a reward is waiting at this distance

            area_events.append({
                "name": name_element.get_text(" ", strip=True),
                "currentDistance": int(re.sub(r"[^\d]", "", basic_block.get_text(" ", strip=True)) or "0"),
                "nextRewardDistance": next_reward_distance,
                "state": state,
                "imageUrl": image_url,
            })

        event_area_events: List[Dict[str, Any]] = []
        for block in soup.select(".eventmap_container"):
            name_element = block.select_one(".map_name_block_inner")
            basic_block = block.select_one(".basic_block")
            image_element = block.select_one("img.w_180")
            if not name_element or not basic_block or not image_element:
                continue

            image_src = image_element.get("src", "")
            image_url = image_src if image_src.startswith("http") else f"{base_url}{image_src}"
            # the small line under the distance: "NEXT REWARD <n> Km" while travelling, "--" once every reward is
            # taken, a first-play gift note before the first play, and nothing at all on the area being travelled
            # when the site shows its running total instead
            note_element = block.select_one(".f_11")
            reward_element = note_element.select_one(".f_14") if note_element else None
            reward_text = reward_element.get_text(" ", strip=True) if reward_element else ""
            state = "in_progress"
            next_reward_distance: Optional[int] = None
            if note_element is not None and reward_element is None:
                state = "not_started"
            elif reward_text == "--":
                state = "completed"
            elif reward_element is not None:
                digits = re.sub(r"[^\d]", "", reward_text)
                next_reward_distance = int(digits) if digits else None    # 0 means a reward is waiting at this distance

            period_element = block.select_one(".t_r.f_11.white")
            event_period = parse_period(period_element.get_text(" ", strip=True) if period_element else None)

            event_area_events.append({
                "name": name_element.get_text(" ", strip=True),
                "currentDistance": int(re.sub(r"[^\d]", "", basic_block.get_text(" ", strip=True)) or "0"),
                "nextRewardDistance": next_reward_distance,
                "state": state,
                "imageUrl": image_url,
                "eventPeriod": event_period,
            })

        return {"areaEvents": area_events, "eventAreaEvents": event_area_events}

    def _parse_official_ended_events(self, html: str, region: str) -> List[Dict[str, Any]]:
        """The Event Area Ended page: each past event's name, its dates and its banner; the site keeps no distance for them.

        :param html: The page source to read.
        :type html: str
        :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
        :type region: str
        :rtype: List[Dict[str, Any]]
        """
        soup = BeautifulSoup(html, "html.parser")
        base_url = get_maimai_base_url(region)
        ended: List[Dict[str, Any]] = []
        for name_element in soup.select(".map_name_block_s_inner"):
            block = name_element.parent.parent if name_element.parent else None      # the .w_250 column beside the banner
            if block is None:
                continue
            name = name_element.get_text(" ", strip=True)
            if not name:
                continue
            period = _period_bounds(block.get_text(" ", strip=True))
            banner = block.find_previous_sibling("img")
            image_src = str(banner.get("src", "") if banner else "").strip()
            image_url = image_src if image_src.startswith("http") else (f"{base_url}{image_src}" if image_src else "")
            ended.append({"name": name, "eventPeriod": period, "imageUrl": image_url, "state": "ended"})
        return ended

    def fetch_official_areas(self, region: str = "intl") -> Dict[str, Any]:
        """The three map pages with the current session: every area and event area with its distance and state, and the events that ended.

        :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
        :type region: str
        :rtype: Dict[str, Any]
        """
        session = getattr(self, "_official_session", None)
        if session is None:
            raise ValueError("Not signed in")
        base_url = get_maimai_base_url(region)
        referer = f"{base_url}/maimai-mobile/"
        area_html = self._fetch_official_html(session, f"{base_url}/maimai-mobile/map/", referer)
        event_area_html = self._fetch_official_html(session, f"{base_url}/maimai-mobile/map/eventMap/", referer)
        events_data = self._parse_official_event_data(area_html, region)
        events_data["eventAreaEvents"] = self._parse_official_event_data(event_area_html, region).get("eventAreaEvents", [])
        try:
            ended_html = self._fetch_official_html(session, f"{base_url}/maimai-mobile/map/eventMapLog/", referer)
            events_data["endedEvents"] = self._parse_official_ended_events(ended_html, region)
        except Exception as error:
            logger.info(f"Ended events page not read: {error}")
            events_data["endedEvents"] = []
        cookies = getattr(self, "_official_cookie_header", "") or cookie_jar_to_header(session)
        for event in events_data["areaEvents"] + events_data["eventAreaEvents"] + events_data["endedEvents"]:
            event["imageKey"] = cache_area_image(str(event.get("imageUrl") or ""), cookies)
        self.events_data = events_data
        self.events_read_at = datetime.now()
        return events_data
