"""Domain validation, encapsulation, conversion and comparison."""

from dataclasses import FrozenInstanceError

import pytest

from src.models import Aeroplane, BoundingBox


def make_aeroplane(**changes):
    values = {
        "icao24": "abc123",
        "callsign": "TEST123",
        "origin_country": "Germany",
        "velocity": 120.0,
        "altitude": 1000.0,
        "on_ground": False,
    }
    values.update(changes)
    return Aeroplane(**values)


def test_normalizes_values_and_exposes_read_only_attributes():
    aeroplane = make_aeroplane(
        icao24=" ABC123 ",
        callsign=" TEST123 ",
        origin_country=" Germany ",
        velocity=120,
        altitude=-10,
    )
    assert aeroplane.icao24 == "abc123"
    assert aeroplane.callsign == "TEST123"
    assert aeroplane.origin_country == "Germany"
    assert aeroplane.velocity == 120.0
    assert aeroplane.altitude == -10.0
    assert aeroplane.on_ground is False
    with pytest.raises(AttributeError):
        aeroplane.altitude = 2000
    with pytest.raises(AttributeError):
        aeroplane.icao24 = "ffffff"


@pytest.mark.parametrize("callsign", [None, "", "   "])
def test_unknown_callsign_and_measurements_are_preserved(callsign):
    aeroplane = make_aeroplane(
        callsign=callsign, velocity=None, altitude=None, on_ground=True
    )
    assert aeroplane.callsign is None
    assert aeroplane.velocity is None
    assert aeroplane.altitude is None
    assert aeroplane.on_ground is True


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"icao24": ""}, ValueError),
        ({"icao24": "nothex"}, ValueError),
        ({"icao24": "12345"}, ValueError),
        ({"icao24": 123456}, TypeError),
        ({"origin_country": " "}, ValueError),
        ({"origin_country": None}, TypeError),
        ({"callsign": 123}, TypeError),
        ({"velocity": -0.1}, ValueError),
        ({"velocity": float("nan")}, ValueError),
        ({"velocity": float("inf")}, ValueError),
        ({"velocity": True}, TypeError),
        ({"velocity": "120"}, TypeError),
        ({"altitude": float("-inf")}, ValueError),
        ({"altitude": False}, TypeError),
        ({"altitude": "100"}, TypeError),
        ({"altitude": 10**1000}, ValueError),
        ({"on_ground": 1}, TypeError),
    ],
)
def test_rejects_invalid_fields(changes, error):
    with pytest.raises(error):
        make_aeroplane(**changes)


@pytest.mark.parametrize("measurement", ["velocity", "altitude"])
@pytest.mark.parametrize(
    ("left", "right", "expected"), [(1, 2, -1), (2, 2, 0), (3, 2, 1)]
)
def test_compare_measurements(measurement, left, right, expected):
    first = make_aeroplane(**{measurement: left})
    second = make_aeroplane(**{measurement: right})
    method = (
        first.compare_speed
        if measurement == "velocity"
        else first.compare_altitude
    )
    assert method(second) == expected


@pytest.mark.parametrize("method", ["compare_speed", "compare_altitude"])
def test_comparison_rejects_other_types(method):
    with pytest.raises(TypeError):
        getattr(make_aeroplane(), method)(100)


@pytest.mark.parametrize("measurement", ["velocity", "altitude"])
@pytest.mark.parametrize("missing_left", [False, True])
def test_unknown_measurement_cannot_be_compared(measurement, missing_left):
    known = make_aeroplane()
    unknown = make_aeroplane(**{measurement: None})
    left, right = (unknown, known) if missing_left else (known, unknown)
    method = (
        left.compare_speed
        if measurement == "velocity"
        else left.compare_altitude
    )
    with pytest.raises(ValueError):
        method(right)


def test_storage_round_trip_preserves_unknown_and_negative_values():
    aeroplane = make_aeroplane(callsign=None, velocity=None, altitude=-50.0)
    data = aeroplane.to_dict()
    assert data == {
        "icao24": "abc123",
        "callsign": None,
        "origin_country": "Germany",
        "velocity": None,
        "altitude": -50.0,
        "on_ground": False,
    }
    assert Aeroplane.from_dict(data).to_dict() == data
    data["altitude"] = 9999
    assert aeroplane.altitude == -50.0


def test_from_dict_defaults_on_ground_and_ignores_extra_fields():
    data = make_aeroplane().to_dict()
    del data["on_ground"]
    data["additional_field"] = "ignored"
    assert Aeroplane.from_dict(data).on_ground is False


@pytest.mark.parametrize(
    "field", ["icao24", "callsign", "origin_country", "velocity", "altitude"]
)
def test_from_dict_reports_missing_field(field):
    data = make_aeroplane().to_dict()
    del data[field]
    with pytest.raises(ValueError, match=field):
        Aeroplane.from_dict(data)


def test_from_dict_validates_types():
    with pytest.raises(TypeError):
        Aeroplane.from_dict([])
    data = make_aeroplane().to_dict()
    data["on_ground"] = "false"
    with pytest.raises(TypeError):
        Aeroplane.from_dict(data)


def test_bounding_box_is_validated_and_immutable():
    bounds = BoundingBox(-90, 90, -180, 180)
    assert bounds.south == -90.0
    assert isinstance(bounds.north, float)
    with pytest.raises(FrozenInstanceError):
        bounds.south = 0


@pytest.mark.parametrize(
    "coordinates",
    [
        (-91, 20, 10, 20),
        (10, 91, 10, 20),
        (20, 10, 10, 20),
        (10, 10, 10, 20),
        (10, 20, -181, 20),
        (10, 20, 10, 181),
        (10, 20, 20, 10),
        (10, 20, 10, 10),
        (float("nan"), 20, 10, 20),
        (10, float("inf"), 10, 20),
    ],
)
def test_bounding_box_rejects_invalid_coordinates(coordinates):
    with pytest.raises(ValueError):
        BoundingBox(*coordinates)


@pytest.mark.parametrize("value", [None, "10", True])
def test_bounding_box_rejects_invalid_coordinate_types(value):
    with pytest.raises(TypeError):
        BoundingBox(value, 20, 10, 20)
