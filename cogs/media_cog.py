import discord
from discord.ext import commands
import logging
from database.db_manager import DBManager
from utils.media_utils import is_media, get_quoted_content, is_spoiler, has_cw_keyword
from discord import app_commands
import asyncio
from datetime import datetime, timedelta

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

        # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
        _, _, _, auto_thread, thread_only, spoiler_only, _ = res

        has_media = is_media(message)

        # 1. Moderation (thread_only)
        if thread_only and not has_media:
            try:
                # Delete and notify
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
                logger.error(f"Error in media moderation (thread_only): {e}")

        # 2. Moderation (spoiler_only)
        if spoiler_only and has_media:
            if not is_spoiler(message):
                try:
                    channel_name = message.channel.name
                    await message.delete()

                    dm_msg = (
                        f"Dein Beitrag im Kanal **#{channel_name}** wurde gelöscht, "
                        f"da in diesem Kanal alle Bilder/Medien als **Spoiler** markiert sein müssen.\n\n"
                        f"Zusätzlich muss eine Inhaltswarnung (CW) angegeben werden, in der du kurz beschreibst, was auf dem Bild zu sehen ist "
                        f"(z.B. `[Contentwarning: Beschreibung des Inhalts]` oder bei NSFW-Inhalten z.B. den Namen der Kinks).\n\n"
                        f"Dein Text:{get_quoted_content(message)}"
                    )
                    # Note: We can't really re-send the files easily as spoilers via DM without re-uploading,
                    # but we can at least send the links/text.
                    await message.author.send(dm_msg)
                    logger.info(f"Deleted non-spoiler media from {message.author} in {channel_name}")
                    return
                except Exception as e:
                    logger.error(f"Error in spoiler moderation: {e}")

            elif not has_cw_keyword(message.content):
                try:
                    # Give 15 minutes grace period
                    grace_time = 15
                    target_time = datetime.now() + timedelta(minutes=grace_time)
                    timestamp = f"<t:{int(target_time.timestamp())}:t>"

                    warning_msg = (
                        f"{message.author.mention}, deinem Beitrag fehlt eines der notwendigen Schlagworte "
                        f"(z.B. `Contentwarning`, `CW`, `Inhaltswarnung`). "
                        f"Bitte füge es nach.\nDu hast dafür bis {timestamp} Zeit. "
                        f"Danach wird der Beitrag gelöscht."
                    )
                    warning_msg_obj = await message.channel.send(warning_msg)

                    # Wait 15 minutes
                    await asyncio.sleep(grace_time * 60)

                    # Re-fetch message to check for edits
                    try:
                        refetched_msg = await message.channel.fetch_message(message.id)
                        if not has_cw_keyword(refetched_msg.content):
                            # Still no keyword, delete
                            await refetched_msg.delete()
                            await warning_msg_obj.delete()

                            dm_msg = (
                                f"Dein Beitrag im Kanal **#{message.channel.name}** wurde gelöscht, "
                                f"da auch nach 15 Minuten kein gültiges Schlagwort (CW) mit einer kurzen Inhaltsbeschreibung ergänzt wurde.\n\n"
                                f"Dein Text:{get_quoted_content(message)}"
                            )
                            await message.author.send(dm_msg)
                            logger.info(f"Deleted media after grace period from {message.author}")
                        else:
                            # Keyword added, delete warning message
                            await warning_msg_obj.delete()
                    except discord.NotFound:
                        # Message was already deleted by user
                        try:
                            await warning_msg_obj.delete()
                        except:
                            pass
                except Exception as e:
                    logger.error(f"Error in CW grace period: {e}")

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
            await interaction.followup.send("Bitte gib mindestens einen Parameter an, den du ändern möchtest.", ephemeral=True)
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
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
