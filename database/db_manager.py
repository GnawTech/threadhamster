import json
import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)


class DBManager:
    """
    Handles all database interactions for ThreadHamster.
    Uses aiosqlite for async operations.
    """

    def __init__(self, db_path="data/threadhamster.db"):
        self.db_path = db_path
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def initialize(self):
        """
        Creates necessary tables if they don't exist.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Guild settings (Global values)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    global_lifespan INTEGER DEFAULT 0,
                    monitor_mode TEXT DEFAULT 'CUSTOM_ONLY'
                )
            """
            )

            # Target settings (Specific overrides for Thread, Channel, Category)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS target_settings (
                    guild_id INTEGER,
                    target_id INTEGER PRIMARY KEY,
                    target_type TEXT, -- 'THREAD', 'CHANNEL', 'CATEGORY'
                    lifespan INTEGER,
                    auto_thread BOOLEAN DEFAULT 0,
                    thread_only BOOLEAN DEFAULT 0,
                    spoiler_only BOOLEAN DEFAULT 0,
                    manually_archived BOOLEAN DEFAULT 0
                )
            """
            )

            # Batch tasks for retro scanning
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS batch_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    task_type TEXT,
                    payload TEXT, -- JSON string
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            await db.commit()
            logger.info("Database initialized.")

            # Migration: Add manually_archived column if it doesn't exist (Backup for existing DBs)
            async with db.execute("PRAGMA table_info(target_settings)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "manually_archived" not in columns:
                    await db.execute(
                        "ALTER TABLE target_settings ADD COLUMN manually_archived BOOLEAN DEFAULT 0"
                    )
                    await db.commit()
                    logger.info("Database migration: Added manually_archived column.")

            # Migration: Add spoiler_only column if it doesn't exist
            async with db.execute("PRAGMA table_info(target_settings)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "spoiler_only" not in columns:
                    await db.execute(
                        "ALTER TABLE target_settings ADD COLUMN spoiler_only BOOLEAN DEFAULT 0"
                    )
                    await db.commit()
                    logger.info("Database migration: Added spoiler_only column.")

    async def set_guild_setting(
        self, guild_id: int, global_lifespan: int = None, monitor_mode: str = None
    ):
        async with aiosqlite.connect(self.db_path) as db:
            # Using INSERT OR IGNORE and then UPDATE for UPSERT behavior
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            if global_lifespan is not None:
                await db.execute(
                    "UPDATE guild_settings SET global_lifespan = ? WHERE guild_id = ?",
                    (global_lifespan, guild_id),
                )
            if monitor_mode:
                await db.execute(
                    "UPDATE guild_settings SET monitor_mode = ? WHERE guild_id = ?",
                    (monitor_mode, guild_id),
                )
            await db.commit()

    async def get_guild_settings(self, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT global_lifespan, monitor_mode FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                return await cursor.fetchone()

    async def set_target_setting(
        self,
        guild_id: int,
        target_id: int,
        target_type: str,
        lifespan: int = None,
        auto_thread: bool = None,
        thread_only: bool = None,
        spoiler_only: bool = None,
        manually_archived: bool = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO target_settings (
                    guild_id, target_id, target_type, lifespan, 
                    auto_thread, thread_only, manually_archived
                )
                VALUES (?, ?, ?, 
                    COALESCE(?, (SELECT lifespan FROM target_settings WHERE target_id = ?)),
                    COALESCE(?, (SELECT auto_thread FROM target_settings WHERE target_id = ?), 0),
                    COALESCE(?, (SELECT thread_only FROM target_settings WHERE target_id = ?), 0),
                    COALESCE(?, (SELECT spoiler_only FROM target_settings WHERE target_id = ?), 0),
                    COALESCE(?, (SELECT manually_archived FROM target_settings WHERE target_id = ?), 0)
                )
            """,
                (
                    guild_id,
                    target_id,
                    target_type,
                    lifespan,
                    target_id,
                    auto_thread,
                    target_id,
                    thread_only,
                    target_id,
                    spoiler_only,
                    target_id,
                    manually_archived,
                    target_id,
                ),
            )
            await db.commit()

    async def get_target_setting(self, target_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived FROM target_settings WHERE target_id = ?",
                (target_id,),
            ) as cursor:
                return await cursor.fetchone()

    async def add_batch_task(self, guild_id: int, task_type: str, payload: dict):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "INSERT INTO batch_tasks (guild_id, task_type, payload) VALUES (?, ?, ?)",
                (guild_id, task_type, json.dumps(payload)),
            ) as cursor:
                await db.commit()
                return cursor.lastrowid

    async def get_pending_batch_tasks(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, guild_id, task_type, payload FROM batch_tasks WHERE status = 'PENDING' ORDER BY created_at ASC"
            ) as cursor:
                tasks = []
                for row in await cursor.fetchall():
                    tasks.append(
                        {
                            "id": row[0],
                            "guild_id": row[1],
                            "type": row[2],
                            "payload": json.loads(row[3]),
                        }
                    )
                return tasks

    async def update_batch_task_status(self, task_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE batch_tasks SET status = ? WHERE id = ?", (status, task_id)
            )
            await db.commit()
