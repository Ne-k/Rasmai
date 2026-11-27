from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from rasmai.images.posters import _esc, mark, panel, rating_plate, stats
from rasmai.images.pages.common import _image


def _reward_text(step: Optional[Dict[str, Any]]) -> str:
    if not step:
        return ""
    kind, name = _esc(str(step.get("kind") or "")), _esc(str(step.get("name") or ""))
    return f"{kind} <b>{name}</b>" if name else kind


def _rows(cards: Sequence[str], across: int) -> str:
    """Lay tickets in rows of at most `across`, split evenly, so no row ends short of the panel's edge.

    :param cards: The tickets' markup.
    :type cards: Sequence[str]
    :param across: Most tickets in a row.
    :type across: int
    :rtype: str
    """
    if not cards:
        return ""
    count = -(-len(cards) // across)
    base, extra = divmod(len(cards), count)
    out, start = "", 0
    for row in range(count):
        size = base + (row < extra)
        out += f'<div class="pg-row{" one" if count == 1 and size == 1 else ""}" style="--across:{size}">{"".join(cards[start:start + size])}</div>'
        start += size
    return out


def _ticket(area: Dict[str, Any], state: str) -> str:
    """One area as a ticket: the distance on the stub in its run's colour, the names over the large artwork on the paper, and the prize on a tag.

    :param area: The area to draw.
    :type area: Dict[str, Any]
    :param state: ``"in_progress"`` for the full ticket; ``"completed"`` or anything else for the small one.
    :type state: str
    :rtype: str
    """
    art = area.get("artUri")
    # an area without artwork draws none, and its names and reward take the room
    picture = f'<img src="{art}" class="pg-art" />' if art else ""
    paper = "pg-paper" if art else "pg-paper bare"
    english = _esc(str(area.get("english") or ""))
    name = f'<div class="pg-name"><b>{_esc(area["name"])}</b>' + (f"<span>{english}</span>" if english else "") + "</div>"
    try:
        end = datetime.fromisoformat(str(area["periodEnd"]))
        ends = f'<span class="pg-ends">until {end.day} {end:%b %Y} JST</span>'
    except (KeyError, ValueError):
        ends = ""
    stub = f'<div class="pg-stub"><strong>{int(area.get("distance") or 0):,}</strong><small>km</small></div>'
    if state != "in_progress":
        if state == "completed":
            line = '<span class="pg-note">every reward collected</span>'
        else:
            line = f'<span class="pg-note">First play &middot; {_reward_text(area.get("firstGift")) or "a gift is waiting"}</span>'
        return f'<article class="pg-tk pg-trip mini">{stub}<div class="{paper}">{name}{picture}<div class="pg-side">{line}{ends}</div></div></article>'
    reward = area.get("nextReward")
    if reward:
        to_go = int(reward.get("toGo") or 0)
        plays = reward.get("playsToGo")
        what = f'<span class="v">{_reward_text(reward) or "&mdash;"}</span>'
        if to_go == 0:
            prize = f'<div class="pg-prize ready"><span class="k">Next reward</span>{what}<b class="pg-go">ready to collect</b></div>'
        else:
            mark_at = f"<br>at {int(area['milestone']):,} km" if area.get("milestone") else ""
            go = (f'<b class="pg-go">{mark("plays")}in ~{plays} play{"" if plays == 1 else "s"}</b>' if plays is not None else "")
            prize = f'<div class="pg-prize"><span class="k">Next reward</span>{what}<span class="w">{to_go:,} km to go{mark_at}</span>{go}</div>'
    else:
        prize = '<div class="pg-prize none"><span class="k">Next reward</span><span class="w">none listed</span></div>'
    return f'<article class="pg-tk pg-trip">{stub}<div class="{paper}">{name}{picture}<div class="pg-side">{prize}{ends}</div></div></article>'


def area_image_html(areas: Sequence[Dict[str, Any]], player_name: str, rating: int, avatar_b64: str,
                    counts: Dict[str, int], pace: Optional[float], date_text: str = "", readings: int = 0) -> str:
    """The map as a board of tickets: the areas under way large, the finished and the untouched small, a panel to a state.

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
    :param readings: How many stored readings the pace comes from.
    :type readings: int
    :rtype: str
    """
    groups: Dict[str, List[str]] = {"in_progress": [], "completed": [], "not_started": []}
    for area in areas:
        state = str(area.get("state") or "")
        groups[state if state in groups else "not_started"].append(_ticket(area, state))
    going, done, fresh = groups["in_progress"], groups["completed"], groups["not_started"]
    # a few areas make a card two thirds as wide, two tickets to a row, so the tickets keep their size; three fill one row of the wide board
    narrow = len(going) <= 4 and len(going) != 3
    small = 3 if narrow else 6
    total = int(counts.get("travelling", 0))
    body = panel("cyan run", "Travelling", _rows(going, 2 if narrow else 3) or '<p class="pg-none">no area under way</p>',
                 f"{len(going)} of {total} shown" if len(going) < total else f"{len(going)} area{'' if len(going) == 1 else 's'}")
    if done and fresh:
        # the two small runs share a row, split where the taller of them is shortest, so they end as near level as they can
        share = min(range(1, small), key=lambda cut: (max(-(-len(done) // (small - cut)), -(-len(fresh) // cut)),
                                                     abs(cut / small - len(fresh) / (len(done) + len(fresh)))))
        body += (f'<div class="pg-rest" style="grid-template-columns:{small - share}fr {share}fr">'
                 + panel("mint run", "Completed", _rows(done, small - share), f"{len(done)} shown")
                 + panel("pink run", "Not started", _rows(fresh, share), "a gift on the first play") + "</div>")
    elif done:
        body += panel("mint run", "Completed", _rows(done, small), f"{len(done)} shown")
    elif fresh:
        body += panel("pink run", "Not started", _rows(fresh, small), "a gift on the first play")
    figures = [("Travelling", str(counts.get("travelling", 0))), ("Completed", str(counts.get("completed", 0))), ("Not started", str(counts.get("untouched", 0)))]
    pace_text = f"{pace:g}<small>km</small>" if pace else "&mdash;"
    source = f"per play, from {readings} reading{'s' if readings != 1 else ''}" if pace and readings else "per play, from your reads"
    banner = f'<div class="banner">{stats(figures)}<div class="sum"><span><b>{pace_text}</b><small>{source}</small></span></div>'
    # the reward fewest plays away, of the areas drawn: what the board is working towards next
    ahead = [x for x in areas if (x.get("nextReward") or {}).get("playsToGo") is not None and int(x["nextReward"].get("toGo") or 0) > 0]
    ready = sum(1 for x in areas if x.get("nextReward") and int(x["nextReward"].get("toGo") or 0) == 0)
    if ahead:
        near = min(ahead, key=lambda x: int(x["nextReward"]["playsToGo"]))
        plays = int(near["nextReward"]["playsToGo"])
        banner += (f'<div class="pg-near"><small>Closest reward</small><b>{mark("plays")}in ~{plays} play{"" if plays == 1 else "s"}</b>'
                   f'<span>{_reward_text(near["nextReward"]) or "a reward"} at {_esc(near["name"])}</span></div>')
    if ready:
        banner += stats([("Ready to collect", str(ready))])
    banner += "</div>"
    return _image("Area travel", player_name, avatar_b64, rating_plate(rating), "rating", banner + body, date_text,
                  "narrow" if narrow else "")
