from typing import Dict, List, Tuple

import discord

from rasmai.bot.core import bot
from rasmai.config import ADMIN_USER_ID, SUPPORT_INVITE
from rasmai.storage.db import dev_flags_get
from rasmai.web.grants import clean_origin

# these only read text out, so there is nothing in them to switch off
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


def switchable() -> List[str]:
    return sorted(c.name for c in bot.tree.get_commands() if c.name not in NOT_SWITCHABLE)


def parse_bots(text: str) -> Tuple[Dict[str, str], List[str]]:
    """The verified bots typed on the developer page, one a line as ``Name https://its.site``: origin to name, and the lines that are not one.

    :param text: What was typed.
    :type text: str
    :rtype: Tuple[Dict[str, str], List[str]]
    """
    bots, refused = {}, []
    for line in (line.strip() for line in text.splitlines()):
        if not line:
            continue
        name, _space, address = line.rpartition(" ")
        origin = clean_origin(address)
        if name.strip() and origin:
            bots[origin] = name.strip()[:40]
        else:
            refused.append(line[:80])
    return bots, refused
