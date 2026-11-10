# Unified Climate 0.1.0

A Home Assistant custom integration that combines existing temperature sensors, hot-water zone thermostats (for example Ecobee), and AC climate entities (for example Sensibo) into one virtual thermostat per **physically controllable zone**. Includes a dependency-free thermostat/history dashboard card.

**Experimental first version. Tested against Home Assistant 2026.11.1 / Python 3.14.6. Requires HA 2026.11 or newer; older climate APIs are not supported/tested. No live HA or hardware was contacted.** Source: [climate-club](https://github.com/Tumtum2814/climate-club). See [TESTING.md](TESTING.md) for executed tests and limitations.

## Physical zones — read before setup

Two Ecobees controlling two hot-water baseboard zones can provide at most two independently controlled heating zones, even when they share one boiler. **You cannot divide one Ecobee's coverage into independently heated rooms using software.** Put all temperature sensors and ACs serving that physical heating zone into one Unified Climate zone. Their temperatures are aggregated; the integration cannot move heat between rooms or operate nonexistent valves. You can create cooling-only zones for independently controlled ACs, but do not assign the same AC to another zone. Shared boiler does **not** mean sharing thermostats: each physical climate entity may belong to only one Unified Climate entry. One actuator cannot be both heater and cooler. Virtual Unified Climate entities cannot be actuators.

## Safety and ownership

- Every new/reloaded/restarted virtual thermostat starts **off and unowned**. Merely installing it, restarting HA, or viewing the card sends no commands to equipment. Mode and dashboard target changes are not restored; targets reset to configured defaults on reload/restart.
- Selecting Heat/Cool/Heat-cool explicitly acquires all mapped equipment: the controller first requests/observes off, waits startup lockout and individual minimum-off timers, then controls it. While owned, it reconciles physical modes **and targets** against its policy. Disable native schedules, Ecobee comfort automations, Sensibo schedules, and other HA automations that compete for these entities. Use the virtual thermostat after takeover. Native hardware safety remains in charge.
- Selecting virtual Off after activation keeps ownership and reconciles off, including retries. Off and total sensor failure override minimum-on time. They cannot force equipment off when HA, connectivity, an IR command, or the appliance fails.
- Options changes, unloading and removing an owned entry attempt safe off before releasing it. An unconfirmed off refuses unload/reload; restore connectivity or manually turn off the equipment and retry. Do not force-delete an offline active entry. No attempt is made to restore arbitrary old native schedules or modes; re-enable native controls yourself after release.
- Integration only calls `climate.set_temperature` then `climate.set_hvac_mode` on existing climate entities. It never drives the boiler, relays, valves, or compressor directly. Ecobee is asked to use native Heat with a bounded demand setpoint, or native Off. Its internal hysteresis/hold behavior, boiler controls and protections still apply. Lower virtual hysteresis does **not** bypass native Ecobee hysteresis or guarantee tighter temperature control.
- All configured actuators across all zones participate in a conservative house interlock: an opposite reported mode/action, unavailable/unknown equipment, uncertain start, or an unexpired changeover delay blocks new opposite demand. Same-direction zones may run together. First eligible zone in config load order wins; there is no fairness optimization. The integration cannot prevent users, native schedules or third-party automations from independently creating conflicts. Unowned equipment is observed, never switched off automatically.
- **Loss of HA is not fail-off.** Equipment can remain in its last native mode/setpoint indefinitely. Heat demand defaults to 75°F (allowed 50–80°F); cool demand defaults to 65°F (allowed 60–85°F), additionally constrained by reported equipment bounds. These are intentionally finite thermostat targets, not infinite demands. An AC's own sensor and thermostat regulate to its native target, not the remote zone sensor. Native Off may leave a heating zone without freeze protection. Do not assume Ecobee freeze protection, off-mode behavior, compressor timers, cloud holds, or restart recovery is guaranteed: verify your exact equipment and configuration independently. Provide separate temperature alarms and an independent native freeze-safe plan. Do not use this as a life-safety controller or leave uncommissioned control unattended.
- Service acknowledgement / HA-reported mode is **not verified physical HVAC action**. Sensibo/IR state is often optimistic and cannot prove compressor operation. A failed command never becomes a stored successful transition; demand is retained for retries. Reconciliation is event-driven plus a 15-second check; failed/unconfirmed commands retry no faster than every 30 seconds per actuator. A new safety-off can bypass an earlier start's retry delay. Native/display rounding is tolerated only within about half a degree.

## Manual installation

1. Back up HA. Extract `dist/unified-climate.zip` somewhere outside your HA configuration directory.
2. Copy **only** `custom_components/unified_climate/` into `<HA configuration>/custom_components/unified_climate/` (avoid an extra nested directory). All runtime files, including frontend and translations, are inside that folder. No Python packages need installing on HA.
3. Restart HA. Go to **Settings → Devices & services → Add integration → Unified Climate**.
4. Add one entry per physical zone. Select temperature sensors (°F or °C), heating climate entities and/or cooling climate entities. Choose optional outdoor temperature sensor; multiple zones can share sensors. Entity selectors allow entities temporarily offline; unavailable or unsupported actuator metadata prevents safe starts. Only equipment supporting individual Heat/Cool and Off plus a single temperature setpoint is supported in v1.
5. Keep each virtual thermostat Off while reviewing configuration. Configure alerts and native fallback behavior. Then deliberately select the desired mode and observe a full startup, run, stop, sensor-failure and network-recovery cycle under supervision. No real equipment commissioning was performed by this project.

### Configuration / options (all temperatures in °F; all timers in seconds)

The integration menu's **Configure** form changes mappings and numeric settings. Saving reloads the entry, safely stops prior owned equipment where possible, and returns the zone Off/unowned. To clear the optional outdoor sensor in YAML/data, use an empty value; in the UI remove its selected entity.

| Setting | Default | Behavior |
|---|---:|---|
| aggregation | median | Median or arithmetic mean of usable sensors |
| heat_target / cool_target | 68 / 75 | Independent indoor targets; not equipment demand setpoints |
| min_band | 2 | Cool target must be at least this far above heat target (minimum configurable 1°F) |
| hysteresis | 0.3 | Minimum 0.1°F; practical performance remains hardware-limited |
| stop_early | 0.3 | Fixed hot-water coast-down offset, 0–2°F; no unvalidated learning |
| heat_min_on / heat_min_off | 180 / 180 | Per-actuator heat run/rest timers (minimum 30s) |
| cool_min_on / cool_min_off | 300 / 300 | Per-actuator cooling timers (minimum 180s); consult AC manufacturer |
| startup_delay | 300 | Lockout after deliberate takeover; minimum 60s, plus minimum-off |
| changeover_delay | 600 | Required all-reported-off interval between house directions; largest configured zone delay wins |
| stale_after | 900 | Ignore temperature samples whose HA update is older than this; choose to match sensor reporting |
| heat_demand / cool_demand | 75 / 65 | Native thermostat demand targets, bounded as above |
| trusted_action_entities | none | Explicitly verified action reporters; never select an IR controller merely because its mode says Cool |

Heating starts below `heat_target - stop_early - hysteresis`, holds until `heat_target - stop_early`; cooling starts above `cool_target + hysteresis`, holds until `cool_target - hysteresis`. Timers may defer normal transitions; safety Off overrides minimum-on. Sensor aggregation excludes invalid, nonfinite, unsupported-unit and stale values. One remaining valid sensor is enough; with no valid sensors all owned actuators are requested off. Outdoor temperature is history-only, never a control input.

## Temperature history card

Each entry creates numeric **Indoor temperature** / **Outdoor temperature** sensors and an **Operation** history sensor. Native sensors are °F; HA's configured display unit may convert them to °C. The card explicitly converts each historical sample back to °F. Operation is heating/cooling/idle only when **every mapped actuator** is selected in `trusted_action_entities` and has a usable `hvac_action`; otherwise unknown (including contradictory actions). Only select action sources after verifying that they actually report equipment operation. IR-only equipment without trustworthy action feedback remains unknown. `requested_action` stays separate on the climate entity.

Enable HA Recorder and History and do not exclude these sensors. Long-term numeric statistics cannot replace the detailed action timeline after recorder retention expires. Missing/unknown temperatures and intervals larger than `max_gap_minutes` are gaps, not invented readings. Unknown operation is dashed purple, never idle. Known idle is gray, heating red, cooling blue; outdoor is dashed gold. Colors are **reported action**, not energy measurements. Temperature interpolation is used only between nearby actual recorded samples and split at action-change boundaries. The last reading is not projected indefinitely into the future.

With HA HTTP enabled, the integration serves its bundled JS. Add **Settings → Dashboards → Resources → Add resource** (advanced mode):

- URL: `/unified_climate/unified-climate-card.js?v=0.1.0`
- Type: **JavaScript module**

Then add a Manual dashboard card:

```yaml
type: custom:unified-climate-card
entity: climate.your_zone
hours: 24
max_gap_minutes: 30
```

Sensor IDs are normally discovered through the climate entity's `history_sensors` attribute. If discovery is unavailable or IDs were customized, set:

```yaml
sensors:
  indoor: sensor.your_zone_indoor_temperature
  outdoor: sensor.your_zone_outdoor_temperature
  operation: sensor.your_zone_operation
```

HA history is fetched through the frontend's authenticated `hass.callApi` connection (`GET /api/history/period/...`); no token entry or CDN is used. Chart history refreshes at most once a minute; range selector supports 1–72 hours. Modes and target controls call HA climate services only after user interaction. Control errors and absent history are displayed rather than replaced with demo data.

If the integration static route is unavailable, copy `frontend/unified-climate-card.js` from the installed component to `<HA configuration>/www/unified-climate-card.js` and register `/local/unified-climate-card.js?v=0.1.0` instead. HACS **integration** installation does not automatically register Lovelace resources; that step is always separate. There is no visual card editor in v1.

## HACS custom-repository installation

1. In HACS, open **Custom repositories** from the menu.
2. Add `https://github.com/Tumtum2814/climate-club` with type **Integration**.
3. Find **Unified Climate**, download it, and restart Home Assistant.
4. Add **Unified Climate** under **Settings → Devices & services** and configure a zone.
5. Register the bundled dashboard resource and add the card as described above.

This repository follows the HACS integration layout and includes `hacs.json`, a versioned manifest with repository URLs and codeowner, a license, and a local brand asset. HACS installation on a live system has not been exercised. HACS default-list acceptance is a separate process and is not claimed. Requirements reference: https://www.hacs.xyz/docs/publish/integration/ .

For a fork, update metadata before publishing:

```sh
python scripts/prepare_release.py --repo-url "$REAL_PUBLIC_GITHUB_REPO_URL" --codeowner "$REAL_GITHUB_HANDLE"
python scripts/build.py
```

The codeowner must include `@`. The helper edits local metadata only; it does not publish or verify the fork's visibility.

## Development

Use explicit Python 3.14, not macOS `/usr/bin/python3` 3.9. Install dependencies only into a venv:

```sh
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest tests -q --timeout=20
npm ci
node --test tests/*.test.js
.venv/bin/python scripts/build.py
```

Tests use disposable HA state machines/config entries and local service doubles, never credentials or installed HA configuration. The browser fixture `tests/fixtures/history-card.html` is explicitly synthetic test data and is not loaded by the production card. See TESTING.md for observed execution evidence.
