import pytest

from custom_components.unified_climate.response import ResponseMonitor
from custom_components.unified_climate.settings import validate


def monitor(**kwargs):
    return ResponseMonitor(
        config(
            response_enabled=True,
            response_start_grace=60,
            response_stop_settling=60,
            response_start_window=120,
            response_stop_window=120,
            **kwargs,
        )
    )


def feed(m, times, values, entity="sensor.room"):
    for t, value in zip(times, values, strict=True):
        m.reading(entity, str(value), "°F", t, t)


def test_start_warming_to_flat_is_consistent_after_grace():
    m = monitor()
    feed(m, [0, 60, 120], [75, 75.2, 75.4])
    m.command("start", 120)
    assert m.state == "observing_start"
    feed(m, [181, 240, 300], [75.5, 75.5, 75.5])
    m.advance(300)
    assert m.state == "cooling_likely"


def config(**kwargs):
    return validate({"sensors": ["sensor.room"], "coolers": ["climate.ac"], **kwargs})


@pytest.mark.parametrize(
    "post, expected",
    [([75, 74.95, 74.9], "stopped_likely"), ([75, 74.8, 74.6], "continued_cooling")],
)
def test_stop_weakening_does_not_require_warming(post, expected):
    m = monitor()
    feed(m, [0, 60, 120], [76, 75.8, 75.6])
    m.command("stop", 120)
    feed(m, [181, 240, 300], post)
    m.advance(300)
    assert m.state == expected


@pytest.mark.parametrize(
    "case",
    [
        "error",
        "retry",
        "stale",
        "invalid",
        "unit_change",
        "same_time",
        "missing_baseline",
        "multi",
        "long_window",
    ],
)
def test_evidence_boundaries(case):
    m = monitor(
        **({"response_baseline_window": 60} if case == "long_window" else {}),
        **(
            {"response_sensors": ["sensor.room", "sensor.other"]}
            if case == "multi"
            else {}
        ),
    )
    if case != "missing_baseline":
        feed(m, [0, 30, 60], [76, 76.1, 76.2])
    m.command("start", 60, delivered=case != "error")
    if case == "retry":
        m.command("start", 90)
        assert m.started == 60
    elif case == "stale":
        m.advance(1000)
        assert m.state == "inconclusive"
        assert not m.samples["sensor.room"]
        return
    elif case == "invalid":
        m.reading("sensor.room", "unavailable", "°F", 61, 61)
    elif case == "unit_change":
        m.reading("sensor.room", "24", "°C", 61, 61)
    elif case == "same_time":
        feed(m, [121, 121, 121], [75, 74, 73])
        m.advance(240)
        assert m.state == "inconclusive"
        return
    feed(m, [121, 180, 240], [76.2, 76.2, 76.2])
    m.advance(240)
    assert m.state == (
        "cooling_likely" if case in ("retry", "long_window") else "inconclusive"
    )


def test_staggered_multi_sensor_reports_build_independent_trends_without_fake_aggregate_samples():
    m = monitor(response_sensors=["sensor.room", "sensor.other"])
    for entity, shift in [("sensor.room", 0), ("sensor.other", 1)]:
        for t, value in [(0, 76), (30, 76.1), (60, 76.2)]:
            feed(m, [t + shift], [value], entity)
            m.advance(t + shift)
    m.command("start", 62)
    for t in [123, 180, 241]:
        for entity in m.sensors:
            feed(m, [t], [76.2], entity)
            m.advance(t)
    m.advance(242)
    assert m.state == "cooling_likely"
    assert m.post_counts == {"sensor.room": 3, "sensor.other": 3}


@pytest.mark.parametrize("method", ["median", "mean"])
def test_reports_are_deduplicated_per_sensor_and_celsius_is_supported(method):
    m = monitor(response_sensors=["sensor.room", "sensor.room"], aggregation=method)
    for t, value in [(0, 24), (60, 24.1), (120, 24.2)]:
        m.reading("sensor.room", str(value), "°C", t, t)
        m.reading("sensor.room", str(value), "°C", t, t + 1)
    assert len(m.samples["sensor.room"]) == 3
    m.command("start", 120)
    for t in (181, 240, 300):
        m.reading("sensor.room", "24.2", "°C", t, t)
    m.advance(300)
    assert m.state == "cooling_likely"
    assert m.baseline_slope == pytest.approx(0.18)
    assert m.post_counts == {"sensor.room": 3}
    m.command("stop", 301)
    assert m.state == "observing_stop"
    assert m.started == 301
    m.command("stop", 330, delivered=False)
    m.advance(1000)
    assert m.state == "inconclusive"


def test_disabled_monitor_never_infers_or_collects():
    m = ResponseMonitor(config())
    feed(m, [0, 60, 120], [75, 76, 77])
    m.command("start", 120)
    m.advance(1000)
    assert m.state == "disabled"
    assert m.samples == {"sensor.room": []}


def test_preexisting_cooling_alone_is_not_a_start_response():
    m = monitor()
    feed(m, [0, 60, 120], [76, 75.8, 75.6])
    m.command("start", 120)
    feed(m, [181, 240, 300], [75.4, 75.2, 75.0])
    m.advance(300)
    assert m.state == "no_start_response"


def test_observation_diagnostics_count_only_fresh_postgrace_reports():
    m = monitor()
    feed(m, [0, 60, 120], [75, 75.2, 75.4])
    m.command("start", 120)
    feed(m, [150, 181], [76, 76])
    m.advance(182)
    assert m.diagnostics["post_counts"] == {"sensor.room": 1}
    assert m.diagnostics["baseline_slope_f_per_min"] == pytest.approx(0.2)
    assert m.state == "observing_start"


def test_response_threshold_ui_preserves_small_slope_tuning():
    from custom_components.unified_climate.config_flow import schema

    fields = schema(config()).schema
    selectors = {str(key): value for key, value in fields.items()}
    assert selectors["response_threshold"].config["step"] == 0.001
    assert selectors["response_enabled"].selector_type == "boolean"


def test_monitor_settings_are_opt_in_and_validate():
    c = config()
    assert c.get("response_enabled") is False
    assert c["response_sensors"] == []
    assert config(response_sensors=["sensor.room", "sensor.room"])[
        "response_sensors"
    ] == ["sensor.room"]
    for kwargs in (
        {"response_enabled": 1},
        {"response_min_samples": 2.5},
        {"response_min_samples": True},
        {"response_threshold": float("nan")},
        {"response_start_window": 0},
        {"response_sensors": ["climate.ac"]},
    ):
        with pytest.raises(ValueError):
            config(**kwargs)
