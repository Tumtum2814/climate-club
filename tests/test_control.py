from custom_components.unified_climate.control import aggregate, demand


def test_demand_has_hysteresis_stop_early_and_separate_band():
    assert demand("heat", 67) == "heat"
    assert demand("heat", 67.6, "heat") == "heat"
    assert demand("heat", 67.8, "heat") == "off"
    assert demand("heat_cool", 76) == "cool"
    assert demand("cool", 74.9, "cool") == "cool"
    assert demand("cool", 74.6, "cool") == "off"
    assert demand("heat_cool", 71) == "off"
    assert demand("off", 60, "heat") == "off"
    assert demand("heat", None, "heat") == "off"


def test_sensor_aggregation_converts_and_rejects_invalid_stale():
    samples = [
        (20, "°C", 0),
        (70, "°F", 10),
        (100, "°F", 301),
        (float("nan"), "°F", 0),
        (20, "K", 0),
    ]
    assert aggregate(samples) == 69
    assert aggregate(samples, "mean") == 69
    assert aggregate([(1, "°F", 301)]) is None
