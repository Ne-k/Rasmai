from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import logging

import discord

from rasmai.engine.analysis import calculate_rating, rank_for
from rasmai.engine.losses import note_losses
from rasmai.engine.insights import plan_credits, rating_forecast
from rasmai.bot.state.cache import CachedAnalysis, cache_get
from rasmai.bot.builders.charts import build_song, build_song_history, charts_for, jacket_file, page_index, songs_by_key
from rasmai.bot.ui.formatting import TIER_NAMES, TIER_SHORT, _fit, chart_link, level_text, message_files, stamp, today
from rasmai.web.links import chart_url
from rasmai.bot.ui import emoji
from rasmai.bot.ui.views import OwnerOnlyView
from rasmai.security import public_reason
from rasmai.storage.db import count_play_history, get_connected_account, load_rating_history
from rasmai.bot.core import try_render
from rasmai.images.cards import play_card_html
from rasmai.images.render import cover_html_factory
from rasmai.images.pages import progress_image_html, recent_image_html, star_text, stars_for

logger = logging.getLogger(__name__)



def recent_key(analyzer: Any, record: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        analyzer._normalize_official_song_name(str(record.get("songName", ""))).casefold(),
        str(record.get("musicType") or "std").lower(),
        str(record.get("difficulty") or "").lower(),
    )


def recent_plays(cached: CachedAnalysis) -> List[Dict[str, Any]]:
    """The recent-plays list with scores, ranks and best-50 context filled in, newest first.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :rtype: List[Dict[str, Any]]
    """
    a = cached.analyzer
    by_key = songs_by_key(cached)
    plays: List[Dict[str, Any]] = []
    for position, record in enumerate(a.recent_songs or []):
        key = recent_key(a, record)
        song = by_key.get(key)
        ref = a.chart_index.get(key)
        raw = float(record.get("achievement") or 0) / 10000.0
        achievement = raw if 0 < raw <= 101.0 else None
        constant = float(song.difficulty or 0) if song else (ref.constant if ref else 0.0)
        chart_rating = calculate_rating(constant, achievement) if achievement and constant > 0 else 0
        is_new = bool(song.is_new) if song else bool(ref and a.current_version and ref.version == a.current_version)
        in_b50 = bool(a.best50) and key in a.best50.pool_for(is_new).in_pool
        pb = bool(song and achievement is not None and abs(float(song.accuracy or 0) - achievement) < 0.00005)
        max_dx = int(record.get("maxDxScore") or 0)
        dx = int(record.get("dxScore") or 0)
        played_at = str(record.get("playedAt", ""))
        try:
            when = datetime.fromisoformat(played_at)
        except ValueError:
            when = None
        plays.append({
            "position": position + 1, "idx": record.get("idx", ""), "key": key,
            "title": song.name if song else (ref.title if ref else str(record.get("songName", ""))),
            "difficulty": key[2], "chart_type": key[1], "level": str(record.get("level") or (song.level if song else "")),
            "constant": round(constant, 1),
            "achievement": achievement, "rank": rank_for(achievement) if achievement is not None else "",
            "dx": dx, "max_dx": max_dx, "dx_pct": (100.0 * dx / max_dx) if max_dx else 0.0,
            "fc": record.get("fc", ""), "fs": record.get("fs", ""),
            "track": f"T{int(record.get('track') or 0)}", "time": played_at[11:16], "day": played_at[:10],
            "when": when,
            "chart_rating": chart_rating, "pb": pb, "in_b50": in_b50,
            "cover": (song.cover_url if song else "") or (ref.cover if ref else ""),
        })
    return plays


def _short_day(label: str) -> str:
    """A day label without its year, for field names where the year is noise."""
    head, _, tail = label.rpartition(" ")
    return head if head and tail.isdigit() and len(tail) == 4 else label


def _day_label(day: str) -> str:
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%a %d %b %Y")
    except ValueError:
        return day or "unknown day"


# ---------------------------------------------------------------- /recent

async def build_recent(cached: CachedAnalysis, owner_id: Optional[int] = None
                       ) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    from rasmai.bot.builders.results import _image
    a = cached.analyzer
    player = a.player
    plays = recent_plays(cached)
    days: List[Tuple[str, List[Dict[str, Any]]]] = []
    for play in plays:
        if days and days[-1][0] == play["day"]:
            days[-1][1].append(play)
        else:
            days.append((play["day"], [play]))
    pbs = sum(1 for p in plays if p["pb"])
    labelled = [(_day_label(day), group) for day, group in days]
    shot = None
    if plays:
        shot = await _image(cached, "recent", lambda: recent_image_html(
            labelled, player.name, cached.start_rating, player.avatar_base64, cover_html_factory(a.jacket_path), pbs, date_text=today(),
        ))
    files, avatar_url = message_files(player, shot, "rasmai-recent.png")
    embed = discord.Embed(title="Recent plays", color=discord.Color.from_rgb(92, 211, 232))
    embed.set_author(name=player.name, icon_url=avatar_url)
    if not plays:
        embed.description = "No recent plays on the account yet."
        return embed, files, None
    scored = [p["achievement"] for p in plays if p["achievement"] is not None]
    average = sum(scored) / len(scored) if scored else 0.0
    b50_hits = sum(1 for p in plays if p["in_b50"])
    embed.description = (f"**{len(plays)}** plays across **{len(days)}** day{'s' if len(days) != 1 else ''} · "
                         f"**{pbs}** new best{'s' if pbs != 1 else ''} · {b50_hits} on best-50 charts · average **{average:.2f}%**")
    # one field per day, side by side, so the reply stays wide rather than tall
    for label, group in labelled[:3]:
        lines = []
        for p in group[:6]:
            short = TIER_SHORT.get(p["difficulty"], p["difficulty"][:3].upper())
            score = f"{p['achievement']:.4f} {emoji.rank(p['rank'], p['rank'])}" if p["achievement"] is not None else "—"
            flags = " ".join(tag for tag in ("`PB`" if p["pb"] else "", "`B50`" if p["in_b50"] else "") if tag)
            clock = stamp(p["when"], "t") if p["when"] else f"`{p['time']}`"
            lines.append(f"{clock} {chart_link(p['title'], p['chart_type'], p['difficulty'], p.get('cover', ''), limit=16)} {flags}\n-# {short} {level_text(p['level'], p.get('constant'))} · {score}")
        more = f"\n-# +{len(group) - 6} more" if len(group) > 6 else ""
        embed.add_field(name=f"{_short_day(label)} · {len(group)}", value=_fit(lines) + more, inline=True)
    if len(labelled) > 3:
        embed.add_field(name="Earlier", value=f"-# {len(labelled) - 3} more day(s) in the image", inline=True)
    stored = count_play_history(cached.user_id)
    kept = f" · {stored} plays kept in your history" if stored else ""
    embed.set_footer(text=f"PB = matches your current best · B50 = counts toward your rating · days are JST · every play in the image{kept}")
    return embed, files, RecentView(owner_id, plays) if owner_id is not None else None


class RecentView(OwnerOnlyView):
    """A menu under the recent list: pick a play to open it in full, judgements and all."""

    def __init__(self, owner_id: int, plays: List[Dict[str, Any]]):
        super().__init__(owner_id, timeout=600)
        options = []
        for p in plays[:25]:
            short = TIER_SHORT.get(p["difficulty"], p["difficulty"][:3].upper())
            score = f"{p['achievement']:.4f}% {p['rank']}" if p["achievement"] is not None else "—"
            options.append(discord.SelectOption(label=f"{p['position']}. {p['title']}"[:100], value=str(p["position"]),
                                                description=f"{short} {p['level']} · {score} · {p['day']} {p['time']}"[:100]))
        menu = discord.ui.Select(placeholder="Open a play in full: judgements and what each note type cost", options=options)
        menu.callback = self._open(menu)
        self.add_item(menu)

    def _open(self, menu: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            cached = cache_get(str(self.owner_id))
            if cached is None:
                await interaction.followup.send("Those results have expired - run the command again.", ephemeral=True)
                return
            try:
                embed, files, view = await build_lastplay(cached, self.owner_id, int(menu.values[0]))
            except Exception as error:
                logger.exception("playlog detail failed")
                await interaction.followup.send(f"Couldn't read that play: {public_reason(error)}", ephemeral=True)
                return
            await interaction.edit_original_response(embed=embed, attachments=files, view=view)
            if view is not None:
                view.message = self.message
        return callback


# ---------------------------------------------------------------- /lastplay

NOTE_ORDER = ("tap", "hold", "slide", "touch", "break")


def lost_text(detail: Dict[str, Any]) -> str:
    """What each note type cost the play, largest first: "break **1.23%** · tap **0.97%**", or "" without judgements.

    :param detail: The play's judgement page.
    :type detail: Dict[str, Any]
    :rtype: str
    """
    lost = note_losses(detail.get("notes") or {}, float(detail.get("achievement") or 0))
    return " · ".join(f"{kind} **{value:.2f}%**" for kind, value in sorted(lost.items(), key=lambda kv: -kv[1]) if value >= 0.005)


def play_detail(cached: CachedAnalysis, idx: str) -> Dict[str, Any]:
    """The judgement page for one play on the recent list, read once and kept with the analysis.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :param idx: The site's own id for the play.
    :type idx: str
    :rtype: Dict[str, Any]
    """
    slot = f"playlog:{idx}"
    detail = cached.extras.get(slot)
    if detail is None:
        a = cached.analyzer
        if getattr(a, "_official_session", None) is None:
            # an analysis loaded from the stored copy has never signed in; the play page needs a session
            account = get_connected_account(cached.user_id)
            if not account or not account.get("token"):
                raise ValueError("Not signed in")
            a.fetch_official_player_profile(str(account["token"]), cached.region)
        detail = a.fetch_playlog_detail(idx, cached.region)
        cached.extras[slot] = detail
    return detail


async def build_lastplay(cached: CachedAnalysis, owner_id: int, position: int) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    a = cached.analyzer
    player = a.player
    plays = recent_plays(cached)
    if not plays:
        embed = discord.Embed(title="No recent plays", description="Nothing on the account's recent-plays list yet.", color=discord.Color.orange())
        return embed, [], None
    position = max(1, min(position, len(plays)))
    play = plays[position - 1]
    detail = await asyncio.to_thread(play_detail, cached, play["idx"])

    card_key = f"playcard:{play['idx']}"
    if card_key not in cached.images:
        cached.images[card_key] = await try_render(play_card_html(
            play, detail, cover_html_factory(a.jacket_path), player.name, cached.start_rating, player.avatar_base64, date_text=today(),
        ))
    files, avatar_url = message_files(player, cached.images[card_key], "rasmai-play.png")
    embed = discord.Embed(
        title=f"{play['title']}",
        url=chart_url(play["title"], play["chart_type"], play["difficulty"], play.get("cover", "")),
        description=(f"**{TIER_NAMES.get(play['difficulty'], play['difficulty'].upper())} {play['level']}** · "
                     f"{play['chart_type'].upper()} · {detail.get('track') or play['track']} · "
                     + (stamp(play["when"], "f") if play["when"] else str(detail.get("played_at") or play["day"]))),
        color=discord.Color.from_rgb(162, 102, 232),
    )
    embed.set_author(name=player.name, icon_url=avatar_url)
    thumb = jacket_file(cached, play["cover"])
    if thumb:
        files.append(thumb)
        embed.set_thumbnail(url=f"attachment://{thumb.filename}")
    achievement = detail.get("achievement") or play["achievement"] or 0.0
    lamp = emoji.lamps(play["fc"], play["fs"])
    shown_rank = rank_for(achievement)
    best = f" {emoji.emoji('pb')} **new best**" if play["pb"] else ""
    embed.add_field(name="Achievement", value=f"**{achievement:.4f}%** {emoji.rank(shown_rank, shown_rank)}{best}" + (f"\n{lamp}" if lamp else ""), inline=True)
    max_dx = detail.get("max_dx_score") or play["max_dx"]
    dx = detail.get("dx_score") or play["dx"]
    stars = stars_for(dx / max_dx) if max_dx else 0
    embed.add_field(name="DX score", value=f"**{dx:,}** / {max_dx:,}\n-# {star_text(stars)} {100.0 * dx / max_dx if max_dx else 0:.1f}%", inline=True)
    embed.add_field(name="Combo", value=f"**{detail.get('combo', 0):,}** / {detail.get('max_combo', 0):,}" + (f"\n-# sync {detail.get('sync', 0):,} / {detail.get('max_sync', 0):,}" if detail.get("max_sync") else ""), inline=True)
    embed.add_field(name="Timing", value=f"fast **{detail.get('fast', 0)}** · late **{detail.get('late', 0)}**", inline=True)
    change = detail.get("rating_change", 0)
    embed.add_field(name="Rating after", value=f"**{detail.get('rating', 0)}** ({change:+d})", inline=True)
    if play["chart_rating"]:
        embed.add_field(name="Chart rating", value=f"**{play['chart_rating']}**" + (" · in best-50" if play["in_b50"] else ""), inline=True)
    notes = detail.get("notes") or {}
    if notes:
        header = f"{'':7s}{'CRIT':>6}{'PERF':>6}{'GREAT':>6}{'GOOD':>6}{'MISS':>6}"
        rows = [header]
        totals = {"critical": 0, "perfect": 0, "great": 0, "good": 0, "miss": 0}
        for kind in NOTE_ORDER:
            n = notes.get(kind)
            if not n:
                continue
            rows.append(f"{kind.upper():7s}{n['critical']:>6}{n['perfect']:>6}{n['great']:>6}{n['good']:>6}{n['miss']:>6}")
            for k in totals:
                totals[k] += n.get(k, 0)
        rows.append(f"{'ALL':7s}{totals['critical']:>6}{totals['perfect']:>6}{totals['great']:>6}{totals['good']:>6}{totals['miss']:>6}")
        cost = lost_text(detail)
        embed.add_field(name="Judgements", value="```\n" + "\n".join(rows) + "\n```" + (f"\n-# lost to {cost}" if cost else ""), inline=False)
    embed.set_footer(text=f"play {position} of {len(plays)} · newest first")
    refs = charts_for(play["title"], a.chart_index)
    return embed, files, LastPlayView(owner_id, position, len(plays), play["title"], page_index(refs, play["chart_type"], play["difficulty"]))


class LastPlayView(OwnerOnlyView):
    def __init__(self, owner_id: int, position: int, total: int, title: str = "", page: Optional[int] = None):
        super().__init__(owner_id, timeout=600)
        self.position, self.total = position, total
        self.title, self.page = title, page
        self.message: Optional[discord.Message] = None
        newer = discord.ui.Button(label="Newer", style=discord.ButtonStyle.primary, disabled=position <= 1)
        newer.callback = self._mover(-1)
        self.add_item(newer)
        older = discord.ui.Button(label="Older", style=discord.ButtonStyle.primary, disabled=position >= total)
        older.callback = self._mover(1)
        self.add_item(older)
        if title:
            for label, build in (("Chart details", build_song), ("Score history", build_song_history)):
                jump = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
                jump.callback = self._jump(build)
                self.add_item(jump)

    def _jump(self, build):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            cached = cache_get(str(self.owner_id))
            try:
                embed, files, view = await build(cached, self.title, self.page, self.owner_id)
            except Exception as error:
                logger.exception("lastplay jump failed")
                await interaction.followup.send(f"Couldn't open that chart: {public_reason(error)}", ephemeral=True)
                return
            await interaction.edit_original_response(embed=embed, attachments=files, view=view)
            if view is not None:
                view.message = self.message
        return callback

    def _mover(self, delta: int):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            cached = cache_get(str(self.owner_id))
            if cached is None:
                await interaction.followup.send("Those results have expired - run the command again.", ephemeral=True)
                return
            try:
                embed, files, view = await build_lastplay(cached, self.owner_id, self.position + delta)
            except Exception as error:
                logger.exception("playlog detail failed")
                await interaction.followup.send(f"Couldn't read that play: {public_reason(error)}", ephemeral=True)
                return
            await interaction.edit_original_response(embed=embed, attachments=files, view=view)
            if view is not None:
                view.message = self.message
        return callback


# ---------------------------------------------------------------- /progress

def _point_before(points: List[Dict[str, Any]], moment: datetime) -> Optional[Dict[str, Any]]:
    best = None
    for p in points:
        try:
            when = datetime.fromisoformat(str(p["recorded_at"]))
        except ValueError:
            continue
        if when <= moment:
            best = p
    return best


async def build_progress(cached: CachedAnalysis) -> Tuple[discord.Embed, List[discord.File], None]:
    from rasmai.bot.builders.results import _image
    a = cached.analyzer
    player = a.player
    points = load_rating_history(cached.user_id)
    embed = discord.Embed(title="Progress", color=discord.Color.from_rgb(240, 192, 74))
    if len(points) < 2:
        files, avatar_url = message_files(player, None, "")
        embed.set_author(name=player.name, icon_url=avatar_url)
        embed.description = (f"Rating **{player.rating}** recorded today as your first reading. "
                             "Every `/analyze` after a session adds a point - come back after your next one to see the line.")
        return embed, files, None
    now = datetime.now()
    latest = points[-1]
    deltas: List[Tuple[str, str]] = []
    for label, reference in (("vs last reading", points[-2]),
                             ("vs 7 days ago", _point_before(points, now - timedelta(days=7))),
                             ("vs 30 days ago", _point_before(points, now - timedelta(days=30))),
                             ("since first", points[0])):
        if reference is None or reference is latest:
            continue
        deltas.append((label, f"{int(latest['rating']) - int(reference['rating']):+d}"))
    forecast = rating_forecast(points, now)
    outlook: List[Tuple[str, str, str]] = []
    forecast_lines: List[str] = []
    if forecast:
        pace = f"{forecast['perWeek']:+.0f} a week"
        if forecast.get("flat"):
            outlook.append(("Pace", "flat", f"over the last {forecast['spanDays']} days"))
            forecast_lines.append(f"Your rating has held flat over the last **{forecast['spanDays']}** days. "
                                  f"`/session` or `/plan` is where the next points are.")
        else:
            outlook.append(("Pace", pace, f"about {forecast['perMonth']:+.0f} a month, over {forecast['spanDays']} days"))
            for target in forecast["targets"][:2]:
                when = datetime.fromisoformat(target["date"])
                outlook.append((str(target["rating"]), when.strftime("%d %b %Y"), f"about {target['days']} days at this pace"))
                forecast_lines.append(f"**{target['rating']}** around {stamp(when, 'D')} at **{pace}**")
    plan = cached.plan_for(None, False, "balanced")
    if plan.steps:
        credits = plan_credits(plan)
        forecast_lines.append(f"the balanced route to **{plan.goal_rating}** is about **{credits}** credits at its odds"
                              + ("" if plan.reached else f", and covers +{plan.total} of the +{plan.needed}"))
    shot = await _image(cached, "progress", lambda: progress_image_html(
        points, deltas, player.name, cached.start_rating, player.avatar_base64, date_text=today(), forecast=outlook,
    ))
    files, avatar_url = message_files(player, shot, "rasmai-progress.png")
    embed.set_author(name=player.name, icon_url=avatar_url)
    first = points[0]
    try:
        since = stamp(datetime.fromisoformat(str(first["recorded_at"])), "D")
    except ValueError:
        since = "the first reading"
    embed.description = (f"**{latest['rating']}** now · **{int(latest['rating']) - int(first['rating']):+d}** since {since} "
                         f"over **{max(0, int(latest['plays']) - int(first['plays']))}** plays · {len(points)} readings")
    for label, value in deltas:
        embed.add_field(name=label, value=f"**{value}**", inline=True)
    embed.add_field(name="Best-50 now", value=f"**{latest['best50']}** · {latest['new_total']} new + {latest['old_total']} old", inline=False)
    if forecast_lines:
        embed.add_field(name="At this pace", value="\n".join(f"- {line}" for line in forecast_lines), inline=False)
    embed.set_footer(text="a reading is taken on every /analyze · the line is in the image")
    return embed, files, None
