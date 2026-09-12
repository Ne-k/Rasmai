from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

import discord

from rasmai.engine.insights import plan_credits, rating_forecast
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import message_files, stamp, today
from rasmai.storage.db import load_rating_history
from rasmai.images.pages import progress_image_html

logger = logging.getLogger(__name__)


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
