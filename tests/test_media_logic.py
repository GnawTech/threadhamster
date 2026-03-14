import sys
import os
import pytest
import discord
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cogs.media_cog import MediaCog
from database.db_manager import DBManager

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user.id = 123456789
    return bot

@pytest.fixture
def cog(mock_bot):
    with patch("discord.ext.tasks.Loop.start"):
        cog = MediaCog(mock_bot)
        cog.db = AsyncMock(spec=DBManager)
        return cog

@pytest.mark.asyncio
async def test_on_message_deletes_non_spoiler_media(cog):
    # Setup: spoiler_only is True
    # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
    cog.db.get_target_setting.return_value = (111, "CHANNEL", 0, False, False, True, False)
    
    # Mock message with non-spoiler image
    message = AsyncMock(spec=discord.Message)
    message.guild.id = 111
    message.channel.id = 222
    message.channel.name = "media-test"
    message.author.bot = False
    message.author.send = AsyncMock()
    message.content = "Look at this pic"
    
    att = MagicMock(spec=discord.Attachment)
    att.is_spoiler.return_value = False
    att.content_type = "image/png"
    message.attachments = [att]
    
    await cog.on_message(message)
    
    assert message.delete.called
    assert message.author.send.called
    kw_args, kw_kwargs = message.author.send.call_args
    embed = kw_kwargs.get("embed")
    assert embed is not None
    assert "Beitrag gelöscht" in embed.title
    assert "inhaltswarnungen" in embed.fields[1].value.lower()

@pytest.mark.asyncio
async def test_on_message_allows_spoiler_with_cw(cog):
    cog.db.get_target_setting.return_value = (111, "CHANNEL", 0, False, False, True, False)
    
    # Mock message with spoiler and CW
    message = AsyncMock(spec=discord.Message)
    message.guild.id = 111
    message.channel.id = 222
    message.author.bot = False
    message.content = "[CW: Test] This is a spoiler"
    
    att = MagicMock(spec=discord.Attachment)
    att.is_spoiler.return_value = True
    att.content_type = "image/png"
    message.attachments = [att]
    
    await cog.on_message(message)
    
    assert not message.delete.called
    # Should not trigger grace period warning
    assert not message.channel.send.called

@pytest.mark.asyncio
async def test_on_message_triggers_grace_period(cog):
    cog.db.get_target_setting.return_value = (111, "CHANNEL", 0, False, False, True, False)
    
    # Mock message with spoiler but NO CW
    message = AsyncMock(spec=discord.Message)
    message.id = 999
    message.guild.id = 111
    message.channel.id = 222
    message.channel.name = "media-test"
    
    # Ensure channel.send returns an AsyncMock for the warning message
    warning_msg = AsyncMock(spec=discord.Message)
    message.channel.send = AsyncMock(return_value=warning_msg)
    message.channel.fetch_message = AsyncMock(return_value=message)
    
    message.author.bot = False
    message.author.send = AsyncMock()
    message.content = "Just a spoiler without any keyword"
    
    att = MagicMock(spec=discord.Attachment)
    att.is_spoiler.return_value = True
    att.content_type = "image/png"
    message.attachments = [att]
    
    # Patch asyncio.sleep just in case, though it's not used in on_message anymore
    with patch("asyncio.sleep", AsyncMock()):
        await cog.on_message(message)
    
    # Check if channel warning was sent
    assert message.channel.send.called
    
    # Check if DM was sent as Embed
    assert message.author.send.called
    _, kw_kwargs = message.author.send.call_args
    embed = kw_kwargs.get("embed")
    assert embed is not None
    assert "Inhaltswarnung (CW) fehlt" in embed.title
    
    # Check if added to DB for persistence
    assert cog.db.add_grace_period.called
    args, _ = cog.db.add_grace_period.call_args
    assert args[0] == 111 # guild_id
    assert args[1] == 222 # channel_id
    assert args[2] == 999 # message_id

@pytest.mark.asyncio
async def test_setup_channel_command(cog):
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.guild_id = 111
    interaction.channel.id = 222
    interaction.channel.mention = "#media-test"
    
    await cog.setup_channel.callback(cog, interaction, channel=None, auto_thread=True, thread_only=False, spoiler_only=True)
    
    cog.db.set_target_setting.assert_called_with(
        111, 222, "CHANNEL", auto_thread=True, thread_only=False, spoiler_only=True
    )
    assert interaction.followup.send.called

@pytest.mark.asyncio
async def test_edit_channel_command(cog):
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.guild_id = 111
    interaction.channel.id = 222
    interaction.channel.mention = "#media-test"
    
    # Only edit spoiler_only
    await cog.edit_channel.callback(cog, interaction, channel=None, spoiler_only=True)
    
    cog.db.set_target_setting.assert_called_with(
        111, 222, "CHANNEL", auto_thread=None, thread_only=None, spoiler_only=True
    )
    assert interaction.followup.send.called
    args, _ = interaction.followup.send.call_args
    assert "Spoiler-Only (+CW): An" in args[0]
    assert "Auto-Thread" not in args[0] # Should only show what changed
