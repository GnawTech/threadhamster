import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="sync",
        description="Synchronisiert die Slash-Commands manuell mit der Discord-API.",
        default_permissions=discord.Permissions(administrator=True),
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"Erfolgreich {len(synced)} Slash-Befehle synchronisiert.",
                ephemeral=True,
            )
            logger.info(f"Manual slash sync performed by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(
                f"Fehler beim Synchronisieren: {e}", ephemeral=True
            )
            logger.error(f"Sync error: {e}")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
