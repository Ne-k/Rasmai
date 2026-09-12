from typing import Any, Dict, List, Optional, Tuple
import discord
import asyncio
import logging

from rasmai.engine.analysis import ChartRef
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_NAMES, stamp
from rasmai.bot.state.snapshots import chart_key
from rasmai.storage.db import save_play_counts
from rasmai.bot.ui import emoji
from rasmai.images.pages import star_text
from rasmai.bot.builders.charts.index import song_for_chart, songs_by_loose_key
from rasmai.bot.builders.charts.ladder import chart_ladder, format_ladder, format_prediction, prediction_for

logger = logging.getLogger(__name__)


DIFFICULTY_COLOUR = {"basic": (75, 184, 95), "advanced": (224, 160, 32), "expert": (226, 69, 90), "master": (162, 102, 232), "remaster": (203, 187, 232)}


# Discord only has four button colours; green, grey, red and blurple map to the difficulty ladder
DIFFICULTY_STYLE = {
    "basic": discord.ButtonStyle.success,
    "advanced": discord.ButtonStyle.secondary,
    "expert": discord.ButtonStyle.danger,
    "master": discord.ButtonStyle.primary,
    "remaster": discord.ButtonStyle.secondary,
}


def page_index(refs: List[ChartRef], chart_type: str, difficulty: str) -> Optional[int]:
    """Which /chart page shows this chart.

    :param refs: Every chart the song has.
    :type refs: List[ChartRef]
    :param chart_type: ``"std"`` or ``"dx"``.
    :type chart_type: str
    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: str
    :rtype: Optional[int]
    """
    for index, ref in enumerate(refs):
        if ref.chart_type == chart_type and ref.difficulty == difficulty:
            return index
    return None


def difficulty_page(refs: List[ChartRef], rows: List[Dict[str, Any]], difficulty: str) -> Optional[int]:
    """The page for a requested difficulty: the played chart of that tier, else the DX one, else any.

    :param refs: Every chart the song has.
    :type refs: List[ChartRef]
    :param rows: The rows to render.
    :type rows: List[Dict[str, Any]]
    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: str
    :rtype: Optional[int]
    """
    matches = [i for i, ref in enumerate(refs) if ref.difficulty == difficulty]
    if not matches:
        return None
    for index in matches:
        if rows[index].get("played"):
            return index
    for index in matches:
        if refs[index].chart_type == "dx":
            return index
    return matches[0]


async def ensure_play_counts(cached: Optional[CachedAnalysis], refs: List[ChartRef]) -> None:
    """Read this song's play counts now if the analysis never needed them.

    The analysis only fetches counts for the charts it recommends, so a chart you
    look up directly may still be unknown; one detail page per song fills it in.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param refs: Every chart the song has.
    :type refs: List[ChartRef]
    """
    if cached is None:
        return
    a = cached.analyzer
    if getattr(a, "_official_session", None) is None:
        return
    loose_map = songs_by_loose_key(cached)
    wanted: Dict[str, Tuple[str, str, str]] = {}
    for ref in refs:
        song = song_for_chart(loose_map, ref)
        if song is None or not song.official_idx:
            continue
        if a.play_counts.get(chart_key(song), 0) > 0:
            continue
        wanted.setdefault(song.official_idx, (song.official_idx, song.name, (song.chart_type or "std").lower()))
    if not wanted:
        return
    try:
        fetched = await asyncio.to_thread(a.fetch_official_play_counts, list(wanted.values()), cached.region)
    except Exception as error:
        logger.info(f"play count lookup for /chart failed: {error}")
        return
    if fetched:
        a.play_counts.update(fetched)
        save_play_counts(cached.user_id, fetched)


def _default_page(rows: List[Dict[str, Any]]) -> int:
    """Open on the hardest chart the player has a score on, else the hardest chart.

    :param rows: The rows to render.
    :type rows: List[Dict[str, Any]]
    :rtype: int
    """
    played = [i for i, r in enumerate(rows) if r.get("played")]
    return played[-1] if played else max(0, len(rows) - 1)


def last_play(cached: Optional[CachedAnalysis], ref: ChartRef) -> Optional[Dict[str, Any]]:
    """The newest play of this chart still on the recent list, or None.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param ref: The chart being shown.
    :type ref: ChartRef
    :rtype: Optional[Dict[str, Any]]
    """
    if cached is None:
        return None
    from rasmai.bot.builders.history import recent_plays
    from rasmai.bot.builders.charts.index import loose_key
    wanted = loose_key(ref.title, ref.chart_type, ref.difficulty)
    for play in recent_plays(cached):
        if loose_key(play["title"], play["chart_type"], play["difficulty"]) == wanted:
            return play
    return None


def _page_fields(embed: discord.Embed, cached: Optional[CachedAnalysis], ref: ChartRef, row: Dict[str, Any],
                 play: Optional[Dict[str, Any]] = None, detail: Optional[Dict[str, Any]] = None) -> None:
    """One chart, laid out as inline fields.

    :param embed: The embed being built.
    :type embed: discord.Embed
    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param ref: The chart being shown.
    :type ref: ChartRef
    :param row: One row of the table.
    :type row: Dict[str, Any]
    """
    if not cached:
        embed.add_field(name="Your score", value="-# /login to see it here", inline=True)
        return
    if not row["played"]:
        expected = cached.analyzer.play_profile.expected_for(ref.constant, ref.difficulty) if cached.analyzer.play_profile else 0.0
        estimate = f"\n-# you'd usually land ~{expected:.1f}% here" if expected else ""
        embed.add_field(name="Your score", value="never played" + estimate, inline=True)
        embed.add_field(name="Best-50", value=row.get("note") or "-", inline=True)
        prediction = prediction_for(cached, ref, row)
        if prediction:
            prediction["tier"] = TIER_NAMES.get(ref.difficulty, ref.difficulty.upper()).title()
            embed.add_field(name="Prediction", value=format_prediction(prediction, played=False), inline=False)
        ladder = chart_ladder(cached, ref, row)
        if ladder:
            embed.add_field(name="What each rank would be worth",
                            value=format_ladder(ladder) + "\n-# odds are for a first pass, judged from how you play this level",
                            inline=False)
        return
    embed.add_field(name="Your score", value=f"**{row['accuracy']:.4f}%** {emoji.rank(row['rank'], row['rank'])}\n-# rating **{row['rating']}**", inline=True)
    lamp = emoji.lamps(row.get("fc"), row.get("fs"))
    embed.add_field(name="Lamp", value=lamp or "-# none yet", inline=True)
    if row.get("max_dx"):
        embed.add_field(name="DX score", value=f"**{row['dx']:,}** / {row['max_dx']:,}\n-# {star_text(row['stars'])}", inline=True)
    elif row.get("dx"):
        embed.add_field(name="DX score", value=f"**{row['dx']:,}**\n-# max unknown for this chart", inline=True)
    plays = row.get("plays") or 0
    embed.add_field(name="Plays", value=str(plays) if plays else "-# unknown", inline=True)
    embed.add_field(name="Best-50", value=row.get("note") or "-", inline=True)
    if play:
        from rasmai.bot.builders.history import lost_text
        when = stamp(play["when"], "R") if play.get("when") else play["day"]
        score = f"**{play['achievement']:.4f}%** {emoji.rank(play['rank'], play['rank'])}" if play.get("achievement") is not None else "—"
        cost = lost_text(detail) if detail else ""
        embed.add_field(name="Last play", value=f"{score} · {when}" + (f"\n-# lost to {cost}" if cost else ""), inline=True)
    prediction = prediction_for(cached, ref, row)
    if prediction:
        prediction["tier"] = TIER_NAMES.get(ref.difficulty, ref.difficulty.upper()).title()
        embed.add_field(name="Prediction", value=format_prediction(prediction, played=True), inline=False)
    ladder = chart_ladder(cached, ref, row)
    if ladder:
        embed.add_field(name="What each rank is worth",
                        value=format_ladder(ladder) + "\n-# gain is what it adds to your best-50 · odds are how often you score like that here",
                        inline=False)
