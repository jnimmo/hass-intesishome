"""Controller for Intesis "AC Cloud Control" (accloud.intesis.com).

pyintesishome.IntesisHome talks to user.intesishome.com:5210, the legacy
IntesisHome socket API. As of August 2026 that service no longer accepts
connections -- the hostname still resolves and serves a 302 to
https://accloud.intesis.com, but nothing answers on the command port
anymore. Intesis now only offers account holders the "AC Cloud Control" web
portal, which has no documented API.

This class was written by capturing a browser session against that portal
(login, device list, status panel, and each control action as a separate
network request) and reproducing the same requests here: log in, scrape
device state out of the HTML the portal returns, and POST the same uid/value
pairs the on-page buttons send. It subclasses IntesisBase rather than
IntesisHome, so it inherits INTESIS_MAP-based property decoding and every
get_*()/set_*() helper built on top of self._devices for free -- only login,
polling and _set_value are new.

Caveats, since there is no documented API to check this against:

- CONFIG_MODE_MAP and CONFIG_FAN_MAP below are inferred from which mode/fan
  buttons the panel rendered for one account's device (a ducted unit
  offering all 5 modes and a 4-speed+auto fan), not read from the page
  itself. A device with a smaller mode/fan set would need these adjusted,
  or -- better -- them being derived from the actual buttons rendered per
  device rather than hardcoded (left for a follow-up; see _fetch_devices).
- The CSRF field regex in _get_csrf_token() was written against the *login
  POST* captured in a HAR file, not the login GET page's HTML (which
  wasn't captured). If login fails with "Could not find CSRF token", view
  source on https://accloud.intesis.com/login and adjust _CSRF_RE to match
  the actual hidden input's attribute order.
- No model/firmware version is scraped, so those two device-info fields
  will show as unknown. Cosmetic only.
- There is no push channel, so state updates are polled every
  _poll_interval seconds instead of arriving instantly like the old socket
  did. Commands still apply immediately; only *seeing* an externally-made
  change (e.g. from the AC's own remote) lags by up to that interval.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

import aiohttp

from pyintesishome import IntesisBase
from pyintesishome.exceptions import IHAuthenticationError, IHConnectionError

_LOGGER = logging.getLogger("pyintesishome")

BASE_URL = "https://accloud.intesis.com"
LOGIN_URL = f"{BASE_URL}/login"
DEVICE_LIST_URL = f"{BASE_URL}/device/list"
VISTA_URL = f"{BASE_URL}/panel/vista"
SET_VAL_URL = f"{BASE_URL}/device/setVal"

# The login page carries two CSRF inputs: a generic page-level "_csrf_token"
# and a form-scoped "signin[_csrf_token]". The login POST needs the latter -
# confirmed from a real GET /login response, name="signin[_csrf_token]" is
# the correct field, just not necessarily the first "csrf"-mentioning input
# on the page.
_CSRF_INPUT_RE = re.compile(r'<input\b[^>]*name="signin\[_csrf_token\]"[^>]*>', re.IGNORECASE)
_VALUE_ATTR_RE = re.compile(r'value="([^"]*)"')
_USER_ID_RE = re.compile(r"userId=(\d+)")
_DEVICE_LI_RE = re.compile(r'id="device_(\d+)"')
_TEMP_RE = re.compile(r'<div class="key_value">([\d.\-]+)&deg;C</div>')
_SETPOINT_RE = re.compile(r'id="setPoint_\d+"[^>]*>([\d.]+)<')
_ONOFF_RE = re.compile(r"var selectedOnOff = (\d+);")
_MODE_RE = re.compile(r"var selectedUsermode = (\d+);")
_FAN_RE = re.compile(r"var selectedfanspeed = (\d+);")

# Inferred, not read from the page - see module docstring.
CONFIG_MODE_MAP = 31  # bits 1+2+4+8+16: auto/heat/dry/fan/cool all present
CONFIG_FAN_MAP = {0: "auto", 1: "quiet", 2: "low", 3: "medium", 4: "high"}

# The vista partial doesn't appear to expose the setpoint's allowed range
# anywhere we've found, so these are hardcoded fallbacks (typical ducted
# split-system range) rather than scraped. Without *some* value here,
# IntesisBase.get_min_setpoint()/get_max_setpoint() return None, which
# leaves ClimateEntity.min_temp/max_temp as None -- and the round
# thermostat card cannot compute where to draw the setpoint on the dial
# without a range, so it renders the dial blank/at-zero even though the
# underlying target temperature is correct. Adjust these if your unit's
# real range differs.
CONFIG_SETPOINT_MIN = 18.0
CONFIG_SETPOINT_MAX = 25.0


class IntesisAccloud(IntesisBase):
    """Cloud controller for Intesis "AC Cloud Control" (accloud.intesis.com)."""

    def __init__(
        self,
        username,
        password,
        loop=None,
        websession=None,
        device_type="intesishome_accloud",
    ) -> None:
        """Initialize the AC Cloud controller."""
        super().__init__(
            device_type=device_type,
            username=username,
            password=password,
            loop=loop,
            websession=websession,
        )
        self._authenticated = False
        self._user_id: str | None = None
        self._poll_task: asyncio.Task = None
        self._poll_interval = 30

    async def _get_csrf_token(self) -> str:
        """Fetch the login page and pull the signin[_csrf_token] value out of it.

        The page also carries an unrelated page-level "_csrf_token" field;
        _CSRF_INPUT_RE is anchored to the form-scoped field name specifically
        so it isn't picked up by mistake.
        """
        async with self._web_session.get(LOGIN_URL) as resp:
            html = await resp.text()

        tag_match = _CSRF_INPUT_RE.search(html)
        if not tag_match:
            _LOGGER.error(
                "AC Cloud login page has no signin[_csrf_token] input. "
                "First 500 chars of <form>: %s",
                (html[html.find("<form") : html.find("<form") + 500])
                if "<form" in html
                else "no <form> tag found",
            )
            raise IHConnectionError(
                "Could not find the signin[_csrf_token] field on the AC "
                "Cloud login page - the login form markup may have changed"
            )

        value_match = _VALUE_ATTR_RE.search(tag_match.group(0))
        if not value_match:
            _LOGGER.error(
                "Found signin[_csrf_token] input but no value attribute: %s",
                tag_match.group(0),
            )
            raise IHConnectionError(
                "Found the signin[_csrf_token] field but it has no value"
            )

        return value_match.group(1)

    async def _login(self) -> None:
        """Authenticate against AC Cloud and capture the session cookie + userId."""
        try:
            csrf_token = await self._get_csrf_token()
            payload = {
                "signin[username]": self._username,
                "signin[password]": self._password,
                "signin[_csrf_token]": csrf_token,
            }
            async with self._web_session.post(
                LOGIN_URL, data=payload, allow_redirects=False
            ) as resp:
                location = resp.headers.get("Location", "")
                if resp.status != 302 or "login" in location:
                    raise IHAuthenticationError("AC Cloud login rejected")
        except aiohttp.ClientError as exc:
            raise IHConnectionError(f"Error connecting to AC Cloud: {exc}") from exc

        self._controller_id = self._username
        self._controller_name = self._username
        self._authenticated = True

    def _get_fan_map(self, device_id):
        """Return this device's fan-speed value map."""
        return self.get_device_property(device_id, "config_fan_map")

    async def _parse_response(self, decoded_data):
        """Unused - AC Cloud has no persistent socket to push frames over."""
        raise NotImplementedError()

    async def _fetch_devices(self) -> None:
        """Discover the account's devices from the device list page."""
        async with self._web_session.get(DEVICE_LIST_URL) as resp:
            html = await resp.text()

        found_ids = _DEVICE_LI_RE.findall(html)
        if not found_ids and self._devices:
            # We previously knew about devices but this page has none -
            # almost always means the session cookie expired and we were
            # redirected to a login page instead of the device list (aiohttp
            # follows redirects by default, so this happens silently rather
            # than as an HTTP error). Force a re-login on the next poll
            # rather than quietly going stale forever.
            _LOGGER.warning(
                "AC Cloud device list returned no devices though %d were "
                "previously known; assuming the session expired and forcing "
                "re-authentication on the next poll",
                len(self._devices),
            )
            self._authenticated = False
            return

        for device_id in dict.fromkeys(found_ids):
            existing = self._devices.get(device_id, {})
            self._devices[device_id] = {
                **existing,
                "name": existing.get("name") or f"Intesis {device_id}",
            }
            # Static per-device config the vista page doesn't expose a raw
            # code for - see module docstring caveats.
            self._update_device_state(device_id, 61, CONFIG_MODE_MAP)
            self._devices[device_id]["config_fan_map"] = CONFIG_FAN_MAP
            # uid 35/36 = setpoint_min/setpoint_max, stored as tenths of a
            # degree to match how IntesisBase.get_min_setpoint()/
            # get_max_setpoint() divide by 10.
            self._update_device_state(device_id, 35, round(CONFIG_SETPOINT_MIN * 10))
            self._update_device_state(device_id, 36, round(CONFIG_SETPOINT_MAX * 10))

    async def _fetch_device_status(self, device_id: str) -> None:
        """Scrape one device's current state out of its status panel."""
        headers = {"X-Requested-With": "XMLHttpRequest"}
        async with self._web_session.get(
            VISTA_URL, params={"id": device_id}, headers=headers
        ) as resp:
            html = await resp.text()

        if self._user_id is None and (match := _USER_ID_RE.search(html)):
            self._user_id = match.group(1)

        onoff_match = _ONOFF_RE.search(html)
        mode_match = _MODE_RE.search(html)
        fan_match = _FAN_RE.search(html)
        setpoint_match = _SETPOINT_RE.search(html)
        temp_match = _TEMP_RE.search(html)

        if onoff_match:
            self._update_device_state(device_id, 1, int(onoff_match.group(1)))
        if mode_match:
            self._update_device_state(device_id, 2, int(mode_match.group(1)))
        if fan_match:
            self._update_device_state(device_id, 4, int(fan_match.group(1)))
        else:
            # Fixed via a HAR capture (2026-08-15): the real JS variable is
            # lowercase "selectedfanspeed", not "selectedFanSpeed" as
            # originally guessed. If this ever fires again it more likely
            # means the session expired (see the check below) than that the
            # variable name has changed again.
            _LOGGER.debug(
                "AC Cloud vista page for device %s has no selectedfanspeed "
                "match this poll",
                device_id,
            )
        if setpoint_match:
            self._update_device_state(
                device_id, 9, round(float(setpoint_match.group(1)) * 10)
            )
        if temp_match:
            self._update_device_state(
                device_id, 10, round(float(temp_match.group(1)) * 10)
            )

        if not any(
            (onoff_match, mode_match, fan_match, setpoint_match, temp_match)
        ):
            # Nothing at all matched - the most likely explanation is that
            # the session expired between _fetch_devices() and here and this
            # response is a login page rather than the status panel.
            _LOGGER.warning(
                "AC Cloud status panel for device %s matched none of the "
                "expected fields; forcing re-authentication on the next poll",
                device_id,
            )
            self._authenticated = False

    async def connect(self) -> None:
        """Log in, discover devices, fetch initial state, and start polling."""
        if self._connected or self._connecting:
            return
        self._connecting = True
        try:
            await self.poll_status()
            self._connected = True
            self._connection_retries = 0
            self._last_successful_update = datetime.now(timezone.utc)
            self._poll_task = self._event_loop.create_task(self._poll_loop())
        except (IHAuthenticationError, IHConnectionError):
            self._connected = False
            raise
        finally:
            self._connecting = False

    async def poll_status(self, sendcallback: bool = False):
        """Refresh device state.

        Called directly (once, unauthenticated) by the config flow to
        validate credentials, and repeatedly by _poll_loop() once connected.
        """
        try:
            if not self._authenticated:
                await self._login()
            await self._fetch_devices()
            device_id = None
            for device_id in list(self._devices):
                await self._fetch_device_status(device_id)
            self._last_successful_update = datetime.now(timezone.utc)
        except aiohttp.ClientError as exc:
            raise IHConnectionError(f"Error polling AC Cloud: {exc}") from exc

        if sendcallback and device_id is not None:
            await self._send_update_callback(device_id=device_id)
        return self._devices

    async def _poll_loop(self) -> None:
        """Background refresh loop - the closest equivalent to a push socket."""
        try:
            while True:
                await asyncio.sleep(self._poll_interval)
                try:
                    await self.poll_status(sendcallback=True)
                except IHConnectionError as exc:
                    _LOGGER.warning("AC Cloud poll failed, will retry: %s", exc)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Stop polling and tear down the session."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        await super().stop()

    async def _set_value(self, device_id, uid, value) -> bool:
        """POST a uid/value command, matching what the panel's buttons send."""
        if self._user_id is None:
            # Should already be populated from the first status fetch in
            # connect()/poll_status(), but guard rather than send a
            # malformed request if it somehow isn't.
            _LOGGER.error("Cannot send command: AC Cloud userId not yet known")
            return False

        headers = {"X-Requested-With": "XMLHttpRequest"}
        # Confirmed against a HAR capture: the real panel sends id/uid/value/
        # userId as URL query parameters with an empty body
        # (Content-Length: 0), not as a form-encoded body. Do not change
        # this to data= without a fresh capture confirming otherwise.
        params = {"id": device_id, "uid": uid, "value": value, "userId": self._user_id}
        try:
            async with self._web_session.post(
                SET_VAL_URL, params=params, headers=headers
            ) as resp:
                text = (await resp.text()).strip()
                if text != "OK":
                    _LOGGER.warning(
                        "AC Cloud setVal for device %s uid %s value %s did "
                        "not return OK (status %s): %.200s",
                        device_id,
                        uid,
                        value,
                        resp.status,
                        text,
                    )
                return text == "OK"
        except aiohttp.ClientError as exc:
            _LOGGER.error("Error sending command to AC Cloud: %s", exc)
            return False