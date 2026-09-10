from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import asyncio

import discord

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import _fit, message_files, progress_bar, stamp
from rasmai.engine.areas import summarise_areas
from rasmai.images.pages import area_image_html
from rasmai.scraping import wiki
from rasmai.scraping.scraper import ensure_area_image
from rasmai.storage.db import load_area_progress
from rasmai.web.links import area_url
import base64


def area_summary(cached: CachedAnalysis, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The areas as the engine describes them; without `history` the pace estimate is left out.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :param history: The stored points, oldest first.
    :type history: Optional[List[Dict[str, Any]]]
    :rtype: Dict[str, Any]
    """
    a = cached.analyzer
    return summarise_areas(getattr(a, "events_data", None), history or [], getattr(a, "events_read_at", None),
                           resolve=wiki.area_lookup)


def area_title(area: Dict[str, Any]) -> str:
    """The area's name with the wiki's English name after it, when it has one.

    :param area: One area from the map.
    :type area: Dict[str, Any]
    :rtype: str
    """
    english = str(area.get("english") or "").strip()
    return f"{area['name']} · {english}" if english and wiki.area_key(english) != wiki.area_key(area["name"]) else str(area["name"])


def area_art_uri(area: Dict[str, Any]) -> str:
    """The cached artwork as a data URI for the rendered image, or "" when there is none.

    :param area: One area from the map.
    :type area: Dict[str, Any]
    :rtype: str
    """
    path = ensure_area_image(str(area.get("imageKey") or ""))
    if path is None:
        return ""
    kind = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix, "image/png")
    try:
        return f"data:{kind};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    except OSError:
        return ""


def area_picture(area: Dict[str, Any], filename: str) -> Optional[discord.File]:
    """The area's artwork as an attachment, when a read has cached it.

    :param area: One area from the map.
    :type area: Dict[str, Any]
    :param filename: The name to attach the file under.
    :type filename: str
    :rtype: Optional[discord.File]
    """
    path = ensure_area_image(str(area.get("imageKey") or ""))
    if path is None:
        return None
    return discord.File(str(path), filename=f"{filename}{path.suffix}")


def _km(value: Any) -> str:
    return f"{int(value or 0):,} km"


def _when(value: Any, style: str) -> str:
    try:
        return stamp(datetime.fromisoformat(str(value)), style)
    except (TypeError, ValueError):
        return ""


def _heading(area: Dict[str, Any], *extra: str) -> str:
    """The area's name, linked to its card on the site, then the English name, anything extra, and the end date.

    :param area: One area from the map.
    :type area: Dict[str, Any]
    :rtype: str
    """
    english = str(area.get("english") or "").strip()
    parts = [f"[**{area['name']}**]({area_url(area['name'])})"]
    if english and wiki.area_key(english) != wiki.area_key(area["name"]):
        parts.append(english)
    parts.extend(extra)
    if area.get("periodEnd"):
        ends = _when(area["periodEnd"], "R")
        if ends:
            parts.append(f"ends {ends}")
    return " · ".join(parts)


def _travel_lines(area: Dict[str, Any]) -> List[str]:
    """One area under way in one or two lines: the heading, then the bar to the next reward and what it is.

    An area the site names no reward for keeps to a single line with its distance.

    :param area: One area from the map.
    :type area: Dict[str, Any]
    :rtype: List[str]
    """
    reward = area.get("nextReward")
    if not reward and not area.get("milestone"):
        return [_heading(area, _km(area["distance"]))]
    bits: List[str] = []
    if area.get("milestone"):
        bits.append(f"{progress_bar(area['distance'], area['milestone'], width=10)} {int(area['distance']):,} / {_km(area['milestone'])}")
    else:
        bits.append(_km(area["distance"]))
    if reward:
        what = (f"{reward.get('kind') or ''} **{reward['name']}**".strip() if reward.get("name") else "next reward")
        to_go = int(reward.get("toGo") or 0)
        if to_go == 0:
            bits.append(f"{what} ready to collect")
        else:
            bits.append(f"{what} in {_km(to_go)}")
            if reward.get("playsToGo") is not None:
                plays = int(reward["playsToGo"])
                bits.append(f"~{plays} play{'s' if plays != 1 else ''}")
    return [_heading(area), "-# " + " · ".join(bits)]


def _add_packed(embed: discord.Embed, name: str, blocks: List[List[str]], limit: int = 1000, max_fields: int = 3) -> None:
    """Add `blocks` of lines as one field, spilling into unnamed continuation fields at the character cap.

    :param embed: The embed being built.
    :type embed: discord.Embed
    :param name: The name to look up.
    :type name: str
    :param limit: Most entries to return.
    :type limit: int
    """
    chunk: List[str] = []
    size = 0
    title = name
    fields = 0
    for index, block in enumerate(blocks):
        text = "\n".join(block)
        if chunk and size + len(text) + 1 > limit:
            fields += 1
            if fields >= max_fields:
                chunk.append(f"-# and {len(blocks) - index} more in the image")
                break
            embed.add_field(name=title, value="\n".join(chunk), inline=False)
            title, chunk, size = "\u200b", [], 0
        chunk.append(text)
        size += len(text) + 1
    if chunk:
        embed.add_field(name=title, value="\n".join(chunk), inline=False)


def _within_limits(embed: discord.Embed) -> None:
    """Drop the least important fields from the end until the embed fits Discord's 6000 characters and 25 fields."""
    while embed.fields and (len(embed) > 5900 or len(embed.fields) > 25):
        embed.remove_field(len(embed.fields) - 1)


def _names(items: List[Dict[str, Any]], detail=None, shown: int = 6) -> str:
    """A short list of area names in small text, the overflow counted rather than listed.

    :param items: The entries to render.
    :type items: List[Dict[str, Any]]
    :param detail: The judgement breakdown of one play.
    :rtype: str
    """
    lines = []
    for x in items[:shown]:
        extra = detail(x) if detail else ""
        lines.append(f"-# {area_title(x)}" + (f" · {extra}" if extra else ""))
    if len(items) > shown:
        lines.append(f"-# and {len(items) - shown} more")
    return _fit(lines, limit=600)


async def build_areas(cached: CachedAnalysis) -> Tuple[discord.Embed, List[discord.File], None]:
    a = cached.analyzer
    player = a.player
    from rasmai.bot.builders.results import _image
    history = await asyncio.to_thread(load_area_progress, cached.user_id)
    summary = area_summary(cached, history)
    shot = None
    if any(x["state"] == "in_progress" for x in summary["areas"] + summary["events"]):
        read_stamp = getattr(a, "events_read_at", None)
        key = f"areas:{read_stamp.isoformat(timespec='minutes') if isinstance(read_stamp, datetime) else 'stored'}"
        # the image carries the areas under way, own areas before events, nine at most so it stays readable in the preview
        pictured_areas = [x for x in summary["areas"] if x["state"] == "in_progress"] + [x for x in summary["events"] if x["state"] == "in_progress"]
        pictured_areas = pictured_areas[:9]
        for area in pictured_areas:
            area["artUri"] = area_art_uri(area)
        shot = await _image(cached, key, lambda: area_image_html(
            pictured_areas, player.name, cached.start_rating, player.avatar_base64, summary["counts"], summary.get("pace"),
            date_text=datetime.now().strftime("%d %B %Y"),
        ))
    files, avatar_url = message_files(player, shot, "rasmai-area.png")
    embed = discord.Embed(title="Area travel", url=area_url(), color=discord.Color.from_rgb(92, 211, 232))
    embed.set_author(name=player.name, icon_url=avatar_url)

    areas = summary["areas"]
    events = summary["events"]
    if not areas and not events:
        embed.description = ("Nothing read from the map pages yet. `/refresh` reads them with your scores; "
                             "if this keeps happening the map pages may have changed shape.")
        return embed, files, None

    counts = summary["counts"]
    head = f"**{counts['travelling']}** under way · **{counts['completed']}** completed · **{counts['untouched']}** not started"
    if summary.get("pace"):
        readings = summary["readings"]
        note = f"about **{summary['pace']} km** a play, from {readings} reading{'s' if readings != 1 else ''} of your map"
    else:
        note = "plays-to-go appear once the map moves between two reads"
    embed.description = f"{head}\n-# {note}"

    travelling = [x for x in areas if x["state"] == "in_progress"]
    if travelling:
        _add_packed(embed, "Under way", [_travel_lines(x) for x in travelling])
    live_events = [x for x in events if x["state"] == "in_progress"]
    if live_events:
        _add_packed(embed, "Events", [_travel_lines(x) for x in live_events])

    done = [x for x in areas + events if x["state"] == "completed"]
    if done:
        embed.add_field(name=f"Completed · {len(done)}", value=_names(done, lambda x: _km(x["distance"])), inline=True)
    untouched = [x for x in areas if x["state"] == "not_started"]
    if untouched:
        def gift(x: Dict[str, Any]) -> str:
            step = x.get("firstGift") or {}
            return f"{step.get('kind', '')} {step.get('name', '')}".strip() if step.get("name") else ""
        embed.add_field(name=f"Not started · {len(untouched)}", value=_names(untouched, gift), inline=True)
    waiting_events = [x for x in events if x["state"] == "not_started"]
    if waiting_events:
        embed.add_field(name=f"Events ahead · {len(waiting_events)}",
                        value=_names(waiting_events, lambda x: f"ends {_when(x.get('periodEnd'), 'R')}" if x.get("periodEnd") else ""), inline=True)
    ended = summary.get("ended") or []
    if ended:
        embed.add_field(name=f"Ended events · {len(ended)}", value=_fit(["-# " + " · ".join(area_title(x) for x in ended)], limit=600), inline=False)

    # the artwork of the area under way, as the cabinet shows it, in the corner; the image below carries every area
    pictured = travelling + live_events
    if pictured:
        corner = area_picture(pictured[0], "rasmai-area-art")
        if corner:
            files.append(corner)
            embed.set_thumbnail(url=f"attachment://{corner.filename}")

    _within_limits(embed)
    from rasmai.bot.builders.results import human_age
    read_at = getattr(a, "events_read_at", None)
    when = f"map read {human_age(read_at)}" if isinstance(read_at, datetime) else "map as last read"
    embed.set_footer(text=f"{when} · distances from maimai DX NET · reward and English names via SilentBlue RemyWiki")
    return embed, files, None
