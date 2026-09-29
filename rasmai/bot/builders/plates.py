from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import asyncio

import discord

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_SHORT, chart_link, level_text, message_files
from rasmai.engine.plates import GOAL_LABELS, PLATE_KEYS, plate_missing, plate_overview
from rasmai.images.pages.plates import plates_image_html

# the plate colour: the cream of the chips
COLOUR = discord.Color.from_rgb(243, 239, 228)

# missing charts listed in one reply; the rest are counted
SHOWN = 20


def _line(plate: Dict[str, Any]) -> str:
    goals = " · ".join(f"{g['label']} {'✓' if g['met'] >= g['required'] else g['met']}" for g in plate["goals"])
    name = f"**{plate['reading']}** {plate['name']}" if plate["reading"] else f"**{plate['name']}**"
    return f"{name} · {goals} · of {plate['required']}"


async def build_plates(cached: CachedAnalysis, plate: Optional[str] = None,
                       goal: Optional[str] = None) -> Tuple[discord.Embed, List[discord.File], Optional[str]]:
    """Every plate at a glance with its picture, or with `plate` the charts one plate still needs.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :param plate: The plate's key, its kanji such as ``"真"``.
    :type plate: Optional[str]
    :param goal: The condition's kanji, such as ``"極"``; defaults to the first one not yet met.
    :type goal: Optional[str]
    :returns: The embed, its files, and the condition shown (None for the overview).
    :rtype: Tuple[discord.Embed, List[discord.File], Optional[str]]
    """
    a = cached.analyzer
    player = a.player
    plates = [p for p in await asyncio.to_thread(plate_overview, a.songs, a.chart_index) if p["required"]]
    if plate:
        return await _detail(cached, plates, plate, goal)
    from rasmai.bot.builders.results import _image
    shot = await _image(cached, "plates", lambda: plates_image_html(
        plates, player.name, player.avatar_base64, date_text=datetime.now().strftime("%d %B %Y")))
    files, avatar_url = message_files(player, shot, "rasmai-plates.png")
    embed = discord.Embed(title="Version plates", color=COLOUR)
    embed.set_author(name=player.name, icon_url=avatar_url)
    embed.description = ("\n".join(_line(p) for p in plates)
                         + "\n-# FC full combo · SSS 100% · AP all perfect · FDX full sync DX · Clear 80% · pick a plate below to see what is left")
    embed.set_footer(text="BASIC to MASTER of every chart in the version; Mai is every standard chart to FiNALE, Re:MASTER too")
    return embed, files, None


async def _detail(cached: CachedAnalysis, plates: List[Dict[str, Any]], key: str,
                  goal: Optional[str]) -> Tuple[discord.Embed, List[discord.File], str]:
    a = cached.analyzer
    files, avatar_url = message_files(a.player, None, "")
    rule = PLATE_KEYS[key]
    progress = next((p for p in plates if p["key"] == key), None)
    if goal not in rule.goals:
        # the first condition still open, so picking a plate answers the question being asked
        open_goals = [g["goal"] for g in (progress or {}).get("goals", []) if g["met"] < g["required"]]
        goal = open_goals[0] if open_goals else rule.goals[-1]
    detail = await asyncio.to_thread(plate_missing, a.songs, a.chart_index, key, goal)
    name = f"{detail['title']} · {detail['name']}" if detail["title"] else f"{detail['name']} {detail['label']}"
    embed = discord.Embed(title=f"{name}: {detail['met']} of {detail['required']} {detail['label']}" if detail["required"] else name,
                          color=COLOUR)
    embed.set_author(name=a.player.name, icon_url=avatar_url)
    if not detail["required"]:
        embed.description = "Your region has no charts for this plate yet."
        return embed, files, goal
    rows = detail["missing"]
    if not rows:
        embed.description = "Every chart is there. The plate is yours."
        return embed, files, goal
    lines = [f"{chart_link(r['title'], r['type'], r['difficulty'], r['cover'], limit=28)} "
             f"{TIER_SHORT.get(r['difficulty'], '')}{' DX' if r['type'] == 'dx' else ''} {level_text(r['level'], r['constant'])} · {r['need']}"
             for r in rows[:SHOWN]]
    more = len(rows) - SHOWN
    body = "\n".join(lines)
    while len(body) > 3700:          # long titles and links; the embed caps a description at 4096
        lines.pop()
        more += 1
        body = "\n".join(lines)
    embed.description = f"{len(rows)} to go, nearest first\n\n{body}" + (f"\n-# and {more} more" if more > 0 else "")
    others = " · ".join(GOAL_LABELS[g] for g in rule.goals if g != goal)
    if others:
        embed.set_footer(text=f"the condition menu switches to {others}")
    return embed, files, goal
