"""Изоляция окружения и запрет настоящих HTTP-запросов в тестах."""

import pytest
import requests


@pytest.fixture(autouse=True)
def isolate_environment_and_network(monkeypatch):
    for name in (
        "AEROPLANES_DATA_FILE",
        "NOMINATIM_URL",
        "OPENSKY_URL",
        "NOMINATIM_USER_AGENT",
        "HTTP_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)

    def block_request(*args, **kwargs):
        raise AssertionError("Реальные HTTP-запросы запрещены в тестах")

    monkeypatch.setattr(requests.sessions.Session, "request", block_request)
