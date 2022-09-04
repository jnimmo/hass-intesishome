# pylint: disable=duplicate-code
"""Config flow for IntesisHome."""
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
    DEVICE_AIRCONWITHME,
    DEVICE_ANYWAIR,
    DEVICE_INTESISBOX,
    DEVICE_INTESISHOME,
    DEVICE_INTESISHOME_LOCAL,
)
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntesisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IntesisHome."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._data = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial device type selection step."""
        # unique_id = user_input["unique_id"]
        # await self.async_set_unique_id(unique_id)
        errors: dict[str, str] = {}
        if user_input is None:
            user_input = {}

        device_type_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=DEVICE_INTESISHOME): vol.In(
                    [
                        DEVICE_AIRCONWITHME,
                        DEVICE_ANYWAIR,
                        DEVICE_INTESISHOME,
                        DEVICE_INTESISBOX,
                        DEVICE_INTESISHOME_LOCAL,
                    ]
                )
            }
        )

        if CONF_DEVICE in user_input:
            self._data.update(user_input)
            return await self.async_step_details()

        return self.async_show_form(
            step_id="user", data_schema=device_type_schema, errors=errors
        )

    async def async_step_details(self, user_input=None):
        """Handle the device connection step."""
        device_type = self._data.get(CONF_DEVICE)
        errors: dict[str, str] = {}
        controller: IntesisBase = None

        cloud_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=device_type): vol.In(
                    [DEVICE_AIRCONWITHME, DEVICE_INTESISHOME]
                ),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        local_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=device_type): vol.In(
                    [DEVICE_INTESISBOX, DEVICE_INTESISHOME_LOCAL]
                ),
                vol.Required(CONF_HOST): str,
            }
        )
        local_auth_schema = local_schema.extend(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        if user_input and CONF_DEVICE in user_input:
            # Select the correct controller
            device_type = user_input[CONF_DEVICE]
            if device_type == DEVICE_INTESISBOX:
                controller = IntesisBox(user_input[CONF_HOST], loop=self.hass.loop)
            elif device_type == DEVICE_INTESISHOME_LOCAL:
                controller = IntesisHomeLocal(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    loop=self.hass.loop,
                    websession=async_get_clientsession(self.hass),
                )
            else:
                controller = IntesisHome(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    loop=self.hass.loop,
                    websession=async_get_clientsession(self.hass),
                    device_type=device_type,
                )

        # Try to attempt a connection
        try:
            if controller and isinstance(controller, IntesisBox):
                await controller.connect()
            elif controller:
                await controller.poll_status()
        except IHAuthenticationError:
            errors["base"] = "invalid_auth"
            controller = None
        except IHConnectionError:
            errors["base"] = "cannot_connect"
            controller = None
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
            controller = None

        if controller:
            if len(controller.get_devices()) == 0:
                errors["base"] = "no_devices"

            if "base" not in errors:
                unique_id = (
                    f"{controller.device_type}_{controller.controller_id}".lower()
                )
                name = f"{controller.device_type} {controller.name}"

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # Pass the controller through to the platform setup
                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN].setdefault("controller", {})
                self.hass.data[DOMAIN]["controller"][unique_id] = controller

                return self.async_create_entry(
                    title=name,
                    data=user_input,
                )

        # Show the correct configuration schema
        if device_type == DEVICE_INTESISBOX:
            return self.async_show_form(
                step_id="details", data_schema=local_schema, errors=errors
            )
        if device_type == DEVICE_INTESISHOME_LOCAL:
            return self.async_show_form(
                step_id="details", data_schema=local_auth_schema, errors=errors
            )
        return self.async_show_form(
            step_id="details", data_schema=cloud_schema, errors=errors
        )

    async def async_step_import(self, import_data) -> FlowResult:
        """Handle configuration by yaml file."""
        return await self.async_step_user(import_data)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class NoDevices(exceptions.HomeAssistantError):
    """Error to indicate the account has no devices."""
