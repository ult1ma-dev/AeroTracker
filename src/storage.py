"""Aircraft storage interface and an atomic JSON file implementation."""

from __future__ import annotations

import json
import math
import os
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from src.exceptions import StorageError
from src.models import Aeroplane


class BaseStorage(ABC):
    """Storage operations used by the application service."""

    @abstractmethod
    def add_aeroplane(self, aeroplane: Aeroplane) -> None:
        """Add an observation or update an existing ICAO identifier."""

    @abstractmethod
    def get_aeroplanes(
        self,
        *,
        origin_countries: Sequence[str] | None = None,
        min_altitude: float | None = None,
        max_altitude: float | None = None,
    ) -> list[Aeroplane]:
        """Read observations matching all supplied criteria."""

    @abstractmethod
    def delete_aeroplane(self, icao24: str) -> bool:
        """Delete by identifier.

        Report whether an observation existed.
        """

    @abstractmethod
    def replace_all(self, aeroplanes: Sequence[Aeroplane]) -> None:
        """Atomically replace the current snapshot."""


class JSONSaver(BaseStorage):
    """Store UTF-8 JSON records without overwriting unreadable data."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.__path = (
            Path(path)
            if path is not None
            else Path(__file__).resolve().parents[1]
            / "data"
            / "aeroplanes.json"
        )

    @property
    def path(self) -> Path:
        return self.__path

    def add_aeroplane(self, aeroplane: Aeroplane) -> None:
        self.__validate_aeroplane(aeroplane)
        observations = {item.icao24: item for item in self.__read()}
        observations[aeroplane.icao24] = aeroplane
        self.__write(list(observations.values()))

    def get_aeroplanes(
        self,
        *,
        origin_countries: Sequence[str] | None = None,
        min_altitude: float | None = None,
        max_altitude: float | None = None,
    ) -> list[Aeroplane]:
        countries = self.__countries(origin_countries)
        lower = self.__altitude(min_altitude, "min_altitude")
        upper = self.__altitude(max_altitude, "max_altitude")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("Нижняя граница высоты превышает верхнюю")
        result: list[Aeroplane] = []
        for aeroplane in self.__read():
            if (
                countries
                and aeroplane.origin_country.casefold() not in countries
            ):
                continue
            altitude = aeroplane.altitude
            if lower is not None and (altitude is None or altitude < lower):
                continue
            if upper is not None and (altitude is None or altitude > upper):
                continue
            result.append(aeroplane)
        return result

    def delete_aeroplane(self, icao24: str) -> bool:
        if not isinstance(icao24, str):
            raise TypeError("icao24: ожидается строка")
        identifier = icao24.strip().lower()
        if not identifier:
            raise ValueError("icao24: строка не должна быть пустой")
        observations = self.__read()
        remaining = [
            item for item in observations if item.icao24 != identifier
        ]
        if len(remaining) == len(observations):
            return False
        self.__write(remaining)
        return True

    def replace_all(self, aeroplanes: Sequence[Aeroplane]) -> None:
        observations: dict[str, Aeroplane] = {}
        for aeroplane in aeroplanes:
            self.__validate_aeroplane(aeroplane)
            observations[aeroplane.icao24] = aeroplane
        self.__read()
        self.__write(list(observations.values()))

    @staticmethod
    def __validate_aeroplane(aeroplane: Aeroplane) -> None:
        if not isinstance(aeroplane, Aeroplane):
            raise TypeError("Ожидается объект Aeroplane")

    @staticmethod
    def __countries(countries: Sequence[str] | None) -> set[str]:
        if isinstance(countries, (str, bytes)):
            raise TypeError("Страны следует передать списком строк")
        result: set[str] = set()
        if countries is None:
            return result
        for country in countries:
            if not isinstance(country, str):
                raise TypeError("Название страны должно быть строкой")
            value = country.strip().casefold()
            if not value:
                raise ValueError("Название страны не должно быть пустым")
            result.add(value)
        return result

    @staticmethod
    def __altitude(value: float | None, name: str) -> float | None:
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

    def __read(self) -> list[Aeroplane]:
        try:
            content = self.__path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError) as exc:
            raise StorageError(
                f"Не удалось прочитать файл {self.__path}: {exc}"
            ) from exc
        try:
            raw: object = json.loads(content)
            if not isinstance(raw, list):
                raise ValueError("В корне JSON ожидается список самолётов")
            observations: dict[str, Aeroplane] = {}
            for record in cast(list[object], raw):
                if not isinstance(record, dict):
                    raise ValueError("Каждая запись должна быть объектом JSON")
                aeroplane = Aeroplane.from_dict(
                    cast(Mapping[str, object], record)
                )
                observations[aeroplane.icao24] = aeroplane
            return list(observations.values())
        except (ValueError, TypeError) as exc:
            raise StorageError(
                f"Некорректные данные в файле {self.__path}: {exc}"
            ) from exc

    def __write(self, aeroplanes: Sequence[Aeroplane]) -> None:
        temporary_path: Path | None = None
        try:
            self.__path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.__path.parent,
                prefix=f".{self.__path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(
                    [item.to_dict() for item in aeroplanes],
                    temporary,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.__path)
        except (OSError, TypeError, ValueError) as exc:
            raise StorageError(
                f"Не удалось сохранить файл {self.__path}: {exc}"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
