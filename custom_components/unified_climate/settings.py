"""Zone configuration, always expressed in Fahrenheit and seconds."""

DEFAULTS = {
    "name": "Zone",
    "sensors": [],
    "heaters": [],
    "coolers": [],
    "trusted_action_entities": [],
    "outdoor_sensor": "",
    "aggregation": "median",
    "hysteresis": 0.3,
    "stop_early": 0.3,
    "heat_target": 68.0,
    "cool_target": 75.0,
    "min_band": 2.0,
    "heat_min_on": 180,
    "heat_min_off": 180,
    "cool_min_on": 300,
    "cool_min_off": 300,
    "startup_delay": 300,
    "changeover_delay": 600,
    "stale_after": 900,
    "heat_demand": 75.0,
    "cool_demand": 65.0,
}


def validate(data, other_actuators=(), virtual_entities=()):
    import math
    import re

    config = {**DEFAULTS, **data}
    actuators = config["heaters"] + config["coolers"]
    if not config["sensors"] or not actuators or not str(config["name"]).strip():
        raise ValueError("Select temperature sensors and at least one actuator")
    for key in ("sensors", "heaters", "coolers"):
        domain = "sensor" if key == "sensors" else "climate"
        if not isinstance(config[key], list) or any(
            not re.fullmatch(domain + r"\.[a-z0-9_]+", entity) for entity in config[key]
        ):
            raise ValueError("Invalid entity mapping")
    if len(set(actuators)) != len(actuators) or set(actuators) & (
        set(other_actuators) | set(virtual_entities)
    ):
        raise ValueError("Actuator already assigned, virtual, or duplicated")
    if not set(config["trusted_action_entities"]).issubset(actuators):
        raise ValueError("Trusted action sources must be mapped actuators")
    if config["outdoor_sensor"] and not re.fullmatch(
        r"sensor\.[a-z0-9_]+", config["outdoor_sensor"]
    ):
        raise ValueError("Invalid outdoor sensor")
    if config["aggregation"] not in ("mean", "median"):
        raise ValueError("Invalid aggregation")
    ranges = {
        "hysteresis": (0.1, 2),
        "stop_early": (0, 2),
        "min_band": (1, 10),
        "heat_target": (50, 85),
        "cool_target": (50, 85),
        "heat_demand": (50, 80),
        "cool_demand": (60, 85),
        "stale_after": (60, 86400),
        "startup_delay": (60, 3600),
        "changeover_delay": (60, 3600),
        "heat_min_on": (30, 3600),
        "heat_min_off": (30, 3600),
        "cool_min_on": (180, 3600),
        "cool_min_off": (180, 3600),
    }
    for key, (low, high) in ranges.items():
        value = float(config[key])
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} outside safe bounds")
        config[key] = value
    if config["cool_target"] - config["heat_target"] < config["min_band"]:
        raise ValueError("Heat/cool targets require a separate band")
    return config
