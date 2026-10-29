"""Additional reports must not change the assessed console workflow."""

import webbrowser
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from src.api import BaseAPI
from src.cli import user_interaction
from src.config import Settings
from src.exceptions import APIError, ReportError
from src.models import Aeroplane, BoundingBox
from src.reporting.service import ReportService, open_report
from src.services import AeroplanesService
from src.snapshots import AircraftObservation, FlightSnapshot
from src.storage import JSONSaver


@pytest.fixture
def snapshot():
    planes = [
        Aeroplane("000001", "HIGH", "Spain", 220, 11000),
        Aeroplane("000002", None, "United States", None, None, True),
        Aeroplane("000003", "LOW", "Spain", 100, -10),
    ]
    return FlightSnapshot(
        country="Spain",
        bounds=BoundingBox(27, 44, -19, 5),
        api_timestamp=1793100000,
        received_at=datetime(2026, 10, 27, 12, tzinfo=timezone.utc),
        observations=(
            AircraftObservation(planes[0], 40, -3, 1793100000),
            AircraftObservation(planes[1], None, None),
            AircraftObservation(planes[2], 0, 0),
        ),
    )


@pytest.fixture
def source(snapshot):
    result = Mock()
    result.get_snapshot.return_value = snapshot
    return result


@pytest.mark.parametrize(
    "country,error", [(None, TypeError), (" ", ValueError)]
)
def test_invalid_country_never_requests(source, tmp_path, country, error):
    with pytest.raises(error):
        ReportService(source, tmp_path).create(country)
    source.get_snapshot.assert_not_called()


def test_create_writes_unique_utf8_reports(source, tmp_path):
    reports = ReportService(source, tmp_path / "отчёты")
    first = reports.create(" Spain ")
    second = reports.create("Spain")
    assert first != second
    assert first.is_file() and second.is_file()
    assert first.suffix == ".html"
    assert "Spain" in first.read_text(encoding="utf-8")
    assert not list(first.parent.glob("*.tmp"))
    assert source.get_snapshot.call_args_list[0].args == ("Spain",)


def test_relative_output_directory_is_resolved(source, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = ReportService(source, "relative").create("Spain")
    assert path.parent == tmp_path / "relative"


def test_api_failure_creates_no_report(source, tmp_path):
    source.get_snapshot.side_effect = APIError("offline")
    folder = tmp_path / "reports"
    with pytest.raises(APIError, match="offline"):
        ReportService(source, folder).create("Spain")
    assert not folder.exists()


def test_failed_atomic_write_preserves_previous_report(
    source, tmp_path, monkeypatch
):
    previous = tmp_path / "previous.html"
    previous.write_text("original", encoding="utf-8")

    def fail_replace(*args):
        raise PermissionError("locked")

    monkeypatch.setattr("src.reporting.service.os.replace", fail_replace)
    with pytest.raises(ReportError, match="locked"):
        ReportService(source, tmp_path).create("Spain")
    assert previous.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.iterdir()) == [previous]


def test_missing_report_assets_are_reported(source, tmp_path, monkeypatch):
    def fail_render(snapshot):
        raise FileNotFoundError("asset missing")

    monkeypatch.setattr("src.reporting.service.render_report", fail_render)
    with pytest.raises(ReportError, match="asset missing"):
        ReportService(source, tmp_path).create("Spain")


def test_numeric_rendering_error_is_readable(source, tmp_path, monkeypatch):
    def fail_render(snapshot):
        raise OverflowError("large number")

    monkeypatch.setattr("src.reporting.service.render_report", fail_render)
    with pytest.raises(ReportError, match="large number"):
        ReportService(source, tmp_path).create("Spain")


@pytest.mark.parametrize("result", [True, False])
def test_browser_receives_a_file_uri(tmp_path, result):
    opener = Mock(return_value=result)
    path = tmp_path / "Мой отчёт.html"
    assert open_report(path, opener) is result
    opener.assert_called_once_with(path.as_uri())


@pytest.mark.parametrize("error", [OSError("missing"), webbrowser.Error("no")])
def test_browser_failure_is_not_a_report_failure(tmp_path, error):
    assert (
        open_report(tmp_path / "report.html", Mock(side_effect=error)) is False
    )


def test_default_browser_can_be_substituted(tmp_path, monkeypatch):
    opener = Mock(return_value=True)
    monkeypatch.setattr("src.reporting.service.webbrowser.open", opener)
    assert open_report(tmp_path / "report.html") is True
    opener.assert_called_once()


def test_additional_menu_preserves_main_json_and_current_selection(
    source, snapshot, tmp_path
):
    api = Mock(spec=BaseAPI)
    storage = JSONSaver(tmp_path / "planes.json")
    storage.replace_all([snapshot.observations[0].plane])
    before = storage.path.read_bytes()
    service = AeroplanesService(api, storage)
    reports = ReportService(source, tmp_path / "reports")
    answers = iter(["8", "", " Spain ", "2", "0"])
    output = []
    browser = Mock(return_value=False)
    user_interaction(
        service,
        report_service=reports,
        read=lambda prompt: next(answers),
        output=output.append,
        open_browser=browser,
    )
    text = "\n".join(output)
    assert "[Дополнительно]" in text
    assert "Значение не должно быть пустым" in text
    assert "Отчёт сохранён:" in text
    assert "Браузер не открылся" in text
    assert "HIGH" in text
    assert storage.path.read_bytes() == before
    assert [plane.icao24 for plane in service.aeroplanes] == ["000001"]
    api.get_aeroplanes.assert_not_called()
    source.get_snapshot.assert_called_once_with("Spain")
    browser.assert_called_once()
    assert len(list((tmp_path / "reports").glob("*.html"))) == 1


def test_report_error_returns_to_original_menu_without_changes(
    source, snapshot, tmp_path
):
    api = Mock(spec=BaseAPI)
    storage = JSONSaver(tmp_path / "planes.json")
    storage.replace_all([snapshot.observations[0].plane])
    original = storage.path.read_bytes()
    service = AeroplanesService(api, storage)
    source.get_snapshot.side_effect = APIError("Нет сети")
    answers = iter(["8", "Spain", "2", "0"])
    output = []
    browser = Mock()
    user_interaction(
        service,
        report_service=ReportService(source, tmp_path / "reports"),
        read=lambda prompt: next(answers),
        output=output.append,
        open_browser=browser,
    )
    assert "Ошибка: Нет сети" in "\n".join(output)
    assert "HIGH" in "\n".join(output)
    assert storage.path.read_bytes() == original
    assert len(service.aeroplanes) == 1
    browser.assert_not_called()


def test_report_dependencies_are_lazy_for_original_menu(tmp_path, monkeypatch):
    api = Mock(spec=BaseAPI)
    service = AeroplanesService(api, JSONSaver(tmp_path / "planes.json"))
    report_factory = Mock()
    api_factory = Mock()
    monkeypatch.setattr("src.cli.ReportService", report_factory)
    monkeypatch.setattr("src.cli.AeroplanesAPI", api_factory)
    user_interaction(service, read=lambda prompt: "0", output=lambda _: None)
    report_factory.assert_not_called()
    api_factory.assert_not_called()


@pytest.mark.parametrize("injected_service", [False, True])
def test_default_report_uses_one_owned_api_and_closes_it(
    tmp_path, monkeypatch, injected_service
):
    api = Mock()
    api_factory = Mock(return_value=api)
    report = Mock()
    report.create.return_value = tmp_path / "report.html"
    report_factory = Mock(return_value=report)
    monkeypatch.setattr("src.cli.AeroplanesAPI", api_factory)
    monkeypatch.setattr("src.cli.ReportService", report_factory)
    monkeypatch.setattr(
        "src.cli.Settings.from_env",
        lambda: Settings(data_file=tmp_path / "planes.json"),
    )
    service = (
        AeroplanesService(Mock(), JSONSaver(tmp_path / "saved.json"))
        if injected_service
        else None
    )
    answers = iter(["8", "Spain", "0"])
    output = []
    browser = Mock(return_value=True)
    user_interaction(
        service,
        read=lambda prompt: next(answers),
        output=output.append,
        open_browser=browser,
    )
    api_factory.assert_called_once()
    report_factory.assert_called_once_with(api)
    report.create.assert_called_once_with("Spain")
    api.close.assert_called_once_with()
    assert "Отчёт сохранён:" in "\n".join(output)
    assert "Браузер не открылся" not in "\n".join(output)
