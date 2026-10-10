from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import logging
import threading
import time

from rasmai.bot.state.prefs import get_prefs
from rasmai.engine.insights import rating_forecast
from rasmai.storage.db import count_play_history, load_rating_history, session_deletes_at, sign_in_providers, since_last_look
from rasmai.util import _json_safe
from rasmai.web.dashboard.analysis import analysis_for_user
from rasmai.web.dashboard.picks import _englished, trait_practice
from rasmai.web.dashboard.refresh import refresh_jobs

logger = logging.getLogger(__name__)


def notice_payload() -> Dict[str, Any]:
    """The banner every visitor should see, whoever they are.

    Public and player-free. Until someone sets one from Discord there is no stored notice and the
    built-in one stands; once set, what they set is the whole truth, empty text included.

    :rtype: Dict[str, Any]
    """
    from rasmai.config import DEFAULT_NOTICE
    from rasmai.storage.db import site_notice_get
    # a planned maintenance close by matters more to every visitor than whatever the band said before
    planned = planned_maintenance()
    if planned:
        return planned
    stored = site_notice_get()
    notice = dict(DEFAULT_NOTICE) if stored is None else stored
    # whoever set it is nobody's business but ours
    return {key: value for key, value in notice.items() if key != "setBy"}


_STATUS_PAGE: Dict[str, Any] = {"at": 0.0, "page": "", "maintenances": []}
_STATUS_LOCK = threading.Lock()
_STATUS_EVERY = 120          # seconds between asks; the site holds the band 30 more on top
_WARN_AHEAD = timedelta(days=3)


def _maintenances() -> List[Dict[str, Any]]:
    """The status page's maintenances, asked of Instatus at most every two minutes; the last answer stands when it fails."""
    import requests
    from rasmai.config import INSTATUS_API
    if not INSTATUS_API:
        return []
    with _STATUS_LOCK:
        if time.monotonic() - _STATUS_PAGE["at"] < _STATUS_EVERY:
            return _STATUS_PAGE["maintenances"]
        _STATUS_PAGE["at"] = time.monotonic()       # set first, so a failing Instatus is asked once per window, not per visitor
        headers = {"Authorization": f"Bearer {INSTATUS_API}"}
        try:
            if not _STATUS_PAGE["page"]:
                pages = requests.get("https://api.instatus.com/v2/pages", headers=headers, timeout=5)
                pages.raise_for_status()
                _STATUS_PAGE["page"] = str((pages.json() or [{}])[0].get("id") or "")
            answer = requests.get(f"https://api.instatus.com/v2/{_STATUS_PAGE['page']}/maintenances?per_page=20", headers=headers, timeout=5)
            answer.raise_for_status()
            found = answer.json()
            _STATUS_PAGE["maintenances"] = found if isinstance(found, list) else []
        except Exception as error:
            from rasmai.errors import expected
            (logger.info if expected(error) else logger.exception)("could not read maintenances from the status page: %s", type(error).__name__)
        return _STATUS_PAGE["maintenances"]


def _when(value: Any) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def planned_maintenance(now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The band for a planned maintenance on the status page: one under way, or the next one starting within three days.

    ``at`` is when it starts or, once under way, when it should end; the site writes it in the reader's own time.

    :param now: The time to judge by, for the checks; now when left out.
    :type now: Optional[datetime]
    :rtype: Optional[Dict[str, Any]]
    """
    from rasmai.config import STATUS_URL
    now = now or datetime.now(timezone.utc)
    choices = []
    for item in _maintenances():
        start = _when(item.get("start"))
        if start is None or str(item.get("status", "")).upper() == "COMPLETED":
            continue
        end = _when(item.get("end")) if item.get("end") else None
        if end is None and isinstance(item.get("duration"), (int, float)) and item["duration"] > 0:
            end = start + timedelta(minutes=item["duration"])
        if end is not None and end <= now:
            continue
        under_way = str(item.get("status", "")).upper() == "INPROGRESS" or start <= now
        if under_way or start - now <= _WARN_AHEAD:
            choices.append((not under_way, start, end, item))
    if not choices:
        return None
    later, start, end, item = min(choices, key=lambda choice: choice[:2])      # one under way first, then the soonest
    name = item.get("name")
    if isinstance(name, dict):        # a translated page keeps the name per language
        name = name.get("en") or next(iter(name.values()), "")
    name = " ".join(str(name or "").split())[:120]
    about = f" ({name})" if name else ""
    if later:
        text, at = f"Heads up - I'm going down for planned maintenance{about}, starting", start
    elif end is not None:
        text, at = f"I'm down for planned maintenance right now{about}. Should be back around", end
    else:
        text, at = f"I'm down for planned maintenance right now{about}.", None
    return {"text": text, "at": at.isoformat() if at else "", "tone": "warning", "link": STATUS_URL,
            "id": f"maintenance-{item.get('id', '')}-{'soon' if later else 'now'}"}


def servers_payload(region: str = "intl") -> Dict[str, Any]:
    """Whether a region's maimai DX NET can be read right now, from the presence watch: maintenance on the schedule, or a site that does not answer.

    Public and player-free, so the site can show a band saying that what it shows is the last read.
    The watch only probes its own region's site, so another region is judged on its schedule alone.

    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :rtype: Dict[str, Any]
    """
    from rasmai.bot.tasks.presence import maintenance_at
    from rasmai.config import PRESENCE_REGION
    window = maintenance_at(region=region)
    try:
        from rasmai.bot.core import watch
        reachable = bool(getattr(watch, "reachable", True)) if region == PRESENCE_REGION else True
        checked = getattr(watch, "checked_at", None) if region == PRESENCE_REGION else None
    except Exception:
        reachable, checked = True, None
    return {
        "maintenance": bool(window.active),
        "reachable": reachable,
        "until": window.moment.isoformat() if window.active else None,
        "next": None if window.active else window.moment.isoformat(),
        "checkedAt": checked.isoformat() if checked else None,
    }


def servers_down_note(region: str = "intl") -> str:
    """Why a region's maimai DX NET cannot be read right now, in plain words; "" when it can be.

    SEGA's Aime gateway is a separate site that stays up through maintenance, so someone can sign in
    there and still not be able to link an account. Saying which site is down is the whole point.

    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :rtype: str
    """
    state = servers_payload(region)
    if state["maintenance"]:
        until = ""
        try:
            until = f" until {datetime.fromisoformat(str(state['until'])).strftime('%H:%M')} JST" if state.get("until") else ""
        except ValueError:
            until = ""
        return f"maimai DX NET is in maintenance{until}"
    if not state["reachable"]:
        return "maimai DX NET is not answering right now"
    return ""


def overview_payload(user: Dict[str, Any], account: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    from rasmai.storage.db import touch_account
    from rasmai.web.dashboard.admin import is_admin
    from rasmai.web.dashboard.beta import beta_state
    from rasmai.web.dashboard.public_profile import nameplate_src, sharing_payload
    if account is not None:
        touch_account(user["id"])
    # the sign-ins are for the account section, which any signed-in person sees, linked to maimai or not
    payload: Dict[str, Any] = {"user": user, "linked": account is not None, "admin": is_admin(user["id"]),
                               "providers": sign_in_providers(user["id"])}
    if account is None:
        return payload
    history = load_rating_history(user["id"])
    profile = account.get("officialProfile") or {}
    snapshot = account.get("latestSnapshot") or {}
    payload.update({
        "region": account.get("region", "intl"),
        "profile": {
            "name": profile.get("name", ""), "rating": int(profile.get("rating") or 0), "dan": profile.get("dan", ""),
            "title": profile.get("title", ""), "totalPlayCount": int(profile.get("totalPlayCount") or 0),
            "updatedAt": profile.get("updatedAt") or snapshot.get("recordedAt") or account.get("updatedAt"),
            "nameplate": nameplate_src(profile),
        },
        "snapshot": {
            "recordedAt": snapshot.get("recordedAt"), "best50": snapshot.get("best50", 0),
            "newTotal": snapshot.get("newTotal", 0), "oldTotal": snapshot.get("oldTotal", 0),
            "charts": len(snapshot.get("charts") or []),
        },
        "history": [
            {"recordedAt": row.get("recorded_at"), "rating": row.get("rating"), "best50": row.get("best50"),
             "newTotal": row.get("new_total"), "oldTotal": row.get("old_total"), "charts": row.get("charts"), "plays": row.get("plays")}
            for row in history
        ],
        "settings": get_prefs(user["id"]),
        "refresh": refresh_jobs.status(user["id"]),
        "sessionExpired": account.get("sessionExpired") or "",
        "sessionDeletesAt": session_deletes_at(account.get("sessionExpired") or ""),
        "sharing": sharing_payload(user["id"], account),
        "beta": beta_state(user["id"]),
    })
    payload["forecast"] = rating_forecast(history)
    cached = analysis_for_user(user["id"])
    if cached is not None:
        summary = cached.analyzer.analysis_summary or {}
        payload["analysis"] = _json_safe({"profile": _englished(summary.get("profile")), "best50": summary.get("best50"),
                                          "reachableGain": summary.get("reachableGain"), "traitPractice": trait_practice(cached)})
    payload["playHistory"] = count_play_history(user["id"])
    from rasmai.engine.judgements import judgement_profile
    from rasmai.storage.db import load_judgements
    payload["judgements"] = judgement_profile(load_judgements(user["id"]))
    try:
        payload["sinceLast"] = since_last_look(user["id"], int(profile.get("rating") or 0), int(profile.get("totalPlayCount") or 0))
    except Exception:
        logger.exception("the since-last-look stat failed")      # the page goes on without it, but it is a bug, not the network
        payload["sinceLast"] = None
    return payload
