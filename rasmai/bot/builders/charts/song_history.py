from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import io
import discord
import asyncio

from rasmai.engine.analysis import ChartRef, rank_for
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_NAMES, stamp, today
from rasmai.bot.state.snapshots import chart_key
from rasmai.storage.db import load_chart_scores
from rasmai.images.cards import history_card_html
from rasmai.bot.ui import emoji
from rasmai.bot.core import try_render
from rasmai.images.render import cover_html_factory
from rasmai.bot.builders.charts.index import charts_for, jacket_file, song_for_chart, songs_by_loose_key
from rasmai.bot.builders.charts.song import DIFFICULTY_COLOUR, _chart_rows, song_videos


def _history_points(cached: CachedAnalysis, ref: ChartRef) -> List[Dict[str, Any]]:
    """Stored scores for a chart, under both the database's and the scraped spelling of its title.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :param ref: The chart being shown.
    :type ref: ChartRef
    :rtype: List[Dict[str, Any]]
    """
    keys = {"|".join(ref.key)}
    song = song_for_chart(songs_by_loose_key(cached), ref)
    if song is not None:
        keys.add("|".join(chart_key(song)))
    points = []
    seen = set()
    for row in load_chart_scores(cached.user_id, sorted(keys)):
        try:
            when = datetime.fromisoformat(str(row["played_at"]))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.astimezone()
        mark = (when.strftime("%Y-%m-%d %H:%M"), round(float(row["achievement"]), 4))
        if mark in seen:
            continue
        seen.add(mark)
        points.append({"when": when, "achievement": float(row["achievement"]), "dx": int(row["dx_score"] or 0),
                       "fc": row["fc"], "fs": row["fs"], "source": row["source"]})
    points.sort(key=lambda p: p["when"])
    return points


async def build_song_history(cached: Optional[CachedAnalysis], title: str, page: int, owner_id: Optional[int]
                             ) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    """Every score the bot has seen for one chart of a song, as a graph and a few numbers.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param title: The song title.
    :type title: str
    :param page: Which page to show, counting from zero.
    :type page: int
    :param owner_id: The Discord user the components answer to.
    :type owner_id: Optional[int]
    :rtype: Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]
    """
    from rasmai.bot.builders.charts.views import SongView
    if cached is None:
        embed = discord.Embed(title=title, description="Run `/analyze` first so there is an account to read history for.",
                              color=discord.Color.orange())
        return embed, [], None
    refs = charts_for(title, cached.analyzer.chart_index)
    if not refs:
        return discord.Embed(title=title, description="The database lists this title but no playable charts."), [], None
    rows = _chart_rows(cached, refs)
    page = max(0, min(page or 0, len(refs) - 1))
    ref = refs[page]
    points = await asyncio.to_thread(_history_points, cached, ref)
    player = cached.analyzer.player

    embed = discord.Embed(
        title=f"{title} · score history",
        color=discord.Color.from_rgb(*DIFFICULTY_COLOUR.get(ref.difficulty, (162, 102, 232))),
    )
    embed.add_field(name=f"{TIER_NAMES.get(ref.difficulty, ref.difficulty.upper())} {ref.level} · {ref.chart_type.upper()}",
                    value=f"const **{ref.constant:.1f}**", inline=False)
    if points:
        values = [p["achievement"] for p in points]
        best = max(values)
        plays = [p for p in points if p["source"] != "best"]
        latest = points[-1]
        first = points[0]
        embed.add_field(name="Best", value=f"**{best:.4f}%** {emoji.rank(rank_for(best), rank_for(best))}", inline=True)
        embed.add_field(name="Latest", value=f"**{latest['achievement']:.4f}%** {stamp(latest['when'], 'R')}", inline=True)
        embed.add_field(name="Since", value=f"{first['achievement']:.4f}% {stamp(first['when'], 'D')}\n-# {best - first['achievement']:+.4f} to your best", inline=True)
        if plays:
            recent = plays[-5:]
            average = sum(p["achievement"] for p in recent) / len(recent)
            embed.add_field(name="Plays seen", value=f"**{len(plays)}** · last {len(recent)} average **{average:.4f}%**", inline=True)
        embed.add_field(name="Points", value=f"**{len(points)}** recorded", inline=True)
    else:
        embed.description = ("No scores recorded for this chart yet. History builds up from every analysis and from "
                             "the plays in your recent list, so it fills in as you play and run commands.")

    files: List[discord.File] = []
    key = f"history:{title}:{page}:{len(points)}"
    if key not in cached.images:
        html = await asyncio.to_thread(history_card_html, title, ref.difficulty, ref.level, ref.chart_type, ref.cover,
                                       cover_html_factory(cached.analyzer.jacket_path), points, player.name,
                                       cached.start_rating, player.avatar_base64, today())
        cached.images[key] = await try_render(html)
    shot = cached.images.get(key)
    if shot:
        files.append(discord.File(io.BytesIO(shot), filename="rasmai-history.png"))
        embed.set_image(url="attachment://rasmai-history.png")
    thumb = jacket_file(cached, ref.cover)
    if thumb:
        files.append(thumb)
        embed.set_thumbnail(url=f"attachment://{thumb.filename}")
    embed.set_footer(text=f"chart {page + 1} of {len(refs)} · a point per play seen and per best that moved")
    view = SongView(owner_id, title, refs, rows, page, history=True, videos=await song_videos(title, refs)) if owner_id is not None else None
    return embed, files, view
