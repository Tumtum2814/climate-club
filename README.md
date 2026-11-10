# Unified Climate 0.2.0

A Home Assistant custom integration that combines existing temperature sensors, hot-water zone thermostats (for example Ecobee), and AC climate entities (for example Sensibo) into one virtual thermostat per **physically controllable zone**. Includes a dependency-free thermostat/history dashboard card.

**Experimental integration. Tested against Home Assistant 2026.11.1 / Python 3.14.6. Requires HA 2026.11 or newer; older climate APIs are not supported/tested. No live HA or hardware was contacted.** Source: [climate-club](https://github.com/Tumtum2814/climate-club). See [TESTING.md](TESTING.md) for executed tests and limitations.

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

## Advisory cooling temperature-response monitoring (0.2.0)

No power-monitor hardware is required. In **Settings → Devices & services → Unified Climate → Configure**, enable **advisory cooling temperature-response monitoring** for the zone. It is **disabled by default**, including existing entries; no migration/recreation is required. Optionally select separate feedback temperature sensors; an empty selection uses the existing indoor sensors. °C and °F, finite/range validation and the zone's `stale_after` limit apply. Clearing the feedback list restores that default. These sensors do not replace the control sensors or alter control aggregation.

| Setting | Default | Allowed range / meaning |
|---|---:|---|
| response_enabled | false | Boolean; advisory only |
| response_sensors | empty | Optional temperature-sensor override; duplicate IDs count once |
| response_start_grace | 180s | 0–3600s compressor startup grace |
| response_stop_settling | 180s | 0–3600s shutdown settling, separate from startup |
| response_baseline_window | 600s | 60–7200s pre-command baseline |
| response_start_window | 600s | 60–7200s observation **after** startup grace |
| response_stop_window | 600s | 60–7200s observation **after** shutdown settling |
| response_min_samples | 3 | Integral 2–100 fresh reports **per sensor, in each window** |
| response_threshold | 0.03°F/min | 0.001–2°F/min meaningful trend change; UI step 0.001 |

**These defaults are illustrative, not equipment-performance guarantees.** Match windows and sample count to actual reporting cadence, room thermal mass, sensor resolution and compressor behavior. For example, a sensor reporting every five minutes may not supply three readings in a ten-minute post-grace window. The result is inconclusive, not a successful startup. Baseline collection starts with fresh reports after loading, not invented historical samples. A newly enabled monitor can therefore lack baseline evidence for its first command.

Monitoring starts only after an actual `climate.set_hvac_mode` cooling start/off call returns without service error, anchored to the time the call was issued. Requested demand, timer-deferred changes, matching modes/targets with no service call, and unconfirmed setpoint calls do not start an observation. The last 20 actually issued cooling-mode commands are exposed as `cooling_commands` (entity ID, start/stop, UTC issue time, delivered/error outcome); “delivered” means only that the HA service returned without error. A service error is ambiguous delivery and explicitly **inconclusive**, never inferred success. Native command reconciliation/retry is unchanged. Same-direction retries and additional AC commands do not restart the window; an opposite command supersedes it. If any command in a multi-AC zone fails, that observation remains inconclusive even if a later same-direction retry succeeds; the next opposite command can begin a new window.

Each feedback sensor gets its own least-squares pre-command and post-grace slope in °F/min. The configured mean/median combines **per-sensor slopes over the same fixed sensor set**, not staggered partial aggregate snapshots. All selected sensors must supply the minimum samples in both windows. Start response is consistent when the post-grace slope falls by at least the threshold relative to baseline: warming → stable can qualify; cooling that was already present at the same rate does not establish a startup response. Stop response is consistent when cooling weakens by at least the threshold or the post-settling slope is flat/warming within the threshold. **Warming after Off is not required.** Continued falling temperatures can be residual cooling, thermal lag or weather; `continued_cooling` is suspicious/unexpected response, **not proof of a failed stop**. The same applies to `no_start_response`: it is not proof of equipment failure.

Sampling consumes HA numeric source events, never the 15-second reconcile rereads. HA 2026.11.1's `async_track_state_report_event` receives genuinely unchanged state reports; these can count equal values using the source report timestamp. State-change events count numeric changes; attribute-only changes and numeric formatting changes do not count. Equal-valued forced state-change events are conservatively ignored; unchanged `state_reported` events do count. `last_updated` can change for metadata alone and is not treated as measurement evidence. A fresh HA report proves only that the source integration reported, **not that its hardware took a new measurement**. Sources that repeatedly republish cached readings may still mislead inference.

Missing/invalid/stale feedback, unit changes and heating contamination invalidate the observation and clear its baseline to inconclusive. No old samples bridge a stale interval. Sensor mapping/aggregation changes reload the entry and reset monitoring, as do unload/restart. Baseline and samples are held in bounded memory, not restored. The previous result is retained only while feedback stays fresh and until superseded/invalidated; it describes the **last command-response window**, not continuous compressor telemetry. Several ACs in one zone yield zone-level inference only; the monitor cannot identify which individual IR unit received a command.

### Diagnostics, recording and graph

Each zone adds **Cooling response** (`response`) and **Inferred cooling operation** (`inferred_operation`) sensors without replacing the existing trusted **Operation** sensor. Stable states are `disabled`, `observing_start`, `observing_stop`, `cooling_likely`, `stopped_likely`, `inconclusive`, `no_start_response`, and `continued_cooling`. The response sensor and climate `cooling_response` attributes expose reason, per-sensor baseline/post counts, slopes, report freshness, window sizes and thresholds; the climate/response sensor also exposes the bounded command audit. Counts update during observation; conclusions wait for the full window. Monotonic timing attributes are process-local diagnostics, not wall-clock timestamps; the command audit has UTC timestamps.

Do not exclude the new sensors from Recorder if you want detailed history. Their string states are recorded timeline events, not numeric long-term statistics. The card discovers `history_sensors.inferred_operation` and fetches it with the existing authenticated `hass.callApi` history request. For manual mappings, add `sensors.inferred_operation: sensor.your_zone_inferred_cooling_operation`. Older entries/history mappings without this sensor still render normally. Keep the resource URL cache reference at **`?v=0.2.0`** after upgrading.

Trusted reported actions remain solid red/blue/gray and take priority over inference. Inferred cooling is dashed blue; inferred stopped/idle is dashed neutral gray; observing/error/uncertain/disabled intervals without trusted feedback are dashed purple. The legend explicitly says **inferred**. Requested demand is never counted as inferred operation. Existing temperature gaps and outdoor dashed gold remain intact.

This is **monitoring only**: no extra IR commands, automatic retries, timer bypasses, setpoint changes, safety-interlock clearance, or automatic persistent notifications. You may use the response sensor in an explicitly configured HA automation for alerts; apply your own dwell/debounce logic. Temperature response cannot prove physical operation or provide independent fail-off/freeze protection.

## Temperature history card

Each entry creates numeric **Indoor temperature** / **Outdoor temperature** sensors and an **Operation** history sensor. Native sensors are °F; HA's configured display unit may convert them to °C. The card explicitly converts each historical sample back to °F. Operation is heating/cooling/idle only when **every mapped actuator** is selected in `trusted_action_entities` and has a usable `hvac_action`; otherwise unknown (including contradictory actions). Only select action sources after verifying that they actually report equipment operation. IR-only equipment without trustworthy action feedback remains unknown. `requested_action` stays separate on the climate entity.

Enable HA Recorder and History and do not exclude these sensors. Long-term numeric statistics cannot replace the detailed action timeline after recorder retention expires. Missing/unknown temperatures and intervals larger than `max_gap_minutes` are gaps, not invented readings. Without a usable response inference, unknown operation is dashed purple, never idle. Known idle is solid gray, heating solid red, cooling solid blue; optional response inference adds explicitly dashed blue/gray as described above; outdoor is dashed gold. Solid colors are **reported action**, not energy measurements. Temperature interpolation is used only between nearby actual recorded samples and split at action-change boundaries. The last reading is not projected indefinitely into the future.

With HA HTTP enabled, the integration serves its bundled JS. Add **Settings → Dashboards → Resources → Add resource** (advanced mode):

- URL: `/unified_climate/unified-climate-card.js?v=0.2.0`
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

If the integration static route is unavailable, copy `frontend/unified-climate-card.js` from the installed component to `<HA configuration>/www/unified-climate-card.js` and register `/local/unified-climate-card.js?v=0.2.0` instead. HACS **integration** installation does not automatically register Lovelace resources; that step is always separate. There is no visual card editor in v1.

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
