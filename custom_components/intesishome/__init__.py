# pylint: disable=duplicate-code
"""The IntesisHome integration."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_vendor_path = _Path(__file__).parent / "_vendor"
if _vendor_path.is_dir():
    _vendor_str = str(_vendor_path)
    if _vendor_str not in _sys.path:
        _sys.path.insert(0, _vendor_str)
    for _name in list(_sys.modules):
        if _name == "pyintesishome" or _name.startswith("pyintesishome."):
            del _sys.modules[_name]
del _sys, _Path, _vendor_path

import logging

from pyintesishome import (
    IHAuthenticationError,
    IHConnectionError,
    IntesisBase,
    IntesisBox,
    IntesisHome,
    IntesisHomeLocal,
)
from pyintesishome.const import (
    DEVICE_INTESISBOX,
    DEVICE_INTESISHOME_LOCAL,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DOMAIN = "intesishome"
PLATFORMS = ["climate"]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntesisHome from a config entry.

    Constructs the shared controller, performs the initial poll, and stores
    the controller on hass.data so each platform (climate, select, ...)
    works against the same TCP session.
    """
    hass.data.setdefault(DOMAIN, {})

    config = entry.data
    ih_user = config.get(CONF_USERNAME)
    ih_host = config.get(CONF_HOST)
    ih_pass = config.get(CONF_PASSWORD)
    device_type = config.get(CONF_DEVICE)
    websession = async_get_clientsession(hass)

    controller: IntesisBase
    if device_type == DEVICE_INTESISBOX:
        controller = IntesisBox(ih_host, loop=hass.loop)
    elif device_type == DEVICE_INTESISHOME_LOCAL:
        controller = IntesisHomeLocal(
            ih_host, ih_user, ih_pass, loop=hass.loop, websession=websession
        )
    else:
        controller = IntesisHome(
            ih_user,
            ih_pass,
            hass.loop,
            websession=websession,
            device_type=device_type,
        )

    # Authenticate and bring the connection up in one shot. Doing it here
    # (rather than in the entity's async_added_to_hass) avoids a
    # duplicate HTTP poll_status, gives the platforms a fully-live
    # controller, and removes the race that produced the "Setup of
    # climate platform taking over 10 seconds" warning during HA boot.
    try:
        await controller.connect()
    except IHAuthenticationError as exc:
        _LOGGER.error("Invalid IntesisHome credentials for %s", device_type)
        raise ConfigEntryAuthFailed from exc
    except IHConnectionError as exc:
        _LOGGER.error("Error connecting to the %s server: %s", device_type, exc)
        raise ConfigEntryNotReady from exc

    if not controller.get_devices():
        await controller.stop()
        _LOGGER.error(
            "No devices returned from %s API: %s",
            device_type,
            controller.error_message,
        )
        raise ConfigEntryNotReady("No devices returned from API")

    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "controller": controller,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and stop the controller."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data and (controller := data.get("controller")):
            await controller.stop()
    return unload_ok
