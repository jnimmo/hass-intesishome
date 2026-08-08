"""Switch platform for IntesisHome."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pyintesishome import IntesisBase

from homeassistant import config_entries, core
from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IntesisEntity, has_device_property


@dataclass(frozen=True, kw_only=True)
class IntesisSwitchEntityDescription(SwitchEntityDescription):
    """Describes an IntesisHome switch."""

    is_on_fn: Callable[[IntesisBase, str], bool | None]
    turn_on_fn: Callable[[IntesisBase, str], Awaitable[bool]]
    turn_off_fn: Callable[[IntesisBase, str], Awaitable[bool]]
    required_property: str


SWITCH_TYPES: tuple[IntesisSwitchEntityDescription, ...] = (
    IntesisSwitchEntityDescription(
        key="remote_controller_lock",
        translation_key="remote_controller_lock",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:remote-off",
        required_property="remote_controller_lock",
        is_on_fn=lambda controller, device_id: controller.get_device_property(
            device_id, "remote_controller_lock"
        )
        == 1,
        turn_on_fn=lambda controller, device_id: controller._set_value(
            device_id, 12, 1
        ),
        turn_off_fn=lambda controller, device_id: controller._set_value(
            device_id, 12, 0
        ),
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create switch entities for each datapoint the device advertises."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    controller: IntesisBase = entry_data["controller"]
    host: str | None = entry_data["config"].get(CONF_HOST)

    async_add_entities(
        IntesisSwitch(controller, device_id, ih_device, host, description)
        for device_id, ih_device in (controller.get_devices() or {}).items()
        for description in SWITCH_TYPES
        if has_device_property(controller, device_id, description.required_property)
    )


class IntesisSwitch(IntesisEntity, SwitchEntity):
    """A switch entity for an Intesis controller."""

    entity_description: IntesisSwitchEntityDescription

    def __init__(
        self,
        controller: IntesisBase,
        device_id: str,
        ih_device: dict,
        host: str | None,
        description: IntesisSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(controller, device_id, ih_device, host)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}-{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True if switch is on."""
        return self.entity_description.is_on_fn(self._controller, self._device_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.entity_description.turn_on_fn(self._controller, self._device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.entity_description.turn_off_fn(self._controller, self._device_id)
