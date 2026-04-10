import asyncio
import os
from datetime import UTC, datetime, timedelta

import discord
from dotenv import load_dotenv

load_dotenv()


async def main():
    intents = discord.Intents.default()
    intents.guilds = True

    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")

        for guild in bot.guilds:
            if guild.id != 1092396673948459113:
                continue

            print(f"\nAnalyzing Guild: {guild.name}")
            active_threads = await guild.active_threads()

            non_forum_threads = []
            for t in active_threads:
                if not isinstance(t.parent, discord.ForumChannel):
                    non_forum_threads.append(t)

            print(f"Non-Forum Active Threads: {len(non_forum_threads)}")

            older_than_14 = 0
            archive_reasons = []

            for thread in non_forum_threads:
                last_msg_at = None
                try:
                    async for msg in thread.history(limit=1):
                        last_msg_at = msg.created_at
                except:
                    pass

                if not last_msg_at:
                    last_msg_at = thread.created_at

                if last_msg_at:
                    delta = datetime.now(UTC) - last_msg_at
                    if delta.days >= 14:
                        older_than_14 += 1
                        if older_than_14 <= 5:
                            print(
                                f"Thread '{thread.name}' ({thread.id}) is {delta.days} days old."
                            )

            print(f"Total threads older than 14 days: {older_than_14}")

        await bot.close()

    await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    asyncio.run(main())
