"""Render standalone offline HTML without changing storage."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from html import escape
from pathlib import Path

from src.services import get_top_aeroplanes
from src.snapshots import FlightSnapshot

_ASSETS = Path(__file__).resolve().parent / "assets"


def build_report_data(snapshot: FlightSnapshot) -> dict[str, object]:
    """Prepare serializable observations and snapshot statistics.

    A missing position affects map visibility only. All aircraft
    contribute to the tables and counts, and means include known
    measurements only.
    """
    planes = [observation.plane for observation in snapshot.observations]
    observations = []
    for observation in snapshot.observations:
        record = observation.plane.to_dict()
        record.update(
            latitude=observation.latitude,
            longitude=observation.longitude,
            position_time=observation.position_time,
        )
        observations.append(record)

    heights = [
        plane.altitude for plane in planes if plane.altitude is not None
    ]
    speeds = [plane.velocity for plane in planes if plane.velocity is not None]
    located = sum(
        observation.latitude is not None and observation.longitude is not None
        for observation in snapshot.observations
    )
    grounded = sum(plane.on_ground for plane in planes)
    registrations = Counter(plane.origin_country for plane in planes)
    bands = [
        {"label": "Ниже 3 000 м", "color": "#40d6b3", "count": 0},
        {"label": "3 000 ≤ h < 9 000 м", "color": "#69aef8", "count": 0},
        {"label": "От 9 000 м", "color": "#ffb36b", "count": 0},
        {"label": "Нет высоты", "color": "#9aa9bd", "count": 0},
    ]
    altitude_counts = [0, 0, 0, 0]
    for plane in planes:
        altitude = plane.altitude
        if altitude is None:
            altitude_counts[3] += 1
        elif altitude < 3000:
            altitude_counts[0] += 1
        elif altitude < 9000:
            altitude_counts[1] += 1
        else:
            altitude_counts[2] += 1
    for band, count in zip(bands, altitude_counts):
        band["count"] = count

    return {
        "country": snapshot.country,
        "bounds": {
            "south": snapshot.bounds.south,
            "north": snapshot.bounds.north,
            "west": snapshot.bounds.west,
            "east": snapshot.bounds.east,
        },
        "api_timestamp": snapshot.api_timestamp,
        "received_at": snapshot.received_at.isoformat(),
        "observations": observations,
        "statistics": {
            "total": len(planes),
            "airborne": len(planes) - grounded,
            "on_ground": grounded,
            "located": located,
            "missing_coordinates": len(planes) - located,
            "mean_altitude": (
                math.fsum(value / len(heights) for value in heights)
                if heights
                else None
            ),
            "mean_velocity": (
                math.fsum(value / len(speeds) for value in speeds)
                if speeds
                else None
            ),
        },
        "top": [plane.to_dict() for plane in get_top_aeroplanes(planes, 10)],
        "registration_counts": [
            {"country": country, "count": count}
            for country, count in sorted(
                registrations.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "altitude_counts": bands,
    }


def _json_for_script(value: object) -> str:
    """Keep JSON inert in HTML, even with </script> in text."""
    result = json.dumps(value, ensure_ascii=False, allow_nan=False)
    for character, replacement in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        result = result.replace(character, replacement)
    return result


def render_report(snapshot: FlightSnapshot) -> str:
    """Return portable HTML with the map, data, styles and scripts."""
    template = (_ASSETS / "report.html").read_text(encoding="utf-8")
    leaflet_css = (_ASSETS / "leaflet-1.9.4.css").read_text(encoding="utf-8")
    # Circle markers require no icon images. Remove upstream image
    # URLs so no relative asset requests are possible when opening
    # the saved report.
    leaflet_css = re.sub(r"url\([^)]*\)", "none", leaflet_css)
    leaflet_js = (_ASSETS / "leaflet-1.9.4.js").read_text(encoding="utf-8")
    leaflet_js = re.sub(r"//# sourceMappingURL=.*", "", leaflet_js)
    geography = json.loads(
        (_ASSETS / "countries-110m.geojson").read_text(encoding="utf-8")
    )
    replacements = {
        "@@TITLE@@": escape(snapshot.country),
        "@@LEAFLET_CSS@@": leaflet_css,
        "@@REPORT_CSS@@": (_ASSETS / "report.css").read_text(encoding="utf-8"),
        "@@DATA@@": _json_for_script(build_report_data(snapshot)),
        "@@GEOGRAPHY@@": _json_for_script(geography),
        "@@LEAFLET_JS@@": leaflet_js,
        "@@LEAFLET_LICENSE@@": (_ASSETS / "LICENSE-Leaflet.txt").read_text(
            encoding="utf-8"
        ),
        "@@REPORT_JS@@": (_ASSETS / "report.js").read_text(encoding="utf-8"),
    }
    # Substitute in one pass: text from external data is never
    # interpreted as another template placeholder.
    return re.sub(
        r"@@[A-Z_]+@@", lambda match: replacements[match.group()], template
    )
