"""Tests for the IntesisHome config flow's reauth handling."""

from unittest.mock import MagicMock, patch

from pyintesishome import IHAuthenticationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


@pytest.fixture
def mock_config_flow_controller() -> MagicMock:
    """Mock the IntesisHome class as referenced from config_flow.py.

    config_flow.py imports IntesisHome into its own module namespace, so
    patching custom_components.intesishome.IntesisHome (as the mock_controller
    fixture in conftest.py does for __init__.py) does not affect what
    config_flow.py resolves the name to -- they're separate attribute
    bindings pointing at the same class. Reauth needs its own patch target.
    """
    with patch(
        "custom_components.intesishome.config_flow.IntesisHome", autospec=True
    ) as mock_intesishome:
        controller = mock_intesishome.return_value
        controller.controller_id = "aabbccddeeff"
        controller.poll_status.return_value = None
        controller.stop.return_value = None
        yield controller


async def _start_reauth(
    hass: HomeAssistant, entry: MockConfigEntry
) -> config_entries.ConfigFlowResult:
    return await hass.config_entries.flow.async_init(
        entry.domain,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )


async def test_reauth_success_updates_entry(
    hass: HomeAssistant,
    mock_config_flow_controller: MagicMock,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Submitting valid new credentials updates the entry and reloads it.

    The reload that follows a successful reauth goes through
    __init__.async_setup_entry, which resolves IntesisHome from its own
    module namespace -- the fully-stubbed mock_controller fixture from
    conftest.py covers that, so entity setup (climate/sensor/binary_sensor)
    doesn't choke on an unconfigured MagicMock.
    """
    mock_config_entry.add_to_hass(hass)

    init_result = await _start_reauth(hass, mock_config_entry)
    assert init_result["type"] is FlowResultType.FORM
    assert init_result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"],
        {CONF_USERNAME: "new@example.com", CONF_PASSWORD: "new-password"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_USERNAME] == "new@example.com"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"
    mock_config_flow_controller.stop.assert_awaited_once()


async def test_reauth_invalid_auth_shows_error(
    hass: HomeAssistant,
    mock_config_flow_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Submitting credentials the cloud still rejects re-shows the form with an error."""
    mock_config_entry.add_to_hass(hass)
    mock_config_flow_controller.poll_status.side_effect = IHAuthenticationError

    init_result = await _start_reauth(hass, mock_config_entry)

    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"],
        {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "still-wrong"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    mock_config_flow_controller.stop.assert_awaited_once()
