"""Serialized zone ownership and Home Assistant service reconciliation."""

import asyncio
import math
import time
from dataclasses import dataclass, field

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .control import aggregate, demand
from .settings import validate


@dataclass
class Zone:
    config: dict
    mode: str = "off"
    owned: bool = False
    requested: str = "off"
    temperature: float | None = None
    error: str | None = None
    callback: object = None
    enabled_at: float = 0
    outdoor: float | None = None
    listeners: list = field(default_factory=list)


class Manager:
    def __init__(self, hass, clock=time.monotonic):
        self.hass = hass
        self.clock = clock
        self.zones = {}
        self.lock = asyncio.Lock()
        self.transitions = {}  # Verified reported mode, not physical HVAC action.
        self.attempts = {}
        self.potential = {}  # A failed/optimistic start might still have reached equipment.
        self.last_direction = None
        self.quiet_since = None

    def house_directions(self):
        directions = set(self.potential.values())
        for zone in self.zones.values():
            for entity in zone.config["heaters"] + zone.config["coolers"]:
                state = self.hass.states.get(entity)
                if not state or state.state in ("unknown", "unavailable"):
                    directions.add("unknown")
                elif state.state in ("heat", "cool"):
                    directions.add(state.state)
                elif state.state != "off":
                    directions.add("unknown")
                action = state.attributes.get("hvac_action") if state else None
                if action in ("heating", "cooling"):
                    directions.add("heat" if action == "heating" else "cool")
        return directions

    def update_quiet(self):
        active = self.house_directions()
        if active:
            self.quiet_since = None
            if len(active) == 1 and next(iter(active)) in ("heat", "cool"):
                self.last_direction = next(iter(active))
        elif self.quiet_since is None:
            self.quiet_since = self.clock()

    def can_start(self, direction):
        if self.house_directions() - {direction}:
            return False
        delay = max(z.config["changeover_delay"] for z in self.zones.values())
        return self.last_direction in (None, direction) or (
            self.quiet_since is not None and self.clock() - self.quiet_since >= delay
        )

    def add(self, key, config):
        others = [
            e
            for z in self.zones.values()
            for e in z.config["heaters"] + z.config["coolers"]
        ]
        self.zones[key] = Zone(validate(config, others))
        return self.zones[key]

    async def set_mode(self, key, mode):
        async with self.lock:
            zone = self.zones[key]
            allowed = ["off"]
            if zone.config["heaters"]:
                allowed.append("heat")
            if zone.config["coolers"]:
                allowed.append("cool")
            if len(allowed) == 3:
                allowed.append("heat_cool")
            if mode not in allowed:
                raise ValueError("Unsupported mode")
            if mode != "off" and not zone.owned:
                self.update_quiet()
                zone.owned = True
                zone.enabled_at = self.clock()
                for entity in zone.config["heaters"] + zone.config["coolers"]:
                    await self.command(zone, entity, "off", None, force=True)
            zone.mode = mode
        await self.tick()

    def record_transition(self, entity, desired):
        if self.transitions.get(entity, (None,))[0] != desired:
            self.transitions[entity] = (desired, self.clock())
        self.potential.pop(entity, None)

    async def command(self, zone, entity, desired, target, force=False):
        state = self.hass.states.get(entity)
        if not state or state.state in ("unavailable", "unknown"):
            zone.error = f"{entity}: unavailable; demand retained"
            return
        payload_target = target
        if desired != "off":
            try:
                unit = state.attributes["temperature_unit"]
                low, high = (
                    float(state.attributes["min_temp"]),
                    float(state.attributes["max_temp"]),
                )
                if (
                    unit not in ("°F", "°C")
                    or not math.isfinite(low + high)
                    or low > high
                ):
                    raise ValueError("invalid equipment bounds")
                policy_low, policy_high = (50, 80) if desired == "heat" else (60, 85)
                low = max(low, TemperatureConverter.convert(policy_low, "°F", unit))
                high = min(high, TemperatureConverter.convert(policy_high, "°F", unit))
                if low > high:
                    raise ValueError(
                        "equipment and policy setpoint bounds do not overlap"
                    )
                target = min(
                    high, max(low, TemperatureConverter.convert(target, "°F", unit))
                )
                payload_target = TemperatureConverter.convert(
                    target, unit, self.hass.config.units.temperature_unit
                )
            except (KeyError, TypeError, ValueError) as err:
                zone.error = f"{entity}: unsafe target metadata: {err}"
                await self.command(zone, entity, "off", None, force=True)
                return

        def target_matches(state):
            try:
                return math.isclose(
                    float(state.attributes.get("temperature")),
                    target,
                    abs_tol=0.26
                    if state.attributes.get("temperature_unit") == "°C"
                    else 0.51,
                )
            except TypeError, ValueError:
                return False

        matches = state.state == desired and (desired == "off" or target_matches(state))
        if desired == "off" and entity in self.potential:
            matches = False
        if matches:
            self.record_transition(entity, desired)
            return
        previous_attempt, previous_desired = self.attempts.get(
            entity, (-float("inf"), None)
        )
        if self.clock() - previous_attempt < 30 and not (
            force and desired == "off" and previous_desired != "off"
        ):
            zone.error = f"{entity}: awaiting retry"
            return
        self.attempts[entity] = (self.clock(), desired)
        try:
            if desired != "off":
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": entity, "temperature": payload_target},
                    blocking=True,
                )
                state = self.hass.states.get(entity)
                if not state or not target_matches(state):
                    zone.error = f"{entity}: target not confirmed; demand retained"
                    return
                self.potential[entity] = desired
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity, "hvac_mode": desired},
                blocking=True,
            )
        except (HomeAssistantError, TimeoutError, ValueError) as err:
            zone.error = f"{entity}: {err}; demand retained"
            return
        state = self.hass.states.get(entity)
        if (
            state
            and state.state == desired
            and (desired == "off" or target_matches(state))
        ):
            self.record_transition(entity, desired)
        else:
            zone.error = f"{entity}: mode not confirmed; demand retained"

    async def tick(self):
        async with self.lock:
            self.update_quiet()
            for zone in self.zones.values():
                c = zone.config
                zone.error = None
                samples = []
                for entity in c["sensors"]:
                    state = self.hass.states.get(entity)
                    if state:
                        samples.append(
                            (
                                state.state,
                                state.attributes.get("unit_of_measurement"),
                                (dt_util.utcnow() - state.last_updated).total_seconds(),
                            )
                        )
                zone.temperature = aggregate(
                    samples, c["aggregation"], c["stale_after"]
                )
                outside = (
                    self.hass.states.get(c["outdoor_sensor"])
                    if c["outdoor_sensor"]
                    else None
                )
                zone.outdoor = (
                    aggregate(
                        [
                            (
                                outside.state,
                                outside.attributes.get("unit_of_measurement"),
                                (
                                    dt_util.utcnow() - outside.last_updated
                                ).total_seconds(),
                            )
                        ],
                        max_age=c["stale_after"],
                    )
                    if outside
                    else None
                )
                zone.requested = demand(
                    zone.mode,
                    zone.temperature,
                    zone.requested,
                    c["heat_target"],
                    c["cool_target"],
                    c["hysteresis"],
                    c["stop_early"],
                )
                if zone.owned:
                    for kind, entities in (
                        ("heat", c["heaters"]),
                        ("cool", c["coolers"]),
                    ):
                        for entity in entities:
                            force = zone.mode == "off" or zone.temperature is None
                            desired = kind if zone.requested == kind else "off"
                            observed = self.hass.states.get(entity)
                            if (
                                entity in self.transitions
                                and entity not in self.potential
                                and observed
                                and observed.state in ("off", "heat", "cool")
                            ):
                                self.record_transition(entity, observed.state)
                            last_mode, changed_at = self.transitions.get(
                                entity, ("off", zone.enabled_at)
                            )
                            minimum = (
                                c[f"{kind}_min_off"]
                                if last_mode == "off"
                                else c[f"{kind}_min_on"]
                            )
                            if entity not in self.transitions:
                                desired = "off"
                                force = True
                            if (
                                not force
                                and self.clock() - zone.enabled_at < c["startup_delay"]
                            ):
                                desired = "off"
                            elif (
                                desired != last_mode
                                and not force
                                and self.clock() - changed_at < minimum
                            ):
                                continue
                            state = self.hass.states.get(entity)
                            if not state or state.state in ("unknown", "unavailable"):
                                zone.error = f"{entity}: unavailable; demand retained"
                                continue
                            if desired != "off":
                                if not self.can_start(desired):
                                    zone.error = "House interlock: opposite or unknown equipment / changeover delay"
                                    continue
                                self.last_direction = desired
                                self.quiet_since = None
                            await self.command(
                                zone, entity, desired, c[f"{kind}_demand"], force=force
                            )
                for listener in list(zone.listeners):
                    listener()
                if zone.callback:
                    zone.callback()
            self.update_quiet()
