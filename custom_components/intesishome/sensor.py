"""Sensor platform for IntesisHome.

Exposes readings the controller already fetches on every poll but which the
climate entity either buries in attributes or discards. Nothing here opens its
own connection -- every value comes from the shared controller in hass.data,
which matters because some gateways (MH-AC-WIFI-1, for one) accept exactly one
authenticated session and evict the previous one on any second login.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyintesishome import IntesisBase

from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_HOST,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IntesisEntity, has_device_property


@dataclass(frozen=True, kw_only=True)
class IntesisSensorEntityDescription(SensorEntityDescription):
    """Describes an IntesisHome sensor."""

    value_fn: Callable[[IntesisBase, str], Any]
    # Device-dict key that must be advertised for this entity to be created.
    required_property: str


SENSOR_TYPES: tuple[IntesisSensorEntityDescription, ...] = (
    IntesisSensorEntityDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        # Deliberately not diagnostic: this is a measurement of the world that
        # people graph and drive automations from, not integration health.
        required_property="outdoor_temp",
        value_fn=lambda controller, device_id: controller.get_outdoor_temperature(
            device_id
        ),
    ),
    IntesisSensorEntityDescription(
        key="run_hours",
        translation_key="run_hours",
        device_class=SensorDeviceClass.DURATION,
        # Monotonic, with an implicit reset if the hardware is replaced.
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        # DURATION ships no default icon.
        icon="mdi:timer-outline",
        required_property="working_hours",
        value_fn=lambda controller, device_id: controller.get_run_hours(device_id),
    ),
    IntesisSensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        # A bare vendor error number means nothing to most users -- the
        # problem binary_sensor is the user-facing signal.
        entity_registry_enabled_default=False,
        icon="mdi:alert-circle-outline",
        required_property="error_code",
        # Reads the raw register rather than get_error(). The library's
        # ERROR_MAP holds Panasonic Aquarea codes and maps 0 to
        # "H00: No abnormality detected", so get_error() returns a truthy
        # string when nothing is wrong, with text that is wrong for other
        # manufacturers' hardware.
        value_fn=lambda controller, device_id: controller.get_device_property(
            device_id, "error_code"
        ),
    ),
    IntesisSensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        required_property="rssi",
        value_fn=lambda controller, device_id: controller.get_rssi(device_id),
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensor entities for each datapoint the device advertises."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    controller: IntesisBase = entry_data["controller"]
    host: str | None = entry_data["config"].get(CONF_HOST)

    async_add_entities(
        IntesisSensor(controller, device_id, ih_device, host, description)
        for device_id, ih_device in (controller.get_devices() or {}).items()
        for description in SENSOR_TYPES
        if has_device_property(controller, device_id, description.required_property)
    )


class IntesisSensor(IntesisEntity, SensorEntity):
    """A single reading from an Intesis controller."""

    entity_description: IntesisSensorEntityDescription

    def __init__(
        self,
        controller: IntesisBase,
        device_id: str,
        ih_device: dict,
        host: str | None,
        description: IntesisSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(controller, device_id, ih_device, host)
        self.entity_description = description
        # The climate entity's unique_id is the bare device_id, so a suffixed
        # key can never collide with it.
        self._attr_unique_id = f"{device_id}-{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the current reading, or None when it is not known yet."""
        return self.entity_description.value_fn(self._controller, self._device_id)
