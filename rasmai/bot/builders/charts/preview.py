from collections import OrderedDict
from typing import Dict, Optional, Tuple
import asyncio
import io
import logging
import math
import time

import discord

from rasmai.config import support_line
from rasmai.engine.analysis import ChartRef
from rasmai.errors import report
from rasmai.images.preview import Preview, render_preview

logger = logging.getLogger(__name__)

COOLDOWN = 20.0                  # seconds between one person's previews: each is a second or two of CPU
UPLOAD_LIMIT = 10 * 1024 * 1024  # what a DM or a user install may upload; a server's own limit is read off the server
MARGIN = 128 * 1024              # left under the limit for the rest of the request
KEPT = 8                         # finished previews held, so the same chart asked twice is drawn once

_last: Dict[int, float] = {}
_made: "OrderedDict[Tuple[str, int], Preview]" = OrderedDict()


def sheet_key(ref: ChartRef) -> str:
    """Where a chart's notation is stored: the folded title, the type and the difficulty."""
    return "|".join(ref.key)


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _draw(text: str, published: int, limit: int) -> Optional[Preview]:
    from rasmai.scraping.simai import _best
    chart = _best(text, published)
    return render_preview(chart, limit) if chart is not None else None


async def build_preview(ref: ChartRef, limit: int) -> Optional[Preview]:
    """The picture for a chart, or None when its notation has not been read yet; drawn off the loop and inside the render slots."""
    from rasmai.bot.core import RENDER_SEMAPHORE
    from rasmai.storage.db import sheet_get
    key = (sheet_key(ref), limit)
    if key in _made:
        _made.move_to_end(key)
        return _made[key]
    text = await asyncio.to_thread(sheet_get, key[0])
    if text is None:
        return None
    async with RENDER_SEMAPHORE:
        made = await asyncio.to_thread(_draw, text, ref.notes, limit)
    if made is not None:
        _made[key] = made
        while len(_made) > KEPT:
            _made.popitem(last=False)
    return made


def preview_button(ref: ChartRef) -> Optional[discord.ui.Button]:
    """A Preview button for a chart, or None when there is no notation to draw it from, so nobody is offered a dead button."""
    from rasmai.storage.db import sheet_held
    try:
        if not sheet_held(sheet_key(ref)):
            return None
    except Exception:
        logger.exception("could not check whether a chart's notation is stored")
        return None
    button = discord.ui.Button(label="Preview", row=4, style=discord.ButtonStyle.secondary)

    async def callback(interaction: discord.Interaction) -> None:
        await send_preview(interaction, ref)
    button.callback = callback
    return button


async def send_preview(interaction: discord.Interaction, ref: ChartRef) -> None:
    """Draw the chart's busiest stretch and post it under the chart page, as a new message so the page stays where it is."""
    from rasmai.bot.core import command_context
    person = interaction.user.id
    now = time.monotonic()
    wait = COOLDOWN - (now - _last.get(person, -COOLDOWN))
    if wait > 0:
        await interaction.response.send_message(f"Easy - one preview every {int(COOLDOWN)} seconds. Try again in {math.ceil(wait)}s.", ephemeral=True)
        return
    if len(_last) > 2000:
        for stale in [p for p, at in _last.items() if now - at > COOLDOWN]:
            del _last[stale]
    _last[person] = now
    await interaction.response.defer(ephemeral=bool(interaction.message and interaction.message.flags.ephemeral), thinking=True)
    limit = (interaction.guild.filesize_limit if interaction.guild else UPLOAD_LIMIT) - MARGIN
    try:
        made = await build_preview(ref, limit)
    except Exception as error:
        _last.pop(person, None)         # it was not their doing, so they may try again at once
        error_id = report(error, "chart preview failed", await command_context(interaction))
        await interaction.followup.send(f"Couldn't draw that preview.\n{support_line(error_id)}", ephemeral=True)
        return
    if made is None:
        _last.pop(person, None)
        await interaction.followup.send("I haven't read that chart's notes yet, so there's nothing to draw. They come in a few at a time, so check back later.",
                                        ephemeral=True)
        return
    if len(made.gif) > limit:
        await interaction.followup.send("That one came out too big to upload here, even at the smallest size.", ephemeral=True)
        return
    name = f"{ref.chart_type}-{ref.difficulty}-preview.gif"
    await interaction.followup.send(
        f"**{ref.title}** · {ref.difficulty.upper()} {ref.chart_type.upper()} · the busiest part, {_clock(made.start)} - {_clock(made.end)}\n"
        "-# Drawn from the chart's notes, so the timing is right but the speed and look aren't exactly the game's.",
        file=discord.File(io.BytesIO(made.gif), filename=name))
