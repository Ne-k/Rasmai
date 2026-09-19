from typing import Dict, Any
import re

from rasmai.storage.db import get_user_settings, set_user_settings


DEFAULTS: Dict[str, Any] = {
    "layout": "both",            # what the result commands send by default
    "new_difficulty": "any",     # default difficulty for /new
    "compare": False,            # let other people run /compare against you
    "leaderboard": False,        # appear on server leaderboards
    "challenge": "balanced",     # how far above your usual scores targets sit
    "history": True,             # read the recent-plays page once a day so no play is missed
    "notify": False,             # DM what the daily read found: new bests and a moved rating
    # the public profile is off until asked for, and each section of it is opted into separately
    "public": False,             # a link anyone can open, with only the sections below on it
    "public_best50": True,       # the fifty charts the rating is made of
    "public_traits": False,      # what they lose points on and what they shine at
    "public_recent": False,      # the plays the bot has seen, newest first
    "public_areas": False,       # area travel and its rewards
    # and what its link turns into when somebody pastes it in Discord
    "card_on": True,             # the picture above the card at all
    "card_chart": True,          # the rating curve drawn on it
    "card_gain": True,           # how much the rating moved, and since when
    "card_charts": True,         # how many charts are scored
    "card_plays": False,         # the play count
    "embed_region": True,        # "international" or "Japan" beside the rating
    "embed_charts": True,        # the chart count beside the rating
    "card_colour": "#ff3d8f",    # the stripe down the card, and the figures on the picture
    "card_visual": "curve",      # what the picture is a picture of
}

# what a public profile may carry, beyond the name and rating that are the point of having one
PUBLIC_SECTIONS = ("best50", "traits", "recent", "areas")

# what the Discord card may carry. The name and the rating are the card, so they are not optional;
# everything else here is the owner's to switch off.
CARD_FIELDS = ("on", "chart", "gain", "charts", "plays")
EMBED_FIELDS = ("region", "charts")

# the stripe down the side of the card and the figures on the picture. Anything a browser's colour
# well can produce is allowed; these are only the ones offered as a starting point.
CARD_COLOURS = ("#ff3d8f", "#21c3e3", "#5ad18f", "#f0c04a", "#a78bfa", "#f4f0e6")

# what the picture can be. Two of them need a section the profile may not be carrying, and the card
# falls back to the figures rather than drawing an empty frame.
CARD_VISUALS = ("curve", "best50", "traits", "figures")
VISUAL_NEEDS = {"best50": "best50", "traits": "traits"}
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")

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


def clean_colour(value: Any, fallback: str = "#ff3d8f") -> str:
    """A colour the card can actually be drawn in, or the one it had.

    :param value: What the browser sent.
    :type value: Any
    :rtype: str
    """
    text = str(value or "").strip()
    return text.lower() if COLOUR.fullmatch(text) else fallback


def clean_visual(value: Any, fallback: str = "curve") -> str:
    """One of the pictures the card knows how to draw, or the one it had.

    :param value: What the browser sent.
    :type value: Any
    :rtype: str
    """
    text = str(value or "").strip().lower()
    return text if text in CARD_VISUALS else fallback


def update_prefs(user_id: str, **changes: Any) -> Dict[str, Any]:
    prefs = get_prefs(user_id)
    for key, value in changes.items():
        if value is not None and key in prefs:
            prefs[key] = value
    set_user_settings(user_id, prefs)
    return prefs
