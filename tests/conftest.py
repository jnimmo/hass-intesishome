"""Fixtures for IntesisHome tests."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME

from custom_components.intesishome.const import DOMAIN


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Force the Home Assistant snapshot extension.

    Pinned here rather than relying on the plugin's own override of this
    fixture: with two installed pytest plugins each defining a fixture named
    "snapshot" (syrupy's own, and pytest-homeassistant-custom-component's),
    resolution order between two *installed plugins* is not guaranteed the
    way it is between a plugin and a project conftest.py. Redefining it in
    our own conftest.py makes this project's version win deterministically,
    so volatile fields (registry ids, timestamps) are masked as <ANY> here
    instead of leaking real random ids into the committed snapshot file.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)

MOCK_DEVICE_ID = "12345"
MOCK_DEVICE_NAME = "MOCK DEVICE"
MOCK_CONTROLLER_ID = "aabbccddeeff"

MOCK_DEVICE = {
    "name": MOCK_DEVICE_NAME,
    "climate_working_mode": True,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components in every test, not just homeassistant/components."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Mock an IntesisHome cloud config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="IntesisHome",
        data={
            CONF_DEVICE: "IntesisHome",
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "password",
        },
        entry_id="mock_entry_id",
    )


@pytest.fixture
def mock_controller() -> Generator[MagicMock]:
    """Mock a pyintesishome IntesisHome controller, autospec'd against the real class."""
    with patch(
        "custom_components.intesishome.IntesisHome", autospec=True
    ) as mock_intesishome:
        controller = mock_intesishome.return_value

        controller.device_type = "IntesisHome"
        controller.controller_id = MOCK_CONTROLLER_ID
        controller.name = MOCK_DEVICE_NAME
        controller.is_connected = True
        controller.error_message = None

        controller.get_devices.return_value = {MOCK_DEVICE_ID: MOCK_DEVICE}
        controller.get_device.return_value = MOCK_DEVICE
        controller.get_model.return_value = "PU-AKB"
        controller.get_fw_version.return_value = "1.0.0"

        controller.has_setpoint_control.return_value = True
        controller.get_mode_list.return_value = ["auto", "heat", "cool", "dry", "fan"]
        controller.get_vertical_swing_list.return_value = ["auto/stop", "swing"]
        controller.get_horizontal_swing_list.return_value = ["auto/stop", "swing"]
        controller.get_fan_speed_list.return_value = [
            "auto",
            "quiet",
            "low",
            "medium",
            "high",
        ]

        controller.is_on.return_value = True
        controller.get_temperature.return_value = 24.0
        controller.get_setpoint.return_value = 21.0
        controller.get_min_setpoint.return_value = 18.0
        controller.get_max_setpoint.return_value = 30.0
        controller.get_fan_speed.return_value = "quiet"
        controller.get_mode.return_value = "cool"
        controller.get_preset_mode.return_value = "eco"
        controller.get_vertical_swing.return_value = "auto/stop"
        controller.get_horizontal_swing.return_value = "auto/stop"
        controller.get_outdoor_temperature.return_value = 26.0
        controller.get_heat_power_consumption.return_value = None
        controller.get_cool_power_consumption.return_value = None
        controller.get_rssi.return_value = None
        controller.get_run_hours.return_value = None

        controller.set_power_on.return_value = True
        controller.set_power_off.return_value = True
        controller.set_temperature.return_value = True
        controller.set_mode.return_value = True
        controller.set_fan_speed.return_value = True
        controller.set_preset_mode.return_value = True
        controller.set_vertical_vane.return_value = True
        controller.set_horizontal_vane.return_value = True

        yield controller
