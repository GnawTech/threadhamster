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
    For a message to be a valid 'spoiler', ALL attachments must be spoilers
    AND any links must be wrapped in spoiler tags ||...||.
    """
    # 1. Check Attachments
    if message.attachments:
        if not all(att.is_spoiler() for att in message.attachments):
            return False

    # 2. Check Links
    has_link = "http://" in message.content or "https://" in message.content
    if has_link:
        # A bit simplistic but usually links are within ||...|| for spoilers
        # Discord doesn't have a specific is_spoiler property for links in the message object,
        # it just defaults to checking if the link is within || tags.
        if "||" not in message.content:
            return False

    # 3. If no attachments and no links, but we are here (is_media was True),
    # it must be a text-only spoiler tag.
    if not message.attachments and not has_link:
        return "||" in message.content

    return True


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
