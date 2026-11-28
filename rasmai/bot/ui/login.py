from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, Optional, Tuple
import asyncio
import logging

import discord

from rasmai.bot.ui.formatting import build_kamaitachi_card, build_kamaitachi_done_embed, build_login_done_embed, build_login_walkthrough_pages
from rasmai.bot.ui.views import LoginView
from rasmai.security import LOGIN_CODE_TTL
from rasmai.storage.db import get_connected_account, is_discord_id
from rasmai.web.links import build_login_session_payload

logger = logging.getLogger(__name__)

Edit = Callable[..., Awaitable[object]]


async def watch_login(user_id: str, view: LoginView, edit: Edit, every: float = 5.0) -> None:
    """Turn a login card into a "Connected" card the moment its link is used.

    A link counts only if the account was written after the card was sent, so an older
    link does not pass for this one. Polling stops when the code would have expired; the
    view's own timeout then rewrites the card as expired.

    :param user_id: The Discord user id.
    :type user_id: str
    :param view: The components under the card.
    :type view: LoginView
    :param edit: Edits the card; called with ``embed=`` and ``view=``.
    :type edit: Edit
    :param every: Seconds between looks.
    :type every: float
    """
    started = datetime.now()
    deadline = started + LOGIN_CODE_TTL
    while datetime.now() < deadline and not view.is_finished():
        await asyncio.sleep(every)
        account = await asyncio.to_thread(get_connected_account, user_id)
        if not account or not account.get("token"):
            continue
        try:
            updated = datetime.fromisoformat(str(account.get("updatedAt", "")))
        except ValueError:
            continue
        if updated < started - timedelta(seconds=5):
            continue
        profile = account.get("officialProfile") or {}
        try:
            await edit(content=None,
                       embed=build_login_done_embed(str(profile.get("name") or ""), str(account.get("region", "intl"))),
                       view=view.finished())
        except discord.HTTPException as error:
            logger.info("login card could not be updated: %s", error)
        return


async def send_login_card(interaction: discord.Interaction, region: str = "intl", intro: Optional[str] = None) -> LoginView:
    """Reply to an interaction with the login walkthrough and start watching for the link to land.

    Used by ``/login`` and by any command run without a linked account, so the first thing a
    new player sees is the way in rather than a refusal. The reply is always ephemeral.

    :param interaction: The Discord interaction the command arrived on.
    :type interaction: discord.Interaction
    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :param intro: A line above the card, such as why it is being shown.
    :type intro: Optional[str]
    :rtype: LoginView
    """
    login_info = build_login_session_payload(str(interaction.user.id), region, f"{interaction.user.name} on Discord")
    pages = build_login_walkthrough_pages(region, login_info)
    embed = pages[0]
    view = LoginView(interaction.user.id, login_info["connectUrl"], region, pages)
    if interaction.response.is_done() and interaction.response.type is discord.InteractionResponseType.deferred_channel_message:
        # a public "thinking" placeholder cannot carry the card: the link on it is personal
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
        await interaction.followup.send(content=intro, embed=embed, view=view, ephemeral=True)
    elif interaction.response.is_done():
        await interaction.edit_original_response(content=intro, embed=embed, attachments=[], view=view)
    else:
        await interaction.response.send_message(content=intro, embed=embed, view=view, ephemeral=True)
    try:
        view.message = await interaction.original_response()
    except discord.HTTPException:
        pass
    asyncio.create_task(watch_login(str(interaction.user.id), view, interaction.edit_original_response))
    return view


async def dm_login_card(bot: discord.Client, user_id: str, region: str, intro: str) -> bool:
    """Send the login walkthrough to someone's DMs, for when a background read finds their link dead.

    :param bot: The Discord client.
    :type bot: discord.Client
    :param user_id: The Discord user id.
    :type user_id: str
    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :param intro: The line above the card saying why it arrived.
    :type intro: str
    :returns: Whether the message could be delivered.
    :rtype: bool
    """
    if not is_discord_id(user_id):
        return False          # an account made on the site has no Discord user to message
    try:
        user = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
        login_info = build_login_session_payload(user_id, region, f"{user.name} on Discord")
        pages = build_login_walkthrough_pages(region, login_info)
        view = LoginView(int(user_id), login_info["connectUrl"], region, pages)
        message = await user.send(content=intro, embed=pages[0], view=view)
    except (discord.HTTPException, ValueError) as error:
        logger.info("login card could not be sent to %s: %s", user_id, error)
        return False
    view.message = message
    asyncio.create_task(watch_login(user_id, view, message.edit))
    return True


# Kamaitachi cards still waiting on their link, by Discord id; the site's callback finishes the link, so it tells the card
_kamaitachi_cards: Dict[str, Tuple[discord.Interaction, datetime]] = {}


async def send_kamaitachi_card(interaction: discord.Interaction, url: str) -> None:
    """Reply with the card that links a Kamaitachi profile, and remember it so it can say when the link lands.

    :param interaction: The Discord interaction the command arrived on.
    :type interaction: discord.Interaction
    :param url: Kamaitachi's approval page for this person's link.
    :type url: str
    """
    now = datetime.now()
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Connect Kamaitachi", url=url))
    await interaction.response.send_message(embed=build_kamaitachi_card(now + LOGIN_CODE_TTL), view=view, ephemeral=True)
    for user_id, (_, sent) in list(_kamaitachi_cards.items()):
        if now - sent > LOGIN_CODE_TTL:
            _kamaitachi_cards.pop(user_id, None)
    _kamaitachi_cards[str(interaction.user.id)] = (interaction, now)


def kamaitachi_card_waiting(user_id: str) -> bool:
    """Whether this person has a Kamaitachi card whose link could still be the one just used."""
    held = _kamaitachi_cards.get(user_id)
    return bool(held) and datetime.now() - held[1] <= LOGIN_CODE_TTL


async def kamaitachi_linked(user_id: str, username: str, counts: Dict[str, int]) -> None:
    """Turn a waiting Kamaitachi card into "Connected", or say so by direct message when the card is gone.

    Nothing here can undo the link: with the card dismissed and direct messages closed, the site's own notice is what is left.

    :param user_id: The Discord user id the link was made for.
    :type user_id: str
    :param username: The Kamaitachi username now followed.
    :type username: str
    :param counts: What the first read found, as ``record_pbs`` returns it.
    :type counts: Dict[str, int]
    """
    if not kamaitachi_card_waiting(user_id):
        return
    interaction, _ = _kamaitachi_cards.pop(user_id)
    embed = build_kamaitachi_done_embed(username, counts)
    try:
        await interaction.edit_original_response(embed=embed, view=None)
        return
    except discord.HTTPException as error:
        logger.info("Kamaitachi card could not be updated: %s", error)
    try:
        await interaction.user.send(embed=embed)
    except discord.HTTPException as error:
        logger.info("could not tell %s by direct message that Kamaitachi is connected: %s", user_id, error)
