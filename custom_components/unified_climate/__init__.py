"""Unified Climate: one config entry and one climate entity per zone."""

from datetime import timedelta

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .runtime import Manager

DOMAIN = "unified_climate"
PLATFORMS = ["climate", "sensor"]


async def async_setup_entry(hass, entry):
    manager = hass.data.setdefault(DOMAIN, Manager(hass))
    if hass.http is not None and not hass.data.get(f"{DOMAIN}_static"):
        from pathlib import Path

        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/unified_climate",
                    str(Path(__file__).parent / "frontend"),
                    cache_headers=False,
                )
            ]
        )
        hass.data[f"{DOMAIN}_static"] = True
    zone = manager.add(entry.entry_id, {**entry.data, **entry.options})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def schedule(_):
        entry.async_create_background_task(
            hass, manager.tick(), "Unified Climate reconcile"
        )

    entry.async_on_unload(
        async_track_time_interval(hass, schedule, timedelta(seconds=15))
    )
    entry.async_on_unload(
        async_track_state_change_event(
            hass,
            zone.config["sensors"]
            + ([zone.config["outdoor_sensor"]] if zone.config["outdoor_sensor"] else [])
            + zone.config["heaters"]
            + zone.config["coolers"],
            schedule,
        )
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    manager = hass.data[DOMAIN]
    zone = manager.zones[entry.entry_id]
    if zone.owned:
        await manager.set_mode(entry.entry_id, "off")
        for entity in zone.config["heaters"] + zone.config["coolers"]:
            state = hass.states.get(entity)
            if (
                entity in manager.potential
                or not state
                or state.state != "off"
                or state.attributes.get("hvac_action") in ("heating", "cooling")
            ):
                raise ConfigEntryError(
                    "Cannot release equipment: off is not confirmed. Restore connectivity or turn equipment off manually, then retry."
                )
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    manager.zones.pop(entry.entry_id)
