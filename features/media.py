import discord
import logging
from typing import Tuple
from utils.media_utils import is_media, is_spoiler, has_cw_keyword

logger = logging.getLogger(__name__)

def should_moderate_message(message: discord.Message, settings: Tuple) -> Tuple[bool, str]:
    """
    Determines if a message violates media moderation rules (thread_only, spoiler_only).
    
    Args:
        message: The discord.Message to check.
        settings: Tuple (guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived)
        
    Returns:
        Tuple[bool, str]: (should_delete, reason_code)
        Reason codes: "THREAD_ONLY", "SPOILER_ONLY", "CW_MISSING", "OK"
    """
    _, _, _, _, thread_only, spoiler_only, _ = settings
    
    is_thread = isinstance(message.channel, discord.Thread)
    is_forum = isinstance(message.channel.parent, discord.ForumChannel) if is_thread else False
    has_media = is_media(message)
    
    # 1. Thread Enforcement Check
    # Only moderate thread_only if we are NOT in a thread (unless it's a forum starter)
    is_starter = is_forum and message.id == message.channel.id
    is_top_level = not is_thread or is_starter
    
    if is_top_level and thread_only and not has_media:
        return True, "THREAD_ONLY"
    
    # 2. Spoiler & CW Check (only applies if media is present)
    if spoiler_only and has_media:
        if not is_spoiler(message):
            return True, "SPOILER_ONLY"
        if not has_cw_keyword(message.content):
            return False, "CW_MISSING" # Not direct delete, but grace period trigger
            
    return False, "OK"
