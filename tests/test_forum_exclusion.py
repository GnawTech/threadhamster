import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, UTC

from features.batch import BatchProcessor
from cogs.lifespan_cog import LifespanCog


@pytest.fixture
def mock_db():
    """Fixture for mock database manager."""
    return AsyncMock()


@pytest.fixture
def mock_bot():
    """Fixture for mock bot."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.user.id = 12345
    return bot


@pytest.fixture
def mock_guild():
    """Fixture for mock guild."""
    guild = MagicMock()
    guild.id = 111
    return guild


@pytest.fixture
def mock_text_channel():
    """Fixture for mock text channel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 222
    channel.category = None
    return channel


@pytest.fixture
def mock_forum_channel():
    """Fixture for mock forum channel."""
    channel = MagicMock(spec=discord.ForumChannel)
    channel.id = 333
    channel.category = None
    return channel


@pytest.fixture
def thread_text(mock_text_channel):
    """Fixture for thread in text channel."""
    thread = AsyncMock(spec=discord.Thread)
    thread.id = 2221
    thread.parent = mock_text_channel
    thread.archived = False
    thread.created_at = datetime.now(UTC) - timedelta(days=10)

    msg = MagicMock()
    msg.created_at = datetime.now(UTC) - timedelta(days=10)

    async def mock_history(*args, **kwargs):
        yield msg

    thread.history.side_effect = mock_history
    return thread


@pytest.fixture
def thread_forum(mock_forum_channel):
    """Fixture for thread in forum channel."""
    thread = AsyncMock(spec=discord.Thread)
    thread.id = 3331
    thread.parent = mock_forum_channel
    thread.archived = False
    thread.created_at = datetime.now(UTC) - timedelta(days=10)

    msg = MagicMock()
    msg.created_at = datetime.now(UTC) - timedelta(days=10)

    async def mock_history(*args, **kwargs):
        yield msg

    thread.history.side_effect = mock_history
    return thread


@pytest.mark.asyncio
async def test_batch_processor_retro_archive_excludes_forum(
    mock_bot, mock_db, mock_guild, thread_text, thread_forum
):
    """
    Test that BatchProcessor RETRO_ARCHIVE excludes forum threads.

    @example
    await test_batch_processor_retro_archive_excludes_forum(...)
    """
    processor = BatchProcessor(mock_bot, mock_db)

    with (
        patch("features.lifespan.resolve_lifespan", AsyncMock(return_value=5)),
        patch("cogs.lifespan_cog.resolve_lifespan", AsyncMock(return_value=5)),
    ):

        task = {
            "id": 1,
            "type": "RETRO_ARCHIVE",
            "guild_id": 111,
            "payload": {"target_id": None, "lifespan": 5},
        }

        mock_bot.get_guild.return_value = mock_guild
        mock_guild.active_threads = AsyncMock(return_value=[thread_text, thread_forum])

        await processor._handle_task(task)

        assert (
            thread_text.edit.called
        ), "Thread in text channel should have been archived"
        assert (
            not thread_forum.edit.called
        ), "Thread in forum channel should NOT have been archived"


@pytest.mark.asyncio
async def test_lifespan_cog_archive_check_excludes_forum(
    mock_bot, mock_db, mock_guild, thread_text, thread_forum
):
    """
    Test that LifespanCog.archive_check excludes forum threads.
    """
    cog = LifespanCog(mock_bot)
    cog.db = mock_db

    mock_bot.guilds = [mock_guild]
    mock_guild.active_threads = AsyncMock(return_value=[thread_text, thread_forum])

    # Needs resolve_lifespan patch if called inside archive_check
    with patch("cogs.lifespan_cog.resolve_lifespan", AsyncMock(return_value=5)):
        await cog.archive_check()

    assert thread_text.edit.called
    assert not thread_forum.edit.called


@pytest.mark.asyncio
async def test_lifespan_cog_on_thread_update_early_return_for_forum(
    mock_bot, mock_forum_channel
):
    """
    Test that on_thread_update returns early for forum threads.
    """
    cog = LifespanCog(mock_bot)

    before = MagicMock(spec=discord.Thread)
    before.archived = False

    after_forum = MagicMock(spec=discord.Thread)
    after_forum.id = 3331
    after_forum.archived = True
    after_forum.parent = mock_forum_channel
    after_forum.guild.id = 111
    after_forum.edit = AsyncMock()

    await cog.on_thread_update(before, after_forum)
    assert not after_forum.edit.called
