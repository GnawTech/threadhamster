import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.db_manager import DBManager
from features.lifespan import resolve_lifespan, should_archive

logger = logging.getLogger(__name__)


class ArchiveView(discord.ui.View):
    """View for paginated archive list."""

    def __init__(
        self, threads: list[discord.Thread], title: str, user_id: int, page: int = 0
    ):
        super().__init__(timeout=60)
        self.threads = threads
        self.title = title
        self.user_id = user_id
        self.page = page
        self.per_page = 10

    def create_embed(self) -> discord.Embed:
        start = self.page * self.per_page
        end = start + self.per_page
        current = self.threads[start:end]
        total_pages = (len(self.threads) - 1) // self.per_page + 1

        embed = discord.Embed(
            title=f"Archivierte Threads: {self.title}",
            color=discord.Color.blue(),
            description=f"Seite {self.page + 1} von {total_pages}",
        )

        if not current:
            embed.description = "Keine archivierten Threads gefunden."
        else:
            for thread in current:
                archive_at = thread.archive_timestamp
                at_str = archive_at.strftime("%d.%m.%Y") if archive_at else "?"
                embed.add_field(
                    name=thread.name,
                    value=f"ID: {thread.id} | Archiviert: {at_str}\n[Link]({thread.jump_url})",
                    inline=False,
                )
        return embed

    @discord.ui.button(label="◀ Zurück", style=discord.ButtonStyle.gray)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "Nicht dein Menü.", ephemeral=True
            )
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(
                embed=self.create_embed(), view=self
            )

    @discord.ui.button(label="Weiter ▶", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "Nicht dein Menü.", ephemeral=True
            )
        if (self.page + 1) * self.per_page < len(self.threads):
            self.page += 1
            await interaction.response.edit_message(
                embed=self.create_embed(), view=self
            )


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
        Periodic task to:
        1. Archive threads whose lifespan expired.
        2. Unarchive (Keepalive) threads that were auto-archived too early.
        """
        await self.bot.wait_until_ready()
        logger.info("Running periodic archive/keepalive check...")
        for guild in self.bot.guilds:
            try:
                # guild.threads gives active threads. We don't fetch archived ones here
                # because it's too expensive hourly. on_thread_update handles keepalive.
                threads = await guild.active_threads()
            except Exception as e:
                logger.error(
                    f"Failed to fetch active threads for guild {guild.id}: {e}"
                )
                continue

            for thread in threads:
                # Normal Archiving Logic
                chan = thread.parent
                if isinstance(chan, discord.ForumChannel):
                    continue  # Protect forums from archival

                cat = chan.category if chan else None
                lifespan = await resolve_lifespan(
                    self.db,
                    guild.id,
                    thread.id,
                    chan.id if chan else None,
                    cat.id if cat else None,
                )

                if lifespan is None or lifespan == 0:
                    continue

                try:
                    history = [msg async for msg in thread.history(limit=1)]
                    if history:
                        last_msg_at = history[0].created_at
                        if should_archive(last_msg_at, lifespan):
                            await thread.edit(archived=True, reason="Lifespan expired")
                            logger.info(f"Archived thread {thread.id}")
                except Exception as e:
                    logger.error(f"Error checking thread {thread.id}: {e}")

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        """
        Detects when a thread is archived and unarchives it if its lifespan
        hasn't expired yet (Keepalive).
        Respects manual archival by admins using Audit Logs.
        """
        guild_id = after.guild.id
        chan = after.parent
        cat = chan.category if chan else None

        # Case 1: Thread was archived
        if not before.archived and after.archived:
            if isinstance(chan, discord.ForumChannel):
                return  # We don't touch forums, even for keepalive (user manual archive is fine)

            # Check Audit Log to see if a human did it
            try:
                await asyncio.sleep(1.5)  # Wait for audit log to propagate
                manual = False
                async for entry in after.guild.audit_logs(
                    action=discord.AuditLogAction.thread_update, limit=5
                ):
                    if entry.target.id == after.id:
                        # Check if 'archived' was changed to True by a user (not bot)
                        if (
                            hasattr(entry.after, "archived")
                            and entry.after.archived is True
                        ):
                            if entry.user.id != self.bot.user.id:
                                manual = True
                                break

                if manual:
                    logger.info(
                        f"Thread {after.id} manually archived by {entry.user}. Flag in DB."
                    )
                    await self.db.set_target_setting(
                        guild_id, after.id, "THREAD", manually_archived=True
                    )
                    return  # Respect manual archival

            except Exception as e:
                logger.error(f"Audit log check error for {after.id}: {e}")

            # Discord Auto-Archival: Check lifespan
            ls = await resolve_lifespan(
                self.db,
                guild_id,
                after.id,
                chan.id if chan else None,
                cat.id if cat else None,
            )

            if ls is not None:
                try:
                    history = [msg async for msg in after.history(limit=1)]
                    last_msg_at = history[0].created_at if history else after.created_at

                    if ls == 0 or not should_archive(last_msg_at, ls):
                        await after.edit(archived=False, reason="Keepalive")
                        logger.info(f"Keepalive: Instantly unarchived {after.id}")
                except Exception as e:
                    logger.error(f"Keepalive event error for {after.id}: {e}")

        # Case 2: Thread was unarchived (active again)
        elif before.archived and not after.archived:
            # Reset manual flag since it's active again
            await self.db.set_target_setting(
                guild_id, after.id, "THREAD", manually_archived=False
            )
            logger.info(f"Thread {after.id} is active again. Resetting manual flag.")

    # Note: Management commands (lifespan, setup_guild, archives)
    # have been moved to ManageCog as part of the Unified Command Architecture.


async def setup(bot):
    await bot.add_cog(LifespanCog(bot))
