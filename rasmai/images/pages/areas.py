from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from rasmai.images.posters import _esc
from rasmai.images.pages.common import _image


def _reward_text(step: Optional[Dict[str, Any]]) -> str:
    if not step:
        return ""
    kind, name = _esc(str(step.get("kind") or "")), _esc(str(step.get("name") or ""))
    return f"{kind} <b>{name}</b>" if name else kind


def area_image_html(areas: Sequence[Dict[str, Any]], player_name: str, rating: int, avatar_b64: str,
                    counts: Dict[str, int], pace: Optional[float], date_text: str = "") -> str:
    """Every area as a card: the artwork, the name on a banner, the distance in a dark readout, the next reward in gold.

    :param player_name: The player's name on maimai DX NET.
    :type player_name: str
    :param rating: The player's rating.
    :type rating: int
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param counts: How often each value was played.
    :type counts: Dict[str, int]
    :param date_text: The date to print on the image.
    :type date_text: str
    :param areas: The areas to show.
    :type areas: Sequence[Dict[str, Any]]
    :param pace: How far a play carries the player, in kilometres.
    :type pace: Optional[float]
    :rtype: str
    """
    cards = ""
    for area in areas:
        state = str(area.get("state") or "")
        art = area.get("artUri")
        picture = f'<img src="{art}" class="area-art" />' if art else '<div class="area-art no-cover"></div>'
        english = _esc(str(area.get("english") or ""))
        title = f'<div class="area-banner"><span>{_esc(area["name"])}</span></div>' + (f'<div class="area-english">{english}</div>' if english else "")
        next_reward = area.get("nextReward")
        if state == "in_progress" and next_reward:
            to_go = int(next_reward.get("toGo") or 0)
            plays = next_reward.get("playsToGo")
            when = "ready to collect" if to_go == 0 else f"{to_go:,} km to go" + (f" &middot; ~{plays} plays" if plays is not None else "")
            reward = f'<div class="area-next"><span class="k">Next reward</span><span class="v">{_reward_text(next_reward) or "&mdash;"}</span><span class="w">{when}</span></div>'
        elif state == "in_progress":
            reward = '<div class="area-next"><span class="k">Next reward</span><span class="w">not listed for this area</span></div>'
        elif state == "completed":
            reward = '<div class="area-next done"><span class="k">Completed</span><span class="w">every reward collected</span></div>'
        else:
            gift = _reward_text(area.get("firstGift"))
            reward = f'<div class="area-next gift"><span class="k">First play</span><span class="v">{gift}</span></div>' if gift else '<div class="area-next gift"><span class="k">First play</span><span class="w">a gift is waiting</span></div>'
        label = {"in_progress": "travelling", "completed": "completed"}.get(state, "not started")
        ends = ""
        if area.get("periodEnd"):
            try:
                ends = f'<div class="area-ends">until {datetime.fromisoformat(str(area["periodEnd"])).strftime("%d %b %Y")} JST</div>'
            except ValueError:
                ends = ""
        cards += f"""
        <div class="area-card {state}">
          {picture}
          <div class="area-body">
            {title}
            <div class="area-readout"><span class="k">Total distance</span><span class="v">{int(area.get("distance") or 0):,} <small>km</small></span><span class="state">{label}</span></div>
            {reward}
            {ends}
          </div>
        </div>"""
    body = f'<div class="section-label">Areas &middot; {counts.get("travelling", 0)} travelling &middot; {counts.get("completed", 0)} completed &middot; {counts.get("untouched", 0)} not started</div><div class="area-grid">{cards}</div>'
    counters = [("Travelling", str(counts.get("travelling", 0))), ("Completed", str(counts.get("completed", 0))), ("Not started", str(counts.get("untouched", 0)))]
    headline = f"{pace:g}" if pace else "&mdash;"
    return _image("Area travel", player_name, avatar_b64, counters, headline, "km per play, from your reads", body, date_text)
