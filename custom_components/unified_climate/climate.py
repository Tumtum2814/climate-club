"""Home Assistant climate entity; policy remains in Fahrenheit."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature

from . import DOMAIN
from .settings import validate


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN]
    async_add_entities([UnifiedClimate(manager, entry.entry_id)])


class UnifiedClimate(ClimateEntity):
    _attr_should_poll = False
    _attr_native_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 0.1
    _attr_min_temp = 50
    _attr_max_temp = 85

    def __init__(self, manager, key):
        self.manager = manager
        self.key = key
        self.zone = manager.zones[key]
        self._attr_unique_id = key
        self._attr_name = self.zone.config["name"]
        self._attr_hvac_modes = [HVACMode.OFF]
        if self.zone.config["heaters"]:
            self._attr_hvac_modes.append(HVACMode.HEAT)
        if self.zone.config["coolers"]:
            self._attr_hvac_modes.append(HVACMode.COOL)
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        if len(self._attr_hvac_modes) == 3:
            self._attr_hvac_modes.append(HVACMode.HEAT_COOL)
            self._attr_supported_features |= (
                ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.zone.callback = self.async_write_ha_state
        await self.manager.tick()

    async def async_will_remove_from_hass(self):
        self.zone.callback = None
        await super().async_will_remove_from_hass()

    @property
    def hvac_mode(self):
        return HVACMode(self.zone.mode)

    @property
    def native_current_temperature(self):
        return self.zone.temperature

    @property
    def native_target_temperature(self):
        return self.zone.config[
            "cool_target" if self.zone.mode == "cool" else "heat_target"
        ]

    @property
    def native_target_temperature_low(self):
        return self.zone.config["heat_target"]

    @property
    def native_target_temperature_high(self):
        return self.zone.config["cool_target"]

    @property
    def extra_state_attributes(self):
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        return {
            "history_sensors": {
                kind: registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{self.key}_{kind}"
                )
                for kind in ("indoor", "outdoor", "operation")
            },
            "requested_action": self.zone.requested,
            "owns_equipment": self.zone.owned,
            "control_error": self.zone.error,
            "physical_hvac_actions": {
                e: (
                    s.attributes.get("hvac_action")
                    if (s := self.hass.states.get(e))
                    else None
                )
                for e in self.zone.config["heaters"] + self.zone.config["coolers"]
            },
        }

    async def async_set_hvac_mode(self, hvac_mode):
        await self.manager.set_mode(self.key, hvac_mode)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        update = {}
        if "temperature" in kwargs:
            update["cool_target" if self.zone.mode == "cool" else "heat_target"] = (
                kwargs["temperature"]
            )
        if "target_temp_low" in kwargs:
            update["heat_target"] = kwargs["target_temp_low"]
        if "target_temp_high" in kwargs:
            update["cool_target"] = kwargs["target_temp_high"]
        self.zone.config = validate({**self.zone.config, **update})
        if "hvac_mode" in kwargs:
            await self.manager.set_mode(self.key, kwargs["hvac_mode"])
        else:
            await self.manager.tick()
        self.async_write_ha_state()
