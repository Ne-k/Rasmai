from collections import OrderedDict
from typing import Dict, Optional, Tuple
import asyncio
import io
import logging
import math
import shutil
import time

import discord

from rasmai.config import support_line
from rasmai.engine.analysis import ChartRef
from rasmai.errors import report
from rasmai.images.preview import NOTE_SPEED, TOUCH_SPEED, Preview, render_preview, render_video

logger = logging.getLogger(__name__)

COOLDOWN = 20.0                  # seconds between one person's previews: each is several seconds of CPU
VIDEO_COOLDOWN = 120.0           # and between their videos: a whole song is a minute or two of it
UPLOAD_LIMIT = 10 * 1024 * 1024  # what a DM or a user install may upload; a server's own limit is read off the server
MARGIN = 128 * 1024              # left under the limit for the rest of the request
KEPT = 8                         # finished previews held, so the same chart asked twice is drawn once
VIDEOS_KEPT = 3                  # and videos, which are up to the upload limit each
# videos waiting their turn: each is a minute or two, and a press not answered within Discord's 15 minutes can no longer be
VIDEOS_QUEUED = 4

_last: Dict[int, float] = {}
_made: "OrderedDict[Tuple[str, int], Preview]" = OrderedDict()
_video_last: Dict[int, float] = {}
_videos: "OrderedDict[Tuple[str, int, int, int], Preview]" = OrderedDict()
_one_video = asyncio.Semaphore(1)       # a video holds a render slot for minutes, so only one of them takes a slot at a time
_videos_waiting = 0


def sheet_key(ref: ChartRef) -> str:
    """Where a chart's notation is stored: the folded title, the type and the difficulty."""
    return "|".join(ref.key)


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _draw(text: str, published: int, limit: int) -> Optional[Preview]:
    from rasmai.scraping.simai import _best
    chart = _best(text, published)
    return render_preview(chart, limit) if chart is not None else None


def _found(ref: ChartRef):
    """The chart's own folder, with its notes on the song's clock and the song, or None when it is not held or cannot be looked for."""
    try:
        from rasmai.scraping.astrodx import find
        return find(ref)
    except Exception:
        logger.exception("could not look for a chart's folder")
        return None


def _held(ref: ChartRef) -> bool:
    try:
        from rasmai.scraping.astrodx import held
        return held(ref)
    except Exception:
        logger.exception("could not check whether a chart's folder is held")
        return False


def _keep(cache: OrderedDict, key: Tuple, made: Optional[Preview], kept: int) -> None:
    if made is not None:
        cache[key] = made
        while len(cache) > kept:
            cache.popitem(last=False)


async def build_preview(ref: ChartRef, limit: int) -> Optional[Preview]:
    """The clip for a chart, or None when its notation has not been read yet; drawn off the loop and inside the render slots."""
    from rasmai.bot.core import RENDER_SEMAPHORE
    from rasmai.storage.db import sheet_get
    key = (sheet_key(ref), limit)
    if key in _made:
        _made.move_to_end(key)
        return _made[key]
    text = await asyncio.to_thread(sheet_get, key[0])
    found = await asyncio.to_thread(_found, ref) if text is None else None     # the chart's own folder when the sheet is missing
    if text is None and found is None:
        return None
    async with RENDER_SEMAPHORE:
        if text is not None:
            made = await asyncio.to_thread(_draw, text, ref.notes, limit)
        else:
            made = await asyncio.to_thread(render_preview, found.chart, limit)
    _keep(_made, key, made, KEPT)
    return made


async def build_video(ref: ChartRef, limit: int, speed: int, touch_speed: int) -> Optional[Preview]:
    """The whole chart with its song at a pair of speeds, or None when its folder is not held; made off the loop in a render slot."""
    global _videos_waiting
    from rasmai.bot.core import RENDER_SEMAPHORE
    key = (sheet_key(ref), speed, touch_speed, limit)
    if key in _videos:
        _videos.move_to_end(key)
        return _videos[key]
    found = await asyncio.to_thread(_found, ref)
    if found is None:
        return None
    _videos_waiting += 1
    try:
        async with _one_video, RENDER_SEMAPHORE:
            made = await asyncio.to_thread(render_video, found.chart, found.track, limit, speed, touch_speed)
    finally:
        _videos_waiting -= 1
    _keep(_videos, key, made, VIDEOS_KEPT)
    return made


def preview_button(ref: ChartRef) -> Optional[discord.ui.Button]:
    """A Preview button for a chart, or None when there is no notation to draw it from, so nobody is offered a dead button."""
    from rasmai.storage.db import sheet_held
    try:
        if not sheet_held(sheet_key(ref)) and not _held(ref):
            return None
    except Exception:
        logger.exception("could not check whether a chart's notation is stored")
        return None
    button = discord.ui.Button(label="Preview", row=4, style=discord.ButtonStyle.secondary)

    async def callback(interaction: discord.Interaction) -> None:
        await send_preview(interaction, ref)
    button.callback = callback
    return button


def full_video_button(ref: ChartRef) -> Optional[discord.ui.Button]:
    """A Video button for a chart, or None when its folder is not held, so nobody is offered a dead button."""
    if not _held(ref):
        return None
    button = discord.ui.Button(label="Video", row=3, style=discord.ButtonStyle.secondary)

    async def callback(interaction: discord.Interaction) -> None:
        await send_video(interaction, ref)
    button.callback = callback
    return button


async def _refuse(interaction: discord.Interaction, text: str) -> None:
    """Say why there is no preview to the person who asked. The public wait is taken down first: the first followup to a deferred reply
    takes its visibility, so an ephemeral one sent straight away would show in the channel."""
    if not (interaction.message and interaction.message.flags.ephemeral):
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
    await interaction.followup.send(text, ephemeral=True)


async def _start(interaction: discord.Interaction, last: Dict[int, float], cooldown: float, what: str) -> Optional[int]:
    """The bytes the post may take once the press is deferred, or None when the person is turned away for pressing again too soon."""
    person = interaction.user.id
    now = time.monotonic()
    wait = cooldown - (now - last.get(person, -cooldown))
    if wait > 0:
        await interaction.response.send_message(f"Easy - one {what} every {int(cooldown)} seconds. Try again in {math.ceil(wait)}s.", ephemeral=True)
        return None
    if len(last) > 2000:
        for stale in [p for p, at in last.items() if now - at > cooldown]:
            del last[stale]
    last[person] = now
    # the post is for the channel, so the wait is public too; a refusal is only for them, which a followup cannot be after a public defer
    await interaction.response.defer(ephemeral=bool(interaction.message and interaction.message.flags.ephemeral), thinking=True)
    return (interaction.guild.filesize_limit if interaction.guild else UPLOAD_LIMIT) - MARGIN


async def send_preview(interaction: discord.Interaction, ref: ChartRef) -> None:
    """Draw the chart's busiest stretch and post it under the chart page, as a new message so the page stays where it is."""
    from rasmai.bot.core import command_context
    person = interaction.user.id
    limit = await _start(interaction, _last, COOLDOWN, "preview")
    if limit is None:
        return
    try:
        made = await build_preview(ref, limit)
    except Exception as error:
        _last.pop(person, None)         # it was not their doing, so they may try again at once
        error_id = report(error, "chart preview failed", await command_context(interaction))
        await _refuse(interaction, f"Couldn't draw that preview.\n{support_line(error_id)}")
        return
    if made is None:
        _last.pop(person, None)
        await _refuse(interaction, "I haven't read that chart's notes yet, so there's nothing to draw. They come in a few at a time, so check back later.")
        return
    if len(made.data) > limit:
        await _refuse(interaction, "That one came out too big to upload here, even at the smallest size.")
        return
    name = f"{ref.chart_type}-{ref.difficulty}-preview.{made.kind}"
    await interaction.followup.send(
        f"**{ref.title}** · {ref.difficulty.upper()} {ref.chart_type.upper()} · the busiest part, {_clock(made.start)} - {_clock(made.end)}\n"
        "-# Drawn from the chart's notes at the game's default speeds, so the timing is right but the look isn't exactly the game's.",
        file=discord.File(io.BytesIO(made.data), filename=name))


async def send_video(interaction: discord.Interaction, ref: ChartRef) -> None:
    """Play the whole chart with its song at the presser's saved speeds and post it under the chart page, as a new message."""
    from rasmai.bot.core import command_context
    from rasmai.bot.state.prefs import NOTE_SPEEDS, TOUCH_SPEEDS, get_prefs, speed_label
    person = interaction.user.id
    limit = await _start(interaction, _video_last, VIDEO_COOLDOWN, "video")
    if limit is None:
        return
    if not shutil.which("ffmpeg"):
        _video_last.pop(person, None)
        await _refuse(interaction, "I can't make videos right now - the tool that encodes them isn't installed here.")
        return
    if _videos_waiting >= VIDEOS_QUEUED:
        _video_last.pop(person, None)
        await _refuse(interaction, f"I'm making {_videos_waiting} other videos right now. Try again in a few minutes.")
        return
    prefs = await asyncio.to_thread(get_prefs, str(person))
    speed, touch_speed = prefs.get("note_speed", NOTE_SPEED), prefs.get("touch_speed", TOUCH_SPEED)
    try:
        made = await build_video(ref, limit, speed, touch_speed)
    except Exception as error:
        _video_last.pop(person, None)
        error_id = report(error, "chart video failed", await command_context(interaction))
        await _refuse(interaction, f"Couldn't make that video.\n{support_line(error_id)}")
        return
    if made is None:
        _video_last.pop(person, None)
        await _refuse(interaction, "I don't have that chart's files, so there's nothing to play.")
        return
    if len(made.data) > limit:
        await _refuse(interaction, "That one came out too big to upload here, even at the smallest size.")
        return
    await interaction.followup.send(
        f"**{ref.title}** · {ref.difficulty.upper()} {ref.chart_type.upper()} · the whole chart, {_clock(made.start)} - {_clock(made.end)} · "
        f"note speed {speed_label(speed, NOTE_SPEEDS)}, touch speed {speed_label(touch_speed, TOUCH_SPEEDS)}\n"
        "-# Drawn from the chart's notes with the song, at your speeds from /settings; the look isn't exactly the game's.",
        file=discord.File(io.BytesIO(made.data), filename=f"{ref.chart_type}-{ref.difficulty}-video.mp4"))
