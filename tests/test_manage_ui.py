import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.manage_cog import SetupModal, SetupButtonView
from cogs.manage_ui import ManageView


class TestManageUI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.interaction.response = AsyncMock()
        self.callback = AsyncMock()

    async def test_setup_modal_callback(self):
        """Test that SetupModal correctly parses input and triggers callback."""
        modal = SetupModal(title="Test", callback=self.callback)
        modal.lifespan = MagicMock()
        modal.lifespan.value = "7"

        # Simulate discord calling the callback
        await modal.on_submit(self.interaction)

        self.callback.assert_called_once_with(self.interaction, 7)

    async def test_setup_modal_invalid_input(self):
        """Test that SetupModal handles non-integer input gracefully."""
        modal = SetupModal(title="Test", callback=self.callback)
        modal.lifespan = MagicMock()
        modal.lifespan.value = "abc"

        await modal.on_submit(self.interaction)

        # Should send an error message instead of calling callback
        self.interaction.response.send_message.assert_called_once()
        self.callback.assert_not_called()

    async def test_manage_view_button_toggles(self):
        """Test that ManageView toggles update settings and state."""
        config = {
            "lifespan": 7,
            "auto_thread": False,
            "thread_only": False,
            "spoiler_only": False
        }
        view = ManageView(config, self.callback)
        
        # Mock button
        mock_button = MagicMock(spec=discord.ui.Button)
        
        # Simulate button click - Call the method directly from the instance/class
        await ManageView.toggle_thread_only(view, self.interaction, mock_button)
        
        # Config should be updated
        assert config["thread_only"] is True
        # Callback should be triggered to update DB
        self.callback.assert_called_once()
        # Interaction should be edited with new state
        self.interaction.response.edit_message.assert_called_once()


    async def test_manage_view_all_toggles(self):
        """Test all other toggles in ManageView."""
        config = {"lifespan": 0, "auto_thread": False, "spoiler_only": False}
        view = ManageView(config, self.callback)
        mock_button = MagicMock(spec=discord.ui.Button)

        await ManageView.toggle_auto_thread(view, self.interaction, mock_button)
        assert config["auto_thread"] is True

        await ManageView.toggle_spoiler_only(view, self.interaction, mock_button)
        assert config["spoiler_only"] is True

    async def test_manage_view_done(self):
        """Test the done button in ManageView."""
        view = ManageView({}, self.callback)
        mock_button = MagicMock(spec=discord.ui.Button)

        await ManageView.done(view, self.interaction, mock_button)
        self.interaction.response.send_message.assert_called_once_with(
            "Einstellungen gespeichert.", ephemeral=True
        )

    async def test_setup_button_view(self):
        """Test that SetupButtonView opens the modal."""
        modal = MagicMock()
        view = SetupButtonView(modal)
        
        await view.start.callback(self.interaction)
        
        self.interaction.response.send_modal.assert_called_once_with(modal)


if __name__ == "__main__":
    unittest.main()
