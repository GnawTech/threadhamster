import os
import aiohttp
import logging

logger = logging.getLogger(__name__)


def is_media(message):
    """
    Checks if a message contains media/links or spoilers.
    """
    # Check for attachments
    if any(
        att.content_type
        and (att.content_type.startswith(("image/", "video/", "audio/")))
        for att in message.attachments
    ):
        return True

    # Check for links in content
    if "http://" in message.content or "https://" in message.content:
        return True

    # Check for spoilers (this is tricky because spoilers are content,
    # but the user specified they count as valid media)
    if "||" in message.content:
        return True

    return False


def get_quoted_content(message):
    """
    Format message content for DM notifications.
    """
    return f"\n> {message.content}" if message.content else ""
