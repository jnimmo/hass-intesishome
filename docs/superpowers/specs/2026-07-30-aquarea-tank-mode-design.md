# Aquarea tank (DHW) mode support

## Context

Panasonic Aquarea AW heat-pump units report an `operating_mode` datapoint
(pyintesishome uid 58) instead of the plain `mode` datapoint (uid 2) other
Intesis-connected hardware uses. `operating_mode`'s values combine the base
space-conditioning mode with a domestic-hot-water (DHW) "tank" bit: `heat`,
`heat+tank`, `tank`, `cool+tank`, `cool`, `auto`, `auto+tank`, `maintenance`.
Dry and fan are never present for these devices — `operating_mode`'s bitmap
(`OPERATING_MODE_BITS`) has no dry/fan bits at all, so a tank-capable device's
`get_mode_list()` only ever yields a subset of `{heat, cool, auto, tank}` plus
their `+tank` combos.

[GitHub issue #2](https://github.com/jnimmo/hass-intesishome/issues/2) reports
the original crash this caused: `climate.py`'s `MAP_IH_TO_HVAC_MODE[mode]`
raised `KeyError` on `"heat+tank"`. That was fixed by skipping unrecognized
modes with a warning instead of raising — but that fix only stopped the crash.
It didn't make tank functional: `get_mode_list()` still drops every `+tank`
combo from the selectable `hvac_modes`, and `async_update()` still does
`self._hvac_mode = MAP_IH_TO_HVAC_MODE.get(mode)`, so a unit actively running
`heat+tank` reports `self._hvac_mode = None` while `self._power` is true —
the climate card shows an invalid/unknown state. An earlier abandoned attempt
([`aquarea-tank-presets` branch](https://github.com/jnimmo/hass-intesishome/tree/aquarea-tank-presets))
tried folding tank into `preset_mode`, but `preset_mode` already drives a
different datapoint (`climate_working_mode`, uid 42: comfort/eco/powerful),
and was never finished.

`tank_water_temperature`, `tank_setpoint_temperature`,
`thermoshift_tank_eco/powerful` are all DHW-specific — there is no "tank
cooling" concept anywhere in the protocol. `"+tank"` always means "and also
heat the hot water tank," independent of what the base word does to the room:
`cool+tank` cools the house and heats the tank.

pyintesishome's public API for writing `operating_mode` is the existing
`set_mode(device_id, mode)` / `get_mode(device_id)` pair (shared with the
`mode` datapoint on non-Aquarea hardware) — there is no separate tank-specific
setter. `_set_gen_mode` and `_set_thermo_shift` also touch tank-adjacent
datapoints (`tank_working_mode`, thermoshift offsets) but are private, and
`tank_setpoint_temperature`/`quiet_mode` have no public setter in the library
at all — those stay out of scope (see "Out of scope" below).

## Goals

- Let users turn Aquarea DHW tank heating on/off from Home Assistant, without
  needing pyintesishome changes.
- Fix the climate entity's invalid/unknown `hvac_mode` display bug for units
  actively running a `+tank` combo.
- Don't let unrelated climate-entity actions (changing HVAC mode, turning the
  climate off) silently kill tank heating as a side effect.
- Surface tank power draw, since the library already computes it but nothing
  exposes it.

## Non-goals

- Tank target temperature control (`tank_setpoint_temperature`) — no public
  setter in pyintesishome.
- Tank working mode / comfort-eco-powerful for the tank specifically
  (`tank_working_mode`) — same reason.
- Quiet/silent mode (`quiet_mode`) — same reason.
- Thermoshift offset tuning — installer-level, same reason, and out of scope
  in spirit even if it became possible.

These all require new public methods on `IntesisBase`/`IntesisHome` in the
`pyintesishome` package first, which is a separate repo/release outside this
project's scope. Noted here so they're not forgotten, not because they're
being deferred within this project.

## Design

### 1. New `custom_components/intesishome/switch.py`

Mirrors the existing `sensor.py`/`binary_sensor.py` shape: `IntesisEntity`
base, one `EntityDescription`-driven type for now (tank), capability-gated
the same way those platforms already gate entities.

- **Gating:** created only when
  `has_device_property(controller, device_id, "operating_mode")` — the
  Aquarea-specific datapoint tank combos live in. This is the same
  presence-check idiom `entity.py`'s `has_device_property` already provides
  for sensor/binary_sensor; no new gating mechanism needed.
- `unique_id = f"{device_id}-tank"`, translation key `tank`,
  `entity_registry_enabled_default=False` — this actuates a physical
  water-heating element on hardware this repo hasn't been tested against
  directly, so it's opt-in like `rssi`/`error_code`.
- **`is_on`:** `"tank" in (controller.get_mode(device_id) or "")` — true for
  `tank`, `heat+tank`, `cool+tank`, `auto+tank`.
- **Turn on:**
  - current mode is `heat`, `cool`, or `auto` → `set_mode(device_id,
    f"{mode}+tank")`
  - current mode already contains `tank` → no-op, already on
  - device is off, or mode is `maintenance`/unrecognized → `set_power_on`
    then `set_mode(device_id, "tank")`
- **Turn off:**
  - current mode is a `+tank` combo → `set_mode(device_id, base)` (strip
    the suffix, e.g. `heat+tank` → `heat`)
  - current mode is plain `tank` → `set_power_off(device_id)` (nothing else
    was running; this is the only path that fully powers the unit down)
  - current mode has no tank bit already → no-op, already off
- Both directions raise `HomeAssistantError` on a controller NACK, matching
  `climate.py`'s `_expect_ack` convention (see CLAUDE.md's documented
  error-surfacing rationale). Whether this reuses `climate.py`'s helper or
  duplicates the three-line check is an implementation-plan-time call, not a
  design one — two call sites don't yet justify moving it to `entity.py`.

### 2. `climate.py` changes

**`MAP_IH_TO_HVAC_MODE` gains:**

```python
"heat+tank": HVACMode.HEAT,
"cool+tank": HVACMode.COOL,
"auto+tank": HVACMode.HEAT_COOL,
"tank": HVACMode.OFF,
```

`"maintenance"` stays unmapped (skipped + warned, same as any other
unrecognized mode today). `"tank"` maps to `HVACMode.OFF` rather than staying
unmapped: once turning the climate off can leave the unit in plain `tank`
mode (see below), that's a real steady-state the entity has to represent, and
`OFF` is the correct read of it — no space conditioning is running. The tank
switch independently reports `on` during this state; the two entities
describe two orthogonal things (room conditioning vs. DHW).

**`MAP_HVAC_MODE_TO_IH` becomes an explicit table**, not
`{v: k for k, v in MAP_IH_TO_HVAC_MODE.items()}`. Once the forward map has
both `"heat"` and `"heat+tank"` pointing at `HVACMode.HEAT`, reversing it
via dict comprehension silently collides — whichever key is processed last
wins, so selecting "Heat" from the climate card could send `"heat+tank"`
instead of `"heat"`, forcing tank on as an undocumented side effect of
picking a plain HVAC mode. The explicit table only ever resolves to base
strings (`heat`, `cool`, `auto`, `dry`, `fan`).

**`async_set_hvac_mode`, for any non-OFF target:** before calling
`set_mode`, check whether tank is currently active
(`"tank" in (get_mode(device_id) or "")`); if so, append `+tank` to the
target base mode instead of sending it plain. A user switching their house
from Heat to Cool almost certainly still wants their hot water heated —
dropping tank as an unannounced side effect of an unrelated HVAC-mode change
would be a functional regression, not just a UX inconsistency. This only
ever needs to handle `heat`/`cool`/`auto`, since dry/fan can't appear for a
tank-capable device's `hvac_modes` in the first place.

**`async_set_hvac_mode(HVACMode.OFF)` / `async_turn_off`:** if tank is
currently active, call `set_mode(device_id, "tank")` instead of
`set_power_off`. This preserves DHW heating when the user turns off room
conditioning from the thermostat card; a full power-off (which does stop
tank too) is now reachable only through the tank switch's own `turn_off`
from plain `tank` state. This makes the switch the single place a user can
actually kill tank heating, while still letting the climate card's OFF
control stop *space conconditioning* without a hidden side effect on DHW.

**`extra_state_attributes` gains `tank_mode: bool`** (read-only), alongside
the existing `outdoor_temp`/power-consumption attributes — visible on the
thermostat card without a second control surface writing to
`operating_mode`. The switch remains the sole writer.

### 3. `sensor.py` addition

New `IntesisSensorEntityDescription`:

```python
IntesisSensorEntityDescription(
    key="tank_power_consumption",
    translation_key="tank_power_consumption",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
    entity_registry_enabled_default=False,
    required_property="aquarea_tank_consumption",
    value_fn=lambda controller, device_id: controller.get_tank_power_consumption(
        device_id
    ),
)
```

`get_tank_power_consumption()` already exists on `IntesisBase` and reads the
`aquarea_tank_consumption` datapoint — this is a straight port of the same
pattern `outdoor_temperature`/`run_hours`/`rssi` already use, no new
capability-gating mechanism or library change needed. Disabled by default
like `rssi`/`error_code`, since it's a niche measurement on untested
hardware, not because it's diagnostic — same reasoning `outdoor_temperature`
already documents for staying non-diagnostic (it's a measurement of the
world, not of integration health), it's just off by default here for the
same "untested hardware" reason the switch is.

### 4. Tests

- `tests/conftest.py`: extend the mock controller (or add a second device
  fixture) with `operating_mode`-capable state — `get_mode_list()` returning
  a tank-inclusive list, `get_mode()` returning a `+tank` combo, and
  `get_device_property`/`get_tank_power_consumption` wired for the new
  sensor.
- `tests/test_switch.py` (new): `snapshot_platform` for entity
  registry/state, plus targeted tests for each turn-on/turn-off branch above
  (mirrors `test_climate.py::test_set_temperature_not_acknowledged_raises`
  for the NACK → `HomeAssistantError` path).
- `tests/test_climate.py`: tests for `hvac_mode` resolving correctly while
  `heat+tank`/`tank` are active, the mode-change-preserves-tank behavior,
  and turn_off-preserves-tank-as-plain-tank-mode.
- `tests/test_sensor.py` (new): `snapshot_platform` covering at least the
  new `tank_power_consumption` sensor (this file doesn't exist yet — the
  original minimal test suite scoped sensor/binary_sensor out; this project
  is what creates it, for this one sensor).

## Open questions

None outstanding — all resolved through discussion above.
