import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def resolve_lifespan(db, guild_id, thread_id, channel_id, category_id):
    """
    Resolves the lifespan for a thread based on the hierarchy:
    Thread > Channel > Category > Global (Guild)
    """
    settings = {}

    # 1. Check specific target IDs (Thread, Channel, Category)
    for target_id in [thread_id, channel_id, category_id]:
        if target_id is None:
            continue
        res = await db.get_target_setting(target_id)
        if res and res[2] is not None:  # res[2] is lifespan
            return res[2]

    # 2. Check Guild Global setting
    guild_res = await db.get_guild_settings(guild_id)
    if guild_res:
        global_lifespan, monitor_mode = guild_res
        if monitor_mode == "GLOBAL_CUSTOM":
            return global_lifespan

    return None  # No specific rule and mode is CUSTOM_ONLY or guild not setup


def should_archive(last_message_at, lifespan_days):
    """
    Calculates if a thread should be archived.
    lifespan_days: 0 = infinite (never archive)
    """
    if lifespan_days == 0:
        return False

    if not last_message_at:
        return False  # Should not happen, but safe check

    # last_message_at should be aware datetime
    now = datetime.now(timezone.utc)
    delta = now - last_message_at

    return delta.days >= lifespan_days
