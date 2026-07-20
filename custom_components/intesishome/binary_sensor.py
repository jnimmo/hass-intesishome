"""Binary sensor platform for IntesisHome."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pyintesishome import IntesisBase

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IntesisEntity, has_device_property

# Sentinel for entities derived from controller state rather than from a
# device datapoint, so they are always created.
_NO_PROPERTY_REQUIRED = None


@dataclass(frozen=True, kw_only=True)
class IntesisBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an IntesisHome binary sensor."""

    value_fn: Callable[[IntesisBase, str], bool | None]
    required_property: str | None = _NO_PROPERTY_REQUIRED
    # True for entities that must keep reporting while the session is down.
    always_available: bool = False


BINARY_SENSOR_TYPES: tuple[IntesisBinarySensorEntityDescription, ...] = (
    IntesisBinarySensorEntityDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        required_property="alarm_status",
        # alarm_status is a dedicated register that rests at 0. Deriving this
        # from get_error() instead would report a permanent problem, because
        # error code 0 maps to a truthy "H00: No abnormality detected".
        value_fn=lambda controller, device_id: bool(
            controller.get_device_property(device_id, "alarm_status")
        ),
    ),
    IntesisBinarySensorEntityDescription(
        key="connectivity",
        translation_key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        # A connectivity sensor that goes unavailable when the connection
        # drops reports nothing at exactly the moment it is needed.
        always_available=True,
        value_fn=lambda controller, device_id: controller.is_connected,
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create binary sensor entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    controller: IntesisBase = entry_data["controller"]
    host: str | None = entry_data["config"].get(CONF_HOST)

    async_add_entities(
        IntesisBinarySensor(controller, device_id, ih_device, host, description)
        for device_id, ih_device in (controller.get_devices() or {}).items()
        for description in BINARY_SENSOR_TYPES
        if description.required_property is _NO_PROPERTY_REQUIRED
        or has_device_property(controller, device_id, description.required_property)
    )


class IntesisBinarySensor(IntesisEntity, BinarySensorEntity):
    """A binary reading from an Intesis controller."""

    entity_description: IntesisBinarySensorEntityDescription

    def __init__(
        self,
        controller: IntesisBase,
        device_id: str,
        ih_device: dict,
        host: str | None,
        description: IntesisBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(controller, device_id, ih_device, host)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}-{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the current state."""
        return self.entity_description.value_fn(self._controller, self._device_id)

    @property
    def available(self) -> bool:
        """Return whether the reading can be trusted."""
        if self.entity_description.always_available:
            return True
        return super().available
