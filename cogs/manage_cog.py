import logging
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from database.db_manager import DBManager
from features.manage import (
    get_config_summary,
    parse_context,
    resolve_ambiguity,
    update_settings,
)
from utils.embeds import create_error_embed, create_status_embed, create_success_embed

from .manage_ui import ManageView, SetupModal

logger = logging.getLogger(__name__)


class ManageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DBManager()

    @app_commands.command(
        name="manage",
        description="Zentrales Management-System für Kanäle und Server.",
        default_permissions=discord.Permissions(administrator=True),
    )
    @app_commands.describe(
        aktion="Was möchtest du tun? (Setup, Status, Archiv, Reset, Guild)",
        target="ID oder Name des Kanals (Optional: Standard = aktuell)",
        scope="Bereich: Channel (Standard) oder Guild (Global)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def manage_router(
        self,
        interaction: discord.Interaction,
        aktion: Literal["Setup", "Status", "Archiv", "Reset", "Guild"],
        target: str | None = None,
        scope: Literal["Channel", "Guild"] = "Channel",
    ):
        await interaction.response.defer(ephemeral=True)

        # 1. Resolve Target
        resolved_channel = None
        if target:
            matches = await resolve_ambiguity(interaction.guild, target)
            if not matches:
                return await interaction.followup.send(
                    embed=create_error_embed(
                        "Nicht gefunden", f"Kanal/Thread `{target}` existiert nicht."
                    ),
                    ephemeral=True,
                )
            if len(matches) > 1:
                # Ambiguity Resolver: Listing options (Simplified for now)
                options = "\n".join([f"- {m.name} ({m.id})" for m in matches[:5]])
                return await interaction.followup.send(
                    embed=create_error_embed(
                        "Mehrdeutig",
                        f"Mehrere Übereinstimmungen gefunden:\n{options}\nBitte gib eine eindeutige ID an.",
                    ),
                    ephemeral=True,
                )
            resolved_channel = matches[0]

        ctx = await parse_context(interaction, resolved_channel)

        # 2. Route based on Action
        if aktion == "Status":
            await self._handle_status(interaction, ctx)
        elif aktion == "Setup":
            await self._handle_setup(interaction, ctx)
        elif aktion == "Reset":
            await self._handle_reset(interaction, ctx)
        elif aktion == "Guild":
            await self._handle_guild(interaction)
        elif aktion == "Archiv":
            await self._handle_archives(interaction, ctx)

    async def _handle_status(self, interaction: discord.Interaction, ctx: dict):
        config = await get_config_summary(self.db, ctx["target_id"])
        embed = create_status_embed(ctx["name"], config)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _handle_setup(self, interaction: discord.Interaction, ctx: dict):
        current_config = await get_config_summary(self.db, ctx["target_id"]) or {}

        async def modal_callback(modal_interaction: discord.Interaction, days: int):
            # After getting days, show the View for toggles
            current_config["lifespan"] = days

            async def view_callback(new_settings):
                await update_settings(
                    self.db,
                    ctx["guild_id"],
                    ctx["target_id"],
                    ctx["target_type"],
                    **new_settings,
                )

            view = ManageView(current_config, view_callback)
            await modal_interaction.response.send_message(
                embed=create_status_embed(
                    f"{ctx['name']} (Editierend)", current_config
                ),
                view=view,
                ephemeral=True,
            )

        modal = SetupModal(title=f"Setup: {ctx['name']}", callback=modal_callback)
        # Discord doesn't support opening modals after defer in the same interaction easily
        # But we can try to send it as a followup if it was a button click,
        # however we deferred the MAIN command.
        # Workaround: For the main Setup command, we might need to NOT defer if we want Modal immediately,
        # but slash commands expect defer or answer.
        # Better: Send a message with a button "Start Setup" which opens the Modal.

        await interaction.followup.send(
            "Klicke auf den Button, um den Konfigurations-Dialog zu öffnen.",
            view=SetupButtonView(modal),
            ephemeral=True,
        )

    async def _handle_reset(self, interaction: discord.Interaction, ctx: dict):
        await self.db.remove_target_setting(ctx["target_id"])
        await interaction.followup.send(
            embed=create_success_embed(
                "Reset erfolgreich", f"Regeln für {ctx['mention']} wurden gelöscht."
            ),
            ephemeral=True,
        )

    async def _handle_guild(self, interaction: discord.Interaction):
        # Global Guild Setup (Simplified for now)
        await interaction.followup.send(
            "Globale Server-Einstellungen folgen in Kürze (UCA Phase 2).",
            ephemeral=True,
        )

    async def _handle_archives(self, interaction: discord.Interaction, ctx: dict):
        # We can reuse the LifespanCog's archive view logic or refer to it
        # For now, we manually implement a simplified version or trigger the logic
        cog = self.bot.get_cog("LifespanCog")
        if cog:
            await cog.archives.callback(cog, interaction, channel=ctx["obj"])
        else:
            await interaction.followup.send(
                "Lifespan-Modul nicht geladen.", ephemeral=True
            )


class SetupButtonView(discord.ui.View):
    def __init__(self, modal):
        super().__init__(timeout=60)
        self.modal = modal

    @discord.ui.button(label="Setup starten", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.modal)


async def setup(bot):
    await bot.add_cog(ManageCog(bot))
