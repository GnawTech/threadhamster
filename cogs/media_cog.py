import asyncio
import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.db_manager import DBManager
from utils.media_utils import (
    ACCEPTED_KEYWORDS,
    get_quoted_content,
    has_cw_keyword,
    is_media,
    is_spoiler,
)

logger = logging.getLogger(__name__)


class MediaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DBManager()
        self.check_grace_periods.start()

    def cog_unload(self):
        self.check_grace_periods.cancel()

    @tasks.loop(seconds=60)
    async def check_grace_periods(self):
        """
        Background task to process expired grace periods.
        """
        try:
            expired = await self.db.get_expired_grace_periods()
            for entry in expired:
                try:
                    channel = self.bot.get_channel(entry["channel_id"])
                    if not channel:
                        # Channel might be inaccessible or bot left guild
                        await self.db.remove_grace_period(entry["id"])
                        continue

                    # Attempt to fetch message
                    try:
                        message = await channel.fetch_message(entry["message_id"])
                        if not has_cw_keyword(message.content):
                            # Still missing CW, delete
                            await message.delete()

                            # Try to delete warning message if it exists
                            if (
                                entry.get("warning_msg_id")
                                and entry["warning_msg_id"] > 0
                            ):
                                try:
                                    warning_msg = await channel.fetch_message(
                                        entry["warning_msg_id"]
                                    )
                                    await warning_msg.delete()
                                except:
                                    pass

                            # Send final DM notification
                            user = self.bot.get_user(entry["author_id"])
                            if user:
                                kw_list = ", ".join(
                                    [f"`{kw}`" for kw in ACCEPTED_KEYWORDS]
                                )
                                embed = discord.Embed(
                                    title="Beitrag gelöscht",
                                    description=(
                                        f"Dein Beitrag im Kanal **#{channel.name}** wurde gelöscht, "
                                        f"da auch nach 15 Minuten kein gültiges Schlagwort ergänzt wurde."
                                    ),
                                    color=discord.Color.red(),
                                )
                                embed.add_field(
                                    name="Akzeptierte Schlagworte",
                                    value=kw_list,
                                    inline=False,
                                )
                                embed.add_field(
                                    name="Dein Text",
                                    value=get_quoted_content(message) or "_Kein Text_",
                                    inline=False,
                                )

                                try:
                                    await user.send(embed=embed)
                                except:
                                    pass

                            logger.info(
                                f"Persistent moderation: Deleted message {entry['message_id']} from author {entry['author_id']}"
                            )
                        else:
                            # CW added, cleanup warning if it exists
                            if (
                                entry.get("warning_msg_id")
                                and entry["warning_msg_id"] > 0
                            ):
                                try:
                                    warning_msg = await channel.fetch_message(
                                        entry["warning_msg_id"]
                                    )
                                    await warning_msg.delete()
                                except:
                                    pass
                    except discord.NotFound:
                        # Message already deleted by user, cleanup warning if it exists
                        if entry.get("warning_msg_id") and entry["warning_msg_id"] > 0:
                            try:
                                warning_msg = await channel.fetch_message(
                                    entry["warning_msg_id"]
                                )
                                await warning_msg.delete()
                            except:
                                pass

                    # Always remove from DB after processing
                    await self.db.remove_grace_period(entry["id"])
                except Exception as e:
                    logger.error(
                        f"Error processing grace period entry {entry['id']}: {e}"
                    )
        except Exception as e:
            logger.error(f"Error in check_grace_periods loop: {e}")

    @check_grace_periods.before_loop
    async def before_check_grace_periods(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Only moderate user messages (default or reply).
        # This prevents moderating system messages like "X started a thread".
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        channel_id = message.channel.id

        # Resolve the effective moderation target (Channel or Parent if in Thread)
        is_thread = isinstance(message.channel, discord.Thread)
        is_forum = (
            isinstance(message.channel.parent, discord.ForumChannel)
            if is_thread
            else False
        )

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

        # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
        _, _, _, auto_thread, thread_only, spoiler_only, _ = res

        has_media = is_media(message)

        from features.media import should_moderate_message

        # Moderation Check
        should_delete, reason = should_moderate_message(message, res)

        if should_delete:
            try:
                channel_name = message.channel.name
                await message.delete()

                if reason == "THREAD_ONLY":
                    description = (
                        f"Dein Post im Kanal **#{channel_name}** wurde gelöscht, "
                        f"da dies ein Thread-Only Medien-Kanal ist. Bitte antworte in den entsprechenden Threads."
                    )
                elif reason == "SPOILER_ONLY":
                    description = (
                        f"Dein Beitrag im Kanal **#{channel_name}** wurde gelöscht, "
                        f"da in diesem Kanal alle Bilder/Medien als **Spoiler** markiert sein müssen."
                    )
                else:
                    description = f"Dein Beitrag im Kanal **#{channel_name}** wurde aufgrund einer Moderationsregel gelöscht."

                embed = discord.Embed(
                    title="Beitrag gelöscht",
                    description=description,
                    color=discord.Color.red(),
                )

                if reason == "SPOILER_ONLY":
                    kw_list = ", ".join([f"`{kw}`" for kw in ACCEPTED_KEYWORDS])
                    embed.add_field(
                        name="Anforderung",
                        value="Alle Medien müssen als Spoiler markiert sein und ein CW-Schlagwort enthalten.",
                        inline=False,
                    )
                    embed.add_field(
                        name="Akzeptierte Schlagworte", value=kw_list, inline=False
                    )

                embed.add_field(
                    name="Dein Text",
                    value=get_quoted_content(message) or "_Kein Text_",
                    inline=False,
                )

                try:
                    await message.author.send(embed=embed)
                except discord.Forbidden:
                    pass

                logger.info(f"Moderated message from {message.author} in {channel_name} (Reason: {reason})")
                return
            except Exception as e:
                logger.error(f"Error in media moderation ({reason}): {e}")

        elif reason == "CW_MISSING":
            # CW Grace Period Trigger
            try:
                grace_time = 15
                target_time = datetime.now() + timedelta(minutes=grace_time)
                timestamp = f"<t:{int(target_time.timestamp())}:t>"

                kw_list_full = ", ".join([f"`{kw}`" for kw in ACCEPTED_KEYWORDS])
                embed = discord.Embed(
                    title="Inhaltswarnung (CW) fehlt",
                    description=(
                        f"Deinem Beitrag im Kanal **#{message.channel.name}** fehlt eine Inhaltswarnung (CW).\n\n"
                        f"Bitte bearbeite deinen Beitrag innerhalb der nächsten 15 Minuten und füge eines der akzeptierten Schlagworte sowie eine kurze Beschreibung hinzu.\n"
                        f"Ansonsten muss der Beitrag leider automatisch gelöscht werden."
                    ),
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="Akzeptierte Schlagworte", value=kw_list_full, inline=False
                )
                embed.add_field(
                    name="Frist", value=f"Bis {timestamp}", inline=False
                )

                try:
                    await message.author.send(embed=embed)
                except discord.Forbidden:
                    pass

                await self.db.add_grace_period(
                    message.guild.id,
                    message.channel.id,
                    message.id,
                    message.author.id,
                    0,
                    target_time,
                )
            except Exception as e:
                logger.error(f"Error in CW grace period initialization: {e}")

        # 3. Auto-Thread (Only if not already in a thread)
        if auto_thread and not is_thread:
            # We only auto-thread media posts in thread_only channels,
            # or all posts if thread_only is false but auto_thread is true
            if not thread_only or (thread_only and has_media):
                try:
                    # Check if thread already exists
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

    # Note: Management commands (setup_channel, edit_channel, reset_channel)
    # have been moved to ManageCog as part of the Unified Command Architecture.


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
