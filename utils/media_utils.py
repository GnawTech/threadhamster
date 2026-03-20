import logging
import os
import re

import aiohttp

logger = logging.getLogger(__name__)


def is_media(message):
    """
    Checks if a message contains media/links or spoilers.
    """
    # Check for attachments
    for att in message.attachments:
        if att.content_type and att.content_type.startswith(
            ("image/", "video/", "audio/")
        ):
            return True

    # Check for links in content
    if "http://" in message.content or "https://" in message.content:
        return True

    # Check for spoilers (||...||)
    if "||" in message.content:
        return True

    return False


def is_spoiler(message):
    """
    Checks if all media in the message is marked as spoiler.
    """
    # If no attachments, check if text has spoiler tags
    if not message.attachments:
        return "||" in message.content

    # If attachments exist, ALL must be spoilers (Discord logic) or the message itself is a spoiler
    return all(att.is_spoiler() for att in message.attachments)


ACCEPTED_KEYWORDS = [
    "contentwarning",
    "contentwarnings",
    "cw",
    "cws",
    "inhaltswarnung",
    "inhaltswarnungen",
    "iw",
    "iws",
    "triggerwarning",
    "triggerwarnings",
    "tw",
    "tws",
    "triggerwarnung",
    "triggerwarnungen",
]


def has_cw_keyword(content):
    """
    Checks if the content contains one of the required CW keywords as a whole word.
    """
    content_lower = content.lower()
    # Use regex to find keywords as whole words
    # regex pattern: \b(keyword1|keyword2|...)\b
    pattern = r"\b(" + "|".join(re.escape(kw) for kw in ACCEPTED_KEYWORDS) + r")\b"
    return bool(re.search(pattern, content_lower))


def get_quoted_content(message):
    """
    Format message content for DM notifications.
    """
    return f"\n> {message.content}" if message.content else ""
