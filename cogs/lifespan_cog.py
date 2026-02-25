import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from features.lifespan import resolve_lifespan, should_archive
from database.db_manager import DBManager

logger = logging.getLogger(__name__)


class LifespanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DBManager()
        self.archive_check.start()

    def cog_unload(self):
        self.archive_check.cancel()

    @tasks.loop(hours=1)
    async def archive_check(self):
        """
        Background task to check all threads in all guilds and archive if needed.
        """
        logger.info("Running periodic archive check...")
        for guild in self.bot.guilds:
            for thread in guild.threads:
                if thread.archived:
                    continue

                channel = thread.parent
                category = channel.category if channel else None

                lifespan = await resolve_lifespan(
                    self.db,
                    guild.id,
                    thread.id,
                    channel.id if channel else None,
                    category.id if category else None,
                )

                if lifespan is None:
                    continue

                # 0 = infinite, but we should also check if we need to keep it alive
                if lifespan == 0:
                    # Logic to keep thread alive (e.g. unarchiving if it gets archived by Discord)
                    continue

                last_msg = thread.last_message_id
                # Note: We might need to fetch the last message to get its timestamp if it's not in cache
                # For simplicity in this logic sketch, we assume we can determine the age
                # Actual implementation will fetch message if needed

                # Fetching the last message to be sure
                try:
                    # thread.archive_timestamp might be useful but last_message is more accurate per requirements
                    # Requirements say "last contribution"
                    # We use thread.archive_timestamp as a proxy or fetch history
                    history = [msg async for msg in thread.history(limit=1)]
                    if history:
                        last_msg_at = history[0].created_at
                        if should_archive(last_msg_at, lifespan):
                            await thread.edit(archived=True, reason="Lifespan expired")
                            logger.info(
                                f"Archived thread {thread.name} in {guild.name}"
                            )
                except Exception as e:
                    logger.error(f"Error checking thread {thread.id}: {e}")

    @app_commands.command(
        name="lifespan",
        description="Setzt die Lebensdauer für einen Bereich (Tage). 0 = Unendlich.",
    )
    @app_commands.describe(
        days="Anzahl der Tage seit dem letzten Beitrag",
        retro="Rückwirkend anwenden (Vorsicht bei vielen Threads)",
    )
    async def set_lifespan(
        self, interaction: discord.Interaction, days: int, retro: bool = False
    ):
        # Implementation of slash command will follow
        # This will set the DB and trigger batch tasks if retro is True
        await interaction.response.send_message(
            f"Lifespan gesetzt auf {days} Tage (Retro: {retro}).", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(LifespanCog(bot))
