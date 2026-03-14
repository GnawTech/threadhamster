import asyncio
import json
import logging

import discord

from database.db_manager import DBManager

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Manages long-running tasks with rate limiting.
    Processes items from a queue and respects Discord API limits.
    """

    def __init__(self, bot, db: DBManager):
        self.bot = bot
        self.db = db
        self.queue = asyncio.Queue()
        self.is_running = False

    async def start(self):
        if self.is_running:
            return
        self.is_running = True

        # Load pending tasks from DB
        pending = await self.db.get_pending_batch_tasks()
        for t in pending:
            await self.queue.put(t)
        if pending:
            logger.info(f"Loaded {len(pending)} pending tasks from database.")

        asyncio.create_task(self._process_loop())

    async def _process_loop(self):
        logger.info("Batch processor loop started. Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        
        # Give it a few seconds for the cache to actually populate guilds
        await asyncio.sleep(5)
        logger.info(f"Bot is ready. Guilds found: {len(self.bot.guilds)}. Processing queue...")

        while self.is_running:
            task = await self.queue.get()
            task_id = task.get("id")
            try:
                await self._handle_task(task)
                if task_id:
                    await self.db.update_batch_task_status(task_id, "COMPLETED")
            except Exception as e:
                logger.error(f"Error in batch task {task_id}: {e}")
                if task_id:
                    await self.db.update_batch_task_status(task_id, "FAILED")
            finally:
                self.queue.task_done()
                # Configurable delay to avoid rate limits
                await asyncio.sleep(0.1)

    async def _handle_task(self, task):
        task_type = task.get("type")
        payload = task.get("payload")
        guild_id = task.get("guild_id")

        guild = self.bot.get_guild(guild_id)
        if not guild:
            # Try one more time with fetch if get fails
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except:
                logger.warning(f"Task {task.get('id')}: Guild {guild_id} not found after fetch.")
                return

        if task_type == "RETRO_ARCHIVE":
            target_id = payload.get("target_id")
            lifespan = payload.get("lifespan")
            if lifespan == 0:
                return

            from features.lifespan import resolve_lifespan, should_archive

            threads_to_check = []
            if target_id is None:
                # Global guild-wide scan
                threads_to_check = await guild.active_threads()
            else:
                # Targeted scan
                target_obj = self.bot.get_channel(target_id)
                if not target_obj:
                    # Might be a thread itself that we need to fetch
                    try:
                        target_obj = await self.bot.fetch_channel(target_id)
                    except:
                        pass

                if isinstance(target_obj, discord.Thread):
                    threads_to_check = [target_obj]
                elif isinstance(target_obj, discord.TextChannel):
                    threads_to_check = await target_obj.active_threads()
                elif isinstance(target_obj, discord.CategoryChannel):
                    for chan in target_obj.channels:
                        if isinstance(chan, discord.TextChannel):
                            threads_to_check.extend(await chan.active_threads())
                elif isinstance(target_obj, discord.ForumChannel):
                    # We still check them to ensure they are skipped properly in the next loop
                    threads_to_check = await target_obj.active_threads()

            for thread in threads_to_check:
                if thread.archived:
                    continue
                
                # Exclusion rule: Forums are NEVER auto-archived by this bot
                if isinstance(thread.parent, discord.ForumChannel):
                    continue

                try:
                    # Resolve real lifespan for this thread to respect hierarchy
                    chan = thread.parent
                    cat = chan.category if chan else None
                    current_l = await resolve_lifespan(
                        self.db,
                        guild_id,
                        thread.id,
                        chan.id if chan else None,
                        cat.id if cat else None,
                    )

                    if current_l and current_l > 0:
                        last_active = None
                        async for msg in thread.history(limit=1):
                            last_active = msg.created_at
                        
                        # If no messages, use thread creation time
                        if not last_active:
                            last_active = thread.created_at
                            
                        if last_active and should_archive(last_active, current_l):
                            await thread.edit(
                                archived=True, reason="Retro-Lifespan"
                            )
                            logger.info(f"Retro-Archived thread {thread.id}")
                            await asyncio.sleep(0.5)  # Rate limit only after action
                        else:
                            await asyncio.sleep(0.05) # Tiny sleep to yield
                except Exception as e:
                    logger.error(f"Retro error in thread {thread.id}: {e}")

    async def add_task(self, task_type, guild_id, payload):
        task_id = await self.db.add_batch_task(guild_id, task_type, payload)
        task = {
            "id": task_id,
            "type": task_type,
            "guild_id": guild_id,
            "payload": payload,
        }
        await self.queue.put(task)
