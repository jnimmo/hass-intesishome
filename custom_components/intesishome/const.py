"""Constants for the IntesisHome integration."""
from __future__ import annotations

DOMAIN = "intesishome"

PLATFORMS: list[str] = ["binary_sensor", "climate", "sensor"]

# The device_type reported by the library ("intesishome", "intesishome_local",
# "intesisbox", "airconwithme") describes the transport, not who made the
# hardware. All of them are Intesis gateways.
MANUFACTURER = "Intesis"

CLOUD_CONFIGURATION_URL = "https://user.intesishome.com"
