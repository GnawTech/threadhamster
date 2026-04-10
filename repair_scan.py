import asyncio
import logging
import os

# Path setup
import sys
from datetime import UTC, datetime

import discord
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db_manager import DBManager
from features.lifespan import resolve_lifespan, should_archive

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RepairScan")


async def main():
    db = DBManager()
    await db.initialize()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True

    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")

        for guild in bot.guilds:
            if guild.id != 1092396673948459113:
                continue

            print(f"\nRepairing Guild: {guild.name}")
            active_threads = await guild.active_threads()
            print(f"Total active threads to check: {len(active_threads)}")

            scanned = 0
            archived = 0
            skipped_forum = 0
            skipped_lifespan = 0
            errors = 0

            for thread in active_threads:
                scanned += 1
                if thread.archived:
                    continue

                # Forum check
                if isinstance(thread.parent, discord.ForumChannel):
                    skipped_forum += 1
                    continue

                try:
                    chan = thread.parent
                    cat = chan.category if chan else None

                    ls = await resolve_lifespan(
                        db,
                        guild.id,
                        thread.id,
                        chan.id if chan else None,
                        cat.id if cat else None,
                    )

                    if ls is None or ls == 0:
                        skipped_lifespan += 1
                        continue

                    last_active = None
                    async for msg in thread.history(limit=1):
                        last_active = msg.created_at

                    if not last_active:
                        last_active = thread.created_at

                    if last_active and should_archive(last_active, ls):
                        print(
                            f"Archiving [{thread.name}] ({thread.id}) - Last active: {last_active} (LS: {ls}d)"
                        )
                        await thread.edit(archived=True, reason="Repair Scan (14d)")
                        archived += 1
                        await asyncio.sleep(1.0)
                    else:
                        pass
                except Exception as e:
                    print(f"Error in thread {thread.id}: {e}")
                    errors += 1

            print(f"\nResults for {guild.name}:")
            print(f" - Scanned: {scanned}")
            print(f" - Would Archive: {archived}")
            print(f" - Skipped (Forum): {skipped_forum}")
            print(f" - Skipped (No Lifespan): {skipped_lifespan}")
            print(f" - Errors: {errors}")

        await bot.close()

    await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    asyncio.run(main())
