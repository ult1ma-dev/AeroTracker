"""Сценарии меню с настоящим JSON и подменённым API."""

from unittest.mock import Mock

import pytest

from src.api import BaseAPI
from src.cli import print_aeroplanes, user_interaction
from src.config import Settings
from src.exceptions import APIError, RateLimitError
from src.models import Aeroplane
from src.services import AeroplanesService
from src.storage import JSONSaver


@pytest.fixture
def app(tmp_path):
    api = Mock(spec=BaseAPI)
    planes = [
        Aeroplane("000001", "HIGH", "United States", 200, 1000),
        Aeroplane("000002", None, "Spain", None, None, True),
    ]
    storage = JSONSaver(tmp_path / "planes.json")
    storage.replace_all(planes)
    api.get_aeroplanes.return_value = planes
    return api, storage, AeroplanesService(api, storage)


def run_dialog(service, answers):
    answers = iter(answers)
    output = []
    user_interaction(
        service, read=lambda prompt: next(answers), output=output.append
    )
    return "\n".join(output)


def test_complete_menu_workflow(app):
    api, storage, service = app
    output = run_dialog(
        service,
        [
            "?",
            "1",
            "",
            " Spain ",
            "2",
            "3",
            "bad",
            "0",
            "5",
            "4",
            "Spain,",
            " united states ",
            "5",
            "nan",
            "0",
            "100",
            "0",
            "0",
            "1000",
            "6",
            "7",
            "invalid",
            "7",
            "000001",
            "7",
            "000001",
            "0",
        ],
    )
    api.get_aeroplanes.assert_called_once_with("Spain")
    assert "Неизвестное действие" in output
    assert "Значение не должно быть пустым" in output
    assert "Получено и сохранено самолётов: 2" in output
    assert "Введите целое положительное число" in output
    assert "Без известной высоты исключено: 1" in output
    assert "Введите полные названия стран" in output
    assert "Некорректный диапазон" in output
    assert "Ошибка ввода" in output
    assert "Запись удалена" in output
    assert "Самолёт не найден" in output
    assert "До свидания" in output
    assert [plane.icao24 for plane in storage.get_aeroplanes()] == ["000002"]


def test_api_error_and_rate_limit_return_to_menu(app):
    api, _, service = app
    api.get_aeroplanes.side_effect = [
        APIError("Сеть недоступна"),
        RateLimitError("Лимит запросов", 30),
        RateLimitError("Лимит запросов без заголовка"),
    ]
    output = run_dialog(service, ["1", "Spain"] * 3 + ["2", "0"])
    assert "Ошибка: Сеть недоступна" in output
    assert "Повторите запрос через 30 с" in output
    assert "HIGH" in output


def test_corrupted_json_can_be_reported_without_crash(app):
    api, storage, service = app
    storage.path.write_text("broken", encoding="utf-8")
    output = run_dialog(service, ["6", "1", "Spain", "0"])
    assert output.count("Ошибка:") == 3
    assert storage.path.read_text(encoding="utf-8") == "broken"
    api.get_aeroplanes.assert_called_once()


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_terminal_interruption_exits_cleanly(app, error):
    _, _, service = app

    def interrupt(prompt):
        raise error

    output = []
    user_interaction(service, read=interrupt, output=output.append)
    assert "Работа завершена" in output[-1]


def test_output_has_units_missing_data_and_ground_state(app):
    _, storage, _ = app
    output = []
    print_aeroplanes(storage.get_aeroplanes(), output.append)
    assert "1000 м" in output[0] and "200 м/с" in output[0]
    assert "в воздухе" in output[0]
    assert "Без позывного" in output[1]
    assert "нет данных" in output[1] and "на земле" in output[1]
    print_aeroplanes([], output.append)
    assert output[-1] == "Подходящих самолётов нет."


def test_default_dependencies_are_created_and_closed(monkeypatch, tmp_path):
    api = Mock()
    factory = Mock(return_value=api)
    monkeypatch.setattr("src.cli.AeroplanesAPI", factory)
    monkeypatch.setattr(
        "src.cli.Settings.from_env",
        lambda: Settings(data_file=tmp_path / "new.json"),
    )
    user_interaction(read=lambda prompt: "0", output=lambda value: None)
    factory.assert_called_once()
    api.close.assert_called_once()


def test_configuration_error_is_readable(monkeypatch):
    monkeypatch.setenv("HTTP_TIMEOUT", "invalid")
    output = []
    user_interaction(output=output.append)
    assert "Ошибка настройки" in output[0]
