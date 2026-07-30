"""Tests for the IntesisHome climate platform."""

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, Platform, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .conftest import MOCK_DEVICE_ID

ENTITY_ID = "climate.mock_device"


async def test_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The climate entity's registry entry and state match the mocked controller."""
    with patch("custom_components.intesishome.PLATFORMS", [Platform.CLIMATE]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(
        hass, entity_registry, snapshot, mock_config_entry.entry_id
    )


async def test_supported_features_minimal(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Only TURN_ON/TURN_OFF are set when the controller reports no optional capabilities."""
    mock_controller.has_setpoint_control.return_value = False
    mock_controller.get_vertical_swing_list.return_value = []
    mock_controller.get_horizontal_swing_list.return_value = []
    mock_controller.get_fan_speed_list.return_value = []
    mock_controller.get_devices.return_value = {
        MOCK_DEVICE_ID: {"name": "MOCK DEVICE"}  # no climate_working_mode
    }
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(ENTITY_ID)
    features = state.attributes["supported_features"]
    assert features & ClimateEntityFeature.TURN_ON
    assert features & ClimateEntityFeature.TURN_OFF
    assert not features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not features & ClimateEntityFeature.SWING_MODE
    assert not features & ClimateEntityFeature.FAN_MODE
    assert not features & ClimateEntityFeature.PRESET_MODE


async def test_unknown_hvac_mode_skipped(
    hass: HomeAssistant,
    mock_controller: MagicMock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An HVAC mode the integration doesn't recognise is logged and skipped."""
    mock_controller.get_mode_list.return_value = ["cool", "heat+tank", "heat"]
    await setup_integration(hass, mock_config_entry)

    assert "heat+tank" in caplog.text
    state = hass.states.get(ENTITY_ID)
    assert HVACMode.COOL in state.attributes["hvac_modes"]
    assert HVACMode.HEAT in state.attributes["hvac_modes"]
    assert "heat+tank" not in state.attributes["hvac_modes"]


async def test_turn_on(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """turn_on calls set_power_on on the shared controller."""
    mock_controller.is_on.return_value = False
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    mock_controller.set_power_on.assert_awaited_once_with(MOCK_DEVICE_ID)


async def test_turn_off(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """turn_off calls set_power_off on the shared controller."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    mock_controller.set_power_off.assert_awaited_once_with(MOCK_DEVICE_ID)


async def test_set_temperature(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """set_temperature is forwarded to the controller with the requested value."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 22.0},
        blocking=True,
    )
    mock_controller.set_temperature.assert_awaited_once_with(MOCK_DEVICE_ID, 22.0)


async def test_set_temperature_not_acknowledged_raises(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A controller NACK (timeout/invalid input) surfaces as a service-call error."""
    mock_controller.set_temperature.return_value = False
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 22.0},
            blocking=True,
        )


async def test_set_hvac_mode_off(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Setting HVACMode.OFF powers the device off rather than calling set_mode."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    mock_controller.set_power_off.assert_awaited_once_with(MOCK_DEVICE_ID)
    mock_controller.set_mode.assert_not_awaited()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_set_hvac_mode_powers_on_if_off(
    hass: HomeAssistant, mock_controller: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Setting a non-OFF mode powers the device on first if it was off."""
    mock_controller.is_on.return_value = False
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )
    mock_controller.set_power_on.assert_awaited_once_with(MOCK_DEVICE_ID)
    mock_controller.set_mode.assert_awaited_once_with(MOCK_DEVICE_ID, "cool")
