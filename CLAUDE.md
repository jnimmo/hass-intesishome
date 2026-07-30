# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (HACS) for Intesis AC controllers. All code lives under
`custom_components/intesishome/`. There is no Python package/build step, no local test suite, and
no local lint config — this is a thin HA integration whose only "runtime" is Home Assistant itself.
All real device-protocol logic (cloud TCP session, local HTTP API, IntesisBox WMP protocol) lives in
the separate `pyintesishome` PyPI package, pinned in `manifest.json`'s `requirements`. This repo
should stay a thin HA-facing layer over that library, not reimplement protocol logic.

## Validation / CI

There is no pytest suite and no local lint command configured (no `pyproject.toml`, `.pylintrc`, or
`requirements_test.txt`). CI (`.github/workflows/`) runs three checks on every PR/push to `master`,
all against GitHub-hosted actions rather than anything invoked locally:

- `hassfest.yaml` — validates `manifest.json` and integration structure against Home Assistant core's
  rules (`home-assistant/actions/hassfest`).
- `lint.yaml` — HACS repository structure validation (`hacs/action`).
- `claude.yml` — Claude Code Action, triggered by `@claude` mentions in issues/PR comments/reviews.

Because there's no local harness, verifying a change generally means: reasoning carefully about the
control flow (see below), and/or manually testing against a real device/account, as PR authors have
done historically (see PR descriptions for hardware used). Don't invent test commands or a lint
config that doesn't exist.

## Architecture

### Shared controller, not per-entity connections

`__init__.py`'s `async_setup_entry` is the only place a `pyintesishome` controller (`IntesisHome`,
`IntesisHomeLocal`, or `IntesisBox`, chosen by `CONF_DEVICE`) is constructed and connected. It's
stored in `hass.data[DOMAIN][entry.entry_id]` as `{"config": entry.data, "controller": controller}`
and every platform (`climate`, `sensor`, `binary_sensor`) reads the *same* controller instance from
there. **No entity should ever open its own connection.** This matters concretely: some gateways
(e.g. MH-AC-WIFI-1) accept exactly one authenticated session and silently evict the previous one on
a second login, so a second connection from an entity would fight the integration's own poll loop.
The controller is torn down once, in `async_unload_entry`.

### `controller_identity()` / `controller.controller_id` can raise

`IntesisBase.controller_id` raises `ValueError` (not `None`) until the device has been identified.
`__init__.py` defines `controller_identity(controller)` to convert that into `None`, and
`async_setup_entry` bails out with `ConfigEntryNotReady` if identity is still unset after `connect()`
returns (covers an IntesisBox that connected without an ID, or a `getinfo` response with no serial).
`config_flow.py` uses the same helper during setup validation. Because of this upstream guard, code
that runs *after* `async_setup_entry` succeeds (i.e. all entity construction) can generally treat
`controller.controller_id` as safe — but don't add a second silent fallback further downstream if it
somehow isn't; letting it raise there is correct (it fails that platform's setup loudly rather than
silently mis-registering a device).

### Device dict is keyed by `str(device_id)`, always

Every `pyintesishome` controller stores per-device state in `self._devices`, and every accessor
(`get_device`, `get_model`, `get_fw_version`, `get_device_property`, etc.) normalizes lookups through
`str(device_id)` internally. Entities should treat `device_id` as an opaque string and not assume
anything about its underlying type from a given controller class.

### Capability gating: entities only exist if the device advertises the datapoint

`entity.py`'s `has_device_property(controller, device_id, prop)` checks whether a key is *present* in
the device dict (not whether it's truthy — a value of `0`/`None` still counts as "present"). Both
`sensor.py` and `binary_sensor.py` use this to decide whether to create an entity at all, rather than
creating an entity that would be permanently unavailable. This is the mechanism that lets one set of
entity descriptions serve local, cloud, and IntesisBox controllers without `isinstance` branching —
prefer extending this mechanism over adding per-controller-type special cases.

For local (`IntesisHomeLocal`) and IntesisBox, the device dict is pre-seeded with `None` for every
advertised uid before any real poll happens; for cloud controllers it's populated during
`poll_status()`, which `async_setup_entry` has already awaited before platforms are forwarded. So by
the time any platform's `async_setup_entry` runs, the device dict is authoritative for capability
checks either way.

### Shared entity base (`entity.py`)

`IntesisEntity` is the base for every entity across all three platforms. It owns:
- `build_device_info()` — constructs the shared `DeviceInfo` so climate + sensors + binary_sensors
  for one physical unit land on the *same* device registry entry (identifiers built as
  `f"{controller.controller_id}-{device_id}"`, a two-element `(DOMAIN, identifier)` tuple —
  `DeviceInfo.identifiers` is typed `set[tuple[str, str]]`, so don't add a third element).
- Update-callback subscription/unsubscription (`async_added_to_hass` / `async_will_remove_from_hass`)
  against the controller's callback list. `remove_update_callback` is a bare `list.remove()` in
  `pyintesishome` and raises `ValueError` if the callback was never registered (reachable if
  `async_added_to_hass` was interrupted) — this is caught deliberately, don't remove the guard.
  Entities must **never** call `controller.stop()` themselves; the controller's lifecycle belongs to
  the integration (`async_unload_entry`), and stopping it from an entity would tear down the shared
  session for every other entity on the config entry.
- A default `available` that tracks `controller.is_connected` and nothing else. A datapoint that's
  merely absent right now should still report `None` ("unknown") and stay *available* — flipping to
  unavailable on a transient missing value would shred recorder long-term statistics and fire
  unavailability automations unnecessarily. `climate.py`'s `IntesisAC` overrides this with its own
  cached `_connected` flag (predates the shared base) rather than using the live property directly.

`climate.py`'s `IntesisAC` sets `_attr_name = None` (the HA "primary entity" pattern) so it inherits
the device's own name for `friendly_name`, while `entity_id` stays whatever was already registered —
this was done deliberately to keep existing installs' `climate.<x>` entity IDs and history/automation
references stable across the `has_entity_name` migration. Its `unique_id` is intentionally the bare
`device_id` (not suffixed like the sensor/binary_sensor entities' `f"{device_id}-{key}"`) for the same
reason — changing it would orphan every existing user's climate entity and its history.

### The `error_code` sensor deliberately does not use `get_error()`

`pyintesishome`'s `ERROR_MAP` is Panasonic/Aquarea-specific and maps code `0` to a truthy
`"H00: No abnormality detected"` string, so `get_error()` reports a "problem" even when there isn't
one, for non-Panasonic hardware. The `error_code` sensor reads the raw `error_code` register instead,
and the `problem` binary_sensor derives from the dedicated `alarm_status` register rather than
`get_error()`, for the same reason. Don't "simplify" these back to `get_error()`.

### Platform list and `DOMAIN`

`PLATFORMS` and `DOMAIN` are defined in `const.py` and re-exported from `__init__.py` (`__all__`)
because `climate.py` and `config_flow.py` still do `from . import DOMAIN` (and `config_flow.py` also
imports `controller_identity` from `__init__.py`) — keep that re-export if refactoring further.
