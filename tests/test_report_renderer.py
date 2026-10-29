"""Report contents, missing data and safe standalone HTML embedding."""

import json
from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser

import pytest

from src.models import Aeroplane, BoundingBox
from src.reporting.renderer import build_report_data, render_report
from src.snapshots import AircraftObservation, FlightSnapshot


class ReportDocument(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_data = False
        self.data = []
        self.external_resources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "report-data":
            self.in_data = True
        if tag in {"script", "link", "img", "iframe"}:
            for name in ("src", "href"):
                value = attributes.get(name) or ""
                if value.startswith(("http:", "https:", "//")):
                    self.external_resources.append(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False

    def handle_data(self, data):
        if self.in_data:
            self.data.append(data)


@pytest.fixture
def snapshot():
    return FlightSnapshot(
        "Spain",
        BoundingBox(27, 44, -19, 5),
        1793100000,
        datetime(2026, 10, 27, 12, tzinfo=timezone.utc),
        (
            AircraftObservation(
                Aeroplane("000001", "HIGH", "Spain", 220, 11000), 40, -3
            ),
            AircraftObservation(
                Aeroplane("000002", None, "United States", None, None, True),
                None,
                None,
            ),
            AircraftObservation(
                Aeroplane("000003", "LOW", "Spain", 100, -10), 0, 0
            ),
        ),
    )


def test_statistics_top_and_distributions_use_all_observations(snapshot):
    data = build_report_data(snapshot)
    assert data["statistics"] == {
        "total": 3,
        "airborne": 2,
        "on_ground": 1,
        "located": 2,
        "missing_coordinates": 1,
        "mean_altitude": 5495.0,
        "mean_velocity": 160.0,
    }
    assert [plane["icao24"] for plane in data["top"]] == [
        "000001",
        "000003",
    ]
    assert data["registration_counts"] == [
        {"country": "Spain", "count": 2},
        {"country": "United States", "count": 1},
    ]
    assert sum(group["count"] for group in data["altitude_counts"]) == 3


def test_report_is_standalone_and_embeds_data(snapshot):
    document = ReportDocument()
    html = render_report(snapshot)
    document.feed(html)
    data = json.loads("".join(document.data))
    assert document.external_resources == []
    assert data == build_report_data(snapshot)
    assert data["observations"][2]["latitude"] == 0
    assert data["observations"][1]["latitude"] is None
    assert "Leaflet" in html
    assert "Natural Earth" in html


def test_api_text_cannot_break_out_of_json_or_html(snapshot):
    attack = '</script><script>alert("unsafe")</script>'
    dangerous = replace(
        snapshot,
        country=attack,
        observations=(
            AircraftObservation(
                Aeroplane("000001", attack, attack, 220, 11000), 40, -3
            ),
        ),
    )
    html = render_report(dangerous)
    document = ReportDocument()
    document.feed(html)
    assert attack not in html
    data = json.loads("".join(document.data))
    assert data["country"] == attack
    assert data["observations"][0]["callsign"] == attack


def test_empty_snapshot_is_a_valid_report(snapshot):
    empty = replace(snapshot, observations=(), api_timestamp=None)
    data = build_report_data(empty)
    assert data["statistics"]["total"] == 0
    assert data["statistics"]["mean_altitude"] is None
    assert data["statistics"]["mean_velocity"] is None
    assert data["top"] == []
    assert data["registration_counts"] == []
    document = ReportDocument()
    document.feed(render_report(empty))
    assert json.loads("".join(document.data))["observations"] == []


def test_all_unknown_measurements_are_not_zero(snapshot):
    unknown = replace(
        snapshot,
        observations=(
            AircraftObservation(
                Aeroplane("000001", None, "Spain", None, None), None, None
            ),
        ),
    )
    data = build_report_data(unknown)
    assert data["statistics"]["mean_altitude"] is None
    assert data["statistics"]["mean_velocity"] is None
    assert data["statistics"]["missing_coordinates"] == 1
    assert data["top"] == []
    assert data["altitude_counts"][-1]["count"] == 1


def test_extreme_optional_api_time_does_not_break_rendering(snapshot):
    assert "Spain" in render_report(replace(snapshot, api_timestamp=10**100))


def test_means_of_large_finite_measurements_remain_finite(snapshot):
    large = replace(
        snapshot,
        observations=tuple(
            AircraftObservation(
                Aeroplane(f"{index:06x}", "LARGE", "Spain", 1e308, 1e308),
                None,
                None,
            )
            for index in (1, 2)
        ),
    )
    statistics = build_report_data(large)["statistics"]
    assert statistics["mean_velocity"] == 1e308
    assert statistics["mean_altitude"] == 1e308
    assert "Spain" in render_report(large)
