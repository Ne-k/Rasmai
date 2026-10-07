from typing import Dict, Optional
import asyncio
import logging
import time

import discord
from discord import app_commands

from rasmai.bot.core import bot, news_watch
from rasmai.bot.tasks.news import NO_MENTIONS
from rasmai.scraping.news import SOURCES
from rasmai.storage.db import (
    add_news_subscription, channel_sources, news_subscription_count, news_webhook, remove_news_subscription, replace_channel_webhook,
)

logger = logging.getLogger(__name__)

MAX_PER_SERVER = 10          # channel-and-account pairs one server may follow, so a server cannot make the bot do unbounded work
MAX_HISTORY = 10             # earlier posts of each account that can be sent on subscribing
HISTORY_SPACING = 300        # seconds a server must leave between two requests for earlier posts: each one is a read, a translation and maybe a video
WEBHOOK_NAME = "Rasmai news"

_history_at: Dict[int, float] = {}

news = app_commands.Group(
    name="news", description="Maimai news from the official accounts, posted in a channel",
    default_permissions=discord.Permissions(manage_webhooks=True),
    # a webhook belongs to a server channel: no DMs, and no user installs, which have no channels to make one in
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
    allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
)

SOURCE_CHOICES = [app_commands.Choice(name=f"{source.label} ({source.platform})", value=source.key) for source in SOURCES.values()]


def _name(key: str) -> str:
    source = SOURCES[key]
    return f"{source.label} ({source.platform})"


async def _reply(interaction: discord.Interaction, text: str, view: Optional[discord.ui.View] = None) -> None:
    """Answer only the person who asked, and never let anything in the text ping anyone."""
    options = {"ephemeral": True, "allowed_mentions": NO_MENTIONS}
    if view is not None:
        options["view"] = view
    if interaction.response.is_done():
        await interaction.followup.send(text, **options)
    else:
        await interaction.response.send_message(text, **options)


def _invite_url(interaction: discord.Interaction, guild: discord.Guild) -> str:
    """A link that adds the bot to this one server again, asking for what it already has plus Manage Webhooks."""
    wanted = discord.Permissions(guild.me.guild_permissions.value)
    wanted.manage_webhooks = True
    return discord.utils.oauth_url(
        interaction.client.application_id, permissions=wanted, guild=discord.Object(id=guild.id),
        scopes=("bot", "applications.commands"), disable_guild_select=True,
    )


async def _ask_for_permission(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
    """The bot cannot give itself a permission, so say what to do: a fresh invite link for this server, or the permission by hand."""
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Give Rasmai Manage Webhooks", url=_invite_url(interaction, channel.guild)))
    await _reply(
        interaction,
        f"I need the **Manage Webhooks** permission to make the webhook the posts are sent through in {channel.mention}. Either:\n"
        "- Someone with **Manage Server** opens the button below. It adds me to this server again with that permission, and nothing else changes.\n"
        f"- Or give my role **Manage Webhooks** in Server Settings > Roles, or in {channel.mention}'s permissions.\n"
        "Then run the command again.", view)


async def _webhook_for(channel: discord.TextChannel) -> str:
    """The webhook URL that posts into this channel: the one already made for it when it still works, otherwise a new one.

    :raises discord.Forbidden: When the bot may not manage webhooks there.
    """
    channel_id = str(channel.id)
    existing = await asyncio.to_thread(news_webhook, channel_id)
    if existing:
        try:
            if (await discord.Webhook.from_url(existing, session=news_watch.session).fetch()).channel_id == channel.id:
                return existing
        except (discord.NotFound, discord.Forbidden, ValueError):
            pass            # deleted by hand, or sealed under a key this install no longer has
    created = await channel.create_webhook(name=WEBHOOK_NAME, reason="Rasmai news subscription")
    if existing:
        await asyncio.to_thread(replace_channel_webhook, channel_id, created.url)
    return created.url


def _refusal(interaction: discord.Interaction, channel: discord.TextChannel) -> str:
    """Why this person may not do this in this channel, or an empty string."""
    if not channel.permissions_for(interaction.user).manage_webhooks:      # type: ignore[arg-type]
        return f"You need the **Manage Webhooks** permission in {channel.mention} to do that."
    return ""


@news.command(name="subscribe", description="Post new maimai news in a channel as it appears")
@app_commands.describe(
    channel="The channel the posts go to", source="Which account to follow; leave it out to follow all three",
    previous=f"How many of each account's earlier posts to send now, up to {MAX_HISTORY} (default 0)",
)
@app_commands.choices(source=SOURCE_CHOICES)
async def subscribe(interaction: discord.Interaction, channel: discord.TextChannel, source: Optional[app_commands.Choice[str]] = None,
                    previous: app_commands.Range[int, 0, MAX_HISTORY] = 0):
    refused = _refusal(interaction, channel)
    if refused:
        await _reply(interaction, refused)
        return
    if not channel.permissions_for(channel.guild.me).manage_webhooks:
        await _ask_for_permission(interaction, channel)
        return
    guild_id, channel_id = str(interaction.guild_id), str(channel.id)
    wait = HISTORY_SPACING - (time.monotonic() - _history_at.get(interaction.guild_id or 0, float("-inf")))
    if previous and wait > 0:
        await _reply(interaction, f"This server asked for earlier posts a moment ago. Try again in {int(wait // 60) + 1} minute(s), or leave `previous` at 0.")
        return
    await interaction.response.defer(ephemeral=True)
    wanted = [source.value] if source else list(SOURCES)
    already = set(await asyncio.to_thread(channel_sources, channel_id))
    fresh = [key for key in wanted if key not in already]
    if not fresh:
        await _reply(interaction, f"{channel.mention} already follows " + ", ".join(_name(key) for key in wanted) + ".")
        return
    if await asyncio.to_thread(news_subscription_count, guild_id) + len(fresh) > MAX_PER_SERVER:
        await _reply(interaction, f"A server can follow up to {MAX_PER_SERVER} accounts across its channels. Use `/news unsubscribe` to free some up.")
        return
    try:
        url = await _webhook_for(channel)
    except discord.Forbidden:
        await _ask_for_permission(interaction, channel)       # the permission was lost between the check and the call, or a channel rule overrides it
        return
    except discord.HTTPException as error:
        logger.warning("news: making a webhook failed with %s", error.status)
        await _reply(interaction, "Discord would not let me make a webhook there (a channel can hold 15). Remove one and try again.")
        return
    for key in fresh:
        await asyncio.to_thread(add_news_subscription, guild_id, channel_id, key, url)
    later = ""
    if previous:
        _history_at[interaction.guild_id or 0] = time.monotonic()
        news_watch.spawn(news_watch.history(channel_id, url, fresh, previous))
        later = f"\nSending the last {previous} post(s) of each now. Bluesky counts only update posts, the kind it will send from here on."
    followed = "\n".join(f"- {_name(key)}" for key in fresh)
    await _reply(
        interaction,
        f"{channel.mention} now gets:\n{followed}{later}\n"
        "-# Bluesky posts arrive within a minute, X posts within about five. The posts come through a webhook called "
        f"\"{WEBHOOK_NAME}\"; deleting it, or `/news unsubscribe`, stops them.")


@news.command(name="unsubscribe", description="Stop posting maimai news in a channel")
@app_commands.describe(channel="The channel to stop posting in", source="Which account to stop; leave it out to stop them all")
@app_commands.choices(source=SOURCE_CHOICES)
async def unsubscribe(interaction: discord.Interaction, channel: discord.TextChannel, source: Optional[app_commands.Choice[str]] = None):
    refused = _refusal(interaction, channel)
    if refused:
        await _reply(interaction, refused)
        return
    await interaction.response.defer(ephemeral=True)
    channel_id = str(channel.id)
    url = await asyncio.to_thread(news_webhook, channel_id)
    removed = await asyncio.to_thread(remove_news_subscription, channel_id, source.value if source else None)
    if not removed:
        await _reply(interaction, f"{channel.mention} was not following " + (_name(source.value) if source else "any account") + ".")
        return
    if url and not await asyncio.to_thread(channel_sources, channel_id):
        try:        # nothing is left to send there, so the webhook it was sent through goes too
            await discord.Webhook.from_url(url, session=news_watch.session).delete()
        except (discord.HTTPException, ValueError):
            pass
    await _reply(interaction, f"{channel.mention} no longer gets " + (_name(source.value) if source else "any of them") + ".")


bot.tree.add_command(news)
