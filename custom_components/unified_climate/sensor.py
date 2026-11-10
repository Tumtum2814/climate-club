"""Recorder-friendly numeric temperatures and observed operation history."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from . import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN]
    async_add_entities(
        [
            ZoneSensor(manager, entry.entry_id, kind)
            for kind in ("indoor", "outdoor", "operation")
        ]
    )


def operation(hass, config):
    actions = []
    for entity in config["heaters"] + config["coolers"]:
        if entity not in config["trusted_action_entities"]:
            return None
        state = hass.states.get(entity)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        action = state.attributes.get("hvac_action")
        if action not in ("heating", "cooling", "idle", "off"):
            return None
        actions.append(action)
    if "heating" in actions and "cooling" in actions:
        return None
    return (
        "heating"
        if "heating" in actions
        else "cooling"
        if "cooling" in actions
        else "idle"
    )


class ZoneSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, manager, key, kind):
        self.manager = manager
        self.zone = manager.zones[key]
        self.kind = kind
        self._attr_unique_id = f"{key}_{kind}"
        self._attr_name = (
            self.zone.config["name"]
            + " "
            + {
                "indoor": "Indoor temperature",
                "outdoor": "Outdoor temperature",
                "operation": "Operation",
            }[kind]
        )
        if kind != "operation":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = "°F"
            self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.zone.listeners.append(self.async_write_ha_state)
        await self.manager.tick()

    async def async_will_remove_from_hass(self):
        self.zone.listeners.remove(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    @property
    def native_value(self):
        if self.kind == "indoor":
            return self.zone.temperature
        if self.kind == "outdoor":
            return self.zone.outdoor
        return operation(self.hass, self.zone.config)
