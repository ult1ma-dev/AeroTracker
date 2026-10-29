"""Операции с текущим набором самолётов, независимые от консоли."""

import math
from collections.abc import Sequence

from src.api import BaseAPI
from src.models import Aeroplane
from src.storage import BaseStorage


def filter_aeroplanes(
    aeroplanes: Sequence[Aeroplane], countries: Sequence[str]
) -> list[Aeroplane]:
    """Фильтрует по полному названию страны регистрации."""
    if isinstance(countries, (str, bytes)) or not isinstance(
        countries, Sequence
    ):
        raise TypeError("Страны следует передать списком или кортежем строк.")
    if any(not isinstance(country, str) for country in countries):
        raise TypeError("Каждое название страны должно быть строкой.")
    names = {country.strip().casefold() for country in countries}
    if not names or "" in names:
        raise ValueError("Укажите хотя бы одну непустую страну регистрации.")
    return [
        plane
        for plane in aeroplanes
        if plane.origin_country.casefold() in names
    ]


def validate_altitude_range(minimum: float, maximum: float) -> None:
    """Проверяет конечность и порядок границ диапазона высот."""
    for value in (minimum, maximum):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Граница высоты должна быть числом.")
        if not math.isfinite(value):
            raise ValueError("Граница высоты должна быть конечным числом.")
    if minimum > maximum:
        raise ValueError("Нижняя граница не может превышать верхнюю.")


def get_aeroplanes_by_altitude(
    aeroplanes: Sequence[Aeroplane], minimum: float, maximum: float
) -> list[Aeroplane]:
    """Выбирает известные высоты в диапазоне включительно."""
    validate_altitude_range(minimum, maximum)
    return [
        plane
        for plane in aeroplanes
        if plane.altitude is not None and minimum <= plane.altitude <= maximum
    ]


def sort_aeroplanes(aeroplanes: Sequence[Aeroplane]) -> list[Aeroplane]:
    """Сортирует известные высоты по убыванию.

    Сохраняет исходный порядок самолётов с равными высотами.
    """
    known = [plane for plane in aeroplanes if plane.altitude is not None]
    return sorted(
        known,
        key=lambda plane: (
            plane.altitude if plane.altitude is not None else -math.inf
        ),
        reverse=True,
    )


def get_top_aeroplanes(
    aeroplanes: Sequence[Aeroplane], top_n: int
) -> list[Aeroplane]:
    """Возвращает до N самолётов с наибольшей известной высотой."""
    if isinstance(top_n, bool) or not isinstance(top_n, int):
        raise TypeError("N должно быть целым числом.")
    if top_n <= 0:
        raise ValueError("N должно быть положительным.")
    return sort_aeroplanes(aeroplanes)[:top_n]


class AeroplanesService:
    """Управляет выборкой через заменяемые API и хранилище."""

    def __init__(self, api: BaseAPI, storage: BaseStorage) -> None:
        self.__api = api
        self.__storage = storage
        self.__aeroplanes: list[Aeroplane] = []

    @property
    def aeroplanes(self) -> list[Aeroplane]:
        """Возвращает копию текущего списка."""
        return self.__aeroplanes.copy()

    def load_saved(self) -> list[Aeroplane]:
        """Заменяет выборку только после успешного чтения файла."""
        loaded = self.__storage.get_aeroplanes()
        self.__aeroplanes = loaded.copy()
        return self.aeroplanes

    def fetch_country(self, country: str) -> list[Aeroplane]:
        """Загружает страну и сохраняет полный снимок.

        Смена текущей выборки происходит после сохранения.
        """
        if not isinstance(country, str):
            raise TypeError("Название страны должно быть строкой.")
        if not country.strip():
            raise ValueError("Название страны не должно быть пустым.")
        loaded = self.__api.get_aeroplanes(country.strip())
        self.__storage.replace_all(loaded)
        self.__aeroplanes = loaded.copy()
        return self.aeroplanes

    def top(self, top_n: int) -> list[Aeroplane]:
        """Возвращает топ по высоте без изменения снимка."""
        return get_top_aeroplanes(self.__aeroplanes, top_n)

    def by_origin(self, countries: Sequence[str]) -> list[Aeroplane]:
        """Выбирает страны регистрации из текущего снимка."""
        return filter_aeroplanes(self.__aeroplanes, countries)

    def by_altitude(self, minimum: float, maximum: float) -> list[Aeroplane]:
        """Выбирает диапазон высот из текущего снимка."""
        return get_aeroplanes_by_altitude(self.__aeroplanes, minimum, maximum)

    def delete(self, icao24: str) -> bool:
        """Удаляет запись из файла и текущей выборки.

        Меняет текущую выборку только после успешной записи файла.
        """
        if not isinstance(icao24, str):
            raise TypeError("ICAO24 должен быть строкой.")
        normalized = icao24.strip().lower()
        if len(normalized) != 6 or any(
            symbol not in "0123456789abcdef" for symbol in normalized
        ):
            raise ValueError("ICAO24 должен содержать шесть hex-символов.")
        deleted = self.__storage.delete_aeroplane(normalized)
        if deleted:
            self.__aeroplanes = [
                plane
                for plane in self.__aeroplanes
                if plane.icao24 != normalized
            ]
        return deleted
