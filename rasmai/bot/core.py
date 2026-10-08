from discord import app_commands
from discord.app_commands.installs import AppCommandContext, AppInstallationType
from discord.ext import commands, tasks
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Optional, Any
import asyncio
import discord
import hashlib
import json
import logging
import time

from rasmai.bot.ui.emoji import sync_application_emojis
from rasmai.bot.tasks.history_watch import HistoryWatch
from rasmai.bot.tasks.presence import ServerWatch
from rasmai.storage.db.status import SAMPLE_MINUTES
from rasmai.config import (
    CONTROL_GUILD_ID, DATABASE_PATH, EXPIRED_ACCOUNT_DAYS, GUILD_ID, MAX_CONCURRENT_RENDERS, MAX_CONCURRENT_SCRAPES, SCRAPE_WORKERS, SHARD_COUNT, WIKI_VIDEOS,
    support_line,
)
from rasmai.images.render import render_html_to_image
from rasmai.scraping import wiki
from rasmai.scraping.scraper import MaimaiRatingAnalyzer

logger = logging.getLogger(__name__)


intents = discord.Intents.default()


intents.message_content = False


# Sharded from the start so the same process serves any number of servers; Discord
# requires it past 2,500. Nothing here needs member lists or message history, so
# neither is cached.
bot = commands.AutoShardedBot(
    # every command is a slash command; nothing answers to a text prefix, so the bot points at
    # mentions instead. A string prefix here would ask for the message content intent it does not have.
    command_prefix=commands.when_mentioned, intents=intents, shard_count=SHARD_COUNT or None,
    chunk_guilds_at_startup=False, member_cache_flags=discord.MemberCacheFlags.none(), max_messages=None,
    # replies quote titles and typed text; none of it may ever page a server
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False),
)


# every command works in servers, in DMs with the bot, and in group DMs, whether the
# app was added to a server or installed to a Discord account
bot.tree.allowed_contexts = AppCommandContext(guild=True, dm_channel=True, private_channel=True)
bot.tree.allowed_installs = AppInstallationType(guild=True, user=True)


SCRAPE_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)


RENDER_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
STARTED = time.monotonic()                  # for the status page's uptime
RENDER_HEALTH = {"failing": 0}              # renders that failed in a row; the status page calls images broken past a few


# Every blocking call (requests, sqlite, otoge-db updates) runs here through asyncio.to_thread.
# The default pool is sized for the machine's cores; this one is sized for waiting on the network.
EXECUTOR = ThreadPoolExecutor(max_workers=SCRAPE_WORKERS, thread_name_prefix="rasmai")


HEAVY_COOLDOWN_SECONDS = 45.0


def _heavy_bucket(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    """No cooldown while the person's analysis is in memory: a second command then costs nothing to answer."""
    from rasmai.bot.state.cache import cache_get
    if cache_get(str(interaction.user.id)) is not None:
        return None
    return app_commands.Cooldown(1, HEAVY_COOLDOWN_SECONDS)


def heavy_cooldown(command):
    """One cooldown per command, so `/analyze` does not lock `/b50` out for the next 45 seconds.

    discord.py builds the bucket map when the decorator is made, so a shared decorator
    object would share one bucket across every command it was put on."""
    return app_commands.checks.dynamic_cooldown(_heavy_bucket, key=lambda i: i.user.id)(command)


def light_cooldown(command):
    return app_commands.checks.cooldown(1, 4.0, key=lambda i: i.user.id)(command)


def private_only(interaction: discord.Interaction) -> bool:
    """Whether Discord will only accept an ephemeral reply here.

    A user-installed app used in a server it was never added to may answer the
    person who ran the command and nobody else.

    :param interaction: The Discord interaction the command arrived on.
    :type interaction: discord.Interaction
    :rtype: bool
    """
    return interaction.guild is not None and not interaction.is_guild_integration()


async def fetch_snapshot_limited(analyzer: "MaimaiRatingAnalyzer", token: str, region: str, on_progress=None) -> Dict[str, Any]:
    async with SCRAPE_SEMAPHORE:
        return await asyncio.to_thread(analyzer.fetch_official_maimai_snapshot, token, region, on_progress)


async def render_limited(html: str) -> bytes:
    async with RENDER_SEMAPHORE:
        return await render_html_to_image(html)


async def try_render(html: str) -> Optional[bytes]:
    """Render, or log and return None so the command still answers without the image.

    :param html: The page source to read.
    :type html: str
    :rtype: Optional[bytes]
    """
    try:
        shot = await render_limited(html)
    except Exception as error:
        RENDER_HEALTH["failing"] += 1
        logger.error(f"Image render failed; sending text only: {type(error).__name__}: {str(error)[:200]}")
        return None
    RENDER_HEALTH["failing"] = 0
    return shot


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    message = ""
    if isinstance(error, app_commands.CommandOnCooldown):
        message = f"Give it a moment - try again in {error.retry_after:.0f}s."
    elif isinstance(error, app_commands.MissingPermissions):
        message = "That needs the **Manage Server** permission here."
    elif isinstance(error, app_commands.NoPrivateMessage):
        message = "That one only works inside a server."
    if message:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass
        return
    original = getattr(error, "original", error)
    if isinstance(original, discord.NotFound) and original.code == 10062:
        age = (discord.utils.utcnow() - interaction.created_at).total_seconds()
        logger.error("Discord no longer knew the %s interaction %.1fs after it arrived: %s", interaction.command.name if interaction.command else "?",
                     age, "answered too late" if age >= 3 else "another process holding this bot token acknowledged it first")
        return
    logger.error("Command failed", exc_info=error)
    # the person is left looking at a command that did nothing, so say so and say where to ask
    text = f"Something went wrong running that command.\n{support_line()}"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        pass


def command_tree_fingerprint() -> str:
    """Hash of every command's definition, so a sync only happens when something changed.

    :rtype: str
    """
    payload = []
    # the control guild's own commands too, so editing one of those is a change worth syncing
    scopes = [None] + ([discord.Object(id=CONTROL_GUILD_ID)] if CONTROL_GUILD_ID else [])
    for scope in scopes:
        for command in bot.tree.get_commands(guild=scope):
            try:
                payload.append(command.to_dict(bot.tree))
            except TypeError:
                payload.append(command.to_dict())
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _where(installs: Any, contexts: Any) -> tuple:
    """Where a command may be used, as plain flags: installed to a server or an account, and in a server, a DM or a group DM."""
    return (bool(installs and installs.guild), bool(installs and installs.user),
            bool(contexts and contexts.guild), bool(contexts and contexts.dm_channel), bool(contexts and contexts.private_channel))


async def discord_holds_the_tree() -> bool:
    """Whether Discord's global commands are the ones the tree defines: the same names, each usable in the same places.

    The saved fingerprint says what this bot last sent, not what Discord holds now, so anything else that
    rewrote the list (a second copy of the bot on the same token, a sync cut short) would go unnoticed
    and the commands, an account install's most of all, would stay missing across restarts. One read at
    startup settles it. When Discord cannot be asked, the fingerprint is trusted as before.

    :rtype: bool
    """
    def defined(command: Any) -> tuple:
        installs = command.allowed_installs if command.allowed_installs is not None else bot.tree.allowed_installs
        contexts = command.allowed_contexts if command.allowed_contexts is not None else bot.tree.allowed_contexts
        return (command.name, *_where(installs, contexts))

    try:
        held = await bot.tree.fetch_commands()
    except discord.HTTPException as error:
        logger.warning(f"Could not read the registered commands to compare them ({error}); trusting the saved fingerprint")
        return True
    return {(c.name, *_where(c.allowed_installs, c.allowed_contexts)) for c in held} == {defined(c) for c in bot.tree.get_commands()}


async def sync_commands_if_changed() -> None:
    """Register slash commands with Discord, but only when their definitions differ from the last sync."""
    commands_found = bot.tree.get_commands()
    if not commands_found:
        logger.error("The command tree is empty, so nothing will be synced: syncing now would delete every "
                     "registered command. rasmai.bot.commands has not been imported.")
        return
    marker = DATABASE_PATH.parent / "commands.sha256"
    fingerprint = command_tree_fingerprint()
    previous = ""
    try:
        previous = marker.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if previous == fingerprint:
        # the fingerprint matches what was last sent; a guild-only development run never touches the global set, so has nothing to compare
        if GUILD_ID or await discord_holds_the_tree():
            logger.info(f"Slash commands unchanged ({len(bot.tree.get_commands())}), skipping sync")
            return
        logger.warning("Discord's commands differ from the ones defined here although the definitions have not changed; syncing to put them back")

    try:
        if GUILD_ID:
            # one server only: it appears at once and never touches the global set, which is what
            # you want while developing. Showing them everywhere means leaving MAIMAI_GUILD_ID unset.
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} command(s) to guild {GUILD_ID} (instant, this server only)")
        else:
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} global command(s); Discord can take up to an hour to show new ones everywhere")
            if CONTROL_GUILD_ID:
                # the control server's own commands are a separate set, and land there at once
                control = await bot.tree.sync(guild=discord.Object(id=CONTROL_GUILD_ID))
                logger.info(f"Synced {len(control)} command(s) to the control guild {CONTROL_GUILD_ID}")
    except discord.HTTPException as error:
        retry = getattr(error, "retry_after", None)
        logger.error(f"Command sync failed: {error}" + (f" (retry after {retry:.0f}s)" if retry else ""))
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(fingerprint, encoding="utf-8")


def _warm_area_pictures() -> None:
    """Fetch, once, every area picture the stored snapshots name, so no page or embed has to wait for one."""
    from rasmai.scraping.scraper import cache_area_image
    from rasmai.storage.db import stored_area_images
    try:
        fetched = sum(1 for item in stored_area_images() if cache_area_image(item["url"]))
        if fetched:
            logger.info("area pictures: %d in the shared cache", fetched)
    except Exception:
        logger.exception("area picture warm-up failed")


def _read_mai_notes() -> None:
    """mai-notes' chart table (note split and pattern tags), refreshed daily behind an ETag."""
    try:
        from rasmai.scraping import mai_notes
        mai_notes.refresh_charts()
    except Exception:
        logger.exception("mai-notes read failed")


def _read_mai_notes_then_simai() -> None:
    """The manifest first, then the charts it says can be read: the second needs the first."""
    _read_mai_notes()
    _read_simai()


def _read_simai() -> None:
    """The charts themselves, note by note, a batch at a time.

    A chart never changes once published, so this works down the list and then has nothing left to
    do but pick up whatever a new version adds. It runs after mai-notes because it needs the
    manifest to know which charts have a file at all. The notation is kept as it arrives, so when
    what is measured changes, the charts are measured again from here rather than fetched again.
    """
    try:
        from rasmai.scraping import simai
        from rasmai.storage.db import squash_sheets
        packed = squash_sheets()
        if packed:
            logger.info("simai: packed %d charts that were held as plain text", packed)
        simai.remeasure()    # a change to what is measured is answered from the copies already held
        while simai.due():
            if not simai.refresh():
                break        # nothing came back: the site is down, so leave the rest for tomorrow
    except Exception:
        logger.exception("simai read failed")


def _crawl_wiki_areas() -> None:
    """The wiki's area list (English names, reward ladders), refreshed weekly, for /area and the dashboard."""
    try:
        wiki.wiki_areas()
    except Exception:
        logger.exception("wiki area crawl failed")


def _chart_db_upkeep() -> None:
    """Fetch the chart database when it is due and build the shared index from it.

    Runs at start and once a day. The fetch used to happen inside whichever analysis came first
    after the refresh interval, which put a full clone of otoge-db in front of someone's /login.
    """
    try:
        from rasmai.bot.builders.charts.index import refresh_shared_index, shared_index
        from rasmai.scraping.otoge import CachedOtogeDB
        from rasmai.scraping import aliases as party_aliases
        from rasmai.scraping import dxdata
        fetched = CachedOtogeDB().update_if_needed()
        try:
            party_aliases.refresh()          # the names people type instead of a title; search only
        except Exception:
            logger.exception("alias table refresh failed")
        if dxdata.refresh() or fetched:
            refresh_shared_index()
        else:
            shared_index()
    except Exception:
        logger.exception("chart database upkeep failed")


@tasks.loop(hours=24)
async def _chart_db_daily() -> None:
    await asyncio.get_running_loop().run_in_executor(None, _chart_db_upkeep)


def _status_sample() -> None:
    from rasmai.storage.db.status import record_status_sample
    from rasmai.web.statuspage import status_payload
    try:
        record_status_sample(status_payload())
    except Exception:
        logger.exception("recording a status sample failed")


@tasks.loop(minutes=SAMPLE_MINUTES)
async def _status_heartbeat() -> None:
    await asyncio.get_running_loop().run_in_executor(None, _status_sample)


def _purge_expired_accounts() -> None:
    from rasmai.bot.state.forget import forget_user
    from rasmai.storage.db import purge_expired_accounts
    try:
        gone = purge_expired_accounts()
    except Exception:
        logger.exception("deleting accounts whose session expired failed")
        return
    for user_id in gone:
        forget_user(user_id)          # what the running bot holds in memory is their data too
    if gone:
        logger.info("Deleted %d account(s) whose maimai session had been expired for %d days or more",
                    len(gone), EXPIRED_ACCOUNT_DAYS)


async def _warn_expiring_accounts() -> None:
    """DM each owner once, a couple of days before their account is deleted, with a card to link again.

    Discord refuses a DM from someone who shares no server with the bot or has DMs closed; the
    attempt is recorded either way, so a closed inbox is not tried again every hour.
    """
    from rasmai.bot.ui.formatting import stamp
    from rasmai.bot.ui.login import dm_login_card
    from rasmai.storage.db import accounts_to_warn, mark_deletion_warned
    try:
        due = await asyncio.to_thread(accounts_to_warn)
    except Exception:
        logger.exception("listing the accounts to warn about deletion failed")
        return
    sent = 0
    for account in due:
        deletes = datetime.fromisoformat(account["deletesAt"])
        since = datetime.fromisoformat(account["since"])
        intro = (f"**Your Rasmai data will be deleted {stamp(deletes, 'R')}** ({stamp(deletes, 'f')}). maimai DX NET "
                 f"stopped accepting your saved sign-in on {stamp(since, 'D')}, and accounts left unlinked for "
                 f"{EXPIRED_ACCOUNT_DAYS} days are deleted: your scores, play history, judgement pages, rating readings "
                 "and settings. Link again below to keep everything. To have it gone now instead, run `/delete-account`.")
        try:
            if await dm_login_card(bot, account["userId"], account["region"], intro):
                sent += 1
        finally:
            await asyncio.to_thread(mark_deletion_warned, account["userId"])
    if due:
        logger.info("Deletion warnings: %d of %d delivered by DM", sent, len(due))


@tasks.loop(hours=1)
async def _expired_account_sweep() -> None:
    await _warn_expiring_accounts()
    await asyncio.get_running_loop().run_in_executor(None, _purge_expired_accounts)


def _crawl_wiki_titles() -> None:
    try:
        wiki.wiki_titles()
    except Exception as error:       # a wiki outage costs nothing but the aliases
        logger.info("wiki title crawl skipped: %s", error)


async def setup_hook() -> None:
    asyncio.get_running_loop().set_default_executor(EXECUTOR)
    # importing the module is what registers the slash commands: the decorators run on import and
    # nothing refers to it by name afterwards. It is imported here, next to the sync that needs it,
    # so the tree is never empty at sync time and no tidy-up can mistake it for an unused import.
    import rasmai.bot.commands  # noqa: F401
    await sync_commands_if_changed()


bot.setup_hook = setup_hook


watch = ServerWatch(bot)


history_watch = HistoryWatch(bot, watch)


@bot.event
async def on_ready():
    logger.info(
        f"Logged in as {bot.user}: {len(bot.guilds)} server(s) over {bot.shard_count or 1} shard(s); "
        f"up to {MAX_CONCURRENT_SCRAPES} analyses and {MAX_CONCURRENT_RENDERS} renders at once"
    )
    watch.start()
    history_watch.start()
    await sync_application_emojis(bot)
    if not _chart_db_daily.is_running():
        _chart_db_daily.start()      # on_ready fires again after a reconnect; the loop must not
    if not _status_heartbeat.is_running():
        _status_heartbeat.start()    # the same again: one heartbeat however many times Discord reconnects
    if not _expired_account_sweep.is_running():
        _expired_account_sweep.start()   # accounts left expired past the allowance are deleted; once, not per reconnect
    # the chart table, and then the charts themselves: nothing to do with the wiki, so not behind its switch
    asyncio.get_running_loop().run_in_executor(None, _read_mai_notes_then_simai)
    if WIKI_VIDEOS:
        # the wiki's song list gives every Japanese song its English name for search; one crawl a week, off the loop
        asyncio.get_running_loop().run_in_executor(None, _crawl_wiki_titles)
        asyncio.get_running_loop().run_in_executor(None, _crawl_wiki_areas)
        asyncio.get_running_loop().run_in_executor(None, _warm_area_pictures)


@bot.event
async def on_guild_remove(guild: discord.Guild) -> None:
    # A server that removed the bot has no one left to change its switches, and one that adds it
    # back should start from the defaults like any new server.
    from rasmai.storage.db.settings import delete_guild_settings
    try:
        had = await asyncio.to_thread(delete_guild_settings, str(guild.id))
    except Exception:
        logger.exception("Could not clear the settings of server %s after leaving it", guild.id)
        return
    logger.info("Left server %s (%s)%s", guild.id, guild.name, "; its settings are cleared" if had else "")
