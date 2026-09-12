from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional
import asyncio
import logging

import discord

from rasmai.bot.ui.formatting import build_login_done_embed, build_login_walkthrough_embed
from rasmai.bot.ui.views import LoginView
from rasmai.security import LOGIN_CODE_TTL
from rasmai.storage.db import get_connected_account
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
    login_info = build_login_session_payload(str(interaction.user.id), region)
    embed = build_login_walkthrough_embed(region, login_info)
    view = LoginView(interaction.user.id, login_info["connectUrl"])
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
    try:
        user = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
        login_info = build_login_session_payload(user_id, region)
        view = LoginView(int(user_id), login_info["connectUrl"])
        message = await user.send(content=intro, embed=build_login_walkthrough_embed(region, login_info), view=view)
    except (discord.HTTPException, ValueError) as error:
        logger.info("login card could not be sent to %s: %s", user_id, error)
        return False
    view.message = message
    asyncio.create_task(watch_login(user_id, view, message.edit))
    return True
