"""Pure, Fahrenheit-based control policy (no Home Assistant imports)."""


def aggregate(samples, method="median", max_age=300):
    """Return an aggregated valid temperature or None."""
    import math
    import statistics

    values = []
    for value, unit, age in samples:
        try:
            value = float(value)
        except TypeError, ValueError:
            continue
        if (
            not math.isfinite(value)
            or age < 0
            or age > max_age
            or unit not in ("°C", "°F")
        ):
            continue
        value = value * 1.8 + 32 if unit == "°C" else value
        if -40 <= value <= 140:
            values.append(value)
    if not values:
        return None
    return statistics.mean(values) if method == "mean" else statistics.median(values)


def demand(
    mode, temperature, previous="off", low=68, high=75, hysteresis=0.3, stop_early=0.3
):
    """Requested action, distinct from physical equipment action."""
    if temperature is None or mode == "off":
        return "off"
    if mode in ("heat", "heat_cool"):
        boundary = (
            low - stop_early if previous == "heat" else low - stop_early - hysteresis
        )
        if temperature < boundary:
            return "heat"
    if mode in ("cool", "heat_cool"):
        boundary = high - hysteresis if previous == "cool" else high + hysteresis
        if temperature > boundary:
            return "cool"
    return "off"
