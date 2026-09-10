from typing import Any, Dict, List, Optional, Sequence, Tuple
import io
import discord
import asyncio
import logging

from rasmai.engine.analysis import ChartRef, loose_title, rank_for
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_NAMES, _fit, today
from rasmai.web.links import chart_url
from rasmai.bot.state.snapshots import chart_key
from rasmai.storage.db import save_play_counts
from rasmai.bot.ui import emoji
from rasmai.scraping import wiki
from rasmai.config import WIKI_VIDEOS
from rasmai.bot.core import try_render
from rasmai.images.cards import song_card_html
from rasmai.images.render import cover_html_factory
from rasmai.images.pages import star_text, stars_for
from rasmai.bot.builders.charts.index import (
    chart_designer, charts_for, jacket_file, resolve_title, shared_index, song_for_chart, song_record,
    songs_by_loose_key, version_name,
)
from rasmai.bot.builders.charts.ladder import (
    _cutoffs, _version_label, chart_ladder, entry_note, format_ladder, format_prediction, prediction_for,
)
from rasmai.bot.builders.charts.details import _note_split, _pattern_field, _song_chart_line, unlock_field

logger = logging.getLogger(__name__)


def _chart_rows(cached: Optional[CachedAnalysis], refs: List[ChartRef]) -> List[Dict[str, Any]]:
    """One row per chart of a song: the chart, and the player's score on it when there is one.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param refs: Every chart the song has.
    :type refs: List[ChartRef]
    :rtype: List[Dict[str, Any]]
    """
    loose_map = songs_by_loose_key(cached) if cached else {}
    rows: List[Dict[str, Any]] = []
    for ref in refs:
        song = song_for_chart(loose_map, ref)
        row: Dict[str, Any] = {
            "difficulty": ref.difficulty, "level": ref.level, "chart_type": ref.chart_type, "constant": ref.constant,
            "played": song is not None, "note": entry_note(cached, ref, song) if cached else "",
        }
        if song is not None:
            dx = int(song.dx_score or 0)
            max_dx = ref.notes * 3 if ref.notes else 0
            row.update({
                "accuracy": float(song.accuracy or 0), "rank": song.current_rank or rank_for(float(song.accuracy or 0)),
                "rating": int(song.rating or 0), "fc": song.fc_status, "fs": song.fs_status,
                "dx": dx, "max_dx": max_dx, "stars": stars_for(dx / max_dx) if max_dx and dx else 0,
                "plays": max(0, cached.analyzer.play_counts.get(chart_key(song), 0)) if cached else 0,
            })
        rows.append(row)
    return rows


def _score_lines(row: Dict[str, Any]) -> str:
    """The per-chart block of the /chart embed.

    :param row: One row of the table.
    :type row: Dict[str, Any]
    :rtype: str
    """
    if not row["played"]:
        return "never played" + (f"\n-# {row['note']}" if row.get("note") else "")
    lines = [f"**{row['accuracy']:.4f}%** {row['rank']} · rating **{row['rating']}**"]
    extras = []
    lamp = " · ".join(b for b in (str(row.get("fc") or "").upper(), str(row.get("fs") or "").upper()) if b and b != "NONE")
    if lamp:
        extras.append(lamp)
    if row.get("plays"):
        extras.append(f"{row['plays']} play{'s' if row['plays'] != 1 else ''}")
    if row.get("max_dx"):
        extras.append(f"DX {row['dx']:,}/{row['max_dx']:,} {star_text(row['stars'])}")
    if extras:
        lines.append("-# " + " · ".join(extras))
    if row.get("note"):
        lines.append(f"-# {row['note']}")
    return "\n".join(lines)


async def _song_card(cached: Optional[CachedAnalysis], title: str, refs: List[ChartRef], rows: List[Dict[str, Any]],
                     highlight: Optional[str] = None, ladder: Optional[List[Dict[str, Any]]] = None,
                     ladder_label: str = "", forecast: str = "", eyebrow: str = "Chart lookup",
                     version: str = "", facts: Sequence[str] = ()) -> Optional[bytes]:
    first = refs[0] if refs else None
    if first is None:
        return None
    jacket_path = cached.analyzer.jacket_path if cached else "otoge_cache/jackets/"
    player = cached.analyzer.player if cached else None
    html = song_card_html(
        title, first.artist, first.genre, version or _version_label(cached, first), first.cover, cover_html_factory(jacket_path),
        rows, player.name if player else "", cached.start_rating if cached else 0,
        player.avatar_base64 if player else "", _cutoffs(cached), date_text=today(), highlight=highlight,
        ladder=ladder or (), ladder_label=ladder_label, forecast=forecast, eyebrow=eyebrow, facts=facts,
    )
    key = f"song:{title}:{highlight or ''}:{'l' if ladder else ''}:{eyebrow}"
    if cached is None:
        return await try_render(html)
    if key not in cached.images:
        cached.images[key] = await try_render(html)
    return cached.images[key]


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


def _page_fields(embed: discord.Embed, cached: Optional[CachedAnalysis], ref: ChartRef, row: Dict[str, Any]) -> None:
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
    prediction = prediction_for(cached, ref, row)
    if prediction:
        prediction["tier"] = TIER_NAMES.get(ref.difficulty, ref.difficulty.upper()).title()
        embed.add_field(name="Prediction", value=format_prediction(prediction, played=True), inline=False)
    ladder = chart_ladder(cached, ref, row)
    if ladder:
        embed.add_field(name="What each rank is worth",
                        value=format_ladder(ladder) + "\n-# gain is what it adds to your best-50 · odds are how often you score like that here",
                        inline=False)


def _resolve_song(cached: Optional[CachedAnalysis], query: str) -> Tuple[Optional[str], List[ChartRef], Optional[discord.Embed]]:
    """Title and charts for a query, or the embed that says why there are none.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param query: What the player typed.
    :type query: str
    :rtype: Tuple[Optional[str], List[ChartRef], Optional[discord.Embed]]
    """
    index = cached.analyzer.chart_index if cached else shared_index()
    title = resolve_title(query, index)
    if not title:
        mine = [s for s in (cached.analyzer.songs if cached else []) if str(s.name).casefold() == str(query).casefold()]
        if mine:
            scores = ", ".join(f"{str(s.difficulty_type).title()} {s.level} at {float(s.accuracy):.4f}%" for s in mine)
            embed = discord.Embed(title=f"{mine[0].name} is not in the chart database yet",
                                  description=(f"It is a new song. The database refreshes itself within a day of a read that meets it; the jacket, "
                                               f"constants and this page arrive with it. Until then your score counts with a constant taken from the "
                                               f"middle of its level.\n-# yours: {scores}"),
                                  color=discord.Color.orange())
            return None, [], embed
        embed = discord.Embed(title="No song found",
                              description=f"Nothing in the chart database matches **{query}**. Try part of the title, or its reading in romaji.",
                              color=discord.Color.orange())
        return None, [], embed
    refs = charts_for(title, index)
    if not refs:
        embed = discord.Embed(title=title, description="The database lists this title but no playable charts.", color=discord.Color.orange())
        return title, [], embed
    return title, refs, None


async def build_song(cached: Optional[CachedAnalysis], query: str, page: Optional[int] = None,
                     owner_id: Optional[int] = None, difficulty: Optional[str] = None
                     ) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    """One page per chart of the song, with buttons to move between them; the card image shows them all.

    `difficulty` opens straight at that tier; otherwise the page is the chart that matters most.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param query: What the player typed.
    :type query: str
    :param page: Which page to show, counting from zero.
    :type page: Optional[int]
    :param owner_id: The Discord user the components answer to.
    :type owner_id: Optional[int]
    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: Optional[str]
    :rtype: Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]
    """
    from rasmai.bot.builders.charts.views import SongView
    title, refs, problem = _resolve_song(cached, query)
    if problem is not None:
        return problem, [], None
    await ensure_play_counts(cached, refs)
    rows = _chart_rows(cached, refs)
    if page is None and difficulty:
        page = difficulty_page(refs, rows, difficulty)
    page = _default_page(rows) if page is None else max(0, min(page, len(refs) - 1))
    ref, row = refs[page], rows[page]

    embed = discord.Embed(
        title=f"{title}",
        description=f"{ref.artist}\n-# {ref.genre} · {_version_label(cached, ref)}",
        color=discord.Color.from_rgb(*DIFFICULTY_COLOUR.get(ref.difficulty, (162, 102, 232))),
    )
    # embeds do not render markdown headings, so the chart name is a field title
    embed.add_field(
        name=f"{TIER_NAMES.get(ref.difficulty, ref.difficulty.upper())} {ref.level} · {ref.chart_type.upper()}",
        value=f"const **{ref.constant:.1f}**" + (f" · {ref.notes:,} notes" if ref.notes else "") + _note_split(ref), inline=False,
    )
    _page_fields(embed, cached, ref, row)
    _pattern_field(embed, cached, ref)

    files: List[discord.File] = []
    forecast = prediction_for(cached, ref, row)
    if forecast:
        forecast_text = f"a good run lands ~{forecast['expected']:.2f}% ({forecast['low']:.1f} to {forecast['high']:.1f})"
        if forecast.get("new_best") is not None:
            forecast_text += f" · {forecast['new_best'] * 100:.0f}% chance of a new best next time"
        else:
            forecast_text += " · first pass"
    else:
        forecast_text = ""
    shot = await _song_card(cached, title, refs, rows, highlight=ref.difficulty,
                            ladder=chart_ladder(cached, ref, row),
                            ladder_label=f"{TIER_NAMES.get(ref.difficulty, ref.difficulty.upper())} {ref.level}",
                            forecast=forecast_text)
    if shot:
        files.append(discord.File(io.BytesIO(shot), filename="rasmai-song.png"))
    thumb = jacket_file(cached, ref.cover)
    if thumb:
        files.append(thumb)
        embed.set_thumbnail(url=f"attachment://{thumb.filename}")
    footer = f"chart {page + 1} of {len(refs)} · constants from otoge-db"
    if cached:
        footer += f" · your cutoffs {_cutoffs(cached)}"
    embed.url = chart_url(title, ref.chart_type, ref.difficulty, ref.cover)
    page_info = await song_page(title, refs)
    videos = page_info["videos"]
    unlock_field(embed, page_info, cached)
    if (ref.chart_type, ref.difficulty) in videos:
        footer += " · video via SilentBlue RemyWiki"
    embed.set_footer(text=footer)
    view = SongView(owner_id, title, refs, rows, page, videos=videos) if owner_id is not None else None
    return embed, files, view


EMPTY_PAGE: Dict[str, Any] = {"page": "", "videos": {}, "unlock": []}


async def song_page(title: str, refs: List[ChartRef]) -> Dict[str, Any]:
    """What the wiki holds for the song (chart videos, unlock notes), within a short wait; a slow first fetch finishes in the background and is cached.

    :param title: The song title.
    :type title: str
    :param refs: Every chart the song has.
    :type refs: List[ChartRef]
    :rtype: Dict[str, Any]
    """
    if not WIKI_VIDEOS or not refs:
        return dict(EMPTY_PAGE)
    record = song_record(title)
    reading = str(record.get("alt_title", "") or "")
    types = [ref.chart_type for ref in refs]
    task = asyncio.ensure_future(asyncio.to_thread(wiki.lookup_page, title, reading, types))
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=8.0)
    except asyncio.TimeoutError:
        return dict(EMPTY_PAGE)
    except Exception as error:      # a wiki hiccup must never break /chart
        logger.info("wiki lookup failed for %r: %s", title, error)
        return dict(EMPTY_PAGE)


async def song_videos(title: str, refs: List[ChartRef]) -> Dict[Tuple[str, str], str]:
    return (await song_page(title, refs))["videos"]


async def build_song_details(cached: Optional[CachedAnalysis], query: str, owner_id: Optional[int] = None
                             ) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    """The song itself: who made it, when it landed, and every chart it has, with your scores where they exist.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param query: What the player typed.
    :type query: str
    :param owner_id: The Discord user the components answer to.
    :type owner_id: Optional[int]
    :rtype: Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]
    """
    from rasmai.bot.builders.charts.views import SongDetailsView
    title, refs, problem = _resolve_song(cached, query)
    if problem is not None:
        return problem, [], None
    record = song_record(title)
    first = refs[0]
    await ensure_play_counts(cached, refs)
    rows = _chart_rows(cached, refs)

    reading = str(record.get("alt_title", "") or "").strip()
    facts: List[str] = []
    if reading and loose_title(reading) != loose_title(title):
        facts.append(reading)
    facts.append(first.genre or "genre unknown")
    bpm = str(record.get("bpm", "") or "").strip()
    if bpm:
        facts.append(f"BPM {bpm}")
    version = version_name(record) or _version_label(cached, first)
    if version:
        facts.append(version)
    if cached and cached.analyzer.current_version and first.version == cached.analyzer.current_version:
        facts.append("current version")
    if not first.intl:
        facts.append("not on the international version")
    if first.deleted:
        facts.append("removed from the game")
    played = [r for r in rows if r.get("played")]
    embed = discord.Embed(
        title=title,
        description=f"{first.artist or 'artist unknown'}\n-# {' · '.join(facts)}",
        color=discord.Color.from_rgb(*DIFFICULTY_COLOUR.get(max(refs, key=lambda r: r.constant).difficulty, (162, 102, 232))),
    )
    for chart_type in ("std", "dx"):
        group = [(ref, row) for ref, row in zip(refs, rows) if ref.chart_type == chart_type]
        if not group:
            continue
        lines = [_song_chart_line(ref, row, chart_designer(record, ref)) for ref, row in group]
        embed.add_field(name=f"{'Standard' if chart_type == 'std' else 'DX'} charts", value=_fit(lines), inline=False)
    if cached:
        if played:
            best = max(played, key=lambda r: r["rating"])
            summary = f"**{len(played)}** of {len(rows)} charts played · best rating **{best['rating']}** on {TIER_NAMES.get(best['difficulty'], best['difficulty'].upper())}"
            if cached.analyzer.best50 is not None:
                inside = sum(1 for r in played if "in your best-50" in str(r.get("note", "")))
                if inside:
                    summary += f" · {inside} in your best-50"
        else:
            summary = "none of its charts played yet"
        embed.add_field(name="You", value=summary, inline=False)
    else:
        embed.add_field(name="You", value="-# /login to see your scores here", inline=False)
    wiki_url = str(record.get("wiki_url", "") or "").strip()
    footer = "levels, constants and note counts from otoge-db · title links to the dashboard"
    embed.set_footer(text=footer)

    files: List[discord.File] = []
    card_facts = [f"BPM {bpm}"] if bpm else []
    if reading and loose_title(reading) != loose_title(title):
        card_facts.insert(0, reading)
    shot = await _song_card(cached, title, refs, rows, eyebrow="Song lookup", version=version_name(record), facts=card_facts)
    if shot:
        files.append(discord.File(io.BytesIO(shot), filename="rasmai-song.png"))
    thumb = jacket_file(cached, first.cover)
    if thumb:
        files.append(thumb)
        embed.set_thumbnail(url=f"attachment://{thumb.filename}")
    embed.url = chart_url(title, first.chart_type, first.difficulty, first.cover)
    page_info = await song_page(title, refs)
    videos = page_info["videos"]
    unlock_field(embed, page_info, cached)
    view = SongDetailsView(owner_id, title, refs, rows, official=videos.get(("", "official")), wiki_url=wiki_url) if owner_id is not None else None
    if videos.get(("", "official")) or page_info.get("unlock"):
        embed.set_footer(text=footer + " · video and unlock notes via SilentBlue RemyWiki")
    return embed, files, view
