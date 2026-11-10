"""UI configuration for independently controllable physical zones."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from . import DOMAIN
from .settings import DEFAULTS, validate


def schema(values):
    fields = {}
    fields[vol.Required("name", default=values["name"])] = selector.TextSelector()
    for key in (
        "sensors",
        "heaters",
        "coolers",
        "trusted_action_entities",
        "response_sensors",
    ):
        fields[vol.Required(key, default=values[key])] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor"
                if key in ("sensors", "response_sensors")
                else "climate",
                multiple=True,
            )
        )
    outdoor = vol.Optional(
        "outdoor_sensor", description={"suggested_value": values["outdoor_sensor"]}
    )
    fields[outdoor] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    )
    fields[vol.Required("aggregation", default=values["aggregation"])] = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(options=["median", "mean"])
        )
    )
    for key, default in DEFAULTS.items():
        if isinstance(default, bool):
            fields[vol.Required(key, default=values[key])] = selector.BooleanSelector()
        elif isinstance(default, (float, int)):
            fields[vol.Required(key, default=values[key])] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    mode=selector.NumberSelectorMode.BOX,
                    step=0.001
                    if key == "response_threshold"
                    else 0.1
                    if isinstance(default, float)
                    else 1,
                    unit_of_measurement="°F"
                    if key
                    in (
                        "hysteresis",
                        "stop_early",
                        "heat_target",
                        "cool_target",
                        "min_band",
                        "heat_demand",
                        "cool_demand",
                    )
                    else "°F/min"
                    if key == "response_threshold"
                    else "reports"
                    if key == "response_min_samples"
                    else "s",
                )
            )
    return vol.Schema(fields)


def checked(hass, data, exclude=None):
    others = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != exclude:
            config = {**entry.data, **entry.options}
            others.extend(config.get("heaters", []) + config.get("coolers", []))
    virtual = [
        entity.entity_id
        for entity in er.async_get(hass).entities.values()
        if entity.platform == DOMAIN
    ]
    return validate(data, others, virtual)


class UnifiedClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return UnifiedClimateOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                config = checked(self.hass, user_input)
            except ValueError, TypeError:
                errors["base"] = "invalid_zone"
            else:
                return self.async_create_entry(title=config["name"], data=config)
        return self.async_show_form(
            step_id="user",
            data_schema=schema({**DEFAULTS, **(user_input or {})}),
            errors=errors,
        )


class UnifiedClimateOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        current = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            try:
                config = checked(
                    self.hass,
                    {
                        **current,
                        **user_input,
                        "outdoor_sensor": user_input.get("outdoor_sensor", ""),
                    },
                    self.config_entry.entry_id,
                )
            except ValueError, TypeError:
                errors["base"] = "invalid_zone"
            else:
                return self.async_create_entry(title="", data=config)
        return self.async_show_form(
            step_id="init",
            data_schema=schema({**current, **(user_input or {})}),
            errors=errors,
        )
