from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture
async def ha(tmp_path):
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components",
        target_is_directory=True,
    )
    hass = HomeAssistant(str(tmp_path))
    from homeassistant.helpers import frame

    frame.async_setup(hass)
    from homeassistant import loader

    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    from homeassistant.helpers import device_registry, entity_registry

    device_registry.async_setup(hass)
    await device_registry.async_load(hass)
    await hass.config_entries.async_initialize()
    await entity_registry.async_load(hass)
    await async_setup_component(hass, "homeassistant", {})
    yield hass
    await hass.async_stop()
    await hass.async_block_till_done()


async def test_ui_creates_off_climate_and_services_set_targets(ha):
    result = await ha.config_entries.flow.async_init(
        "unified_climate", context={"source": "user"}
    )
    assert result["type"] == "form"
    assert "sensors" in str(result["data_schema"])
    result = await ha.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living",
            "sensors": ["sensor.room"],
            "heaters": ["climate.ecobee"],
            "coolers": ["climate.sensibo"],
        },
    )
    assert result["type"] == "create_entry"
    await ha.async_block_till_done()
    entry = result["result"]
    entities = ha.states.async_all("climate")
    assert len(entities) == 1
    state = entities[0]
    assert state.state == "off"
    assert set(state.attributes["hvac_modes"]) == {"off", "heat", "cool", "heat_cool"}
    await ha.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": state.entity_id, "target_temp_low": 20, "target_temp_high": 25},
        blocking=True,
    )
    updated = ha.states.get(state.entity_id)
    assert updated.attributes["target_temp_low"] == 20
    assert updated.attributes["target_temp_high"] == 25
    assert await ha.config_entries.async_unload(entry.entry_id)


async def test_history_sensors_have_numeric_units_and_observed_operation(ha):
    ha.states.async_set("sensor.room", "68", {"unit_of_measurement": "°F"})
    ha.states.async_set("sensor.outside", "10", {"unit_of_measurement": "°C"})
    ha.states.async_set("climate.ecobee", "heat", {"hvac_action": "heating"})
    flow = await ha.config_entries.flow.async_init(
        "unified_climate", context={"source": "user"}
    )
    result = await ha.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "History",
            "sensors": ["sensor.room"],
            "heaters": ["climate.ecobee"],
            "outdoor_sensor": "sensor.outside",
        },
    )
    assert result["type"] == "create_entry"
    await ha.async_block_till_done()
    states = {
        s.attributes.get("friendly_name"): s for s in ha.states.async_all("sensor")
    }
    assert float(states["History Indoor temperature"].state) == 20
    assert float(states["History Outdoor temperature"].state) == 10
    assert (
        states["History Operation"].state == "unknown"
    )  # No explicitly trusted action sources
    from custom_components.unified_climate import DOMAIN

    zone = next(iter(ha.data[DOMAIN].zones.values()))
    zone.config["trusted_action_entities"] = ["climate.ecobee"]
    await ha.data[DOMAIN].tick()
    assert ha.states.get(states["History Operation"].entity_id).state == "heating"
    ha.states.async_set("climate.ecobee", "heat", {})
    await ha.async_block_till_done()
    assert ha.states.get(states["History Operation"].entity_id).state == "unknown"
    assert ha.states.async_all("climate")[-1].attributes["requested_action"] == "off"


async def test_card_resource_served_by_isolated_ha_http(ha):
    from aiohttp.test_utils import TestClient, TestServer
    from homeassistant.components.http import HomeAssistantHTTP
    from homeassistant.components.http.const import SSLProfile

    ha.http = HomeAssistantHTTP(
        ha, None, None, None, ["127.0.0.1"], 0, [], SSLProfile.MODERN_V4
    )
    from homeassistant.components.http.cors import setup_cors

    setup_cors(ha.http.app, [])
    flow = await ha.config_entries.flow.async_init(
        "unified_climate", context={"source": "user"}
    )
    await ha.config_entries.flow.async_configure(
        flow["flow_id"], {"sensors": ["sensor.room"], "heaters": ["climate.ecobee"]}
    )
    await ha.async_block_till_done()
    async with TestClient(TestServer(ha.http.app)) as client:
        response = await client.get("/unified_climate/unified-climate-card.js")
        assert response.status == 200
        assert "class UnifiedClimateCard" in await response.text()


async def test_unload_keeps_ownership_when_uncertain_start_cannot_be_stopped(ha):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.unified_climate import DOMAIN

    flow = await ha.config_entries.flow.async_init(
        "unified_climate", context={"source": "user"}
    )
    result = await ha.config_entries.flow.async_configure(
        flow["flow_id"], {"sensors": ["sensor.room"], "heaters": ["climate.ecobee"]}
    )
    await ha.async_block_till_done()
    entry = result["result"]
    manager = ha.data[DOMAIN]
    zone = manager.zones[entry.entry_id]
    called = []

    async def fail(call):
        called.append(call)
        raise HomeAssistantError("Cannot confirm off")

    ha.services.async_register("climate", "set_hvac_mode", fail)
    zone.owned = True
    manager.potential["climate.ecobee"] = "heat"
    ha.states.async_set("climate.ecobee", "off", {})
    outcome = await ha.config_entries.async_unload(entry.entry_id)
    assert called, (outcome, manager.potential, zone.error)
    assert outcome is False
    assert entry.entry_id in manager.zones
    assert zone.owned


async def test_options_reject_reuse_and_reload_new_mapping_off(ha):
    async def create(name, heater):
        flow = await ha.config_entries.flow.async_init(
            "unified_climate", context={"source": "user"}
        )
        result = await ha.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                "name": name,
                "sensors": ["sensor.room"],
                "heaters": [heater],
                "outdoor_sensor": "sensor.outside",
            },
        )
        await ha.async_block_till_done()
        return result

    one = await create("One", "climate.ecobee")
    duplicate = await create("Bad", "climate.ecobee")
    assert duplicate["type"] == "form"
    assert duplicate["errors"]["base"] == "invalid_zone"
    entry = one["result"]
    flow = await ha.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] == "form"
    result = await ha.config_entries.options.async_configure(
        flow["flow_id"],
        {"name": "Renamed", "sensors": ["sensor.room"], "heaters": ["climate.new"]},
    )
    assert result["type"] == "create_entry"
    await ha.async_block_till_done()
    from custom_components.unified_climate import DOMAIN

    assert ha.data[DOMAIN].zones[entry.entry_id].config["heaters"] == ["climate.new"]
    assert ha.data[DOMAIN].zones[entry.entry_id].config["outdoor_sensor"] == ""
    assert ha.data[DOMAIN].zones[entry.entry_id].owned is False
    ha.states.async_set("sensor.room", "20", {"unit_of_measurement": "°C"})
    await ha.async_block_till_done()
    entity = ha.states.async_all("climate")[0]
    assert entity.attributes["current_temperature"] == 20
