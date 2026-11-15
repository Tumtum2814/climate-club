import pytest

from custom_components.unified_climate.settings import validate

BASE = {"sensors": ["sensor.room"], "heaters": ["climate.ecobee"]}


@pytest.mark.parametrize(
    "change,others,virtual",
    [
        ({"sensors": []}, (), ()),
        ({"heaters": [], "coolers": []}, (), ()),
        ({"coolers": ["climate.ecobee"]}, (), ()),
        ({}, ("climate.ecobee",), ()),
        ({}, (), ("climate.ecobee",)),
        ({"heat_target": 75, "cool_target": 75, "coolers": ["climate.ac"]}, (), ()),
        ({"hysteresis": float("nan")}, (), ()),
        ({"cool_min_off": 0}, (), ()),
        ({"heat_demand": 100}, (), ()),
        ({"sensors": ["climate.bad"]}, (), ()),
    ],
)
def test_rejects_unsafe_config(change, others, virtual):
    with pytest.raises(ValueError):
        validate({**BASE, **change}, others, virtual)


def test_valid_mapping_has_cautious_defaults():
    assert validate(BASE)["startup_delay"] == 300


@pytest.mark.parametrize("age", [0, -1, 86401, float("nan"), float("inf")])
def test_outdoor_age_limit_is_validated(age):
    with pytest.raises(ValueError):
        validate({**BASE, "outdoor_stale_after": age})


@pytest.mark.parametrize(
    "config",
    [
        {**BASE, "heat_target": 80, "cool_target": 75},
        {"sensors": ["sensor.room"], "coolers": ["climate.ac"], "cool_target": 60},
    ],
)
def test_single_direction_zone_has_no_unused_target_band(config):
    assert validate(config)


def test_valid_decimal_band_is_not_rejected_by_float_rounding():
    assert validate(
        {
            **BASE,
            "coolers": ["climate.ac"],
            "heat_target": 68.2,
            "cool_target": 69.3,
            "min_band": 1.1,
        }
    )
