from typing import Any, Dict, List, Optional, Tuple
import asyncio

import discord
from rasmai.bot.ui import palette

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_SHORT, add_link_run, chart_link, level_text, message_files, today
from rasmai.bot.ui.views import OwnerOnlyView
from rasmai.engine.plates import GOAL_LABELS, ORDERS, PLATE_KEYS, chance_text, plate_choices, plate_missing, plate_overview, plate_standing
from rasmai.images.pages import plate_detail_image_html, plates_image_html
from rasmai.images.render import cover_html_factory

# missing charts listed in one reply; the rest are counted
SHOWN = 20

LEGEND = "-# FC full combo · SSS 100% · AP all perfect · FDX full sync DX · Clear 80%"

# the sort menu, and the heading over the charts it orders
ORDER_LABELS = {"likely": "Most likely first", "unlikely": "Least likely first"}


def _line(plate: Dict[str, Any]) -> str:
    goals = " · ".join(f"{g['label']} {'✓' if g['met'] >= g['required'] else g['met']}" for g in plate["goals"])
    name = f"**{plate['reading']}** {plate['name']}" if plate["reading"] else f"**{plate['name']}**"
    return f"{name} · {goals} · of {plate['required']}"


async def build_plates(cached: CachedAnalysis, owner_id: int, plate: Optional[str] = None, goal: Optional[str] = None,
                       order: str = "likely") -> Tuple[discord.Embed, List[discord.File], "PlatesView"]:
    """Every plate at a glance with its picture, or with `plate` the charts one plate still needs.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :param owner_id: The Discord user the menus answer to.
    :type owner_id: int
    :param plate: The plate's key, its kanji such as ``"真"``.
    :type plate: Optional[str]
    :param goal: The condition's kanji, such as ``"極"``; defaults to the first one not yet met.
    :type goal: Optional[str]
    :param order: ``"likely"`` to list the charts most likely to meet it first, ``"unlikely"`` the longest shots first.
    :type order: str
    :rtype: Tuple[discord.Embed, List[discord.File], PlatesView]
    """
    a = cached.analyzer
    plates = [p for p in await asyncio.to_thread(plate_overview, a.songs, a.chart_index) if p["required"]]
    order = order if order in ORDERS else "likely"
    if plate in PLATE_KEYS:
        embed, files, goal = await _detail(cached, plates, plate, goal, order)
        return embed, files, PlatesView(owner_id, plate, goal, order)
    from rasmai.bot.builders.results import _image
    player = a.player
    shot = await _image(cached, "plates", lambda: plates_image_html(plates, player.name, player.avatar_base64, date_text=today()))
    files, avatar_url = message_files(player, shot, "rasmai-plates.png")
    embed = discord.Embed(title="Version plates", color=palette.RATING)
    embed.set_author(name=player.name, icon_url=avatar_url)
    earned, closest = plate_standing(plates)
    near = ""
    if closest:
        nearest, nearest_goal = closest
        near = (f" · closest: **{nearest_goal['title'] or nearest['name'] + ' ' + nearest_goal['label']}**, "
                f"{nearest_goal['required'] - nearest_goal['met']} to go")
    head = f"**{earned}** earned{near}\n"
    if shot is not None:
        # the image carries every plate's bars and counts
        embed.description = head + "-# pick a plate below to list the charts it still needs"
    else:
        embed.description = head + "\n" + "\n".join(_line(p) for p in plates) + "\n" + LEGEND
    embed.set_footer(text="BASIC to MASTER of every chart in the version; Mai is every standard chart to FiNALE, Re:MASTER too")
    return embed, files, PlatesView(owner_id, None, None, order)


async def _detail(cached: CachedAnalysis, plates: List[Dict[str, Any]], key: str,
                  goal: Optional[str], order: str) -> Tuple[discord.Embed, List[discord.File], str]:
    a = cached.analyzer
    rule = PLATE_KEYS[key]
    progress = next((p for p in plates if p["key"] == key), None)
    if goal not in rule.goals:
        # the first condition still open, so picking a plate answers the question being asked
        open_goals = [g["goal"] for g in (progress or {}).get("goals", []) if g["met"] < g["required"]]
        goal = open_goals[0] if open_goals else rule.goals[-1]
    detail = await asyncio.to_thread(plate_missing, a.songs, a.chart_index, key, goal, a.play_profile, order)
    rows = detail["missing"]
    heading = ORDER_LABELS[order] if detail["odds"] else "Closest first"
    shot = None
    if detail["required"]:
        from rasmai.bot.builders.results import _image
        shot = await _image(cached, f"plate:{key}:{goal}:{order}", lambda: plate_detail_image_html(
            detail, a.player.name, a.player.avatar_base64, rows[:SHOWN], heading, date_text=today(), cover_html=cover_html_factory(a.jacket_path)))
    files, avatar_url = message_files(a.player, shot, "rasmai-plate.png")
    name = f"{detail['title']} · {detail['name']}" if detail["title"] else f"{detail['name']} {detail['label']}"
    embed = discord.Embed(title=f"{name}: {detail['met']} of {detail['required']}" if detail["required"] and shot is None else name,
                          color=palette.RATING)
    embed.set_author(name=a.player.name, icon_url=avatar_url)
    if not detail["required"]:
        embed.description = "Your region has no charts for this plate yet."
        return embed, files, goal
    if not rows:
        embed.description = "Every chart meets it. Plate earned."
        return embed, files, goal
    if shot is not None:
        # the image draws each chart's level, what it lacks and its chance under the same number
        embed.description = f"{len(rows)} to go"
        add_link_run(embed, heading, [f"`{n}` {chart_link(r['title'], r['type'], r['difficulty'], r['cover'])}"
                                              for n, r in enumerate(rows[:SHOWN], 1)])
        return embed, files, goal
    lines = [f"{chart_link(r['title'], r['type'], r['difficulty'], r['cover'], limit=28)} "
             f"{TIER_SHORT.get(r['difficulty'], '')}{' DX' if r['type'] == 'dx' else ''} {level_text(r['level'], r['constant'])} · {r['need']}"
             + (f" · **{chance_text(r['chance'])}** chance" if r["chance"] is not None else "")
             for r in rows[:SHOWN]]
    more = len(rows) - len(lines)
    body = "\n".join(lines)
    while len(body) > 3700:          # long titles and links; the embed caps a description at 4096
        lines.pop()
        more += 1
        body = "\n".join(lines)
    embed.description = f"{len(rows)} to go, {heading.lower()}\n\n{body}" + (f"\n-# and {more} more" if more > 0 else "")
    return embed, files, goal


class PlatesView(OwnerOnlyView):
    def __init__(self, owner_id: int, plate: Optional[str], goal: Optional[str], order: str):
        super().__init__(owner_id, timeout=600)
        self.plate, self.goal, self.order = plate, goal, order
        # 28 plates is over a menu's 25, so the plates up to FiNALE and the DX ones get a menu each
        choices = plate_choices()
        for row, (placeholder, older) in enumerate((("Plates to FiNALE", True), ("DX plates", False))):
            options = [discord.SelectOption(label=label, value=key, default=key == plate)
                       for label, key in choices if (PLATE_KEYS[key].versions[-1] < "200") == older]
            pick = discord.ui.Select(placeholder=placeholder, row=row, options=options)
            pick.callback = self._picker(pick, plate=True)
            self.add_item(pick)
        if plate:
            goals = discord.ui.Select(placeholder="Condition", row=2, options=[
                discord.SelectOption(label=GOAL_LABELS[g], value=g, default=g == goal) for g in PLATE_KEYS[plate].goals])
            goals.callback = self._picker(goals, plate=False)
            self.add_item(goals)
            sort = discord.ui.Select(placeholder="Sort", row=3, options=[
                discord.SelectOption(label=label, value=value, default=value == order) for value, label in ORDER_LABELS.items()])
            sort.callback = self._sorter(sort)
            self.add_item(sort)
            back = discord.ui.Button(label="All plates", row=4, style=discord.ButtonStyle.secondary)
            back.callback = self._back
            self.add_item(back)

    async def _redraw(self, interaction: discord.Interaction, plate: Optional[str], goal: Optional[str], order: Optional[str] = None) -> None:
        from rasmai.bot.state.cache import cache_get
        await interaction.response.defer()
        cached = cache_get(str(self.owner_id))
        if cached is None:
            await interaction.followup.send("Those results have expired - run the command again.", ephemeral=True)
            return
        embed, files, view = await build_plates(cached, self.owner_id, plate, goal, order or self.order)
        await interaction.edit_original_response(embed=embed, attachments=files, view=view)
        view.message = self.message

    def _picker(self, select: discord.ui.Select, plate: bool):
        async def callback(interaction: discord.Interaction) -> None:
            if plate:
                await self._redraw(interaction, select.values[0], None)
            else:
                await self._redraw(interaction, self.plate, select.values[0])
        return callback

    def _sorter(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            await self._redraw(interaction, self.plate, self.goal, select.values[0])
        return callback

    async def _back(self, interaction: discord.Interaction) -> None:
        await self._redraw(interaction, None, None)
