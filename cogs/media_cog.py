import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db_manager import DBManager
from utils.media_utils import get_quoted_content, is_media

logger = logging.getLogger(__name__)


class MediaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DBManager()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        channel_id = message.channel.id

        # Resolve the effective moderation target (Channel or Parent if in Thread)
        is_thread = isinstance(message.channel, discord.Thread)
        is_forum = isinstance(message.channel.parent, discord.ForumChannel) if is_thread else False
        
        # We only moderate the parent's settings if:
        # 1. It's a regular channel message.
        # 2. It's the starter message of a Forum thread.
        # In all other cases (replies in threads), we skip thread_only moderation.
        
        target_id = channel_id
        if is_thread:
            if is_forum and message.id == message.channel.id:
                target_id = message.channel.parent.id
            else:
                # Normal thread reply or non-forum thread: skip thread_only enforcement
                # but we still check if auto_thread is needed (unlikely for replies but safe)
                target_id = message.channel.id

        # Check settings for this target
        res = await self.db.get_target_setting(target_id)
        if not res:
            return

        _, _, _, auto_thread, thread_only, _ = res

        has_media = is_media(message)

        # 1. Moderation (thread_only)
        # ONLY enforce thread_only if we are NOT in a thread (unless it's a forum starter)
        should_moderate = not is_thread or (is_forum and message.id == message.channel.id)

        if should_moderate and thread_only and not has_media:
            try:
                # Delete and notify
                channel_name = message.channel.name
                await message.delete()

                dm_msg = (
                    f"Dein Post im Kanal **#{channel_name}** wurde gelöscht, "
                    f"da dies ein Thread-Only Medien-Kanal ist. "
                    f"Bitte antworte in den entsprechenden Threads.\n\n"
                    f"Dein Text:{get_quoted_content(message)}"
                )
                await message.author.send(dm_msg)
                logger.info(
                    f"Deleted non-media post from {message.author} in {channel_name}"
                )
                return  # Don't process further
            except Exception as e:
                logger.error(f"Error in media moderation: {e}")

        # 2. Auto-Thread (Only if not already in a thread)
        if auto_thread and not is_thread:
            # We only auto-thread media posts in thread_only channels,
            # or all posts if thread_only is false but auto_thread is true
            if not thread_only or (thread_only and has_media):
                try:
                    # Check if thread already exists
                    if not message.thread:
                        name = message.author.display_name
                        title = f"Diskussion: {name}'s Beitrag"
                        if message.content:
                            title = (
                                (message.content[:30] + "...")
                                if len(message.content) > 30
                                else message.content
                            )

                        await message.create_thread(
                            name=title, auto_archive_duration=10080
                        )
                except Exception as e:
                    logger.error(f"Error creating auto-thread: {e}")

    @app_commands.command(
        name="setup_channel",
        description="Konfiguriert Medien-Moderation und Auto-Threads.",
    )
    @app_commands.describe(
        auto_thread="Soll automatisch ein Thread erstellt werden?",
        thread_only="Dürfen im Hauptkanal NUR Medien gepostet werden?",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_channel(
        self,
        interaction: discord.Interaction,
        auto_thread: bool = False,
        thread_only: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id

        target_type = "CHANNEL"
        if isinstance(interaction.channel, discord.Thread):
            target_type = "THREAD"

        await self.db.set_target_setting(
            guild_id,
            channel_id,
            target_type,
            auto_thread=auto_thread,
            thread_only=thread_only,
        )

        msg = (
            f"Kanal-Setup abgeschlossen: Auto-Thread: `{auto_thread}`, "
            f"Thread-Only: `{thread_only}`."
        )
        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
