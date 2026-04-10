import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database.db_manager import DBManager

# Basic logging setup (following Limithamster pattern)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThreadHamster(commands.Bot):
    """
    Core Bot class for ThreadHamster.
    Handles cog loading and multi-server configuration.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            status=discord.Status.invisible,
        )

        self.db = DBManager()
        self.batch_processor = None

    async def setup_hook(self):
        """
        Initializes the database, starts the batch processor, and loads cogs.
        """
        logger.info("Initializing setup_hook...")

        # Initialize Database
        await self.db.initialize()

        # Initialize Batch Processor
        from features.batch import BatchProcessor

        self.batch_processor = BatchProcessor(self, self.db)
        await self.batch_processor.start()

        # Load Extensions
        cogs = [
            "cogs.lifespan_cog",
            "cogs.media_cog",
            "cogs.admin_cog",
            "cogs.manage_cog",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}")

    async def on_ready(self):
        await self.change_presence(status=discord.Status.invisible)
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot status set to invisible.")
        logger.info("------")


async def main():
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN not found in environment variables.")
        return

    bot = ThreadHamster()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
