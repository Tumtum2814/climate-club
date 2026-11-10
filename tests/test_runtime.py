import pytest
from homeassistant.core import HomeAssistant

from custom_components.unified_climate.runtime import Manager


@pytest.fixture
async def rig(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    hass.config.units = US_CUSTOMARY_SYSTEM
    calls = []
    now = [0.0]

    async def service(call):
        calls.append((call.service, dict(call.data)))
        entity = call.data["entity_id"]
        old = hass.states.get(entity)
        attrs = dict(old.attributes)
        if "temperature" in call.data:
            attrs["temperature"] = call.data["temperature"]
        hass.states.async_set(entity, call.data.get("hvac_mode", old.state), attrs)

    for name in ("set_temperature", "set_hvac_mode"):
        hass.services.async_register("climate", name, service)
    hass.states.async_set("sensor.room", "65", {"unit_of_measurement": "°F"})
    hass.states.async_set(
        "climate.heat",
        "heat",
        {
            "temperature": 70,
            "temperature_unit": "°F",
            "min_temp": 45,
            "max_temp": 90,
            "hvac_modes": ["off", "heat"],
        },
    )
    manager = Manager(hass, clock=lambda: now[0])
    zone = manager.add("one", {"sensors": ["sensor.room"], "heaters": ["climate.heat"]})
    yield hass, manager, zone, calls, now
    await hass.async_stop()


async def test_change_report_identity_uses_event_timestamp_not_mutable_state_reported(
    rig,
):
    from datetime import timedelta

    from homeassistant.core import Event, State
    from homeassistant.util import dt as dt_util

    from custom_components.unified_climate.response import ResponseMonitor

    hass, manager, zone, calls, now = rig
    hass.states.async_set("climate.heat", "off")
    zone.config["response_enabled"] = True
    zone.response = ResponseMonitor(zone.config)
    state = State("sensor.room", "75", {"unit_of_measurement": "°F"})
    original = dt_util.utcnow() - timedelta(seconds=3)
    event = Event(
        "state_changed",
        {"entity_id": "sensor.room", "new_state": state},
        time_fired_timestamp=original.timestamp(),
    )
    manager.feedback(zone, event)
    assert zone.response.identities["sensor.room"] == original
    state.last_reported = dt_util.utcnow()
    manager.feedback(zone, event)
    assert len(zone.response.samples["sensor.room"]) == 1


async def test_heating_reports_cannot_create_cooling_evidence(rig):
    from homeassistant.core import Event, State

    from custom_components.unified_climate.response import ResponseMonitor

    hass, manager, zone, calls, now = rig
    zone.config["response_enabled"] = True
    zone.response = ResponseMonitor(zone.config)
    state = State("sensor.room", "75", {"unit_of_measurement": "°F"})
    manager.feedback(
        zone, Event("state_changed", {"entity_id": "sensor.room", "new_state": state})
    )
    assert zone.response.samples["sensor.room"] == []
    assert "Heating" in zone.response.reason


async def test_cooling_monitor_anchors_baseline_before_awaited_service(rig):
    hass, manager, zone, calls, now = rig
    zone = manager.add(
        "cool",
        {
            "sensors": ["sensor.room"],
            "coolers": ["climate.ac"],
            "response_enabled": True,
        },
    )
    hass.states.async_set(
        "climate.ac",
        "off",
        {"temperature": 65, "temperature_unit": "°F", "min_temp": 60, "max_temp": 85},
    )
    zone.response.reading("sensor.room", "76", "°F", 0, 0)

    async def delayed(call):
        now[0] = 30
        zone.response.reading("sensor.room", "74", "°F", 30, 30)

    hass.services.async_register("climate", "set_hvac_mode", delayed)
    await manager.command(zone, "climate.ac", "cool", 65)
    assert zone.response.started == 0
    assert zone.response.baseline["sensor.room"] == [(0, 76.0)]
    assert zone.cooling_commands[-1]["outcome"] == "delivered"


async def test_feedback_numeric_format_and_metadata_are_not_measurements(rig):
    from homeassistant.core import Event, State

    hass, manager, zone, calls, now = rig
    zone.config["response_enabled"] = True
    from custom_components.unified_climate.response import ResponseMonitor

    zone.response = ResponseMonitor(zone.config)
    hass.states.async_set("climate.heat", "off")
    old = State("sensor.room", "75", {"unit_of_measurement": "°F"})
    first = State("sensor.room", "75.0", {"unit_of_measurement": "°F", "battery": 50})
    manager.feedback(
        zone,
        Event(
            "state_changed",
            {"entity_id": "sensor.room", "old_state": old, "new_state": first},
        ),
    )
    assert zone.response.samples["sensor.room"] == []


async def test_cooling_command_audit_keeps_errors_unknown_and_noop_unissued(rig):
    from homeassistant.exceptions import HomeAssistantError

    hass, manager, zone, calls, now = rig
    zone = manager.add(
        "cool",
        {
            "sensors": ["sensor.room"],
            "coolers": ["climate.ac"],
            "response_enabled": True,
        },
    )
    hass.states.async_set(
        "climate.ac",
        "off",
        {"temperature": 65, "temperature_unit": "°F", "min_temp": 60, "max_temp": 85},
    )
    await manager.command(zone, "climate.ac", "off", None)
    assert getattr(zone, "cooling_commands", []) == []

    async def fail(call):
        raise HomeAssistantError("Ambiguous IR delivery")

    hass.services.async_register("climate", "set_hvac_mode", fail)
    await manager.command(zone, "climate.ac", "cool", 65)
    assert zone.response.state == "inconclusive"
    assert "error" in zone.response.reason
    assert zone.cooling_commands[-1]["outcome"] == "error"
    assert zone.cooling_commands[-1]["action"] == "start"
    assert zone.cooling_commands[-1]["entity_id"] == "climate.ac"
    now[0] = 1
    await manager.command(zone, "climate.ac", "cool", 65)
    assert len(zone.cooling_commands) == 1


async def test_observed_external_stop_restarts_minimum_off_timer(rig):
    hass, manager, zone, calls, now = rig
    await manager.set_mode("one", "heat")
    now[0] = 301
    await manager.tick()
    state = hass.states.get("climate.heat")
    hass.states.async_set("climate.heat", "off", dict(state.attributes))
    now[0] = 340
    await manager.tick()
    assert hass.states.get("climate.heat").state == "off"
    now[0] = 521
    await manager.tick()
    assert hass.states.get("climate.heat").state == "heat"


async def test_equipment_bounds_cannot_raise_heat_above_policy_limit(rig):
    hass, manager, zone, calls, now = rig
    await manager.set_mode("one", "heat")
    state = hass.states.get("climate.heat")
    hass.states.async_set(
        "climate.heat", "off", {**state.attributes, "min_temp": 90, "max_temp": 100}
    )
    now[0] = 301
    await manager.tick()
    assert hass.states.get("climate.heat").state == "off"
    assert not any(name == "set_temperature" for name, _ in calls)
    assert zone.error is not None


async def test_stale_sensor_forces_off_before_min_on(rig, monkeypatch):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    hass, manager, zone, calls, now = rig
    await manager.set_mode("one", "heat")
    now[0] = 301
    await manager.tick()
    assert hass.states.get("climate.heat").state == "heat"
    future = dt_util.utcnow() + timedelta(seconds=901)
    monkeypatch.setattr(dt_util, "utcnow", lambda: future)
    await manager.tick()
    assert zone.temperature is None
    assert hass.states.get("climate.heat").state == "off"


async def test_default_off_does_not_touch_equipment_then_enable_takes_ownership(rig):
    hass, manager, zone, calls, now = rig
    await manager.tick()
    assert calls == []
    await manager.set_mode("one", "heat")
    assert calls[0] == (
        "set_hvac_mode",
        {"entity_id": "climate.heat", "hvac_mode": "off"},
    )
    now[0] = 301
    await manager.tick()
    assert hass.states.get("climate.heat").state == "heat"
    assert hass.states.get("climate.heat").attributes["temperature"] == 75
    count = len(calls)
    await manager.tick()
    assert len(calls) == count
    assert zone.requested == "heat"


async def test_global_opposite_demand_blocked_until_observed_off_and_changeover(rig):
    hass, manager, zone, calls, now = rig
    hass.states.async_set("sensor.hot", "80", {"unit_of_measurement": "°F"})
    hass.states.async_set(
        "climate.ac",
        "off",
        {
            "temperature": 75,
            "temperature_unit": "°F",
            "min_temp": 60,
            "max_temp": 85,
            "hvac_modes": ["off", "cool"],
        },
    )
    manager.add("two", {"sensors": ["sensor.hot"], "coolers": ["climate.ac"]})
    await manager.set_mode("one", "heat")
    await manager.set_mode("two", "cool")
    now[0] = 301
    await manager.tick()
    assert hass.states.get("climate.heat").state == "heat"
    assert hass.states.get("climate.ac").state == "off"
    await manager.set_mode("one", "off")
    now[0] = 700
    await manager.tick()
    assert hass.states.get("climate.ac").state == "off"
    now[0] = 902
    await manager.tick()
    assert hass.states.get("climate.ac").state == "cool"


@pytest.mark.parametrize("celsius", [False, True])
async def test_bounded_target_reconciles_already_heat_mode_in_system_units(
    rig, celsius
):
    from homeassistant.util.unit_system import METRIC_SYSTEM

    hass, manager, zone, calls, now = rig
    await manager.set_mode("one", "heat")
    if celsius:
        hass.config.units = METRIC_SYSTEM
    unit = "°C" if celsius else "°F"
    attrs = {
        "temperature": 20 if celsius else 68,
        "temperature_unit": unit,
        "min_temp": 7 if celsius else 45,
        "max_temp": 23 if celsius else 73,
        "hvac_modes": ["off", "heat"],
    }
    hass.states.async_set("climate.heat", "heat", attrs)
    now[0] = 301
    await manager.tick()
    expected = 23 if celsius else 73
    assert hass.states.get("climate.heat").attributes["temperature"] == expected
    assert calls[-2][1]["temperature"] == expected


@pytest.mark.parametrize(
    "scenario",
    [
        "failed_start_then_off",
        "startup_stop_failed",
        "external_heat_changeover",
        "rounded_target",
    ],
)
async def test_uncertain_equipment_stays_safe_and_reported_rounding_is_supported(
    rig, scenario
):
    from homeassistant.exceptions import HomeAssistantError

    hass, manager, zone, calls, now = rig
    if scenario == "external_heat_changeover":
        hass.states.async_set("sensor.hot", "80", {"unit_of_measurement": "°F"})
        hass.states.async_set(
            "climate.ac",
            "off",
            {
                "temperature": 70,
                "temperature_unit": "°F",
                "min_temp": 60,
                "max_temp": 85,
            },
        )
        manager.add("two", {"sensors": ["sensor.hot"], "coolers": ["climate.ac"]})
        await manager.set_mode("one", "heat")  # Takes over pre-existing native heating
        await manager.set_mode("two", "cool")
        now[0] = 301
        await manager.set_mode("one", "off")
        assert (
            hass.states.get("climate.ac").state == "off"
        )  # Need full 600s since prior heat stopped
        return
    if scenario == "startup_stop_failed":

        async def fail(call):
            calls.append((call.service, dict(call.data)))
            raise HomeAssistantError("offline")

        hass.services.async_register("climate", "set_hvac_mode", fail)
        await manager.set_mode("one", "heat")
        now[0] = 301
        await manager.tick()
        assert not any(name == "set_temperature" for name, _ in calls)
        return
    await manager.set_mode("one", "heat")
    if scenario == "rounded_target":
        from homeassistant.util.unit_system import METRIC_SYSTEM

        hass.config.units = METRIC_SYSTEM
        hass.states.async_set(
            "climate.heat",
            "off",
            {
                "temperature": 20,
                "temperature_unit": "°C",
                "min_temp": 7,
                "max_temp": 30,
            },
        )

        async def rounded(call):
            calls.append((call.service, dict(call.data)))
            old = hass.states.get("climate.heat")
            hass.states.async_set(
                "climate.heat",
                old.state,
                {**old.attributes, "temperature": round(call.data["temperature"], 1)},
            )

        hass.services.async_register("climate", "set_temperature", rounded)
        now[0] = 301
        await manager.tick()
        assert hass.states.get("climate.heat").state == "heat"
        count = len(calls)
        now[0] = 332
        await manager.tick()
        assert len(calls) == count
        return

    async def uncertain(call):
        calls.append((call.service, dict(call.data)))
        if call.data["hvac_mode"] == "heat":
            raise HomeAssistantError("May have reached hardware")

    hass.services.async_register("climate", "set_hvac_mode", uncertain)
    now[0] = 301
    await manager.tick()
    await manager.set_mode("one", "off")
    assert calls[-1] == (
        "set_hvac_mode",
        {"entity_id": "climate.heat", "hvac_mode": "off"},
    )


@pytest.mark.parametrize("failure", ["service_error", "unavailable", "silent"])
async def test_failed_commands_retry_without_flooding_or_losing_demand(rig, failure):
    from homeassistant.exceptions import HomeAssistantError

    hass, manager, zone, calls, now = rig
    await manager.set_mode("one", "heat")
    if failure == "unavailable":
        hass.states.async_set("climate.heat", "unavailable", {})
    else:

        async def fail(call):
            calls.append((call.service, dict(call.data)))
            if failure == "service_error":
                raise HomeAssistantError("offline")

        hass.services.async_register("climate", "set_temperature", fail)
    now[0] = 301
    await manager.tick()
    assert zone.requested == "heat"
    assert zone.error is not None
    count = len(calls)
    now[0] = 302
    await manager.tick()
    assert len(calls) == count
    now[0] = 332
    await manager.tick()
    if failure != "unavailable":
        assert len(calls) > count
    assert manager.transitions["climate.heat"][0] == "off"


async def test_minimum_times_but_user_off_and_sensor_failure_force_off(rig):
    hass, manager, zone, calls, now = rig
    await manager.set_mode("one", "heat")
    now[0] = 301
    await manager.tick()
    hass.states.async_set("sensor.room", "70", {"unit_of_measurement": "°F"})
    now[0] = 310
    await manager.tick()
    assert hass.states.get("climate.heat").state == "heat"  # min-on
    await manager.set_mode("one", "off")
    assert hass.states.get("climate.heat").state == "off"
    hass.states.async_set("sensor.room", "65", {"unit_of_measurement": "°F"})
    await manager.set_mode("one", "heat")
    now[0] = 400
    await manager.tick()
    assert hass.states.get("climate.heat").state == "off"  # min-off
    now[0] = 491
    await manager.tick()
    assert hass.states.get("climate.heat").state == "heat"
    hass.states.async_set("sensor.room", "unavailable", {"unit_of_measurement": "°F"})
    await manager.tick()
    assert hass.states.get("climate.heat").state == "off"
