import discord
from discord.ext import commands
import logging
from database.db_manager import DBManager
from utils.media_utils import is_media, get_quoted_content

logger = logging.getLogger(__name__)


class MediaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DBManager()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id

        # Check settings for this channel
        res = await self.db.get_target_setting(channel_id)
        if not res:
            return

        _, _, _, auto_thread, thread_only = res

        has_media = is_media(message)

        # 1. Moderation (thread_only)
        if thread_only and not has_media:
            try:
                # Delete and notify
                content = message.content
                channel_name = message.channel.name
                await message.delete()

                dm_msg = (
                    f"Dein Post im Kanal **#{channel_name}** wurde gelöscht, "
                    f"da dies ein Thread-Only Medien-Kanal ist. Bitte antworte in den entsprechenden Threads.\n\n"
                    f"Dein Text:{get_quoted_content(message)}"
                )
                await message.author.send(dm_msg)
                logger.info(
                    f"Deleted non-media post from {message.author} in {channel_name}"
                )
                return  # Don't process further
            except Exception as e:
                logger.error(f"Error in media moderation: {e}")

        # 2. Auto-Thread
        if auto_thread:
            # We only auto-thread media posts in thread_only channels,
            # or all posts if thread_only is false but auto_thread is true
            if not thread_only or (thread_only and has_media):
                try:
                    # Check if thread already exists (though for new messages it shouldn't)
                    if not message.thread:
                        # Use a descriptive title
                        title = f"Diskussion: {message.author.display_name}'s Beitrag"
                        if message.content:
                            title = (
                                (message.content[:30] + "...")
                                if len(message.content) > 30
                                else message.content
                            )

                        await message.create_thread(
                            name=title, auto_archive_duration=10080
                        )  # 1 week archive default
                except Exception as e:
                    logger.error(f"Error creating auto-thread: {e}")


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
