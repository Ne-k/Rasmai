from typing import Optional
import discord

from rasmai.bot.state.cache import forget_analysis
from rasmai.storage.db import delete_connected_account, get_connected_account
from rasmai.security import LOGIN_CODE_TTL


class OwnerOnlyView(discord.ui.View):
    """Components answer only to the user who ran the command."""

    def __init__(self, owner_id: int, *, timeout: Optional[float]):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        """Grey the components out once they stop answering, so a dead button never looks live."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Those buttons belong to someone else - run the command to get your own.", ephemeral=True
            )
            return False
        return True


class LoginView(OwnerOnlyView):
    def __init__(self, owner_id: int, connect_url: str):
        super().__init__(owner_id, timeout=LOGIN_CODE_TTL.total_seconds())
        self.add_item(discord.ui.Button(label="1 · Sign in at my-aime", url="https://my-aime.net/en/"))
        self.add_item(discord.ui.Button(label="2 · Start setup", url=connect_url))
        check = discord.ui.Button(label="Check connection", style=discord.ButtonStyle.success)
        check.callback = self._check
        self.add_item(check)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="This link has expired. Run `/login` for a new one.", embed=None, view=self)
            except discord.HTTPException:
                pass

    def finished(self) -> "LoginView":
        """The view once the link landed: nothing left to press.

        :rtype: 'LoginView'
        """
        self.clear_items()
        self.stop()
        return self

    async def _check(self, interaction: discord.Interaction) -> None:
        account = get_connected_account(str(self.owner_id))
        if account and account.get("token"):
            profile = account.get("officialProfile") or {}
            who = profile.get("name") or "your maimai account"
            await interaction.response.send_message(
                f"Connected as **{who}** ({str(account.get('region', 'intl')).upper()}). Try `/analyze`.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Not connected yet. Finish the steps on the setup page, then check again.", ephemeral=True
            )


class LogoutView(OwnerOnlyView):
    def __init__(self, owner_id: int):
        super().__init__(owner_id, timeout=120)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="Nothing changed. Run `/logout` again if you still want to disconnect.", view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Disconnect", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        delete_connected_account(str(self.owner_id))
        forget_analysis(str(self.owner_id))
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Disconnected. Your session key and cached data are gone.", view=self)

    @discord.ui.button(label="Keep it", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Kept. Nothing changed.", view=self)
