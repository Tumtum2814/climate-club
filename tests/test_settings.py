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
        ({"heat_target": 75, "cool_target": 75}, (), ()),
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
