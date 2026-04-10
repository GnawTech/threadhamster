from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from features.manage import (
    get_config_summary,
    parse_context,
    resolve_ambiguity,
    update_settings,
)


class MockChannel:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.mention = f"<#{id}>"


class MockThread:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.mention = f"<#{id}>"


@pytest.mark.asyncio
async def test_parse_context_default():
    interaction = MagicMock(spec=discord.Interaction)
    interaction.channel = MockChannel(123, "general")
    interaction.guild_id = 456

    ctx = await parse_context(interaction)

    assert ctx["target_id"] == 123
    assert ctx["target_type"] == "CHANNEL"
    assert ctx["guild_id"] == 456
    assert ctx["name"] == "general"


@pytest.mark.asyncio
async def test_parse_context_thread():
    interaction = MagicMock(spec=discord.Interaction)
    mock_thread = MagicMock(spec=discord.Thread)
    mock_thread.id = 789
    mock_thread.name = "my-thread"
    mock_thread.mention = "<#789>"

    ctx = await parse_context(interaction, target=mock_thread)

    assert ctx["target_id"] == 789
    assert ctx["target_type"] == "THREAD"


@pytest.mark.asyncio
async def test_parse_context_category():
    interaction = MagicMock(spec=discord.Interaction)
    mock_category = MagicMock(spec=discord.CategoryChannel)
    mock_category.id = 111
    mock_category.name = "My Category"
    mock_category.mention = "@My Category"

    ctx = await parse_context(interaction, target=mock_category)

    assert ctx["target_id"] == 111
    assert ctx["target_type"] == "CATEGORY"
    assert ctx["name"] == "My Category"


@pytest.mark.asyncio
async def test_update_settings():
    db = MagicMock()
    db.set_target_setting = AsyncMock()

    success = await update_settings(
        db, 456, 123, "CHANNEL", lifespan=7, auto_thread=True
    )

    assert success is True
    db.set_target_setting.assert_called_once_with(
        guild_id=456,
        target_id=123,
        target_type="CHANNEL",
        lifespan=7,
        auto_thread=True,
        thread_only=None,
        spoiler_only=None,
        manually_archived=None,
    )


@pytest.mark.asyncio
async def test_update_settings_error():
    db = MagicMock()
    db.set_target_setting = AsyncMock(side_effect=Exception("DB Error"))

    success = await update_settings(db, 456, 123, "CHANNEL", lifespan=7)

    assert success is False


@pytest.mark.asyncio
async def test_get_config_summary():
    db = MagicMock()
    # res: guild_id, target_type, lifespan, auto_thread, thread_only, spoiler_only, manually_archived
    db.get_target_setting = AsyncMock(return_value=(456, "CHANNEL", 7, 1, 0, 1, 0))

    summary = await get_config_summary(db, 123)

    assert summary["lifespan"] == 7
    assert summary["auto_thread"] is True
    assert summary["spoiler_only"] is True
    assert summary["thread_only"] is False


@pytest.mark.asyncio
async def test_get_config_summary_none():
    db = MagicMock()
    db.get_target_setting = AsyncMock(return_value=None)
    
    summary = await get_config_summary(db, 123)
    assert summary is None


@pytest.mark.asyncio
async def test_resolve_ambiguity_id():
    guild = MagicMock()
    channel = MockChannel(123, "general")
    guild.get_channel.return_value = channel

    matches = await resolve_ambiguity(guild, "123")
    assert len(matches) == 1
    assert matches[0].id == 123


@pytest.mark.asyncio
async def test_resolve_ambiguity_name():
    guild = MagicMock()
    c1 = MockChannel(1, "general")
    c2 = MockChannel(2, "testing")
    guild.channels = [c1, c2]
    guild.threads = []

    matches = await resolve_ambiguity(guild, "gen")
    assert len(matches) == 1
    assert matches[0].name == "general"


@pytest.mark.asyncio
async def test_resolve_ambiguity_no_match():
    guild = MagicMock()
    guild.channels = [MockChannel(1, "general")]
    guild.threads = []
    guild.get_channel.return_value = None
    guild.get_thread.return_value = None

    matches = await resolve_ambiguity(guild, "missing")
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_resolve_ambiguity_multiple_matches():
    guild = MagicMock()
    c1 = MockChannel(1, "media-1")
    c2 = MockChannel(2, "media-2")
    guild.channels = [c1, c2]
    guild.threads = []

    matches = await resolve_ambiguity(guild, "media")
    assert len(matches) == 2


@pytest.mark.asyncio
async def test_resolve_ambiguity_thread_match():
    guild = MagicMock()
    guild.channels = []
    t1 = MockThread(123, "my-thread")
    guild.threads = [t1]
    
    matches = await resolve_ambiguity(guild, "thread")
    assert len(matches) == 1
    assert matches[0].id == 123


@pytest.mark.asyncio
async def test_resolve_ambiguity_no_name_match():
    guild = MagicMock()
    guild.channels = [MockChannel(1, "other")]
    guild.threads = []
    guild.get_channel.return_value = None
    
    matches = await resolve_ambiguity(guild, "missing")
    assert len(matches) == 0
