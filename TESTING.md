# Executed verification and boundaries

## Environment / commands

Executed locally in this project with:

- `/opt/homebrew/bin/python3`: Python 3.14.6 (macOS `/usr/bin/python3` was 3.9.6 and was not used for the integration runtime).
- Isolated venv: `/Users/tom/.hermes/cache/scratch/unified-climate-venv`.
- Installed Home Assistant **2026.11.1**, pytest **9.2.0**, pytest-asyncio **1.4.1.post1**, pytest-timeout **2.4.0**; requirements pinned in `requirements-test.txt`.
- Node **v26.7.0**, jsdom **31.0.0**; lockfile checked into the source tree (no git commit performed).

Final verification commands (run from the project directory):

```sh
PY=/Users/tom/.hermes/cache/scratch/unified-climate-venv/bin/python
$PY -m pytest tests -q --timeout=20 --basetemp=/Users/tom/.hermes/cache/scratch/unified-climate-pytest
node --test tests/*.test.js
/Users/tom/.hermes/cache/scratch/unified-climate-venv/bin/ruff check custom_components tests scripts
/Users/tom/.hermes/cache/scratch/unified-climate-venv/bin/ruff format --check custom_components tests scripts
$PY scripts/build.py
```

Observed final functional results: **35 Python tests passed** and **3 Node tests passed**. Final raw execution output and JUnit results are in `artifacts/`. The Python suite emits **5 upstream deprecation warnings** from HA's aiohttp Application subclass and the `backoff` package's deprecated `asyncio.iscoroutinefunction` use; these are reported, not hidden or described as warning-free. HA also logs its normal custom-integration caution. The deliberately refused unload test exercises a `ConfigEntryError` path; that expected log does not mean the test was skipped.

## Behavioral RED → GREEN evidence

Test-driven-development skill was loaded before implementation. Importable minimal interfaces were used where needed; missing-import, setup and collection failures were **not** counted as behavioral RED. Changes were made in successive vertical slices, running the new behavior before implementation and rerunning regressions after green. Representative exact test selectors and observed RED failures from the tool transcript:

| Test selector / behavior | Observed behavioral RED | Observed GREEN |
|---|---|---|
| `tests/test_control.py::test_sensor_aggregation_converts_and_rejects_invalid_stale` | Expected 69°F; aggregate returned None | 1 passed |
| `tests/test_control.py::test_demand_has_hysteresis_stop_early_and_separate_band` | Expected heat; demand returned off | Full suite 2 passed |
| `tests/test_settings.py::test_rejects_unsafe_config` (10 inputs) | All 10 unsafe mappings/ranges did not raise | Full suite 13 passed |
| `tests/test_runtime.py::test_default_off_does_not_touch_equipment_then_enable_takes_ownership` | Enable produced no off service call (empty recorded calls) | Full suite 14 passed |
| `tests/test_runtime.py::test_minimum_times_but_user_off_and_sensor_failure_force_off` | Normal stop turned heat off before minimum-on elapsed | Full suite 15 passed |
| `tests/test_runtime.py::test_global_opposite_demand_blocked_until_observed_off_and_changeover` | AC was cool while heat was heat | Full suite 16 passed |
| `tests/test_runtime.py::test_failed_commands_retry_without_flooding_or_losing_demand` | Raised service error; unavailable/silent cases had no retained diagnostic | Full suite 19 passed |
| `tests/test_runtime.py::test_bounded_target_reconciles_already_heat_mode_in_system_units` | Sent 75 instead of bounded 73°F / 23°C | Full suite 21 passed |
| `tests/test_integration.py::test_ui_creates_off_climate_and_services_set_targets` | User form had no sensor schema | Real HA config-flow creation and climate-service target conversion passed |
| `tests/test_integration.py::test_options_reject_reuse_and_reload_new_mapping_off` | Options flow handler absent | Real options flow, conflict rejection, reload/off and source-state event update passed |
| `tests/test_integration.py::test_history_sensors_have_numeric_units_and_observed_operation` | Outdoor selector rejected; history sensor platform absent | Numeric °C display of °F-native readings and operation history passed |
| `tests/frontend.test.js` | Transform returned zero segments rather than heating/cooling boundaries; unknown segment absent | 2 Node tests passed |
| `tests/card.test.js` | Card issued zero history requests | Actual custom element in jsdom loaded the authenticated history interface, plotted colors/outside, issued no services on render, and sent mode service on user change |
| `tests/test_runtime.py::test_uncertain_equipment_stays_safe_and_reported_rounding_is_supported` (4 cases) | Failed-start off was not sent, failed startup stop still set a target, pre-existing heating bypassed changeover, rounded °C target never enabled heat | All 4 cases passed; full suite 28 passed |
| `tests/test_integration.py::test_card_resource_served_by_isolated_ha_http` | Actual isolated HTTP route returned 404 | Route returned 200 with bundled card JavaScript |
| Strengthened history test: explicit trust required | Unverified action source yielded heating instead of unknown | Unknown by default; explicitly verified reporter yields heating; missing action reverts to unknown |
| `tests/test_distribution.py` | Build produced no ZIP; repository-dependent metadata absent | ZIP structure/CRC, source exclusions, explicit metadata generation and invalid repository rejection passed |
| `tests/test_integration.py::test_unload_keeps_ownership_when_uncertain_start_cannot_be_stopped` | Unload returned True while a deliberately failed off retained uncertain demand | Refused unload and retained ownership. An eagerly scheduled fixture event initially bypassed the failure double; fixture order was corrected, implementation change removed, RED reproduced with the double confirmed invoked, then fix reapplied and full suite passed |
| Outdoor-clear options behavior (same options test strengthened) | Removed outdoor mapping remained `sensor.outside` | Omitted optional UI selection clears mapping; reload stays off |
| `tests/test_runtime.py::test_equipment_bounds_cannot_raise_heat_above_policy_limit` | Equipment minimum 90°F caused a 90°F heat command | Non-overlapping equipment/policy bounds refused; safe off |
| `tests/test_runtime.py::test_observed_external_stop_restarts_minimum_off_timer` | External off was immediately restarted after the retry interval but before minimum-off | Reported external stop resets the per-actuator minimum-off timer |

For any Python row, the reproducible targeted command is `$PY -m pytest <exact selector above> -q --basetemp=/Users/tom/.hermes/cache/scratch/unified-climate-pytest`. Parameterized rows use the named function to run all its inputs. Historical RED results are summarized from actual tool output, not fabricated log files. Re-running current source should be GREEN, not recreate a missing feature. Supplemental regression coverage for stale-sensor immediate off passed when added because the already-implemented fail-safe behavior was present; it was not misrepresented as a new RED cycle.

## What the HA tests actually execute

The tests instantiate real `HomeAssistant`, loader, frame helper, device/entity registries and `ConfigEntries`; exercise actual config and options flow APIs, climate and sensor entity platforms, HA climate service unit conversion, source-state event listeners and unload behavior. They do not use fake modules named `homeassistant`. Equipment endpoints are explicitly local service doubles and state fixtures. A real `HomeAssistantHTTP` static route is requested through an ephemeral-loopback aiohttp test server. This does not validate full production HTTP authentication middleware or a real Recorder database.

Initial fixture attempts exposed HA registry initialization dependencies, a missing HTTP CORS initialization and an eager state-change task ordering issue. Those setup errors were fixed, not counted as implementation RED. No live HA URL, token, Ecobee or Sensibo credentials were used. No hardware was touched.

## Browser execution

Opened `tests/fixtures/history-card.html` in an actual browser, served temporarily on loopback. The page explicitly says **synthetic fixture — no real equipment**. Observed:

- One authenticated-connection-shaped history request (GET `history/period/...`, entity filter and end time) to the fixture's local test double.
- Indoor paths contained heating, cooling, idle and unknown segments; six distinct outdoor intervals.
- No service calls from rendering.
- Explicit UI changes produced `climate.set_hvac_mode` with heat, and `climate.set_temperature` with 69/76°F target band, both to the fixture double only.
- Screenshot inspected visually and retained at `artifacts/history-card-browser.png`.
- Temporary HTTP server shut down after verification.

This is real-browser rendering/interaction evidence, **not** a live dashboard integration or real recorded-house history demonstration. Production contains no fixture data or CDN dependency.

## Explicit limitations

- No hardware commissioning, native Ecobee freeze-protection validation, Sensibo compressor feedback verification, real cloud transport, boiler timing validation, HA restart with running equipment or unattended reliability testing.
- Mode/setpoint state can be optimistic. Operation coloring requires explicit trust of every physical action reporter; lack of trustworthy action feedback is unknown, not inferred heating/cooling. A user can misclassify a source as trusted; software cannot establish physical truth from IR state.
- No full Recorder/history-backend database test or live authenticated browser-to-HA session. Unit conversions and REST history request/response processing are tested separately from HA's Recorder implementation.
- No guarantee of fail-off during lost HA/network. Bounded native equipment targets remain in effect until native equipment/user action changes them. Independent freeze-safe controls and alarms are required.
- One physical heat thermostat cannot become multiple independent room heat zones. Global first-eligible arbitration is conservative and has no fairness/energy optimization.
- Public GitHub repository URL and owner are intentionally absent. Manual source installation is ready; HACS repository validation/distribution remains blocked until real public-repository metadata is supplied. The release helper does not publish or verify repository existence.
- Only HA 2026.11.1 / Python 3.14.6 and Node 26.7.0 were executed. GitHub Actions configuration was created but not run remotely. No publish, push or commit was performed.
