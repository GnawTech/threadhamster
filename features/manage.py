import logging
from typing import Any, Optional, Union

import discord

from database.db_manager import DBManager

logger = logging.getLogger(__name__)


async def parse_context(
    interaction: discord.Interaction, target: discord.abc.GuildChannel | None = None
) -> dict[str, Any]:
    """
    Extracts the effective target and its metadata from the context.
    Detects if called within a thread and resolves the parent channel if necessary.

    Args:
        interaction: The discord interaction.
        target: Optional manually specified target channel/thread.

    Returns:
        dict: Processed target information (target_id, target_type, guild_id, mention).

    @example:
        ctx = await parse_context(interaction)
    """
    effective_target = target or interaction.channel
    guild_id = interaction.guild_id

    target_type = "CHANNEL"
    if isinstance(effective_target, discord.Thread):
        target_type = "THREAD"
    elif isinstance(effective_target, discord.CategoryChannel):
        target_type = "CATEGORY"

    return {
        "target_id": effective_target.id,
        "target_type": target_type,
        "guild_id": guild_id,
        "mention": effective_target.mention,
        "name": (
            effective_target.name
            if hasattr(effective_target, "name")
            else str(effective_target.id)
        ),
        "obj": effective_target,
    }


async def update_settings(
    db: DBManager,
    guild_id: int,
    target_id: int,
    target_type: str,
    **settings: Any,
) -> bool:
    """
    Updates specific settings for a target.

    Args:
        db: The database manager.
        guild_id: Guild ID.
        target_id: Target ID.
        target_type: Type (THREAD/CHANNEL/CATEGORY).
        **settings: Key-value pairs of settings (lifespan, auto_thread, etc.).

    Returns:
        bool: True if successful.

    @example:
        await update_settings(db, 123, 456, "CHANNEL", lifespan=7)
    """
    try:
        await db.set_target_setting(
            guild_id=guild_id,
            target_id=target_id,
            target_type=target_type,
            lifespan=settings.get("lifespan"),
            auto_thread=settings.get("auto_thread"),
            thread_only=settings.get("thread_only"),
            spoiler_only=settings.get("spoiler_only"),
            manually_archived=settings.get("manually_archived"),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to update settings for {target_id}: {e}")
        return False


async def get_config_summary(db: DBManager, target_id: int) -> dict[str, Any] | None:
    """
    Retrieves a summary of current configuration for a target.

    Args:
        db: The database manager.
        target_id: Target ID.

    Returns:
        dict: Summary of configurations or None.
    """
    res = await db.get_target_setting(target_id)
    if not res:
        return None

    # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
    return {
        "guild_id": res[0],
        "type": res[1],
        "lifespan": res[2],
        "auto_thread": bool(res[3]),
        "thread_only": bool(res[4]),
        "spoiler_only": bool(res[5]),
        "manually_archived": bool(res[6]),
    }


async def resolve_ambiguity(
    guild: discord.Guild, query: str
) -> list[discord.abc.GuildChannel]:
    """
    Resolves a string query to a list of potential channels/threads.

    Args:
        guild: The discord guild.
        query: Search string (Name or ID).

    Returns:
        list: Matching channels or threads.
    """
    # 1. Check if it's an ID
    if query.isdigit():
        target = guild.get_channel(int(query)) or guild.get_thread(int(query))
        if target:
            return [target]

    # 2. Fuzzy search by name
    matches = []
    query_lower = query.lower()

    # Search channels
    for channel in guild.channels:
        if query_lower in channel.name.lower():
            matches.append(channel)

    # Search threads
    for thread in guild.threads:
        if query_lower in thread.name.lower():
            matches.append(thread)

    return matches
