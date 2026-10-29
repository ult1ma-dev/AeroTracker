"""Validated domain objects independent of API response formats."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name}: ожидается строка")
    result = value.strip()
    if not result:
        raise ValueError(f"{name}: строка не должна быть пустой")
    return result


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name}: ожидается строка или None")
    return value.strip() or None


def _number(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name}: ожидается число или None")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name}: число должно быть конечным") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name}: число должно быть конечным")
    return result


@dataclass(frozen=True)
class BoundingBox:
    """A rectangular search area in decimal degrees."""

    south: float
    north: float
    west: float
    east: float

    def __post_init__(self) -> None:
        for name in ("south", "north", "west", "east"):
            value = _number(getattr(self, name), name)
            if value is None:
                raise TypeError(f"{name}: координата обязательна")
            object.__setattr__(self, name, value)
        if not -90 <= self.south < self.north <= 90:
            raise ValueError("Некорректные южная и северная широты")
        if not -180 <= self.west < self.east <= 180:
            raise ValueError("Некорректные западная и восточная долготы")


class Aeroplane:
    """An aircraft observation with read-only, validated attributes.

    Velocity is measured in metres per second and altitude in metres.
    Missing measurements stay ``None``; altitude may be negative.
    """

    __slots__ = (
        "__icao24",
        "__callsign",
        "__origin_country",
        "__velocity",
        "__altitude",
        "__on_ground",
    )

    def __init__(
        self,
        icao24: str,
        callsign: str | None,
        origin_country: str,
        velocity: float | None,
        altitude: float | None,
        on_ground: bool = False,
    ) -> None:
        identifier = _text(icao24, "icao24").lower()
        if re.fullmatch(r"[0-9a-f]{6}", identifier) is None:
            raise ValueError(
                "icao24: ожидаются шесть шестнадцатеричных знаков"
            )
        speed = _number(velocity, "velocity")
        if speed is not None and speed < 0:
            raise ValueError("velocity: скорость не может быть отрицательной")
        if not isinstance(on_ground, bool):
            raise TypeError("on_ground: ожидается bool")
        self.__icao24 = identifier
        self.__callsign = _optional_text(callsign, "callsign")
        self.__origin_country = _text(origin_country, "origin_country")
        self.__velocity = speed
        self.__altitude = _number(altitude, "altitude")
        self.__on_ground = on_ground

    @property
    def icao24(self) -> str:
        return self.__icao24

    @property
    def callsign(self) -> str | None:
        return self.__callsign

    @property
    def origin_country(self) -> str:
        return self.__origin_country

    @property
    def velocity(self) -> float | None:
        return self.__velocity

    @property
    def altitude(self) -> float | None:
        return self.__altitude

    @property
    def on_ground(self) -> bool:
        return self.__on_ground

    def compare_speed(self, other: Aeroplane) -> int:
        """Return -1, 0 or 1; unknown speeds cannot be compared."""
        if not isinstance(other, Aeroplane):
            raise TypeError("Сравнивать можно только самолёты")
        return self.__compare(self.velocity, other.velocity, "скорости")

    def compare_altitude(self, other: Aeroplane) -> int:
        """Return -1, 0 or 1; unknown altitudes cannot be compared."""
        if not isinstance(other, Aeroplane):
            raise TypeError("Сравнивать можно только самолёты")
        return self.__compare(self.altitude, other.altitude, "высоты")

    @staticmethod
    def __compare(left: float | None, right: float | None, name: str) -> int:
        if left is None or right is None:
            raise ValueError(f"Нельзя сравнить самолёты: неизвестны {name}")
        return (left > right) - (left < right)

    def to_dict(self) -> dict[str, object]:
        """Return the storage format without API-specific fields."""
        return {
            "icao24": self.icao24,
            "callsign": self.callsign,
            "origin_country": self.origin_country,
            "velocity": self.velocity,
            "altitude": self.altitude,
            "on_ground": self.on_ground,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Aeroplane:
        """Restore a validated observation from its stored fields."""
        if not isinstance(data, Mapping):
            raise TypeError("Запись самолёта должна быть словарём")
        try:
            identifier = _text(data["icao24"], "icao24")
            callsign = _optional_text(data["callsign"], "callsign")
            country = _text(data["origin_country"], "origin_country")
            velocity = _number(data["velocity"], "velocity")
            altitude = _number(data["altitude"], "altitude")
        except KeyError as exc:
            raise ValueError(
                f"В записи отсутствует поле {exc.args[0]}"
            ) from exc
        on_ground = data.get("on_ground", False)
        if not isinstance(on_ground, bool):
            raise TypeError("on_ground: ожидается bool")
        return cls(
            identifier, callsign, country, velocity, altitude, on_ground
        )
