"""Read-only report data separate from the coursework storage schema."""

from dataclasses import dataclass
from datetime import datetime

from src.models import Aeroplane, BoundingBox


@dataclass(frozen=True)
class AircraftObservation:
    """Aircraft with optional map metadata from one API response."""

    plane: Aeroplane
    latitude: float | None
    longitude: float | None
    position_time: int | None = None


@dataclass(frozen=True)
class FlightSnapshot:
    """An immutable, coherent result for a country's map and report."""

    country: str
    bounds: BoundingBox
    api_timestamp: int | None
    received_at: datetime
    observations: tuple[AircraftObservation, ...]
