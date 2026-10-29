"""Проверки настройки приложения без зависимости от окружения машины."""

from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, Settings


def test_default_settings():
    settings = Settings.from_env()
    assert settings.timeout == 10
    assert settings.data_file == PROJECT_ROOT / "data" / "aeroplanes.json"
    assert settings.nominatim_url.startswith("https://")


def test_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("AEROPLANES_DATA_FILE", str(tmp_path / "planes.json"))
    monkeypatch.setenv("NOMINATIM_URL", "http://localhost:8000/search")
    monkeypatch.setenv("OPENSKY_URL", "http://localhost:8001/states/all")
    monkeypatch.setenv("NOMINATIM_USER_AGENT", "CustomCoursework/1.0")
    monkeypatch.setenv("HTTP_TIMEOUT", "2.5")
    settings = Settings.from_env()
    assert settings.data_file == tmp_path / "planes.json"
    assert settings.nominatim_url == "http://localhost:8000/search"
    assert settings.opensky_url == "http://localhost:8001/states/all"
    assert settings.user_agent == "CustomCoursework/1.0"
    assert settings.timeout == 2.5


def test_relative_file_is_anchored_to_project(monkeypatch):
    monkeypatch.setenv("AEROPLANES_DATA_FILE", "custom/planes.json")
    assert Settings.from_env().data_file == PROJECT_ROOT / "custom/planes.json"


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "nonsense"])
def test_invalid_timeout(monkeypatch, timeout):
    monkeypatch.setenv("HTTP_TIMEOUT", timeout)
    with pytest.raises(ValueError, match="HTTP_TIMEOUT"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name,value",
    [
        ("NOMINATIM_URL", "ftp://example.org"),
        ("OPENSKY_URL", "not-a-url"),
        ("NOMINATIM_USER_AGENT", " "),
        ("AEROPLANES_DATA_FILE", ""),
    ],
)
def test_invalid_settings(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_custom_path_can_be_constructed(tmp_path):
    assert isinstance(Settings(data_file=tmp_path / "p.json").data_file, Path)
