"""Constants for the IntesisHome integration."""
from __future__ import annotations

DOMAIN = "intesishome"

PLATFORMS: list[str] = ["binary_sensor", "button", "climate", "sensor", "switch"]

# The device_type reported by the library ("intesishome", "intesishome_local",
# "intesisbox", "airconwithme") describes the transport, not who made the
# hardware. All of them are Intesis gateways.
MANUFACTURER = "Intesis"

# The legacy socket API (user.intesishome.com:5210) that DEVICE_INTESISHOME /
# DEVICE_AIRCONWITHME / DEVICE_ANYWAIR connect to via pyintesishome.IntesisHome
# stopped accepting connections in August 2026 - the hostname still resolves
# and 302s a browser to the URL below, but nothing answers on the command
# port. DEVICE_ACCLOUD (accloud_controller.IntesisAccloud) talks to that
# replacement portal directly instead. The old device types are left in place
# rather than removed, in case Intesis ever restores the socket API.
DEVICE_ACCLOUD = "intesishome_accloud"

CLOUD_CONFIGURATION_URL = "https://accloud.intesis.com"