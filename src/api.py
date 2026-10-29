"""Country boundaries and current OpenSky state vectors."""

import math
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

import requests

from src.exceptions import (
    APIError,
    APIResponseError,
    CountryNotFoundError,
    RateLimitError,
)
from src.models import Aeroplane, BoundingBox
from src.snapshots import AircraftObservation, FlightSnapshot


class BaseAPI(ABC):
    """API contract independent of HTTP services."""

    @abstractmethod
    def get_country_coordinates(self, country: str) -> BoundingBox:
        """Return the requested country's bounding rectangle."""

    @abstractmethod
    def get_aeroplanes(self, country: str) -> list[Aeroplane]:
        """Return current aircraft within the country's bounding box."""


class AeroplanesAPI(BaseAPI):
    """Read Nominatim bounds and OpenSky aircraft anonymously."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        nominatim_url: str = "https://nominatim.openstreetmap.org/search",
        opensky_url: str = "https://opensky-network.org/api/states/all",
        user_agent: str = "SkyProAeroplanesCoursework/1.0",
        timeout: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Тайм-аут должен быть положительным числом.")
        if not isinstance(user_agent, str) or not user_agent.strip():
            raise ValueError("Укажите User-Agent с названием приложения.")
        self.__owns_session = session is None
        self.__session = session if session is not None else requests.Session()
        self.__nominatim_url = nominatim_url
        self.__opensky_url = opensky_url
        self.__user_agent = user_agent.strip()
        self.__timeout = timeout
        self.__clock = clock
        self.__sleep = sleep
        self.__last_geocoding_request: float | None = None
        self.__country_cache: dict[str, BoundingBox] = {}

    def get_country_coordinates(self, country: str) -> BoundingBox:
        """Find and cache country bounds for this connector's life."""
        if not isinstance(country, str) or not country.strip():
            raise ValueError("Введите непустое название страны.")
        query = country.strip()
        cache_key = query.casefold()
        if cache_key in self.__country_cache:
            return self.__country_cache[cache_key]
        payload = self.__request_json(
            self.__nominatim_url,
            {
                "country": query,
                "featureType": "country",
                "format": "jsonv2",
                "limit": 1,
            },
            geocoding=True,
        )
        if not isinstance(payload, list):
            raise APIResponseError("Nominatim вернул некорректный список.")
        if not payload:
            raise CountryNotFoundError(f"Страна «{query}» не найдена.")
        result: object = payload[0]
        if not isinstance(result, dict):
            raise APIResponseError("Nominatim вернул некорректный результат.")
        raw_bounds: object = result.get("boundingbox")
        if not isinstance(raw_bounds, list) or len(raw_bounds) != 4:
            raise APIResponseError("В ответе Nominatim нет четырёх границ.")
        try:
            bounds = BoundingBox(
                south=self.__coordinate(raw_bounds[0]),
                north=self.__coordinate(raw_bounds[1]),
                west=self.__coordinate(raw_bounds[2]),
                east=self.__coordinate(raw_bounds[3]),
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise APIResponseError(
                "Nominatim вернул некорректные координаты."
            ) from exc
        self.__country_cache[cache_key] = bounds
        return bounds

    def get_aeroplanes(self, country: str) -> list[Aeroplane]:
        """Parse an OpenSky response; reject malformed batches."""
        _, states, _ = self.__fetch_states(country)
        return [self.__parse_state(state) for state in states]

    def get_snapshot(self, country: str) -> FlightSnapshot:
        """Return a fresh snapshot with optional report positions."""
        bounds, states, api_timestamp = self.__fetch_states(country)
        return FlightSnapshot(
            country=country.strip(),
            bounds=bounds,
            api_timestamp=self.__optional_timestamp(api_timestamp),
            received_at=datetime.now(timezone.utc),
            observations=tuple(
                self.__parse_observation(state) for state in states
            ),
        )

    def __fetch_states(
        self, country: str
    ) -> tuple[BoundingBox, list[object], object]:
        """Fetch the validated envelope, retaining optional metadata."""
        bounds = self.get_country_coordinates(country)
        payload = self.__request_json(
            self.__opensky_url,
            {
                "lamin": bounds.south,
                "lamax": bounds.north,
                "lomin": bounds.west,
                "lomax": bounds.east,
            },
        )
        if not isinstance(payload, dict) or "states" not in payload:
            raise APIResponseError("В ответе OpenSky отсутствует states.")
        states: object = payload["states"]
        if states is None:
            return bounds, [], payload.get("time")
        if not isinstance(states, list):
            raise APIResponseError(
                "OpenSky вернул некорректный список states."
            )
        return bounds, states, payload.get("time")

    def close(self) -> None:
        """Close the HTTP session only if this connector created it."""
        if self.__owns_session:
            self.__session.close()

    def __wait_for_geocoding(self) -> None:
        """Keep every Nominatim attempt at least one second apart."""
        if self.__last_geocoding_request is not None:
            wait = self.__last_geocoding_request + 1.0 - self.__clock()
            if wait > 0:
                self.__sleep(wait)
        self.__last_geocoding_request = self.__clock()

    def __request_json(
        self,
        url: str,
        params: dict[str, str | float | int],
        *,
        geocoding: bool = False,
    ) -> object:
        for attempt in range(2):
            if geocoding:
                self.__wait_for_geocoding()
            try:
                response = self.__session.get(
                    url,
                    params=params,
                    headers={"User-Agent": self.__user_agent},
                    timeout=self.__timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == 0:
                    self.__sleep(1.0)
                    continue
                raise APIError(
                    "Не удалось подключиться к API. Повторите запрос позже."
                ) from exc
            except requests.RequestException as exc:
                raise APIError("Не удалось выполнить запрос к API.") from exc
            if response.status_code == 429:
                retry_after = self.__retry_after(response)
                raise RateLimitError(
                    "Лимит запросов к API исчерпан. Повторите запрос позже.",
                    retry_after=retry_after,
                )
            if response.status_code in (502, 503, 504) and attempt == 0:
                self.__sleep(1.0)
                continue
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise APIError(
                    f"API вернул ошибку HTTP {response.status_code}."
                ) from exc
            try:
                payload: object = response.json()
            except ValueError as exc:
                raise APIResponseError(
                    "API вернул некорректный JSON."
                ) from exc
            return payload
        raise APIError("Не удалось получить ответ API.")

    @staticmethod
    def __retry_after(response: requests.Response) -> float | None:
        for header in (
            "X-Rate-Limit-Retry-After-Seconds",
            "Retry-After",
        ):
            raw = response.headers.get(header)
            if raw is None:
                continue
            try:
                seconds = float(raw)
            except ValueError:
                continue
            if math.isfinite(seconds) and seconds >= 0:
                return seconds
        return None

    @staticmethod
    def __coordinate(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("Координата должна быть числом.")
        coordinate = float(value)
        if not math.isfinite(coordinate):
            raise ValueError("Координата должна быть конечной.")
        return coordinate

    @staticmethod
    def __optional_position(value: object, limit: float) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            coordinate = float(value)
        except OverflowError:
            return None
        if not math.isfinite(coordinate) or not -limit <= coordinate <= limit:
            return None
        return coordinate

    @staticmethod
    def __optional_timestamp(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @classmethod
    def __parse_observation(cls, state: object) -> AircraftObservation:
        plane = cls.__parse_state(state)
        # Core parsing has checked the vector's type and length.
        vector = cast(list[object], state)
        latitude = cls.__optional_position(vector[6], 90.0)
        longitude = cls.__optional_position(vector[5], 180.0)
        if latitude is None or longitude is None:
            latitude = longitude = None
        return AircraftObservation(
            plane=plane,
            latitude=latitude,
            longitude=longitude,
            position_time=cls.__optional_timestamp(vector[3]),
        )

    @staticmethod
    def __optional_number(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Измерение должно быть числом или null.")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Измерение должно быть конечным.")
        return number

    @classmethod
    def __parse_state(cls, state: object) -> Aeroplane:
        if not isinstance(state, list) or len(state) < 17:
            raise APIResponseError("OpenSky вернул неполный вектор самолёта.")
        icao24: object = state[0]
        callsign: object = state[1]
        origin_country: object = state[2]
        on_ground: object = state[8]
        if (
            not isinstance(icao24, str)
            or (callsign is not None and not isinstance(callsign, str))
            or not isinstance(origin_country, str)
            or not isinstance(on_ground, bool)
        ):
            raise APIResponseError("OpenSky вернул неверные типы полей.")
        try:
            return Aeroplane(
                icao24=icao24,
                callsign=callsign.strip() if callsign is not None else None,
                origin_country=origin_country,
                velocity=cls.__optional_number(state[9]),
                altitude=cls.__optional_number(state[7]),
                on_ground=on_ground,
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise APIResponseError(
                "OpenSky вернул некорректные данные самолёта."
            ) from exc
