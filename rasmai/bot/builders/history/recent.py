from typing import Any, Dict, List, Optional, Tuple
import logging

import discord

from rasmai.bot.state.cache import CachedAnalysis, cache_get
from rasmai.bot.ui.formatting import TIER_SHORT, _fit, chart_link, level_text, message_files, stamp, today
from rasmai.bot.ui import emoji
from rasmai.bot.ui.views import OwnerOnlyView
from rasmai.security import public_reason
from rasmai.storage.db import count_play_history
from rasmai.images.render import cover_html_factory
from rasmai.images.pages import recent_image_html
from rasmai.bot.builders.history.lastplay import build_lastplay
from rasmai.bot.builders.history.plays import _day_label, _short_day, recent_plays

logger = logging.getLogger(__name__)


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
