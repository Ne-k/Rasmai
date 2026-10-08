from typing import Dict, List, Optional
import asyncio
import logging
import time

import aiohttp
import discord
from discord import app_commands

from rasmai.bot.core import bot, cannot_see_channel, news_watch, server_invite_url
from rasmai.bot.tasks.news import NO_MENTIONS, all_sources, load_sources
from rasmai.bot.ui.views import OwnerOnlyView
from rasmai.scraping import news as feeds
from rasmai.scraping.news import SOURCES, Source
from rasmai.storage.db import (
    add_news_source, add_news_subscription, channel_sources, followed_news_source_count, guild_news, news_subscription_count,
    news_webhook, remove_news_subscription, replace_channel_webhook,
)

logger = logging.getLogger(__name__)

MAX_PER_SERVER = 10          # channel-and-account pairs one server may follow, so a server cannot make the bot do unbounded work
MAX_HISTORY = 10             # earlier posts of each account that can be sent on subscribing
HISTORY_SPACING = 300        # seconds a server must leave between two requests for earlier posts: each one is a read, a translation and maybe a video
WEBHOOK_NAME = "Rasmai news"
MENU_TIMEOUT = 600           # seconds a menu answers for
NEWS_COLOR = discord.Color.from_rgb(92, 211, 232)
CHANNEL_TYPES = [discord.ChannelType.text, discord.ChannelType.news]     # the kinds of channel a webhook can post in
MAX_ADDED = 50               # accounts servers added that the bot reads at once: each X one is a Nitter read every few minutes, and those are public servers
MAX_CHOICES = 25             # what one Discord select can list

_history_at: Dict[int, float] = {}

news = app_commands.Group(
    name="news", description="Get maimai news posted in a channel",
    default_permissions=discord.Permissions(manage_webhooks=True),
    # a webhook belongs to a server channel: no DMs, and no user installs, which have no channels to make one in
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
    allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
)


def _name(key: str) -> str:
    source = all_sources().get(key)
    return source.label if source is not None else key


def _names(keys: List[str]) -> str:
    return ", ".join(_name(key) for key in keys) or "nothing"


async def _reply(interaction: discord.Interaction, text: str, view: Optional[discord.ui.View] = None) -> None:
    """Answer only the person who asked, and never let anything in the text ping anyone."""
    options = {"ephemeral": True, "allowed_mentions": NO_MENTIONS}
    if view is not None:
        options["view"] = view
    if interaction.response.is_done():
        await interaction.followup.send(text, **options)
    else:
        await interaction.response.send_message(text, **options)


async def _ask_for_permission(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
    """The bot cannot give itself a permission, so say what to do: a fresh invite link for this server, or the permission by hand."""
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Give Rasmai Manage Webhooks", url=server_invite_url(channel.guild.id, channel.guild.me.guild_permissions)))
    await _reply(
        interaction,
        f"I need **Manage Webhooks** to post news in {channel.mention}. Either:\n"
        "- Someone with **Manage Server** uses the button below to add me again with it (nothing else changes)\n"
        f"- Or give my role **Manage Webhooks** in Server Settings > Roles, or in {channel.mention}'s permissions\n"
        "Then try again.", view)


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
            pass            # deleted by hand
        except discord.HTTPException:
            return existing     # Discord is busy or failing, which says nothing about the webhook
    created = await channel.create_webhook(name=WEBHOOK_NAME, reason="Rasmai news subscription")
    # every row of the channel moves to it, including any sealed under a key this install no longer has, which news_webhook cannot open
    await asyncio.to_thread(replace_channel_webhook, channel_id, created.url)
    return created.url


def _refusal(interaction: discord.Interaction, channel: discord.TextChannel) -> str:
    """Why this person may not do this in this channel, or an empty string."""
    if channel.guild.id != interaction.guild_id:
        return "Pick a channel in this server."
    if not channel.permissions_for(interaction.user).manage_webhooks:      # type: ignore[arg-type]
        return f"You need **Manage Webhooks** in {channel.mention} to do that."
    return ""


async def _drop_webhook(url: Optional[str]) -> None:
    """Delete the webhook a channel was sent news through, now that nothing is left to send there."""
    if url:
        try:
            await discord.Webhook.from_url(url, session=news_watch.session).delete()
        except (discord.HTTPException, ValueError, aiohttp.ClientError, asyncio.TimeoutError):
            pass


async def save_channel(interaction: discord.Interaction, channel: discord.TextChannel, wanted: List[str], previous: int = 0,
                       added: Optional[Dict[str, Source]] = None) -> Optional[str]:
    """Make a channel follow exactly these accounts: start the new ones, stop the ones left out.

    ``added`` holds the accounts typed into the menu, which are kept only once a channel follows them.
    Returns what changed, to show; None when it could not be done, which has been explained to the person already.
    """
    refused = _refusal(interaction, channel)
    if refused:
        await _reply(interaction, refused)
        return None
    guild_id, channel_id = str(interaction.guild_id), str(channel.id)
    already = await asyncio.to_thread(channel_sources, channel_id)
    fresh = [key for key in wanted if key not in already]
    dropped = [key for key in already if key not in wanted]
    if not fresh and not dropped:
        return f"Nothing changed - {channel.mention} already gets {_names(already)}."
    if fresh:
        if not channel.permissions_for(channel.guild.me).manage_webhooks:
            await _ask_for_permission(interaction, channel)
            return None
        wait = HISTORY_SPACING - (time.monotonic() - _history_at.get(interaction.guild_id or 0, float("-inf")))
        if previous and wait > 0:
            await _reply(interaction, f"This server asked for earlier posts a moment ago. Try again in {int(wait // 60) + 1} min, or leave `previous` out.")
            return None
        if await asyncio.to_thread(news_subscription_count, guild_id) - len(dropped) + len(fresh) > MAX_PER_SERVER:
            await _reply(interaction, f"A server can follow up to {MAX_PER_SERVER} accounts across all its channels. Untick some here or in another channel first.")
            return None
        try:
            url = await _webhook_for(channel)
        except discord.Forbidden:
            await _ask_for_permission(interaction, channel)       # the permission was lost between the check and the call, or a channel rule overrides it
            return None
        except discord.HTTPException as error:
            logger.warning("news: making a webhook failed with %s", error.status)
            if error.code == 30007:         # Discord's "maximum number of webhooks reached"
                await _reply(interaction, "That channel already has 15 webhooks, which is Discord's limit. Remove one and try again.")
            else:
                await _reply(interaction, "Discord wouldn't let me make a webhook there - try again in a minute.")
            return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("news: making a webhook failed with %s", type(error).__name__)
            await _reply(interaction, "Couldn't reach Discord - try again in a minute.")
            return None
        for key in fresh:
            if added and key in added:
                source = added[key]
                await asyncio.to_thread(add_news_source, key, source.platform, source.handle, source.did, source.label)
            await asyncio.to_thread(add_news_subscription, guild_id, channel_id, key, url)
        await asyncio.to_thread(load_sources)
    gone = await asyncio.to_thread(news_webhook, channel_id) if not wanted else None       # nothing left to send there, so its webhook goes too
    for key in dropped:
        await asyncio.to_thread(remove_news_subscription, channel_id, key)
    await _drop_webhook(gone)
    lines = []
    if fresh:
        lines.append(f"{channel.mention} now gets {_names(fresh)}.")
    if dropped:
        lines.append(f"{channel.mention} no longer gets {_names(dropped)}.")
    if fresh and previous:
        _history_at[interaction.guild_id or 0] = time.monotonic()
        news_watch.spawn(news_watch.history(channel_id, url, fresh, previous))
        lines.append(f"Sending the last {previous} post(s) from each now.")
        filtered = [key for key in fresh if getattr(all_sources().get(key), "maimai_only", False)]
        if filtered:
            lines[-1] += f" For {_names(filtered)} that's only the maimai ones, same as what gets posted from now on."
    return "\n".join(lines)


async def stop_channel(channel_id: str) -> int:
    """Stop everything a channel follows and delete the webhook it came through; returns how many accounts it was."""
    url = await asyncio.to_thread(news_webhook, channel_id)
    removed = await asyncio.to_thread(remove_news_subscription, channel_id)
    await _drop_webhook(url)
    return removed


class AddAccount(discord.ui.Modal, title="Add an account"):
    """The box an account is typed into: a Bluesky handle, an X username, or a link to either."""

    account = discord.ui.TextInput(label="Bluesky handle or X username", placeholder="someone.bsky.social or @someone", max_length=200)

    def __init__(self, menu: "SubscribeMenu"):
        super().__init__(timeout=MENU_TIMEOUT)
        self.menu = menu

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.menu.add_account(interaction, self.account.value)


class SubscribeMenu(OwnerOnlyView):
    """Where the news goes and from which accounts: a channel, the accounts ticked for it, and Save.

    Picking a channel that already gets news ticks what it follows, so this is also where accounts are switched on and off.
    Besides the built-in accounts it lists the ones this server added, and any typed in with "Add an account".
    """

    def __init__(self, owner_id: int, guild_id: int, following: Dict[str, List[str]], previous: int = 0):
        super().__init__(owner_id, timeout=MENU_TIMEOUT)
        self.guild_id, self.following, self.previous = guild_id, following, previous
        self.channel: Optional[discord.TextChannel] = None
        self.current: List[str] = []
        self.added: Dict[str, Source] = {}      # typed in here and not followed by any channel yet
        self.where = discord.ui.ChannelSelect(placeholder="Pick a channel", channel_types=CHANNEL_TYPES, row=0)
        self.which = discord.ui.Select(placeholder="Pick the accounts", min_values=0, row=1)
        self.save = discord.ui.Button(label="Save", style=discord.ButtonStyle.success, row=2, disabled=True)
        self.test = discord.ui.Button(label="Send a test post", style=discord.ButtonStyle.secondary, row=2, disabled=True)
        self.add = discord.ui.Button(label="Add an account", style=discord.ButtonStyle.secondary, row=2)
        self.where.callback, self.which.callback, self.save.callback, self.test.callback = self.pick_channel, self.pick_accounts, self.submit, self.send_test
        self.add.callback = self.open_add
        for item in (self.where, self.which, self.save, self.test, self.add):
            self.add_item(item)
        self._fill(set(SOURCES))

    def choices(self) -> Dict[str, Source]:
        """The accounts the picker lists: the built-in ones, the ones a channel here follows, and the ones typed in here."""
        known = all_sources()
        here = {key: known[key] for keys in self.following.values() for key in keys if key in known}
        return {**SOURCES, **here, **self.added}

    def _fill(self, ticked: set) -> None:
        self.which.options = [discord.SelectOption(label=source.label[:100], value=key, default=key in ticked)
                              for key, source in list(self.choices().items())[:MAX_CHOICES]]
        self.which.max_values = len(self.which.options)
        self.add.disabled = len(self.which.options) >= MAX_CHOICES

    @property
    def ticked(self) -> List[str]:
        return [option.value for option in self.which.options if option.default]

    def embed(self, note: str = "") -> discord.Embed:
        lines = ["Pick a channel, tick the accounts you want posted there, then hit **Save**. Untick one to stop it."]
        if self.channel is not None:
            lines.append(f"\n{self.channel.mention} currently gets {_names(self.current)}.")
        if note:
            lines.append("\n" + note)
        embed = discord.Embed(title="News", description="\n".join(lines), color=NEWS_COLOR)
        where = [f"<#{cid}>: {_names(keys)}" for cid, keys in self.following.items()]
        embed.add_field(name="Getting news now", value="\n".join(where)[:1024] if where else "No channels yet.", inline=False)
        embed.set_footer(text=f"Bluesky posts show up within a minute and X posts within about 5. They come through a webhook called \"{WEBHOOK_NAME}\".")
        return embed

    async def pick_channel(self, interaction: discord.Interaction) -> None:
        chosen = self.where.values[0]
        channel = interaction.guild.get_channel(chosen.id) if interaction.guild is not None else None
        if channel is None:
            # the picker lists every text channel the person can see, and the bot may not see this one
            message, view = cannot_see_channel(interaction, getattr(chosen, "mention", "that channel"))
            await _reply(interaction, message, view)
            return
        self.channel = channel
        self.current = await asyncio.to_thread(channel_sources, str(channel.id))
        self._fill(set(self.current) or set(SOURCES))       # a channel that gets nothing yet starts with every built-in account ticked
        self.where.default_values = [discord.Object(id=channel.id)]       # it stays shown as picked when the message is redrawn
        self.save.disabled = False
        self.test.disabled = not self.current
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def pick_accounts(self, interaction: discord.Interaction) -> None:
        chosen = set(self.which.values)
        for option in self.which.options:
            option.default = option.value in chosen       # kept, so the ticks survive the message being redrawn
        await interaction.response.defer()

    async def submit(self, interaction: discord.Interaction) -> None:
        if self.channel is None:
            await _reply(interaction, "Pick a channel first.")
            return
        await interaction.response.defer()
        done = await save_channel(interaction, self.channel, self.ticked, self.previous, self.added)
        if done is None:
            return
        self.current = await asyncio.to_thread(channel_sources, str(self.channel.id))
        self.following = await asyncio.to_thread(guild_news, str(self.guild_id))
        self.added = {key: source for key, source in self.added.items() if key not in all_sources()}
        self._fill(set(self.ticked))
        self.test.disabled = not self.current
        await interaction.edit_original_response(embed=self.embed(done), view=self)

    async def open_add(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddAccount(self))

    async def add_account(self, interaction: discord.Interaction, text: str) -> None:
        """Look up an account someone typed and list it, ticked; Save then starts it in the picked channel."""
        await interaction.response.defer()
        try:
            source = await feeds.find_account(news_watch.session, text)
        except Exception:
            logger.exception("news: looking up an account failed")
            source = None
        if source is None:
            await _reply(interaction, "Couldn't find that account. A Bluesky handle looks like `someone.bsky.social`, an X username like `@someone`, "
                                      "and a private X account can't be followed.")
            return
        # an account the bot already has goes by its existing key, so it is read once however it was typed
        same = next((key for key, known in all_sources().items() if known.platform == source.platform
                     and ((source.did and known.did == source.did) or known.handle.lower() == source.handle.lower())), None)
        if same is None and await asyncio.to_thread(followed_news_source_count) >= MAX_ADDED:
            await _reply(interaction, "Rasmai already follows as many extra accounts as it can. Ask in the support server if you need one added.")
            return
        key = same or source.key
        if key not in self.choices():
            self.added[key] = source
        self._fill(set(self.ticked) | {key})
        if key not in {option.value for option in self.which.options}:
            await _reply(interaction, "The list is full - untick and remove some accounts first.")
            return
        where = self.channel.mention if self.channel is not None else "the channel you pick"
        note = f"Added **{_name(key) if same else source.label}** and ticked it. Hit **Save** to start it in {where}."
        await interaction.edit_original_response(embed=self.embed(note), view=self)

    async def send_test(self, interaction: discord.Interaction) -> None:
        """Send the channel the latest post of the first account it follows, so it can be seen working without waiting for news."""
        if self.channel is None or not self.current:
            await _reply(interaction, "Save a channel with at least one account first.")
            return
        refused = _refusal(interaction, self.channel)
        if refused:
            await _reply(interaction, refused)
            return
        # it costs what earlier posts cost, a read, a translation and maybe a video, so it shares their wait
        wait = HISTORY_SPACING - (time.monotonic() - _history_at.get(self.guild_id, float("-inf")))
        if wait > 0:
            await _reply(interaction, f"This server asked for a post a moment ago. Try again in {int(wait // 60) + 1} min.")
            return
        channel_id = str(self.channel.id)
        url = await asyncio.to_thread(news_webhook, channel_id)
        if not url:
            await _reply(interaction, f"{self.channel.mention}'s webhook is gone - hit **Save** to make a new one.")
            return
        _history_at[self.guild_id] = time.monotonic()
        key = self.current[0]
        news_watch.spawn(news_watch.history(channel_id, url, [key], 1))
        await _reply(interaction, f"Sending the latest {_name(key)} post to {self.channel.mention} so you can see how it looks. It can take a moment.")


class UnsubscribeMenu(OwnerOnlyView):
    """Every channel here that gets news and from what, with a picker of channels to stop it in."""

    def __init__(self, owner_id: int, guild: discord.Guild, following: Dict[str, List[str]]):
        super().__init__(owner_id, timeout=MENU_TIMEOUT)
        self.guild, self.following = guild, following
        self.which = discord.ui.Select(placeholder="Pick the channels to stop", row=0)
        self.stop_button = discord.ui.Button(label="Stop news", style=discord.ButtonStyle.danger, row=1, disabled=True)
        self.which.callback, self.stop_button.callback = self.pick, self.submit
        self.add_item(self.which)
        self.add_item(self.stop_button)
        self._fill()

    def _label(self, channel_id: str) -> str:
        channel = self.guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
        return f"#{channel.name}" if channel is not None else "A deleted channel"

    def _fill(self) -> None:
        self.which.options = [discord.SelectOption(label=self._label(cid)[:100], value=cid, description=_names(keys)[:100])
                              for cid, keys in list(self.following.items())[:25]]
        self.which.max_values = max(1, len(self.which.options))
        self.which.disabled = self.stop_button.disabled = not self.which.options
        if not self.which.options:
            self.which.options = [discord.SelectOption(label="Nothing left", value="none")]       # a select needs one, even greyed out

    def embed(self, note: str = "") -> discord.Embed:
        if self.following:
            lines = [f"<#{cid}>: {_names(keys)}" for cid, keys in self.following.items()]
            lines.append("\nPick the channels to stop. To turn single accounts on or off, use `/news subscribe` and pick the channel.")
        else:
            lines = ["No channels here get news right now. Use `/news subscribe` to set one up."]
        if note:
            lines.append("\n" + note)
        return discord.Embed(title="News in this server", description="\n".join(lines), color=NEWS_COLOR)

    async def pick(self, interaction: discord.Interaction) -> None:
        chosen = set(self.which.values)
        for option in self.which.options:
            option.default = option.value in chosen
        self.stop_button.disabled = not chosen
        await interaction.response.edit_message(view=self)

    async def submit(self, interaction: discord.Interaction) -> None:
        chosen = [option.value for option in self.which.options if option.default and option.value in self.following]
        await interaction.response.defer()
        stopped, refused = [], []
        for channel_id in chosen:
            channel = self.guild.get_channel(int(channel_id))
            if channel is not None and _refusal(interaction, channel):      # a deleted channel has nobody to ask, and only its rows are left
                refused.append(f"<#{channel_id}>")
                continue
            await stop_channel(channel_id)
            stopped.append(f"<#{channel_id}>")
        self.following = await asyncio.to_thread(guild_news, str(self.guild.id))
        self._fill()
        note = (f"Stopped news in {', '.join(stopped)}." if stopped else "") + \
               (f" You need **Manage Webhooks** in {', '.join(refused)} to stop it there." if refused else "")
        await interaction.edit_original_response(embed=self.embed(note.strip()), view=self)


# the group's default permission is only where Discord starts: a server can let anyone run the commands in its settings, so it is checked here too
@news.command(name="subscribe", description="Pick a channel and which accounts post maimai news there")
@app_commands.checks.has_permissions(manage_webhooks=True)
@app_commands.describe(previous=f"Earlier posts to send from each newly ticked account, up to {MAX_HISTORY} (default 0)")
async def subscribe(interaction: discord.Interaction, previous: app_commands.Range[int, 0, MAX_HISTORY] = 0):
    await asyncio.to_thread(load_sources)
    following = await asyncio.to_thread(guild_news, str(interaction.guild_id))
    menu = SubscribeMenu(interaction.user.id, interaction.guild_id or 0, following, previous)
    await interaction.response.send_message(embed=menu.embed(), view=menu, ephemeral=True, allowed_mentions=NO_MENTIONS)
    menu.message = await interaction.original_response()


@news.command(name="unsubscribe", description="See which channels get maimai news and stop them")
@app_commands.checks.has_permissions(manage_webhooks=True)
async def unsubscribe(interaction: discord.Interaction):
    await asyncio.to_thread(load_sources)
    following = await asyncio.to_thread(guild_news, str(interaction.guild_id))
    if not following or interaction.guild is None:
        await _reply(interaction, "No channels here get news right now. Use `/news subscribe` to set one up.")
        return
    menu = UnsubscribeMenu(interaction.user.id, interaction.guild, following)
    await interaction.response.send_message(embed=menu.embed(), view=menu, ephemeral=True, allowed_mentions=NO_MENTIONS)
    menu.message = await interaction.original_response()


bot.tree.add_command(news)
