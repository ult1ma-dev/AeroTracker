"""Storage contracts and filtering.

Check data preservation on filesystem failures.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.exceptions import StorageError
from src.models import Aeroplane
from src.storage import BaseStorage, JSONSaver


def make_aeroplane(identifier="abc123", **changes):
    values = {
        "icao24": identifier,
        "callsign": "TEST123",
        "origin_country": "Germany",
        "velocity": 120.0,
        "altitude": 1000.0,
    }
    values.update(changes)
    return Aeroplane(**values)


@pytest.fixture
def saver(tmp_path):
    return JSONSaver(tmp_path / "nested" / "aeroplanes.json")


def test_abstract_storage_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseStorage()


def test_default_path_belongs_to_project_data_folder():
    assert JSONSaver().path == (
        Path(__file__).resolve().parents[1] / "data" / "aeroplanes.json"
    )


def test_missing_file_is_empty_and_is_not_created_by_read(saver):
    assert saver.get_aeroplanes() == []
    assert saver.delete_aeroplane("abc123") is False
    assert not saver.path.exists()


def test_add_round_trip_creates_utf8_json_and_parent_directory(saver):
    aeroplane = make_aeroplane(origin_country="Россия")
    saver.add_aeroplane(aeroplane)
    assert saver.get_aeroplanes()[0].to_dict() == aeroplane.to_dict()
    content = saver.path.read_text(encoding="utf-8")
    assert "Россия" in content
    assert json.loads(content) == [aeroplane.to_dict()]


def test_add_upserts_existing_identifier_without_losing_other_records(saver):
    saver.replace_all([make_aeroplane(), make_aeroplane("def456")])
    updated = make_aeroplane(altitude=9000)
    saver.add_aeroplane(updated)
    records = saver.get_aeroplanes()
    assert len(records) == 2
    assert records[0].to_dict() == updated.to_dict()
    assert records[1].icao24 == "def456"


def test_replace_all_replaces_snapshot_and_upserts_duplicates(saver):
    saver.add_aeroplane(make_aeroplane())
    saver.replace_all(
        [make_aeroplane("def456"), make_aeroplane("def456", altitude=5000)]
    )
    records = saver.get_aeroplanes()
    assert len(records) == 1
    assert records[0].icao24 == "def456"
    assert records[0].altitude == 5000
    saver.replace_all([])
    assert json.loads(saver.path.read_text(encoding="utf-8")) == []


def test_duplicate_records_on_disk_use_latest_observation(saver):
    saver.path.parent.mkdir(parents=True)
    saver.path.write_text(
        json.dumps(
            [
                make_aeroplane().to_dict(),
                make_aeroplane(altitude=5000).to_dict(),
            ]
        ),
        encoding="utf-8",
    )
    records = saver.get_aeroplanes()
    assert len(records) == 1
    assert records[0].altitude == 5000


def test_delete_normalizes_identifier_and_reports_result(saver):
    saver.replace_all([make_aeroplane(), make_aeroplane("def456")])
    assert saver.delete_aeroplane(" ABC123 ") is True
    assert [item.icao24 for item in saver.get_aeroplanes()] == ["def456"]
    assert saver.delete_aeroplane("abc123") is False


def test_filters_use_and_semantics_inclusive_height_and_whole_country(saver):
    saver.replace_all(
        [
            make_aeroplane(origin_country="United States", altitude=100),
            make_aeroplane("def456", origin_country="Germany", altitude=200),
            make_aeroplane("fed321", origin_country="Germany", altitude=300),
            make_aeroplane("aaa111", origin_country="Germany", altitude=None),
        ]
    )
    assert len(saver.get_aeroplanes(origin_countries=[])) == 4
    countries = saver.get_aeroplanes(
        origin_countries=[" united STATES ", "germany"]
    )
    assert len(countries) == 4
    selected = saver.get_aeroplanes(
        origin_countries=["GERMANY"], min_altitude=200, max_altitude=300
    )
    assert [item.icao24 for item in selected] == ["def456", "fed321"]
    assert saver.get_aeroplanes(origin_countries=["United"]) == []
    assert len(saver.get_aeroplanes(min_altitude=200)) == 2
    assert len(saver.get_aeroplanes(max_altitude=200)) == 2


def test_negative_altitudes_can_be_filtered(saver):
    saver.add_aeroplane(make_aeroplane(altitude=-50))
    assert len(saver.get_aeroplanes(min_altitude=-50, max_altitude=-50)) == 1


@pytest.mark.parametrize(
    ("criteria", "error"),
    [
        ({"origin_countries": "Germany"}, TypeError),
        ({"origin_countries": [1]}, TypeError),
        ({"origin_countries": [" "]}, ValueError),
        ({"min_altitude": True}, TypeError),
        ({"max_altitude": "200"}, TypeError),
        ({"min_altitude": float("nan")}, ValueError),
        ({"max_altitude": float("inf")}, ValueError),
        ({"max_altitude": 10**1000}, ValueError),
        ({"min_altitude": 200, "max_altitude": 100}, ValueError),
    ],
)
def test_invalid_filter_criteria(saver, criteria, error):
    with pytest.raises(error):
        saver.get_aeroplanes(**criteria)


@pytest.mark.parametrize("content", ["not json", "{}", "[1]", "[{}]", ""])
@pytest.mark.parametrize("operation", ["read", "add", "delete", "replace"])
def test_corrupt_file_is_reported_and_preserved(saver, content, operation):
    saver.path.parent.mkdir(parents=True)
    saver.path.write_text(content, encoding="utf-8")
    with pytest.raises(StorageError):
        if operation == "read":
            saver.get_aeroplanes()
        elif operation == "add":
            saver.add_aeroplane(make_aeroplane())
        elif operation == "delete":
            saver.delete_aeroplane("abc123")
        else:
            saver.replace_all([])
    assert saver.path.read_text(encoding="utf-8") == content


def test_invalid_utf8_is_reported_and_preserved(saver):
    saver.path.parent.mkdir(parents=True)
    content = b"\xff\xfe\x00"
    saver.path.write_bytes(content)
    with pytest.raises(StorageError):
        saver.replace_all([])
    assert saver.path.read_bytes() == content


def test_invalid_model_in_file_is_reported(saver):
    saver.path.parent.mkdir(parents=True)
    data = make_aeroplane().to_dict()
    data["velocity"] = -1
    saver.path.write_text(json.dumps([data]), encoding="utf-8")
    with pytest.raises(StorageError):
        saver.get_aeroplanes()


def test_read_permission_error_is_translated(saver):
    with patch.object(
        Path, "read_text", side_effect=PermissionError("denied")
    ):
        with pytest.raises(StorageError, match="прочитать"):
            saver.get_aeroplanes()


def test_directory_creation_error_is_translated(saver):
    with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
        with pytest.raises(StorageError, match="сохранить"):
            saver.add_aeroplane(make_aeroplane())
    assert not saver.path.exists()


def test_failed_atomic_replace_preserves_snapshot_and_cleans_temp_file(saver):
    saver.add_aeroplane(make_aeroplane())
    before = saver.path.read_bytes()
    with patch(
        "src.storage.os.replace", side_effect=PermissionError("denied")
    ):
        with pytest.raises(StorageError):
            saver.replace_all([make_aeroplane("def456")])
    assert saver.path.read_bytes() == before
    assert list(saver.path.parent.iterdir()) == [saver.path]


def test_serialization_failure_preserves_snapshot_and_cleans_temp_file(saver):
    saver.add_aeroplane(make_aeroplane())
    before = saver.path.read_bytes()
    with patch("src.storage.json.dump", side_effect=ValueError("bad data")):
        with pytest.raises(StorageError):
            saver.add_aeroplane(make_aeroplane("def456"))
    assert saver.path.read_bytes() == before
    assert list(saver.path.parent.iterdir()) == [saver.path]


def test_temporary_file_creation_failure_is_translated(saver):
    with patch(
        "src.storage.tempfile.NamedTemporaryFile",
        side_effect=PermissionError("denied"),
    ):
        with pytest.raises(StorageError):
            saver.replace_all([])
    assert not saver.path.exists()


@pytest.mark.parametrize("method", ["add_aeroplane", "replace_all"])
def test_invalid_objects_do_not_change_saved_data(saver, method):
    saver.add_aeroplane(make_aeroplane())
    before = saver.path.read_bytes()
    with pytest.raises(TypeError):
        getattr(saver, method)("invalid" if method == "add_aeroplane" else [1])
    assert saver.path.read_bytes() == before


@pytest.mark.parametrize(
    ("identifier", "error"), [(None, TypeError), (" ", ValueError)]
)
def test_delete_rejects_invalid_identifier(saver, identifier, error):
    with pytest.raises(error):
        saver.delete_aeroplane(identifier)
