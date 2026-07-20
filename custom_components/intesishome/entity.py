"""Shared entity plumbing for the IntesisHome integration.

Every platform builds its device_info here so the climate entity and the
diagnostic sensors always land on the same device registry entry. If each
platform built its own, a single mismatched identifier would silently split
one AC unit into two devices.
"""
from __future__ import annotations

import logging

from pyintesishome import IntesisBase
from pyintesishome.const import DEVICE_INTESISBOX, DEVICE_INTESISHOME_LOCAL

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CLOUD_CONFIGURATION_URL, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

LOCAL_DEVICE_TYPES = (DEVICE_INTESISHOME_LOCAL, DEVICE_INTESISBOX)


def has_device_property(
    controller: IntesisBase, device_id: str, prop: str
) -> bool:
    """Return True when the device advertises the given property.

    Used to decide whether an entity should exist at all. IntesisHomeLocal
    seeds a key for every datapoint the gateway advertises (see
    ``get_datapoints``), and the cloud controllers populate their keys during
    ``poll_status()`` -- which ``async_setup_entry`` has already awaited by the
    time a platform is forwarded. So the device dict is authoritative for all
    controller types, and reading it avoids having to special-case each one.

    A hardware unit that does not support a datapoint never gets the key, so
    the entity is not created rather than existing permanently unavailable.
    """
    return prop in (controller.get_device(device_id) or {})


def build_device_info(
    controller: IntesisBase,
    device_id: str,
    ih_device: dict,
    host: str | None = None,
) -> DeviceInfo:
    """Build the device registry entry shared by every platform."""
    # A two-element identifier, as DeviceInfo requires. controller_id is folded
    # into the string rather than becoming a third tuple element so the same
    # device id appearing under two different cloud accounts still resolves to
    # two distinct devices.
    identifier = f"{controller.controller_id}-{device_id}"

    if controller.device_type in LOCAL_DEVICE_TYPES and host:
        configuration_url = f"http://{host}"
    else:
        configuration_url = CLOUD_CONFIGURATION_URL

    return DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        # The fallback is load-bearing: with _attr_name = None on the climate
        # entity, a device with no name renders its friendly name as the raw
        # entity_id.
        name=ih_device.get("name") or f"Intesis {device_id}",
        manufacturer=MANUFACTURER,
        model=controller.get_model(device_id),
        sw_version=controller.get_fw_version(device_id),
        configuration_url=configuration_url,
    )


class IntesisEntity(Entity):
    """Base for every IntesisHome entity.

    Owns the update-callback subscription so platforms do not each
    reimplement it.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        controller: IntesisBase,
        device_id: str,
        ih_device: dict,
        host: str | None = None,
    ) -> None:
        """Initialise shared state."""
        self._controller: IntesisBase = controller
        self._device_id: str = str(device_id)
        self._ih_device: dict = ih_device
        self._device_name: str = ih_device.get("name")
        self._device_type: str = controller.device_type
        self._attr_device_info = build_device_info(
            controller, device_id, ih_device, host
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        self._controller.add_update_callback(self.async_update_callback)

    async def async_will_remove_from_hass(self) -> None:
        """Detach from the shared controller's update stream.

        The controller's lifecycle is owned by the integration (constructed in
        __init__.async_setup_entry, stopped in async_unload_entry) so an entity
        must NOT call stop() here. Doing so would tear down the shared
        controller when a single entity is removed or disabled, and would race
        the integration-level stop on entry unload.
        """
        try:
            self._controller.remove_update_callback(self.async_update_callback)
        except ValueError:
            # remove_update_callback is a bare list.remove(), which raises if
            # the callback was never registered -- reachable when
            # async_added_to_hass was interrupted.
            pass

    async def async_update_callback(self, device_id=None) -> None:
        """Let HA know the controller has new data."""
        if not device_id or self._device_id == str(device_id):
            self.async_schedule_update_ha_state(True)

    @property
    def available(self) -> bool:
        """Availability tracks the controller session, nothing else.

        A value that is merely absent right now must stay available and
        report None (rendered as "unknown"); flipping to unavailable would
        break recorder statistics and fire unavailability automations.
        """
        return self._controller.is_connected
