"""Проверки бизнес-операций и сохранности текущего снимка."""

from unittest.mock import Mock

import pytest

from src.api import BaseAPI
from src.exceptions import APIError, StorageError
from src.models import Aeroplane
from src.services import (
    AeroplanesService,
    filter_aeroplanes,
    get_aeroplanes_by_altitude,
    get_top_aeroplanes,
    sort_aeroplanes,
)
from src.storage import BaseStorage


@pytest.fixture
def planes():
    return [
        Aeroplane("000001", "ONE", "United States", 100, 1000),
        Aeroplane("000002", "TWO", "Spain", None, None),
        Aeroplane("000003", "THREE", "Spain", 150, -50),
        Aeroplane("000004", "FOUR", "United States", 200, 1000),
    ]


@pytest.fixture
def dependencies(planes):
    api = Mock(spec=BaseAPI)
    storage = Mock(spec=BaseStorage)
    storage.get_aeroplanes.return_value = planes
    return api, storage, AeroplanesService(api, storage)


def test_stable_descending_top_without_mutation(planes):
    original = planes.copy()
    assert [p.icao24 for p in get_top_aeroplanes(planes, 10)] == [
        "000001",
        "000004",
        "000003",
    ]
    assert len(get_top_aeroplanes(planes, 1)) == 1
    assert sort_aeroplanes([]) == []
    assert planes == original


@pytest.mark.parametrize("number", [0, -1])
def test_invalid_top_value(planes, number):
    with pytest.raises(ValueError):
        get_top_aeroplanes(planes, number)


@pytest.mark.parametrize("number", [True, 1.2, "2", None])
def test_invalid_top_type(planes, number):
    with pytest.raises(TypeError):
        get_top_aeroplanes(planes, number)


def test_complete_country_names_and_altitude_boundaries(planes):
    assert filter_aeroplanes(planes, [" UNITED STATES "]) == [
        planes[0],
        planes[3],
    ]
    assert filter_aeroplanes(planes, ["spain", "United States"]) == planes
    assert filter_aeroplanes(planes, ["France"]) == []
    assert get_aeroplanes_by_altitude(planes, -50, -50) == [planes[2]]
    assert get_aeroplanes_by_altitude(planes, 0, 1000) == [
        planes[0],
        planes[3],
    ]


@pytest.mark.parametrize("countries", [[], [""], ["Spain", " "]])
def test_invalid_country_filter(planes, countries):
    with pytest.raises(ValueError):
        filter_aeroplanes(planes, countries)


@pytest.mark.parametrize(
    "countries", ["Spain", b"Spain", [None], [42], None, 42, {"Spain"}]
)
def test_country_filter_rejects_wrong_container_and_items(planes, countries):
    with pytest.raises(TypeError):
        filter_aeroplanes(planes, countries)


def test_country_filter_accepts_a_tuple(planes):
    assert filter_aeroplanes(planes, ("spain",)) == [planes[1], planes[2]]


@pytest.mark.parametrize(
    "minimum,maximum,error",
    [
        (100, 0, ValueError),
        (float("nan"), 100, ValueError),
        (0, float("inf"), ValueError),
        (True, 100, TypeError),
        (0, "100", TypeError),
    ],
)
def test_invalid_altitude_range(planes, minimum, maximum, error):
    with pytest.raises(error):
        get_aeroplanes_by_altitude(planes, minimum, maximum)


def test_fetch_saves_snapshot_before_switching(dependencies, planes):
    api, storage, service = dependencies
    service.load_saved()
    fresh = [planes[2]]
    api.get_aeroplanes.return_value = fresh
    assert service.fetch_country(" Spain ") == fresh
    api.get_aeroplanes.assert_called_once_with("Spain")
    storage.replace_all.assert_called_once_with(fresh)
    fresh.clear()
    snapshot = service.aeroplanes
    snapshot.clear()
    assert service.aeroplanes == [planes[2]]


def test_api_failure_keeps_snapshot_and_does_not_save(dependencies, planes):
    api, storage, service = dependencies
    service.load_saved()
    api.get_aeroplanes.side_effect = APIError("Сеть недоступна")
    with pytest.raises(APIError):
        service.fetch_country("Spain")
    assert service.aeroplanes == planes
    storage.replace_all.assert_not_called()


def test_save_failure_keeps_snapshot(dependencies, planes):
    api, storage, service = dependencies
    service.load_saved()
    api.get_aeroplanes.return_value = []
    storage.replace_all.side_effect = StorageError("Запись невозможна")
    with pytest.raises(StorageError):
        service.fetch_country("Spain")
    assert service.aeroplanes == planes


def test_valid_empty_response_replaces_snapshot(dependencies):
    api, storage, service = dependencies
    service.load_saved()
    api.get_aeroplanes.return_value = []
    assert service.fetch_country("Spain") == []
    storage.replace_all.assert_called_once_with([])


def test_reload_failure_keeps_snapshot(dependencies, planes):
    _, storage, service = dependencies
    service.load_saved()
    storage.get_aeroplanes.side_effect = StorageError("Повреждён JSON")
    with pytest.raises(StorageError):
        service.load_saved()
    assert service.aeroplanes == planes


@pytest.mark.parametrize("country,error", [("  ", ValueError), (0, TypeError)])
def test_invalid_fetch_input(dependencies, country, error):
    api, storage, service = dependencies
    with pytest.raises(error):
        service.fetch_country(country)
    api.get_aeroplanes.assert_not_called()
    storage.replace_all.assert_not_called()


def test_service_filters_and_delete(dependencies, planes):
    _, storage, service = dependencies
    service.load_saved()
    assert service.top(1) == [planes[0]]
    assert service.by_origin(["Spain"]) == [planes[1], planes[2]]
    assert service.by_altitude(-50, 0) == [planes[2]]
    storage.delete_aeroplane.return_value = False
    assert service.delete("000001") is False
    assert service.aeroplanes == planes
    storage.delete_aeroplane.return_value = True
    assert service.delete(" 000001 ") is True
    assert service.aeroplanes == planes[1:]
    storage.delete_aeroplane.assert_called_with("000001")


def test_delete_failure_keeps_snapshot(dependencies, planes):
    _, storage, service = dependencies
    service.load_saved()
    storage.delete_aeroplane.side_effect = StorageError("Ошибка записи")
    with pytest.raises(StorageError):
        service.delete("000001")
    assert service.aeroplanes == planes


@pytest.mark.parametrize(
    "icao,error", [(None, TypeError), ("ghijkl", ValueError)]
)
def test_invalid_delete_input(dependencies, icao, error):
    _, storage, service = dependencies
    with pytest.raises(error):
        service.delete(icao)
    storage.delete_aeroplane.assert_not_called()
