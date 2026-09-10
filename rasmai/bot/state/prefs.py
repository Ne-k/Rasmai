from typing import Dict, Any

from rasmai.storage.db import get_user_settings, set_user_settings


DEFAULTS: Dict[str, Any] = {
    "layout": "both",            # what the result commands send by default
    "new_difficulty": "any",     # default difficulty for /new
    "compare": False,            # let other people run /compare against you
    "leaderboard": False,        # appear on server leaderboards
    "challenge": "balanced",     # how far above your usual scores targets sit
    "history": False,            # read the recent-plays page once a day so no play is missed
    "notify": False,             # DM what the daily read found: new bests and a moved rating
}

LAYOUTS = ("both", "embed", "image")
NEW_DIFFICULTIES = ("any", "master", "remaster", "expert", "advanced", "basic")
CHALLENGES = ("easy", "balanced", "hard")


def get_prefs(user_id: str) -> Dict[str, Any]:
    prefs = dict(DEFAULTS)
    for key, value in (get_user_settings(user_id) or {}).items():
        if key in prefs:
            prefs[key] = value
    if prefs["layout"] not in LAYOUTS:
        prefs["layout"] = "both"
    if prefs["new_difficulty"] not in NEW_DIFFICULTIES:
        prefs["new_difficulty"] = "any"
    if prefs["challenge"] not in CHALLENGES:
        prefs["challenge"] = "balanced"
    return prefs


def update_prefs(user_id: str, **changes: Any) -> Dict[str, Any]:
    prefs = get_prefs(user_id)
    for key, value in changes.items():
        if value is not None and key in prefs:
            prefs[key] = value
    set_user_settings(user_id, prefs)
    return prefs
