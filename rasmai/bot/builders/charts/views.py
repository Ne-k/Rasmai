from typing import Any, Dict, List, Optional, Tuple
import discord
import logging

from rasmai.engine.analysis import ChartRef
from rasmai.bot.ui.formatting import TIER_SHORT, level_text
from rasmai.bot.ui import emoji
from rasmai.bot.ui.views import OwnerOnlyView
from rasmai.scraping import wiki
from rasmai.bot.builders.charts.song import DIFFICULTY_STYLE, build_song, build_song_details
from rasmai.bot.builders.charts.details import video_button
from rasmai.bot.builders.charts.song_history import build_song_history
from rasmai.security import public_reason

logger = logging.getLogger(__name__)


class SongDetailsView(OwnerOnlyView):
    """One button per chart of the song; each opens that chart's /chart page in place."""

    def __init__(self, owner_id: int, title: str, refs: List[ChartRef], rows: List[Dict[str, Any]],
                 official: Optional[str] = None, wiki_url: str = ""):
        super().__init__(owner_id, timeout=600)
        self.title = title
        if official:
            self.add_item(discord.ui.Button(label="Official video", style=discord.ButtonStyle.link, row=4,
                                            url=wiki.video_url(official)))
        if wiki_url:
            self.add_item(discord.ui.Button(label="Wiki page", style=discord.ButtonStyle.link, row=4, url=wiki_url))
        both_types = len({r.chart_type for r in refs}) > 1
        for index, (ref, row) in enumerate(zip(refs, rows)):
            label = f"{TIER_SHORT.get(ref.difficulty, ref.difficulty[:3].upper())} {level_text(ref.level, ref.constant)}"
            if both_types:
                label += f" {ref.chart_type.upper()}"
            if row.get("played"):
                label += f" · {row['rank']}"
            button = discord.ui.Button(
                label=label[:80], row=index // 5, emoji=emoji.partial(f"diff_{ref.difficulty}"),
                style=DIFFICULTY_STYLE.get(ref.difficulty, discord.ButtonStyle.secondary),
            )
            button.callback = self._opener(index)
            self.add_item(button)

    def _opener(self, page: int):
        async def callback(interaction: discord.Interaction) -> None:
            from rasmai.bot.state.cache import cache_get
            await interaction.response.defer()
            cached = cache_get(str(self.owner_id))
            try:
                embed, files, view = await build_song(cached, self.title, page, self.owner_id)
            except Exception as error:
                logger.exception("song details button failed")
                await interaction.followup.send(f"Couldn't open that chart: {public_reason(error)}", ephemeral=True)
                return
            await interaction.edit_original_response(embed=embed, attachments=files, view=view)
            if view is not None:
                view.message = self.message
        return callback


class SongView(OwnerOnlyView):
    """A button per chart of the song; the one on screen is lit and disabled.

    In history mode the same buttons move between charts' score graphs, and the
    row-4 toggle flips between the chart page and its history."""

    def __init__(self, owner_id: int, title: str, refs: List[ChartRef], rows: List[Dict[str, Any]], page: int,
                 history: bool = False, videos: Optional[Dict[Tuple[str, str], str]] = None, last_play: Optional[int] = None):
        super().__init__(owner_id, timeout=600)
        self.title = title
        self.history = history
        self.page = page
        self.videos = videos or {}
        both_types = len({r.chart_type for r in refs}) > 1
        if len(refs) > 1:
            for index, (ref, row) in enumerate(zip(refs, rows)):
                label = f"{TIER_SHORT.get(ref.difficulty, ref.difficulty[:3].upper())} {level_text(ref.level, ref.constant)}"
                if both_types:
                    label += f" {ref.chart_type.upper()}"
                if row.get("played"):
                    label += f" · {row['rank']}"
                button = discord.ui.Button(
                    label=label[:80], row=index // 5, emoji=emoji.partial(f"diff_{ref.difficulty}"),
                    style=DIFFICULTY_STYLE.get(ref.difficulty, discord.ButtonStyle.secondary),
                    disabled=index == page,
                )
                button.callback = self._switcher(index)
                self.add_item(button)
        toggle = discord.ui.Button(
            label="Chart details" if history else "Score history", row=4,
            style=discord.ButtonStyle.success if history else discord.ButtonStyle.secondary,
            emoji=emoji.partial("up") if not history else None,
        )
        toggle.callback = self._toggle
        self.add_item(toggle)
        overview = discord.ui.Button(label="Song", row=4, style=discord.ButtonStyle.secondary)
        overview.callback = self._overview
        self.add_item(overview)
        if last_play:
            # the chart's newest run on the recent list: judgements, timing, what each note type cost
            recent = discord.ui.Button(label="Last play", row=4, style=discord.ButtonStyle.secondary)
            recent.callback = self._last_play(last_play)
            self.add_item(recent)
        # a link button needs no callback; it opens the chart's video, or a search for one
        self.add_item(video_button(refs[page], self.videos, both_types))

    async def _overview(self, interaction: discord.Interaction) -> None:
        """The song page: artist, BPM, version, every chart with a button to open it."""
        from rasmai.bot.state.cache import cache_get
        await interaction.response.defer()
        cached = cache_get(str(self.owner_id))
        try:
            embed, files, view = await build_song_details(cached, self.title, owner_id=self.owner_id)
        except Exception as error:
            logger.exception("song overview button failed")
            await interaction.followup.send(f"Couldn't open the song: {public_reason(error)}", ephemeral=True)
            return
        await interaction.edit_original_response(embed=embed, attachments=files, view=view)
        if view is not None:
            view.message = self.message

    async def _show(self, interaction: discord.Interaction, page: int, history: bool) -> None:
        from rasmai.bot.state.cache import cache_get
        await interaction.response.defer()
        cached = cache_get(str(self.owner_id))
        try:
            if history:
                embed, files, view = await build_song_history(cached, self.title, page, self.owner_id)
            else:
                embed, files, view = await build_song(cached, self.title, page, self.owner_id)
        except Exception as error:
            logger.exception("song view button failed")
            await interaction.followup.send(f"Couldn't open that chart: {public_reason(error)}", ephemeral=True)
            return
        await interaction.edit_original_response(embed=embed, attachments=files, view=view)
        if view is not None:
            view.message = self.message

    def _switcher(self, page: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self._show(interaction, page, self.history)
        return callback

    def _last_play(self, position: int):
        async def callback(interaction: discord.Interaction) -> None:
            from rasmai.bot.state.cache import cache_get
            from rasmai.bot.builders.history import build_lastplay
            await interaction.response.defer()
            cached = cache_get(str(self.owner_id))
            if cached is None:
                await interaction.followup.send("Those results have expired - run the command again.", ephemeral=True)
                return
            try:
                embed, files, view = await build_lastplay(cached, self.owner_id, position)
            except Exception as error:
                logger.exception("last play button failed")
                await interaction.followup.send(f"Couldn't read that play: {public_reason(error)}", ephemeral=True)
                return
            await interaction.edit_original_response(embed=embed, attachments=files, view=view)
            if view is not None:
                view.message = self.message
        return callback

    async def _toggle(self, interaction: discord.Interaction) -> None:
        await self._show(interaction, self.page, not self.history)
