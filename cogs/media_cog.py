import discord
from discord.ext import commands, tasks
import logging
from database.db_manager import DBManager
from utils.media_utils import (
    is_media,
    get_quoted_content,
    is_spoiler,
    has_cw_keyword,
    ACCEPTED_KEYWORDS,
)
from discord import app_commands
import asyncio
from datetime import datetime, timedelta

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

        guild_id = message.guild.id
        channel_id = message.channel.id

        # Only moderate user messages (default or reply).
        # This prevents moderating system messages like "X started a thread".
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        # Check settings for this channel
        res = await self.db.get_target_setting(channel_id)
        if not res:
            return

        # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
        _, _, _, auto_thread, thread_only, spoiler_only, _ = res

        has_media = is_media(message)

        # 1. Moderation (thread_only)
        # Skip this check if we are already in a thread, because text-only is ALLOWED in threads.
        if (
            thread_only
            and not has_media
            and not isinstance(message.channel, discord.Thread)
        ):
            try:
                # Delete and notify
                channel_name = message.channel.name
                await message.delete()

                embed = discord.Embed(
                    title="Beitrag gelöscht",
                    description=(
                        f"Dein Post im Kanal **#{channel_name}** wurde gelöscht, "
                        f"da dies ein Thread-Only Medien-Kanal ist. Bitte antworte in den entsprechenden Threads."
                    ),
                    color=discord.Color.red(),
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

                logger.info(
                    f"Deleted non-media post from {message.author} in {channel_name}"
                )
                return  # Don't process further
            except Exception as e:
                logger.error(f"Error in media moderation (thread_only): {e}")

        # 2. Moderation (spoiler_only)
        if spoiler_only and has_media:
            # Special case for Forum starter messages: Deleting them deletes the whole thread.
            # We allow them if they are in a thread AND it's a ForumChannel parent.
            # Actually, standard spoiler_only should still apply, but maybe be more lenient?
            # For now, we keep it as is, but we could add a check if it's a starter message.

            if not is_spoiler(message):
                try:
                    channel_name = message.channel.name
                    await message.delete()

                    kw_list = ", ".join([f"`{kw}`" for kw in ACCEPTED_KEYWORDS])
                    embed = discord.Embed(
                        title="Beitrag gelöscht",
                        description=(
                            f"Dein Beitrag im Kanal **#{channel_name}** wurde gelöscht, "
                            f"da in diesem Kanal alle Bilder/Medien als **Spoiler** markiert sein müssen."
                        ),
                        color=discord.Color.red(),
                    )
                    embed.add_field(
                        name="Anforderung",
                        value="Alle Medien müssen als Spoiler markiert sein und ein CW-Schlagwort enthalten.",
                        inline=False,
                    )
                    embed.add_field(
                        name="Akzeptierte Schlagworte", value=kw_list, inline=False
                    )
                    embed.add_field(
                        name="Beispiel",
                        value="`[CW: Beschreibung des Inhalts]` oder bei NSFW-Inhalten z.B. den Namen der Kinks",
                        inline=False,
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

                    logger.info(
                        f"Deleted non-spoiler media from {message.author} in {channel_name}"
                    )
                    return
                except Exception as e:
                    logger.error(f"Error in spoiler moderation: {e}")

            elif not has_cw_keyword(message.content):
                try:
                    # Give 15 minutes grace period
                    grace_time = 15
                    target_time = datetime.now() + timedelta(minutes=grace_time)
                    timestamp = f"<t:{int(target_time.timestamp())}:t>"

                    # we NO LONGER send a public warning in the channel.
                    # warning_msg = (...)
                    # warning_msg_obj = await message.channel.send(warning_msg)

                    # Also send a DM to the user as Embed
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
                        name="Empfohlene Darstellung",
                        value="`[CW: Kurze Inhaltsbeschreibung]`\n`[TW: Trigger-Thema]`\n`CW: Beschreibung`",
                        inline=False,
                    )
                    embed.add_field(
                        name="Frist", value=f"Bis {timestamp}", inline=False
                    )

                    try:
                        await message.author.send(embed=embed)
                    except discord.Forbidden:
                        logger.warning(
                            f"Could not send grace period DM to {message.author} (DMs closed)"
                        )

                    # Save to DB for persistence (warning_msg_id is now 0)
                    await self.db.add_grace_period(
                        guild_id,
                        message.channel.id,
                        message.id,
                        message.author.id,
                        0,
                        target_time,
                    )
                except Exception as e:
                    logger.error(f"Error in CW grace period initialization: {e}")

        # 3. Auto-Thread
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

    @app_commands.command(
        name="setup_channel",
        description="Konfiguriert Medien-Moderation und Auto-Threads.",
    )
    @app_commands.describe(
        channel="Der Kanal, der konfiguriert werden soll (Standard: aktuell)",
        auto_thread="Erstellt automatisch einen Thread für jeden Medien-Post",
        thread_only="Erlaubt nur Medien-Posts (Text ohne Medien wird gelöscht)",
        spoiler_only="Erfordert, dass alle Medien als Spoiler markiert sind + CW Schlagwort",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        auto_thread: bool = False,
        thread_only: bool = False,
        spoiler_only: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        target_channel = channel or interaction.channel

        await self.db.set_target_setting(
            guild_id,
            target_channel.id,
            "CHANNEL",
            auto_thread=auto_thread,
            thread_only=thread_only,
            spoiler_only=spoiler_only,
        )

        msg = f"Medien-Einstellungen für {target_channel.mention} konfiguriert:\n"
        msg += f"- Auto-Thread: {'An' if auto_thread else 'Aus'}\n"
        msg += f"- Thread-Only: {'An' if thread_only else 'Aus'}\n"
        msg += f"- Spoiler-Only (+CW): {'An' if spoiler_only else 'Aus'}\n"

        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(
        name="edit_channel",
        description="Ändert einzelne Medien-Einstellungen eines Kanals.",
    )
    @app_commands.describe(
        channel="Der Kanal, der bearbeitet werden soll (Standard: aktuell)",
        auto_thread="Erstellt automatisch einen Thread für jeden Medien-Post",
        thread_only="Erlaubt nur Medien-Posts (Text ohne Medien wird gelöscht)",
        spoiler_only="Erfordert, dass alle Medien als Spoiler markiert sind + CW Schlagwort",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        auto_thread: bool = None,
        thread_only: bool = None,
        spoiler_only: bool = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        target_channel = channel or interaction.channel

        # Validate that at least one value is being changed
        if auto_thread is None and thread_only is None and spoiler_only is None:
            await interaction.followup.send(
                "Bitte gib mindestens einen Parameter an, den du ändern möchtest.",
                ephemeral=True,
            )
            return

        await self.db.set_target_setting(
            guild_id,
            target_channel.id,
            "CHANNEL",
            auto_thread=auto_thread,
            thread_only=thread_only,
            spoiler_only=spoiler_only,
        )

        msg = f"Medien-Einstellungen für {target_channel.mention} wurden angepasst:\n"
        if auto_thread is not None:
            msg += f"- Auto-Thread: {'An' if auto_thread else 'Aus'}\n"
        if thread_only is not None:
            msg += f"- Thread-Only: {'An' if thread_only else 'Aus'}\n"
        if spoiler_only is not None:
            msg += f"- Spoiler-Only (+CW): {'An' if spoiler_only else 'Aus'}\n"

        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(
        name="reset_channel",
        description="Entfernt alle Bot-Einstellungen für einen Kanal (Lifespan + Medien).",
    )
    @app_commands.describe(
        channel="Der Kanal, der zurückgesetzt werden soll (Standard: aktuell)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)
        target_channel = channel or interaction.channel

        await self.db.remove_target_setting(target_channel.id)

        await interaction.followup.send(
            f"Alle Einstellungen für {target_channel.mention} wurden gelöscht. Der Kanal ist nun wieder 'normal'.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
