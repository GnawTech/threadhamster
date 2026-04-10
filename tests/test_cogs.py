import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

# Mock DBManager before any imports that use it
with patch("database.db_manager.DBManager"):
    from cogs.manage_cog import ManageCog
    from cogs.admin_cog import AdminCog


class TestCogs(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()
        self.interaction.guild = MagicMock(spec=discord.Guild)
        self.interaction.guild_id = 456

    @patch("cogs.manage_cog.parse_context")
    @patch("cogs.manage_cog.get_config_summary")
    async def test_manage_router_status(self, mock_summary, mock_parse):
        """Test that /manage Status correctly routes and sends status embed."""
        cog = ManageCog(self.bot)
        mock_parse.return_value = {
            "target_id": 123,
            "target_type": "CHANNEL",
            "guild_id": 456,
            "name": "general",
            "mention": "<#123>",
            "obj": MagicMock()
        }
        mock_summary.return_value = {"lifespan": 7}
        
        await cog.manage_router.callback(cog, self.interaction, "Status")
        
        self.interaction.followup.send.assert_called_once()
        # Verify it sent an embed
        args, kwargs = self.interaction.followup.send.call_args
        assert "embed" in kwargs

    @patch("cogs.manage_cog.parse_context")
    async def test_manage_router_reset(self, mock_parse):
        """Test that /manage Reset correctly deletes settings."""
        cog = ManageCog(self.bot)
        cog.db.remove_target_setting = AsyncMock()
        mock_parse.return_value = {"target_id": 123, "mention": "<#123>"}
        
        await cog.manage_router.callback(cog, self.interaction, "Reset")
        
        cog.db.remove_target_setting.assert_called_once_with(123)
        self.interaction.followup.send.assert_called_once()

    @patch("cogs.manage_cog.resolve_ambiguity")
    async def test_manage_router_ambiguity(self, mock_resolve):
        """Test that /manage handles multiple matches."""
        cog = ManageCog(self.bot)
        m1 = MagicMock(spec=discord.TextChannel)
        m1.name = "media-1"
        m1.id = 1
        m2 = MagicMock(spec=discord.TextChannel)
        m2.name = "media-2"
        m2.id = 2
        mock_resolve.return_value = [m1, m2]
        
        await cog.manage_router.callback(cog, self.interaction, "Status", target="media")
        
        self.interaction.followup.send.assert_called_once()
        args, kwargs = self.interaction.followup.send.call_args
        assert "Mehrdeutig" in kwargs["embed"].title

    @patch("cogs.manage_cog.parse_context")
    @patch("cogs.manage_cog.ManageView")
    async def test_manage_router_setup_callbacks(self, mock_view_class, mock_parse):
        """Test the nested callbacks in handle_setup."""
        cog = ManageCog(self.bot)
        cog.db.get_target_setting = AsyncMock(return_value=None)
        mock_parse.return_value = {"target_id": 123, "name": "general", "guild_id": 456, "target_type": "CHANNEL"}
        
        # 1. Trigger handle_setup
        await cog.manage_router.callback(cog, self.interaction, "Setup")
        
        # Capture the modal from SetupButtonView
        args, kwargs = self.interaction.followup.send.call_args
        view = kwargs["view"]
        modal = view.modal
        
        # 2. Trigger modal callback
        modal_inter = AsyncMock(spec=discord.Interaction)
        modal_inter.response = AsyncMock()
        await modal.on_submit_callback(modal_inter, 14)
        
        # 3. Capture and trigger view callback
        # mock_view_class was called inside modal_callback
        args, kwargs = mock_view_class.call_args
        v_callback = args[1]
        
        with patch("cogs.manage_cog.update_settings") as mock_update:
            await v_callback({"thread_only": True})
            mock_update.assert_called_once()

    @patch("cogs.manage_cog.parse_context")
    async def test_manage_router_archives_missing_cog(self, mock_parse):
        """Test handle_archives when LifespanCog is not found."""
        cog = ManageCog(self.bot)
        mock_parse.return_value = {"target_id": 123, "obj": MagicMock()}
        self.bot.get_cog.return_value = None
        
        await cog.manage_router.callback(cog, self.interaction, "Archiv")
        self.interaction.followup.send.assert_called_with(
            "Lifespan-Modul nicht geladen.", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_setup_entrypoint(self):
        """Test the setup function for the cog."""
        from cogs.manage_cog import setup
        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()


    @pytest.mark.asyncio
    async def test_admin_setup_entrypoint(self):
        """Test the setup function for the admin cog."""
        from cogs.admin_cog import setup
        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()

    @patch("cogs.manage_cog.resolve_ambiguity")
    async def test_manage_router_not_found(self, mock_resolve):
        """Test that /manage sends error if target not found."""
        cog = ManageCog(self.bot)
        mock_resolve.return_value = []
        
        await cog.manage_router.callback(cog, self.interaction, "Status", target="unknown")
        
        self.interaction.followup.send.assert_called_once()
        args, kwargs = self.interaction.followup.send.call_args
        assert "embed" in kwargs

    @patch("cogs.manage_cog.parse_context")
    async def test_manage_router_setup(self, mock_parse):
        """Test that /manage Setup sends the toggle message."""
        cog = ManageCog(self.bot)
        mock_parse.return_value = {"target_id": 123, "name": "general"}
        
        await cog.manage_router.callback(cog, self.interaction, "Setup")
        self.interaction.followup.send.assert_called_once()

    async def test_manage_router_guild(self):
        """Test that /manage Guild sends the placeholders."""
        cog = ManageCog(self.bot)
        await cog.manage_router.callback(cog, self.interaction, "Guild")
        self.interaction.followup.send.assert_called_once()

    @patch("cogs.manage_cog.parse_context")
    async def test_manage_router_archives(self, mock_parse):
        """Test that /manage Archiv routes to LifespanCog."""
        cog = ManageCog(self.bot)
        mock_parse.return_value = {"target_id": 123, "obj": MagicMock()}
        
        # Mock LifespanCog
        mock_lifespan = MagicMock()
        mock_lifespan.archives = MagicMock()
        mock_lifespan.archives.callback = AsyncMock()
        self.bot.get_cog.return_value = mock_lifespan
        
        await cog.manage_router.callback(cog, self.interaction, "Archiv")
        mock_lifespan.archives.callback.assert_called_once()

    async def test_admin_sync_success(self):
        """Test that /sync correctly triggers tree sync."""
        cog = AdminCog(self.bot)
        self.bot.tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
        
        await cog.sync_slash.callback(cog, self.interaction)
        
        self.bot.tree.sync.assert_called_once()
        self.interaction.followup.send.assert_called_once_with(
            "Erfolgreich 2 Slash-Befehle synchronisiert.", ephemeral=True
        )

    async def test_admin_sync_failure(self):
        """Test that /sync handles errors gracefully."""
        cog = AdminCog(self.bot)
        self.bot.tree.sync = AsyncMock(side_effect=Exception("API Error"))
        
        await cog.sync_slash.callback(cog, self.interaction)
        
        self.interaction.followup.send.assert_called_with(
            "Fehler beim Synchronisieren: API Error", ephemeral=True
        )


if __name__ == "__main__":
    unittest.main()
