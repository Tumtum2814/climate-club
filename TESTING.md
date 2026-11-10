# Executed verification and boundaries

> **Prior baseline:** Everything through the original “Explicit limitations” section below records the 0.1.0 implementation, not current 0.2.0 results. Its 35/3 test totals, browser screenshot and metadata limitation are historical. The repository metadata is now supplied for `https://github.com/Tumtum2814/climate-club`; no publication action was performed for this change. Current executed monitoring evidence is appended under **0.2.0 temperature-response monitoring**.

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

## 0.2.0 temperature-response monitoring — current evidence

Implemented and exercised locally against **Home Assistant 2026.11.1, Python 3.14.6 and Node v26.7.0**, without live HA, credentials, cloud endpoints or equipment. Manifest and dashboard resource references are now 0.2.0; domain, prior entity unique IDs and trusted Operation semantics remain compatible. The prior baseline above is retained as history, not presented as current evidence.

### Executed gates

```sh
PY=/Users/tom/.hermes/cache/scratch/unified-climate-venv/bin/python
$PY -m pytest tests -q --timeout=20 --basetemp=/Users/tom/.hermes/cache/scratch/climate-club-response-pytest --junitxml=artifacts/response-pytest.xml
/Users/tom/.hermes/tools/node-26.7.0-darwin-arm64/bin/node --test tests/*.test.js
/Users/tom/.hermes/cache/scratch/unified-climate-venv/bin/ruff check custom_components tests scripts
/Users/tom/.hermes/cache/scratch/unified-climate-venv/bin/ruff format --check custom_components tests scripts
/Users/tom/.hermes/tools/node-26.7.0-darwin-arm64/bin/node node_modules/prettier/bin/prettier.cjs --check custom_components/unified_climate/frontend/unified-climate-card.js tests/card.test.js tests/frontend.test.js
$PY scripts/build.py
```

Observed functional results: **61 Python tests passed**, **5 Node tests passed**. Python still emits the **5 upstream deprecation warnings** described above; they were not suppressed. Ruff check, Ruff format check, Prettier check and `git diff --check` pass. Raw current outputs are retained in ignored `artifacts/response-pytest.txt`, `artifacts/response-pytest.xml` and `artifacts/response-node.txt`. The source/manual-install ZIP is rebuilt as `dist/unified-climate.zip`; CRC and required monitoring/frontend/manifest members are checked locally. No commit, push or live commissioning was performed.

### Successive behavioral RED → GREEN slices

Required development/testing/TDD skills were loaded before implementation. New behavior was added through tested slices; minimal importable interfaces were used rather than treating collection errors as RED. Representative actual observed failures and fixes:

| Test / slice | Observed RED | Observed GREEN |
|---|---|---|
| `test_monitor_settings_are_opt_in_and_validate` | Missing `response_enabled` returned None, not False | Default-off settings, duplicate feedback-ID handling, numeric/integral/bool/range rejection pass |
| `test_start_warming_to_flat_is_consistent_after_grace` | State remained inconclusive instead of observing_start | Warming baseline → flat post-grace produces cooling_likely |
| `test_stop_weakening_does_not_require_warming` | Both stop cases incorrectly returned no_start_response | Weaker falling response gives stopped_likely; sustained falling gives continued_cooling |
| `test_evidence_boundaries` | Error/invalid/unit-change inferred success; retry reset anchor; stale baseline retained; long post-window lost samples | Ambiguous/missing/stale/invalid evidence stays inconclusive, retries retain anchor, post-window retention passes |
| Real-HA `test_temperature_response_end_to_end_reports_commands_and_history` | Boolean monitor setting was rejected by the numeric selector; later source-event ordering missed the last baseline sample | Real UI flow, timer-deferred start, source reports including equal-value reports, actual mode-service start/stop, diagnostics and separate trusted/inferred sensors pass |
| Runtime numeric-format / command-audit slices | Formatting-only report counted as numeric evidence; issued-command audit was absent | Metadata/numeric-format changes excluded; no-op and retry-deferred work unissued; ambiguous mode service is audited error/unknown |
| `test_staggered_multi_sensor_reports_build_independent_trends_without_fake_aggregate_samples` | Missing second sensor repeatedly erased first sensor's initial baseline | Independent fixed-membership sensor baselines and per-sensor minimums pass |
| `test_cooling_monitor_anchors_baseline_before_awaited_service` | Started at service completion 30 instead of issuance 0; included reading taken during await in baseline | Baseline anchored before awaited service; successful delivery with unconfirmed reported mode is still advisory, never physical proof |
| `test_heating_reports_cannot_create_cooling_evidence` | Heating source event entered the cooling baseline | Heating contamination clears evidence to inconclusive |
| Observation diagnostics / small-slope UI tuning | Post count stayed empty during observation; selector step was 0.1 instead of 0.001 | Live per-sensor counts and baseline slope, sub-tenth threshold tuning pass |
| `test_preexisting_cooling_alone_is_not_a_start_response` | Same preexisting falling trend yielded cooling_likely | Requires meaningful baseline-to-post change for startup |
| Immutable source-report identity | Used mutable State.last_reported instead of original event timestamp | Source event timestamp deduplication survives later State.last_reported mutation |
| Frontend inferred timeline transform | Only three actual-action intervals, missing inferred boundaries | Inferred cooling/stopped and uncertainty split intervals; trusted actions win; requested Cool is not inference |
| Actual card custom element in jsdom | Authenticated history URL omitted sensor.inferred | Optional inferred history fetched and dashed blue/gray/purple paths/legend rendered; old mappings still pass; rendering sends no control services |

Fixture mistakes (climate component replacing early service doubles, metric display units in a Fahrenheit-only double, and the Event constructor's `time_fired_timestamp` argument) were corrected and are not counted as behavioral implementation RED. Additional regression assertions for Celsius conversion, mean/median slopes, duplicate source identities/config IDs, disabled monitoring, superseding stop/error, options reload/feedback override and unchanged control aggregation passed against the implemented behavior; these are not misrepresented as additional RED cycles.

### Runtime and scope findings

Inspected the installed HA release source: `async_track_state_report_event` handles unchanged state/attributes, opposite `state_changed`; StateMachine updates `State.last_reported` in place for unchanged reports. Monitoring therefore combines source change/report events, uses immutable source timestamps, ignores metadata-only/numeric-format changes and conservatively ignores equal-valued forced change events. HA source report freshness is not a guarantee of a new physical measurement.

Actual HA tests run local state machines, registries, config/options flows, entity platforms, source-event subscribers, service doubles and safe unload/reload. The complete start/stop test proves exactly one setpoint/start/stop sequence, no monitor-triggered retries, timer-deferred demand with no monitor, separate unknown trusted Operation, fresh equal-valued source reports, override-only feedback, reset after options reload and no control-temperature changes from feedback overrides. Existing safety/timer/retry/interlock tests all remain green. The monitor is not read by the control demand, command retry or house-interlock policy.

Node tests execute actual history transformations and the production custom element in jsdom through a locally doubled `hass.callApi`; no live Recorder database or authenticated HA backend was contacted. The original browser screenshot is **prior-baseline evidence only**; no new real-browser monitoring screenshot or hardware validation is claimed. No full Recorder persistence test, appliance tuning guarantee or per-AC IR success attribution is claimed. Sensor outcomes describe the last command-response window, not continuous physical compressor telemetry; continued cooling after Off may be natural. README documents setup, defaults/bounds, measurement/report caveats, recording, notifications via user automations and these limitations.
