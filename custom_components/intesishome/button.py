"""Button platform for IntesisHome."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pyintesishome import IntesisBase

from homeassistant import config_entries, core
from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IntesisEntity, has_device_property


@dataclass(frozen=True, kw_only=True)
class IntesisButtonEntityDescription(ButtonEntityDescription):
    """Describes an IntesisHome button."""

    press_fn: Callable[[IntesisBase, str], Awaitable[bool]]
    required_property: str


BUTTON_TYPES: tuple[IntesisButtonEntityDescription, ...] = (
    IntesisButtonEntityDescription(
        key="reset_filter",
        translation_key="reset_filter",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:filter-remove",
        required_property="filter_clean",
        press_fn=lambda controller, device_id: controller._set_value(
            device_id, 184, 0
        ),
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create button entities for each datapoint the device advertises."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    controller: IntesisBase = entry_data["controller"]
    host: str | None = entry_data["config"].get(CONF_HOST)

    async_add_entities(
        IntesisButton(controller, device_id, ih_device, host, description)
        for device_id, ih_device in (controller.get_devices() or {}).items()
        for description in BUTTON_TYPES
        if has_device_property(controller, device_id, description.required_property)
    )


class IntesisButton(IntesisEntity, ButtonEntity):
    """A button entity for an Intesis controller."""

    entity_description: IntesisButtonEntityDescription

    def __init__(
        self,
        controller: IntesisBase,
        device_id: str,
        ih_device: dict,
        host: str | None,
        description: IntesisButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(controller, device_id, ih_device, host)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}-{description.key}"

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.press_fn(self._controller, self._device_id)
