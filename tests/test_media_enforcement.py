import sys
import os
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock the database and utils before importing MediaCog
with patch('database.db_manager.DBManager'), \
     patch('utils.media_utils.is_media', return_value=False), \
     patch('utils.media_utils.get_quoted_content', return_value="Test Content"):
    from cogs.media_cog import MediaCog

class TestMediaEnforcement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.cog = MediaCog(self.bot)
        self.cog.db = AsyncMock()

    async def test_on_message_in_thread_allowed(self):
        """Non-media message in a thread should NOT be deleted."""
        # Setup channel settings: thread_only=True
        self.cog.db.get_target_setting.return_value = (1, "CHANNEL", 0, True, True, False)
        
        # Setup message in a thread
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
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
        self.cog.db.get_target_setting.return_value = (1, "CHANNEL", 0, True, True, False)
        
        # Setup message in a regular channel
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
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
        self.cog.db.get_target_setting.return_value = (1, "CHANNEL", 0, False, True, False)
        
        # Setup message as starter of a forum thread
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
        message.channel = MagicMock(spec=discord.Thread)
        message.channel.id = 789
        message.channel.parent = MagicMock(spec=discord.ForumChannel)
        message.channel.parent.id = 123
        message.channel.parent.name = "gallery-forum"
        message.id = 789 # Message ID == Channel ID means it's the starter message
        
        await self.cog.on_message(message)
        
        # Verify starter message WAS deleted
        message.delete.assert_called_once()

    async def test_on_message_forum_reply_allowed(self):
        """Non-media reply in a Forum thread should NOT be deleted."""
        self.cog.db.get_target_setting.return_value = (1, "CHANNEL", 0, False, True, False)
        
        # Setup message as reply in a forum thread
        message = AsyncMock(spec=discord.Message)
        message.author.bot = False
        message.channel = MagicMock(spec=discord.Thread)
        message.channel.id = 789
        message.channel.parent = MagicMock(spec=discord.ForumChannel)
        message.channel.parent.id = 123
        message.id = 999 
        
        await self.cog.on_message(message)
        
        # Verify reply WAS NOT deleted
        message.delete.assert_not_called()

if __name__ == '__main__':
    unittest.main()
