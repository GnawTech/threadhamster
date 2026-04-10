from collections.abc import Callable
from typing import Any, Optional

import discord


class SetupModal(discord.ui.Modal):
    """Modal for entering numerical lifespan data."""

    lifespan = discord.ui.TextInput(
        label="Lebensdauer (Tage)",
        placeholder="0 = Unendlich",
        default="0",
        min_length=1,
        max_length=3,
    )

    def __init__(self, title: str, callback: Callable):
        super().__init__(title=title)
        self.on_submit_callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.lifespan.value)
            await self.on_submit_callback(interaction, days)
        except ValueError:
            await interaction.response.send_message(
                "Bitte gib eine gültige Zahl ein.", ephemeral=True
            )


class ManageView(discord.ui.View):
    """View with toggles for media and thread settings."""

    def __init__(self, initial_settings: dict[str, Any], callback: Callable):
        super().__init__(timeout=120)
        self.settings = initial_settings
        self.on_change_callback = callback
        self._update_buttons()

    def _update_buttons(self):
        # Find buttons and update labels/colors based on current settings
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "toggle_auto_thread":
                    child.style = (
                        discord.ButtonStyle.green
                        if self.settings.get("auto_thread")
                        else discord.ButtonStyle.gray
                    )
                    child.label = f"Auto-Thread: {'An' if self.settings.get('auto_thread') else 'Aus'}"
                elif child.custom_id == "toggle_thread_only":
                    child.style = (
                        discord.ButtonStyle.green
                        if self.settings.get("thread_only")
                        else discord.ButtonStyle.gray
                    )
                    child.label = f"Thread-Only: {'An' if self.settings.get('thread_only') else 'Aus'}"
                elif child.custom_id == "toggle_spoiler_only":
                    child.style = (
                        discord.ButtonStyle.green
                        if self.settings.get("spoiler_only")
                        else discord.ButtonStyle.gray
                    )
                    child.label = f"Spoiler-Only: {'An' if self.settings.get('spoiler_only') else 'Aus'}"

    @discord.ui.button(label="Auto-Thread", custom_id="toggle_auto_thread")
    async def toggle_auto_thread(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.settings["auto_thread"] = not self.settings.get("auto_thread", False)
        self._update_buttons()
        await interaction.response.edit_message(view=self)
        await self.on_change_callback(self.settings)

    @discord.ui.button(label="Thread-Only", custom_id="toggle_thread_only")
    async def toggle_thread_only(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.settings["thread_only"] = not self.settings.get("thread_only", False)
        self._update_buttons()
        await interaction.response.edit_message(view=self)
        await self.on_change_callback(self.settings)

    @discord.ui.button(label="Spoiler-Only", custom_id="toggle_spoiler_only")
    async def toggle_spoiler_only(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.settings["spoiler_only"] = not self.settings.get("spoiler_only", False)
        self._update_buttons()
        await interaction.response.edit_message(view=self)
        await self.on_change_callback(self.settings)

    @discord.ui.button(label="Fertig", style=discord.ButtonStyle.blurple, row=1)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Einstellungen gespeichert.", ephemeral=True
        )
        self.stop()
