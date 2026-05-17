# IntesisHome for Home Assistant

A Home Assistant integration for Intesis AC controllers, supporting cloud control (IntesisHome, anywAir, airconwithme) and local control (IntesisBox, IntesisHome Local HTTP).

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/jnimmo)

---

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant and go to **Integrations**
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/jnimmo/hass-intesishome` with category **Integration**
4. Search for **IntesisHome** and install it
5. Restart Home Assistant

### Manual

Download the `custom_components/intesishome` directory into your Home Assistant `custom_components` folder, then restart.

---

## Configuration

1. Restart Home Assistant after installation
2. [![Add IntesisHome integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=intesishome) or go to **Settings → Devices & Services → Add Integration** and search for **IntesisHome**
3. Select your device type (see [Device types](#device-types) below)
4. Enter the required credentials or IP address for your device type
5. Your AC devices will appear as climate entities

---

## Device types

| Device type       | Protocol     | Required details                              |
| ----------------- | ------------ | --------------------------------------------- |
| IntesisHome       | Cloud        | Username and password                         |
| anywAir           | Cloud        | Username and password                         |
| airconwithme      | Cloud        | Username and password                         |
| IntesisBox        | Local (WMP)  | IP address or hostname                        |
| IntesisHome Local | Local (HTTP) | IP address or hostname, username and password |

---

## Supported functionality

Features supported depend on the physical device. The integration detects capabilities at setup time and only exposes features your device supports.

| Feature             | Notes                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------- |
| HVAC modes          | Heat, cool, heat/cool (auto), dry, fan only, off                                                              |
| Target temperature  | Whole or half-degree steps depending on device                                                                |
| Fan modes           | Auto, quiet, low, medium, high (device-dependent)                                                             |
| Vertical swing      | Off, swing, or up to 9 discrete vane positions (device-dependent)                                             |
| Horizontal swing    | Off, swing, or up to 9 discrete vane positions (device-dependent), controlled independently of vertical swing |
| Preset modes        | Eco, comfort, boost (powerful)                                                                                |
| Turn on / turn off  | Independent on/off without changing mode                                                                      |
| Outdoor temperature | Exposed as `outdoor_temp` state attribute where supported                                                     |
| Power consumption   | `power_consumption_heat_kw` and `power_consumption_cool_kw` state attributes where supported                  |

If a command is not acknowledged by the device or cloud within 5 seconds, Home Assistant will display a visible error notification rather than silently dropping the change.

---

## Cloud control

IntesisHome, anywAir, and airconwithme devices connect via a persistent TCP connection established through the Intesis cloud API. This requires outgoing HTTPS access to reach the API endpoint; control then moves to a TCP port returned by the API.

If the connection drops, the integration reconnects automatically. Reconnect behaviour (backoff timing, retries) is handled by the pyintesishome library.

---

## Local control

### HTTP — IntesisHome Local

Experimental local control for devices that expose an HTTP API on port 80 (`http://<ip>/api.cgi`). Requires IP address, username, and password.

| Device        | Supported |
| ------------- | --------- |
| DK-RC-WIFI-1B | Yes       |
| FJ-AC-WIFI-1B | Yes       |
| MH-AC-WIFI-1  | Yes       |
| IS-ASX-WIFI-1 | No        |

### WMP — IntesisBox

IntesisBox devices use the WMP protocol over a local TCP connection. Only an IP address or hostname is required — no cloud account needed.

For dedicated IntesisBox support, the standalone [hass-intesisbox](https://github.com/jnimmo/hass-intesisbox) integration may be better maintained.

---

## Troubleshooting

**Invalid username or password** — verify your credentials in the Intesis mobile app. Cloud accounts are per-service: an IntesisHome account will not work for anywAir.

**No devices found** — ensure at least one device is registered and visible in the Intesis mobile app before setting up the integration.

**Unavailable after connection drop** — the integration reconnects automatically. If a device stays unavailable, check that your Home Assistant instance has outgoing internet access (cloud) or that the device IP has not changed (local).

**Changing mode resets temperature** — some devices reset the setpoint when the HVAC mode changes. The integration re-sends the current target temperature after a mode change to compensate.

## Debug logging

To capture detailed logs for troubleshooting, add the following to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.intesishome: debug
    pyintesishome: debug
```

Restart Home Assistant, reproduce the issue, then download the logs from **Settings → System → Logs**.

## Raising an issue

Before opening an issue, check the [existing issues](https://github.com/jnimmo/hass-intesishome/issues) to see if it has already been reported.

When opening a new issue, please include:

- Your Home Assistant version
- The device type you are using (IntesisHome, anywAir, IntesisBox, etc.)
- Debug logs covering the period when the problem occurred (see above)
- A description of what you expected to happen and what actually happened

---

## About

This integration extends the [IntesisHome core integration](https://www.home-assistant.io/integrations/intesishome) with config flow support, local HTTP control, and additional climate features.

_This project is seeking a new maintainer — I no longer own an Intesis device and have limited time to contribute. Please contact me if you are interested in taking it over._
