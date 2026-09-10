from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
import math
import re

_IMAGE_STEM = re.compile(r"/img/(Map/Body|EventMap/Banner)/([0-9a-f]{6,40})\.(?:png|jpg|jpeg|webp|gif)(?:\?.*)?$", re.I)


def image_key_for(event: Dict[str, Any]) -> str:
    """The picture key a read stored, or the site's file stem from the address, which the site can be asked for later.

    :param event: One entry from the map pages.
    :type event: Dict[str, Any]
    :rtype: str
    """
    key = str(event.get("imageKey") or "")
    if key:
        return key
    match = _IMAGE_STEM.search(str(event.get("imageUrl") or ""))
    if not match:
        return ""
    return ("banner_" if match.group(1).lower().startswith("eventmap") else "") + match.group(2).lower()


STATE_LABEL = {"not_started": "not started", "in_progress": "travelling", "completed": "completed"}


def _pairs(rows: Sequence[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """(distance gained, plays made) between consecutive readings where both moved.

    :param rows: The rows to render.
    :type rows: Sequence[Dict[str, Any]]
    :rtype: List[Tuple[int, int]]
    """
    out: List[Tuple[int, int]] = []
    for older, newer in zip(rows, rows[1:]):
        gained = int(newer.get("distance") or 0) - int(older.get("distance") or 0)
        plays = int(newer.get("plays") or 0) - int(older.get("plays") or 0)
        if gained > 0 and plays > 0:
            out.append((gained, plays))
    return out


def _pace(pairs: Sequence[Tuple[int, int]], last: int = 6) -> Optional[float]:
    """Kilometres per play over the latest readings, pooled so one short session cannot swing it.

    :param pairs: The readings to measure between.
    :type pairs: Sequence[Tuple[int, int]]
    :param last: How many of the latest readings to use.
    :type last: int
    :rtype: Optional[float]
    """
    recent = list(pairs)[-last:]
    plays = sum(p for _g, p in recent)
    return sum(g for g, _p in recent) / plays if plays > 0 else None


def _iso(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    try:
        return datetime.fromtimestamp(int(value) / 1000).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def summarise_areas(events: Optional[Dict[str, Any]], history: Sequence[Dict[str, Any]],
                    read_at: Optional[datetime] = None, names: Optional[Dict[str, Dict[str, Any]]] = None,
                    key_for=None, resolve=None) -> Dict[str, Any]:
    """The player's areas with a plays-to-next-reward estimate where the history allows one.

    `events` is the scraper's map data (areaEvents, eventAreaEvents); `history` the stored
    readings; `names` the wiki's areas keyed by `key_for(name)`, which add the English name and
    the reward ladder. Returns {"areas": [...], "events": [...], "pace": km per play or None,
    "readings": how many stored readings back the pace, "readAt": when the map was read}.

    :param events: The map data, as the site lists it.
    :type events: Optional[Dict[str, Any]]
    :param history: The stored points, oldest first.
    :type history: Sequence[Dict[str, Any]]
    :param read_at: When the map was last read.
    :type read_at: Optional[datetime]
    :param names: The wiki's areas, keyed the way names are matched.
    :type names: Optional[Dict[str, Dict[str, Any]]]
    :param key_for: Folds an area name into its matching key.
    :param resolve: Looks an area up by name.
    :rtype: Dict[str, Any]
    """
    history = list(history or [])
    names = names or {}
    by_name: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in history:
        by_name.setdefault((str(row.get("kind")), str(row.get("name"))), []).append(row)
    pooled: List[Tuple[int, int]] = []
    for rows in by_name.values():
        pooled.extend(_pairs(rows))
    overall = _pace(pooled)

    def describe(kind: str, event: Dict[str, Any]) -> Dict[str, Any]:
        name = str(event.get("name") or "").strip()
        distance = int(event.get("currentDistance") or 0)
        next_reward = event.get("nextRewardDistance")
        state = str(event.get("state") or "in_progress")
        rows = by_name.get((kind, name), [])
        own = _pace(_pairs(rows))
        pace = own or overall
        known = resolve(name) if resolve else (names.get(key_for(name)) if key_for and names else None)
        # the area being travelled shows its distance and no NEXT REWARD line, which reads as untouched
        if state == "not_started" and distance > 0:
            state = "in_progress"
        to_go: Optional[int] = None
        milestone: Optional[int] = None
        if state == "in_progress" and next_reward is not None:
            # the site's NEXT REWARD is the distance still to go: it shows 0 Km with a reward waiting
            to_go = max(0, int(next_reward))
            milestone = distance + to_go
        ladder: List[Dict[str, Any]] = []
        for step in (known.get("rewards") or []) if known else []:
            total = int(step.get("total") or 0)
            ladder.append({"total": total, "kind": str(step.get("kind") or ""), "name": str(step.get("name") or "")})
        if state == "in_progress" and next_reward is None and ladder and distance >= ladder[-1]["total"]:
            state = "completed"          # nothing left on the wiki's ladder, and the site names no next reward
        next_step: Optional[Dict[str, Any]] = None
        if state == "in_progress":
            if milestone is not None:
                next_step = next((step for step in ladder if step["total"] == milestone), None)
            if next_step is None:
                next_step = next((step for step in ladder if step["total"] > distance), None)
            if next_step is not None and milestone is None:
                to_go, milestone = next_step["total"] - distance, next_step["total"]
        plays_to_go = math.ceil(to_go / pace) if to_go is not None and pace and pace > 0 else None
        for step in ladder:
            pending = next_step is not None and step["total"] == next_step["total"]
            step["reached"] = state == "completed" or (step["total"] <= distance and not pending)
            ahead = step["total"] - distance
            step["playsToGo"] = math.ceil(ahead / pace) if not step["reached"] and ahead > 0 and pace and pace > 0 else None
        next_reward_entry = None
        if next_step is not None:
            next_reward_entry = {**next_step, "toGo": to_go, "playsToGo": plays_to_go}
        elif to_go is not None:
            next_reward_entry = {"total": milestone, "kind": "", "name": "", "toGo": to_go, "playsToGo": plays_to_go, "reached": False}
        first_gift = ladder[0] if ladder and ladder[0]["total"] == 0 else None
        period = event.get("eventPeriod") or [None, None]
        first = rows[0] if rows else None
        return {
            "name": name, "kind": kind, "distance": distance, "state": state, "stateLabel": STATE_LABEL.get(state, state),
            "toGo": to_go, "milestone": milestone, "playsToGo": plays_to_go,
            "pace": round(pace, 1) if pace else None, "ownPace": bool(own),
            "image": str(event.get("imageUrl") or ""), "imageKey": image_key_for(event),
            "english": str(known.get("english") or "") if known else "",
            "chinese": str(known.get("chinese") or "") if known else "",
            "version": str(known.get("version") or "") if known else "",
            "addedAsia": str(known.get("addedAsia") or "") if known else "",
            "rewards": ladder,
            "nextReward": next_reward_entry,
            "firstGift": first_gift,
            "nextRewards": [step for step in ladder if not step["reached"]][:3],
            "periodStart": _iso(period[0]) if period else None, "periodEnd": _iso(period[1]) if period else None,
            "since": first.get("recorded_at") if first else None,
            "gained": distance - int(first.get("distance") or 0) if first else 0,
        }

    def describe_ended(event: Dict[str, Any]) -> Dict[str, Any]:
        name = str(event.get("name") or "").strip()
        known = resolve(name) if resolve else (names.get(key_for(name)) if key_for and names else None)
        period = event.get("eventPeriod") or [None, None]
        return {
            "name": name, "kind": "ended", "distance": 0, "state": "ended", "stateLabel": "ended",
            "toGo": None, "milestone": None, "playsToGo": None, "pace": None, "ownPace": False,
            "image": str(event.get("imageUrl") or ""), "imageKey": image_key_for(event),
            "english": str(known.get("english") or "") if known else "", "chinese": "", "version": "", "addedAsia": "",
            "rewards": [], "nextReward": None, "firstGift": None, "nextRewards": [],
            "periodStart": _iso(period[0]) if period else None, "periodEnd": _iso(period[1]) if period else None,
            "since": None, "gained": 0,
        }

    areas = [describe("area", e) for e in (events or {}).get("areaEvents") or []]
    event_areas = [describe("event", e) for e in (events or {}).get("eventAreaEvents") or []]
    ended = [describe_ended(e) for e in (events or {}).get("endedEvents") or []]
    order = {"in_progress": 0, "not_started": 1, "completed": 2}
    areas.sort(key=lambda a: (order.get(a["state"], 3), -a["distance"]))
    event_areas.sort(key=lambda a: (order.get(a["state"], 3), -a["distance"]))
    return {
        "areas": areas, "events": event_areas, "ended": ended,
        "pace": round(overall, 1) if overall else None,
        "readings": sum(len(p) for p in map(_pairs, by_name.values())),
        "readAt": read_at.isoformat(timespec="seconds") if isinstance(read_at, datetime) else None,
        "counts": {
            "travelling": sum(1 for a in areas + event_areas if a["state"] == "in_progress"),
            "completed": sum(1 for a in areas + event_areas if a["state"] == "completed"),
            "untouched": sum(1 for a in areas + event_areas if a["state"] == "not_started"),
            "ended": len(ended),
        },
    }


_DECORATION = re.compile(r"[\s「」『』【】\[\]()（）・･:：\-−—～~!！?？.,、。]")


def area_mentions(line: str, summary: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The player's areas whose name appears in an unlock note, for a "you are at N km there" aside.

    Names are compared without spaces or brackets and only when three characters or longer,
    so a short word like "DX" cannot claim every note.

    :param line: The line to read.
    :type line: str
    :param summary: The figures the analysis produced.
    :type summary: Optional[Dict[str, Any]]
    :rtype: List[Dict[str, Any]]
    """
    if not summary or not line:
        return []
    haystack = _DECORATION.sub("", line).casefold()
    found: List[Dict[str, Any]] = []
    for area in list(summary.get("areas") or []) + list(summary.get("events") or []):
        needle = _DECORATION.sub("", str(area.get("name") or "")).casefold()
        if len(needle) >= 3 and needle in haystack:
            found.append(area)
    return found
