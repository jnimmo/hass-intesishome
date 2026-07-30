"""Tests for the IntesisHome integration setup and teardown."""

from unittest.mock import MagicMock, PropertyMock

from pyintesishome import IHAuthenticationError, IHConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.intesishome.const import DOMAIN

from . import setup_integration


async def test_setup_entry_success(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A reachable controller with an identity and devices loads the entry."""
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_controller.connect.assert_awaited_once()


async def test_setup_entry_auth_failure(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Invalid credentials surface as ConfigEntryAuthFailed (reauth flow)."""
    mock_controller.connect.side_effect = IHAuthenticationError
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_connection_error(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A connection error is retried rather than failing setup permanently."""
    mock_controller.connect.side_effect = IHConnectionError
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_no_identity(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A device that connects but never reports an identity is retried, not loaded."""
    type(mock_controller).controller_id = PropertyMock(side_effect=ValueError)
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_controller.stop.assert_awaited_once()


async def test_setup_entry_no_devices(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """An identified controller that reports no devices is retried, not loaded."""
    mock_controller.get_devices.return_value = {}
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_controller.stop.assert_awaited_once()


async def test_unload_entry_stops_controller(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Unloading the entry tears down the shared controller."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})
    mock_controller.stop.assert_awaited_once()
