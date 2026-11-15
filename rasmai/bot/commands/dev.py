from typing import List, Optional
import asyncio
import logging

import discord
from discord import app_commands
import requests

from rasmai.bot import core
from rasmai.bot.core import bot
from rasmai.bot.ui.views import OwnerOnlyView
from rasmai.config import ADMIN_USER_ID, CONTROL_GUILD_ID, INTERNAL_API_SECRET, SUPPORT_INVITE, TUNNEL_ORIGIN
from rasmai.storage.db import dev_flags_get, dev_flags_set
from rasmai.web.dashboard.admin import SOURCES, admin_payload, start_update

logger = logging.getLogger(__name__)

_SCOPE = {"guilds": [discord.Object(id=CONTROL_GUILD_ID)]} if CONTROL_GUILD_ID else {}
PANEL_OPEN = 900            # seconds the panel's buttons answer
# these only read text out; a select holds 25 and the bot has more commands than that
NOT_SWITCHABLE = {"help", "invite", "ping", "support"}
MAINTENANCE_SAID = "Rasmai is under maintenance for a moment. Try again in a few minutes."


async def gate(interaction: discord.Interaction) -> bool:
    """Every command passes here first: while maintenance is on, or a command is switched off, everyone but the developer is told so.

    Buttons, menus and autocomplete pass: the command they belong to was let through when it was run.
    """
    if interaction.type is not discord.InteractionType.application_command or str(interaction.user.id) == ADMIN_USER_ID:
        return True
    name = str((interaction.data or {}).get("name", ""))
    flags = dev_flags_get()
    if flags["maintenance"]:
        said = MAINTENANCE_SAID
    elif name in flags["disabled"]:
        said = f"`/{name}` is switched off for a moment while something is being fixed."
    else:
        return True
    # the support server is where the news of it is, and the reply has no cooldown to fall back on
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Support server", style=discord.ButtonStyle.link, url=SUPPORT_INVITE))
    await interaction.response.send_message(said, view=view, ephemeral=True)
    return False


bot.tree.interaction_check = gate


def _hours(seconds: int) -> str:
    return f"{seconds // 86400}d {seconds % 86400 // 3600}h" if seconds >= 86400 else f"{seconds // 3600}h {seconds % 3600 // 60}m"


def switchable() -> List[str]:
    return sorted(c.name for c in bot.tree.get_commands() if c.name not in NOT_SWITCHABLE)[:25]


async def panel_embed() -> discord.Embed:
    """What the bot is doing right now, and which switches are set."""
    from rasmai.bot.tasks import presence
    from rasmai.scraping import news
    try:
        found = await asyncio.wait_for(asyncio.to_thread(admin_payload), 8)
    except Exception:
        logger.exception("the developer panel could not read the bot's state")
        found = {}
    live, flags = found.get("live", {}), dev_flags_get()
    region = core.watch.region
    site = "answering" if core.watch.reachable else f"not answering ({presence._said.get(region) or 'no answer'})"
    accounts = ", ".join(f"{a['region']} {a['count']:,}" + (f" ({a['expired']} expired)" if a["expired"] else "") for a in found.get("accounts", [])) or "none"
    updates = []
    for source in SOURCES:
        state = found.get("updates", {}).get(source) or {}
        updates.append(f"{source}: " + ("running" if state.get("running") else f"{'ok' if state.get('ok') else 'failed'} {state.get('at', '')[11:16]}, {state.get('said', '')}" if state.get("at") else "not run by hand"))
    mirrors = ", ".join(f"{handle} → {news.urlparse(base).hostname}" for handle, base in sorted(news._working.items())) or "no feed read yet"
    embed = discord.Embed(
        title="Rasmai developer panel",
        colour=0xE8A33D if flags["maintenance"] or flags["disabled"] else 0x5B8DEF,
        description=(f"Up {_hours(int(live.get('uptimeSeconds', 0)))} · {live.get('guilds', '?')} servers over {live.get('shards', '?')} shard(s) · {live.get('latencyMs', '?')} ms\n"
                     f"maimai DX NET ({region}): {site}"),
    )
    embed.add_field(name="Accounts", value=accounts, inline=False)
    embed.add_field(name="In flight", value=(f"{live.get('scrapesMax', 0) - live.get('scrapesFree', 0)}/{live.get('scrapesMax', '?')} score reads · "
                                             f"{live.get('rendersMax', 0) - live.get('rendersFree', 0)}/{live.get('rendersMax', '?')} renders · "
                                             f"{live.get('analysesCached', 0)} analyses in memory · {live.get('refreshesRunning', 0)} dashboard refreshes"), inline=False)
    embed.add_field(name="Switches", value=(f"Maintenance: **{'on' if flags['maintenance'] else 'off'}**\n"
                                            f"Switched off: {', '.join(f'`/{n}`' for n in flags['disabled']) or 'nothing'}\n"
                                            f"Expired-account deletion: **{'running' if flags['deletions'] else 'held'}**"
                                            + ("" if flags["deletions"] else ", deadlines move an hour for every hour held")), inline=False)
    embed.add_field(name="Chart databases", value="\n".join(updates), inline=False)
    embed.add_field(name="News mirrors", value=mirrors[:1024], inline=False)
    embed.set_footer(text=f"Only you see this. The buttons answer for {PANEL_OPEN // 60} minutes; Refresh redraws it.")
    return embed


class DevView(OwnerOnlyView):
    """The panel's controls. A restart wants two presses: the first arms the button, the second does it."""

    def __init__(self, owner_id: int):
        super().__init__(owner_id=owner_id, timeout=PANEL_OPEN)
        self.armed = ""
        self.switches = discord.ui.Select(placeholder="Switch commands off", min_values=0, max_values=len(switchable()), row=1)
        self.switches.callback = self.switch
        self.add_item(self.switches)
        self.draw()

    def draw(self) -> None:
        flags = dev_flags_get()
        self.maintenance.label = "Maintenance off" if flags["maintenance"] else "Maintenance on"
        self.maintenance.style = discord.ButtonStyle.success if flags["maintenance"] else discord.ButtonStyle.secondary
        self.deletions.label = "Resume deletions" if not flags["deletions"] else "Hold deletions"
        self.deletions.style = discord.ButtonStyle.success if not flags["deletions"] else discord.ButtonStyle.secondary
        for button, name, label in ((self.restart_bot, "bot", "Restart bot"), (self.restart_site, "site", "Restart website")):
            button.label = f"Confirm: {label.lower()}" if self.armed == name else label
        self.switches.options = [discord.SelectOption(label=f"/{name}", value=name, default=name in flags["disabled"]) for name in switchable()]

    async def redraw(self, interaction: discord.Interaction, note: str = "") -> None:
        self.draw()
        embed = await panel_embed()
        if note:
            embed.add_field(name="Last action", value=note[:1024], inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.armed = ""
        await self.redraw(interaction)

    @discord.ui.button(label="Maintenance on", row=0)
    async def maintenance(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.armed = ""
        now = not dev_flags_get()["maintenance"]
        await asyncio.to_thread(dev_flags_set, maintenance=now)
        logger.warning("maintenance %s by the developer from /dev", "on" if now else "off")
        await self.redraw(interaction, "Maintenance is on: every command answers that Rasmai is under maintenance, and the presence says so within a minute. "
                                       "The website banner is yours to set with /notice." if now else "Maintenance is off: commands answer again.")

    @discord.ui.button(label="Hold deletions", row=0)
    async def deletions(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.armed = ""
        running = not dev_flags_get()["deletions"]
        await asyncio.to_thread(dev_flags_set, deletions=running)
        logger.warning("expired-account deletion %s by the developer from /dev", "resumed" if running else "held")
        await self.redraw(interaction, "Deletions resumed: the hourly sweep warns and deletes again from its next run." if running else
                          "Deletions held: the hourly sweep deletes nobody and sends no warning, and every expired account's deadline moves an hour "
                          "for each hour held, so resuming deletes nobody at once.")

    @discord.ui.button(label="Restart bot", style=discord.ButtonStyle.danger, row=0)
    async def restart_bot(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.armed != "bot":
            self.armed = "bot"
            await self.redraw(interaction, "Press **Confirm: restart bot** to do it. The bot is gone for about a minute; Docker starts it again.")
            return
        logger.warning("restart asked for by the developer from /dev")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Restarting. Run `/dev` again once the bot is back.", embed=None, view=self)
        self.stop()
        # the process ends cleanly, which the container's restart policy answers by starting it again
        asyncio.get_running_loop().call_later(1, lambda: asyncio.ensure_future(bot.close()))

    @discord.ui.button(label="Restart website", style=discord.ButtonStyle.danger, row=2)
    async def restart_site(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.armed != "site":
            self.armed = "site"
            await self.redraw(interaction, "Press **Confirm: restart website** to do it. The site is down for a few seconds; Docker starts it again.")
            return
        self.armed = ""

        def ask() -> str:
            # the site's own address from this side: on the compose network the one the tunnel is pointed at
            try:
                answer = requests.post(f"{TUNNEL_ORIGIN}/api/internal/restart", headers={"X-Rasmai-Internal": INTERNAL_API_SECRET}, timeout=10)
            except requests.RequestException as error:
                return f"The website could not be reached at {TUNNEL_ORIGIN}: {type(error).__name__}."
            if answer.status_code == 200:
                return "The website is restarting. It answers again within about half a minute."
            return f"The website refused (HTTP {answer.status_code}). Both halves must share RASMAI_INTERNAL_SECRET, and the site must carry /api/internal/restart."
        logger.warning("website restart asked for by the developer from /dev")
        await self.redraw(interaction, await asyncio.to_thread(ask))

    async def switch(self, interaction: discord.Interaction) -> None:
        self.armed = ""
        chosen = sorted(self.switches.values)
        await asyncio.to_thread(dev_flags_set, disabled=chosen)
        logger.warning("commands switched off by the developer from /dev: %s", ", ".join(chosen) or "none")
        await self.redraw(interaction, f"Switched off: {', '.join(f'`/{n}`' for n in chosen) or 'nothing'}. Everyone but you is told so when they run one.")

    @discord.ui.button(label="Update charts", row=2)
    async def update_simai(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.update(interaction, "simai")

    @discord.ui.button(label="Update otoge-db", row=2)
    async def update_otoge(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.update(interaction, "otoge")

    async def update(self, interaction: discord.Interaction, source: str) -> None:
        self.armed = ""
        started = start_update(source)
        await self.redraw(interaction, f"The {source} update is running; Refresh shows how it went." if started.get("ok")
                          else f"The {source} update was already running since {started.get('at', '')[11:16]}.")

    @discord.ui.button(label="Sweep expired accounts", row=2)
    async def sweep(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.armed = ""
        await interaction.response.defer()
        await core._expired_account_sweep.coro()
        self.draw()
        embed = await panel_embed()
        embed.add_field(name="Last action", value="The hourly sweep ran now: warnings sent and accounts deleted are in the log, and the expired counts above.", inline=False)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Resync commands", row=2)
    async def resync(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.armed = ""
        await interaction.response.defer()
        marker = core.DATABASE_PATH.parent / "commands.sha256"
        try:
            marker.unlink()       # the sync skips when the definitions match the last sync; without the record they cannot
        except OSError:
            pass
        await core.sync_commands_if_changed()
        self.draw()
        embed = await panel_embed()
        embed.add_field(name="Last action", value="Commands synced with Discord. Global ones can take up to an hour to show everywhere.", inline=False)
        await interaction.edit_original_response(embed=embed, view=self)


async def dev(interaction: discord.Interaction):
    # a guild command is invisible outside its server, but a user-installed bot carries it into DMs, so this line decides
    if not ADMIN_USER_ID or str(interaction.user.id) != ADMIN_USER_ID:
        await interaction.response.send_message("That command is not yours to run.", ephemeral=True)
        return
    view = DevView(interaction.user.id)
    await interaction.response.send_message(embed=await panel_embed(), view=view, ephemeral=True)
    view.message = await interaction.original_response()


if ADMIN_USER_ID:
    dev = bot.tree.command(name="dev", description="The developer panel: state, switches, maintenance and restarts", **_SCOPE)(dev)
