import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.media_utils import has_cw_keyword, is_media, is_spoiler

# Mock the database before importing MediaCog
with patch("database.db_manager.DBManager"):
    from cogs.media_cog import MediaCog


def test_utils_is_media():
    msg = MagicMock()
    msg.attachments = []
    msg.content = "No media here"
    assert is_media(msg) is False

    msg.content = "Check out this link: http://example.com"
    assert is_media(msg) is True

    msg.content = "||secret spoiler||"
    assert is_media(msg) is True

    att = MagicMock()
    att.content_type = "image/png"
    msg.attachments = [att]
    msg.content = ""
    assert is_media(msg) is True


def test_utils_is_spoiler():
    msg = MagicMock()
    msg.attachments = []
    msg.content = "Not a spoiler"
    assert is_spoiler(msg) is False

    msg.content = "||spoiler||"
    assert is_spoiler(msg) is True

    # Single attachment
    att = MagicMock()
    att.is_spoiler.return_value = True
    msg.attachments = [att]
    msg.content = ""
    assert is_spoiler(msg) is True

    # Multiple attachments, all spoilers
    att2 = MagicMock()
    att2.is_spoiler.return_value = True
    msg.attachments = [att, att2]
    assert is_spoiler(msg) is True

    # Multiple attachments, one non-spoiler
    att3 = MagicMock()
    att3.is_spoiler.return_value = False
    msg.attachments = [att, att2, att3]
    assert is_spoiler(msg) is False

    # Mixed media: spoiler attachment + plaintext link (FAIL)
    msg.attachments = [att]
    msg.content = "Check this link: http://example.com"
    assert is_spoiler(msg) is False

    # Mixed media: spoiler attachment + spoiled link (PASS)
    msg.content = "Check this spoiler: ||http://example.com||"
    assert is_spoiler(msg) is True

    # Only plaintext link (FAIL)
    msg.attachments = []
    msg.content = "http://example.com"
    assert is_spoiler(msg) is False

    # Only spoiled link (PASS)
    msg.content = "||http://example.com||"
    assert is_spoiler(msg) is True


def test_utils_has_cw_keyword():
    assert has_cw_keyword("No keyword here") is False
    assert has_cw_keyword("This is a [Contentwarning: test]") is True
    assert has_cw_keyword("CW: Spiders") is True
    assert has_cw_keyword("inhaltswarnung: Blut") is True
    assert has_cw_keyword("TW: Violence") is True
    assert has_cw_keyword("Something iw: test") is True
    assert has_cw_keyword("Here are some Triggerwarnungen") is True
    assert has_cw_keyword("CWS: test") is True


class TestMediaEnforcement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        with patch("discord.ext.tasks.Loop.start"):
            self.cog = MediaCog(self.bot)
        self.cog.db = AsyncMock()

    async def test_on_message_in_thread_allowed(self):
        """Non-media message in a thread should NOT be deleted."""
        # Setup channel settings: thread_only=True
        # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
        self.cog.db.get_target_setting.return_value = (
            1,
            "CHANNEL",
            0,
            True,
            True,
            False,
            False,
        )

        # Setup message in a thread
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
        message.type = discord.MessageType.default
        message.channel = MagicMock(spec=discord.Thread)
        message.channel.id = 123
        message.channel.parent = MagicMock(spec=discord.TextChannel)
        message.channel.parent.id = 123
        message.id = 456

        await self.cog.on_message(message)

        # Verify message was NOT deleted
        message.delete.assert_not_called()

    async def test_on_message_in_channel_deleted(self):
        """Non-media message in a thread_only channel should be deleted."""
        self.cog.db.get_target_setting.return_value = (
            1,
            "CHANNEL",
            0,
            True,
            True,
            False,
            False,
        )

        # Setup message in a regular channel
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
        message.type = discord.MessageType.default
        message.channel = MagicMock(spec=discord.TextChannel)
        message.channel.id = 123
        message.channel.name = "media-only"
        message.id = 456

        await self.cog.on_message(message)

        # Verify message WAS deleted
        message.delete.assert_called_once()

    async def test_on_message_forum_starter_deleted(self):
        """Non-media starter message in a thread_only Forum should be deleted."""
        # Forum settings: thread_only=True
        self.cog.db.get_target_setting.return_value = (
            1,
            "CHANNEL",
            0,
            False,
            True,
            False,
            False,
        )

        # Setup message as starter of a forum thread
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
        message.type = discord.MessageType.default
        message.channel = MagicMock(spec=discord.Thread)
        message.channel.id = 789
        message.channel.parent = MagicMock(spec=discord.ForumChannel)
        message.channel.parent.id = 123
        message.channel.parent.name = "gallery-forum"
        message.id = 789  # Message ID == Channel ID means it's the starter message

        with patch("cogs.media_cog.is_media", return_value=False):
            await self.cog.on_message(message)

        # Verify starter message WAS deleted
        message.delete.assert_called_once()

    async def test_on_message_forum_reply_allowed(self):
        """Non-media reply in a Forum thread should NOT be deleted."""
        self.cog.db.get_target_setting.return_value = (
            1,
            "CHANNEL",
            0,
            False,
            True,
            False,
            False,
        )

        # Setup message as reply in a forum thread
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
        message.type = discord.MessageType.default
        message.channel = MagicMock(spec=discord.Thread)
        message.channel.id = 789
        message.channel.parent = MagicMock(spec=discord.ForumChannel)
        message.channel.parent.id = 123
        message.id = 999

        await self.cog.on_message(message)

        # Verify reply WAS NOT deleted
        message.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
