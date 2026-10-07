from typing import Optional
import asyncio
import logging

import discord
from discord import app_commands

from rasmai.bot.core import bot, news_watch
from rasmai.scraping.news import SOURCES
from rasmai.storage.db import (
    add_news_subscription, channel_sources, news_subscription_count, news_webhook, remove_news_subscription, replace_channel_webhook,
)

logger = logging.getLogger(__name__)

MAX_PER_SERVER = 10          # channel-and-account pairs one server may follow, so a server cannot make the bot do unbounded work
WEBHOOK_NAME = "Rasmai news"

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


def _refusal(interaction: discord.Interaction, channel: discord.TextChannel, bot_needs_webhooks: bool) -> str:
    """Why this person may not do this in this channel, or an empty string."""
    if not channel.permissions_for(interaction.user).manage_webhooks:      # type: ignore[arg-type]
        return f"You need the **Manage Webhooks** permission in {channel.mention} to do that."
    if bot_needs_webhooks and not channel.permissions_for(channel.guild.me).manage_webhooks:
        return f"I need the **Manage Webhooks** permission in {channel.mention} to make the webhook the posts are sent through."
    return ""


@news.command(name="subscribe", description="Post new maimai news in a channel as it appears")
@app_commands.describe(channel="The channel the posts go to", source="Which account to follow; leave it out to follow all three")
@app_commands.choices(source=SOURCE_CHOICES)
async def subscribe(interaction: discord.Interaction, channel: discord.TextChannel, source: Optional[app_commands.Choice[str]] = None):
    refused = _refusal(interaction, channel, bot_needs_webhooks=True)
    if refused:
        await interaction.response.send_message(refused, ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    guild_id, channel_id = str(interaction.guild_id), str(channel.id)
    wanted = [source.value] if source else list(SOURCES)
    already = set(await asyncio.to_thread(channel_sources, channel_id))
    fresh = [key for key in wanted if key not in already]
    if not fresh:
        await interaction.followup.send(f"{channel.mention} already follows " + ", ".join(_name(key) for key in wanted) + ".", ephemeral=True)
        return
    if await asyncio.to_thread(news_subscription_count, guild_id) + len(fresh) > MAX_PER_SERVER:
        await interaction.followup.send(f"A server can follow up to {MAX_PER_SERVER} accounts across its channels. Use `/news unsubscribe` to free some up.", ephemeral=True)
        return
    try:
        url = await _webhook_for(channel)
    except discord.Forbidden:
        await interaction.followup.send(f"I could not make a webhook in {channel.mention}. Give me **Manage Webhooks** there and try again.", ephemeral=True)
        return
    except discord.HTTPException as error:
        logger.warning("news: making a webhook failed with %s", error.status)
        await interaction.followup.send("Discord would not let me make a webhook there (a channel can hold 15). Remove one and try again.", ephemeral=True)
        return
    for key in fresh:
        await asyncio.to_thread(add_news_subscription, guild_id, channel_id, key, url)
    followed = "\n".join(f"- {_name(key)}" for key in fresh)
    await interaction.followup.send(
        f"{channel.mention} now gets:\n{followed}\n"
        "-# Bluesky posts arrive within a minute, X posts within about five. The posts come through a webhook called "
        f"\"{WEBHOOK_NAME}\"; deleting it, or `/news unsubscribe`, stops them.", ephemeral=True)


@news.command(name="unsubscribe", description="Stop posting maimai news in a channel")
@app_commands.describe(channel="The channel to stop posting in", source="Which account to stop; leave it out to stop them all")
@app_commands.choices(source=SOURCE_CHOICES)
async def unsubscribe(interaction: discord.Interaction, channel: discord.TextChannel, source: Optional[app_commands.Choice[str]] = None):
    refused = _refusal(interaction, channel, bot_needs_webhooks=False)
    if refused:
        await interaction.response.send_message(refused, ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    channel_id = str(channel.id)
    url = await asyncio.to_thread(news_webhook, channel_id)
    removed = await asyncio.to_thread(remove_news_subscription, channel_id, source.value if source else None)
    if not removed:
        await interaction.followup.send(f"{channel.mention} was not following " + (_name(source.value) if source else "any account") + ".", ephemeral=True)
        return
    if url and not await asyncio.to_thread(channel_sources, channel_id):
        try:        # nothing is left to send there, so the webhook it was sent through goes too
            await discord.Webhook.from_url(url, session=news_watch.session).delete()
        except (discord.HTTPException, ValueError):
            pass
    await interaction.followup.send(f"{channel.mention} no longer gets " + (_name(source.value) if source else "any of them") + ".", ephemeral=True)


bot.tree.add_command(news)
