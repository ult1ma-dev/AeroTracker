"""HTTP connector tests are isolated from networks and real waits."""

import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from src.api import AeroplanesAPI, BaseAPI
from src.exceptions import (
    APIError,
    APIResponseError,
    CountryNotFoundError,
    RateLimitError,
)
from src.models import BoundingBox


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def response(payload: object, status: int = 200) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode("utf-8")
    result.url = "https://example.test/api"
    return result


def country_response() -> requests.Response:
    return response([{"boundingbox": ["35.0", "44.0", "-10.0", "5.0"]}])


def state_vector() -> list[object]:
    return [
        "ABC123",
        " IBE123 ",
        "Spain",
        1,
        2,
        -3.0,
        40.0,
        10203.18,
        False,
        268.79,
        1.0,
        0.0,
        None,
        10400.0,
        None,
        False,
        0,
    ]


@pytest.fixture
def session() -> Mock:
    return Mock(spec=requests.Session)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def api(session: Mock, fake_clock: FakeClock) -> AeroplanesAPI:
    return AeroplanesAPI(
        session,
        nominatim_url="https://example.test/countries",
        opensky_url="https://example.test/states",
        user_agent="CourseworkTests/1.0",
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


def test_api_interface_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseAPI()


def test_country_request_and_coordinate_order(
    api: AeroplanesAPI, session: Mock
) -> None:
    session.get.return_value = country_response()
    assert api.get_country_coordinates(" Spain ") == BoundingBox(
        35.0, 44.0, -10.0, 5.0
    )
    session.get.assert_called_once_with(
        "https://example.test/countries",
        params={
            "country": "Spain",
            "featureType": "country",
            "format": "jsonv2",
            "limit": 1,
        },
        headers={"User-Agent": "CourseworkTests/1.0"},
        timeout=10.0,
    )


def test_country_cache_avoids_http_and_waits(
    api: AeroplanesAPI, session: Mock, fake_clock: FakeClock
) -> None:
    session.get.return_value = country_response()
    bounds = api.get_country_coordinates("Spain")
    assert api.get_country_coordinates(" spain ") == bounds
    assert session.get.call_count == 1
    assert fake_clock.waits == []


def test_different_country_requests_are_rate_limited(
    api: AeroplanesAPI, session: Mock, fake_clock: FakeClock
) -> None:
    session.get.return_value = country_response()
    api.get_country_coordinates("Spain")
    api.get_country_coordinates("France")
    assert fake_clock.waits == [1.0]


def test_elapsed_time_avoids_unnecessary_wait(
    api: AeroplanesAPI, session: Mock, fake_clock: FakeClock
) -> None:
    session.get.return_value = country_response()
    api.get_country_coordinates("Spain")
    fake_clock.now += 2.0
    api.get_country_coordinates("France")
    assert fake_clock.waits == []


@pytest.mark.parametrize("country", ["", "  ", None, 42])
def test_invalid_country_does_not_request(
    api: AeroplanesAPI, session: Mock, country: object
) -> None:
    with pytest.raises(ValueError):
        api.get_country_coordinates(country)
    session.get.assert_not_called()


def test_country_not_found(api: AeroplanesAPI, session: Mock) -> None:
    session.get.return_value = response([])
    with pytest.raises(CountryNotFoundError):
        api.get_country_coordinates("Imaginary country")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [None],
        [{}],
        [{"boundingbox": [1, 2]}],
        [{"boundingbox": [False, 2, 3, 4]}],
        [{"boundingbox": ["invalid", 2, 3, 4]}],
        [{"boundingbox": [1, "NaN", 3, 4]}],
        [{"boundingbox": [1, 91, 3, 4]}],
        [{"boundingbox": [2, 1, 3, 4]}],
        [{"boundingbox": [1, 2, 4, 3]}],
    ],
)
def test_malformed_country_response(
    api: AeroplanesAPI, session: Mock, payload: object
) -> None:
    session.get.return_value = response(payload)
    with pytest.raises(APIResponseError):
        api.get_country_coordinates("Spain")


def test_opensky_request_and_vector_mapping(
    api: AeroplanesAPI, session: Mock
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"time": 123, "states": [state_vector()]}),
    ]
    aircraft = api.get_aeroplanes("Spain")
    assert len(aircraft) == 1
    assert aircraft[0].icao24 == "abc123"
    assert aircraft[0].callsign == "IBE123"
    assert aircraft[0].origin_country == "Spain"
    assert aircraft[0].velocity == 268.79
    assert aircraft[0].altitude == 10203.18
    assert aircraft[0].on_ground is False
    session.get.assert_called_with(
        "https://example.test/states",
        params={"lamin": 35.0, "lamax": 44.0, "lomin": -10.0, "lomax": 5.0},
        headers={"User-Agent": "CourseworkTests/1.0"},
        timeout=10.0,
    )


def test_unknown_measurements_are_preserved(
    api: AeroplanesAPI, session: Mock
) -> None:
    state = state_vector()
    state[1], state[7], state[9] = None, None, None
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    aircraft = api.get_aeroplanes("Spain")[0]
    assert aircraft.callsign is None
    assert aircraft.altitude is None
    assert aircraft.velocity is None


def test_negative_altitude_is_valid(api: AeroplanesAPI, session: Mock) -> None:
    state = state_vector()
    state[7] = -30.0
    state[8] = True
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    aircraft = api.get_aeroplanes("Spain")[0]
    assert aircraft.altitude == -30.0
    assert aircraft.on_ground is True


@pytest.mark.parametrize("states", [None, []])
def test_no_aircraft_is_an_empty_list(
    api: AeroplanesAPI, session: Mock, states: object
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"states": states}),
    ]
    assert api.get_aeroplanes("Spain") == []


def test_each_query_returns_a_fresh_list(
    api: AeroplanesAPI, session: Mock
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"states": [state_vector()]}),
        response({"states": [state_vector()]}),
    ]
    first = api.get_aeroplanes("Spain")
    first.clear()
    assert len(api.get_aeroplanes("Spain")) == 1
    assert session.get.call_count == 3


@pytest.mark.parametrize("payload", [None, [], {}, {"states": {}}])
def test_invalid_opensky_schema(
    api: AeroplanesAPI, session: Mock, payload: object
) -> None:
    session.get.side_effect = [country_response(), response(payload)]
    with pytest.raises(APIResponseError):
        api.get_aeroplanes("Spain")


@pytest.mark.parametrize(
    ("index", "value"),
    [
        (0, None),
        (0, "bad-id"),
        (1, 42),
        (2, None),
        (2, ""),
        (7, "100"),
        (7, float("nan")),
        (8, 0),
        (9, True),
        (9, -1),
        (9, float("inf")),
    ],
)
def test_malformed_vector_rejects_entire_batch(
    api: AeroplanesAPI, session: Mock, index: int, value: object
) -> None:
    malformed = state_vector()
    malformed[index] = value
    session.get.side_effect = [
        country_response(),
        response({"states": [state_vector(), malformed]}),
    ]
    with pytest.raises(APIResponseError):
        api.get_aeroplanes("Spain")


@pytest.mark.parametrize("state", [None, {}, [], [1] * 16])
def test_missing_vector_fields(
    api: AeroplanesAPI, session: Mock, state: object
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    with pytest.raises(APIResponseError):
        api.get_aeroplanes("Spain")


@pytest.mark.parametrize(
    "failure",
    [requests.ConnectionError("offline"), requests.Timeout("slow")],
)
def test_transient_connection_failure_gets_one_retry(
    api: AeroplanesAPI,
    session: Mock,
    fake_clock: FakeClock,
    failure: Exception,
) -> None:
    session.get.side_effect = [failure, country_response()]
    assert api.get_country_coordinates("Spain").south == 35.0
    assert session.get.call_count == 2
    assert fake_clock.waits == [1.0]


@pytest.mark.parametrize("status", [502, 503, 504])
def test_transient_status_gets_one_retry(
    api: AeroplanesAPI, session: Mock, fake_clock: FakeClock, status: int
) -> None:
    session.get.side_effect = [response({}, status), country_response()]
    assert api.get_country_coordinates("Spain").south == 35.0
    assert session.get.call_count == 2
    assert fake_clock.waits == [1.0]


def test_exhausted_connection_retry(api: AeroplanesAPI, session: Mock) -> None:
    session.get.side_effect = requests.Timeout("slow")
    with pytest.raises(APIError):
        api.get_country_coordinates("Spain")
    assert session.get.call_count == 2


def test_exhausted_status_retry(api: AeroplanesAPI, session: Mock) -> None:
    session.get.return_value = response({}, 503)
    with pytest.raises(APIError, match="503"):
        api.get_country_coordinates("Spain")
    assert session.get.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
def test_other_http_errors_are_not_retried(
    api: AeroplanesAPI, session: Mock, status: int
) -> None:
    session.get.return_value = response({}, status)
    with pytest.raises(APIError, match=str(status)):
        api.get_country_coordinates("Spain")
    assert session.get.call_count == 1


def test_generic_request_error_is_wrapped(
    api: AeroplanesAPI, session: Mock
) -> None:
    session.get.side_effect = requests.TooManyRedirects("redirect loop")
    with pytest.raises(APIError):
        api.get_country_coordinates("Spain")
    assert session.get.call_count == 1


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "60"}, 60.0),
        ({"X-Rate-Limit-Retry-After-Seconds": "120"}, 120.0),
        ({"Retry-After": "invalid"}, None),
        ({"Retry-After": "-1"}, None),
        ({"Retry-After": "inf"}, None),
        ({}, None),
        (
            {
                "X-Rate-Limit-Retry-After-Seconds": "invalid",
                "Retry-After": "30",
            },
            30.0,
        ),
    ],
)
def test_rate_limit_does_not_retry(
    api: AeroplanesAPI,
    session: Mock,
    headers: dict[str, str],
    expected: float | None,
) -> None:
    limited = response({}, 429)
    limited.headers.update(headers)
    session.get.return_value = limited
    with pytest.raises(RateLimitError) as error:
        api.get_country_coordinates("Spain")
    assert error.value.retry_after == expected
    assert session.get.call_count == 1


def test_invalid_json_is_wrapped(api: AeroplanesAPI, session: Mock) -> None:
    invalid = response({})
    invalid._content = b"<html>upstream error</html>"
    session.get.return_value = invalid
    with pytest.raises(APIResponseError):
        api.get_country_coordinates("Spain")
    assert session.get.call_count == 1


def test_injected_session_is_not_closed(
    api: AeroplanesAPI, session: Mock
) -> None:
    api.close()
    session.close.assert_not_called()


def test_owned_session_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    owned = Mock(spec=requests.Session)
    factory = Mock(return_value=owned)
    monkeypatch.setattr(requests, "Session", factory)
    api = AeroplanesAPI()
    api.close()
    owned.close.assert_called_once_with()
    owned.get.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf")])
def test_invalid_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(ValueError):
        AeroplanesAPI(timeout=timeout)


def test_empty_user_agent_is_rejected() -> None:
    with pytest.raises(ValueError):
        AeroplanesAPI(user_agent=" ")


def test_snapshot_uses_one_response_for_aircraft_and_metadata(
    api: AeroplanesAPI, session: Mock
) -> None:
    before = datetime.now(timezone.utc)
    session.get.side_effect = [
        country_response(),
        response({"time": 123, "states": [state_vector()]}),
    ]
    snapshot = api.get_snapshot(" Spain ")
    after = datetime.now(timezone.utc)
    assert snapshot.country == "Spain"
    assert snapshot.bounds == BoundingBox(35, 44, -10, 5)
    assert snapshot.api_timestamp == 123
    assert before <= snapshot.received_at <= after
    assert snapshot.received_at.tzinfo is timezone.utc
    assert len(snapshot.observations) == 1
    observation = snapshot.observations[0]
    assert observation.plane.icao24 == "abc123"
    assert observation.plane.callsign == "IBE123"
    assert observation.plane.altitude == 10203.18
    assert observation.latitude == 40.0
    assert observation.longitude == -3.0
    assert observation.position_time == 1
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["params"] == {
        "lamin": 35.0,
        "lamax": 44.0,
        "lomin": -10.0,
        "lomax": 5.0,
    }


@pytest.mark.parametrize("states", [None, []])
def test_snapshot_with_no_aircraft_preserves_metadata(
    api: AeroplanesAPI, session: Mock, states: object
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"time": 0, "states": states}),
    ]
    snapshot = api.get_snapshot("Spain")
    assert snapshot.observations == ()
    assert snapshot.api_timestamp == 0
    assert snapshot.bounds == BoundingBox(35, 44, -10, 5)


@pytest.mark.parametrize(
    ("latitude", "longitude"), [(0, 0), (-90, -180), (90, 180)]
)
def test_snapshot_accepts_zero_and_boundary_coordinates(
    api: AeroplanesAPI, session: Mock, latitude: float, longitude: float
) -> None:
    state = state_vector()
    state[5], state[6] = longitude, latitude
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    observation = api.get_snapshot("Spain").observations[0]
    assert observation.latitude == latitude
    assert observation.longitude == longitude


@pytest.mark.parametrize("index", [5, 6])
@pytest.mark.parametrize(
    "invalid",
    [None, True, False, "0", [], {}, float("nan"), float("inf"), 10**400],
)
def test_snapshot_keeps_aircraft_with_invalid_optional_position(
    api: AeroplanesAPI, session: Mock, index: int, invalid: object
) -> None:
    state = state_vector()
    state[index] = invalid
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    observation = api.get_snapshot("Spain").observations[0]
    assert observation.latitude is None
    assert observation.longitude is None
    assert observation.plane.icao24 == "abc123"


@pytest.mark.parametrize(
    ("index", "value"), [(5, -181), (5, 181), (6, -91), (6, 91)]
)
def test_snapshot_rejects_out_of_range_optional_positions(
    api: AeroplanesAPI, session: Mock, index: int, value: float
) -> None:
    state = state_vector()
    state[index] = value
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    observation = api.get_snapshot("Spain").observations[0]
    assert observation.latitude is None
    assert observation.longitude is None


@pytest.mark.parametrize("value", [None, True, False, -1, 1.5, "123", [], {}])
def test_snapshot_ignores_invalid_optional_timestamps(
    api: AeroplanesAPI, session: Mock, value: object
) -> None:
    state = state_vector()
    state[3] = value
    session.get.side_effect = [
        country_response(),
        response({"time": value, "states": [state]}),
    ]
    snapshot = api.get_snapshot("Spain")
    assert snapshot.api_timestamp is None
    assert snapshot.observations[0].position_time is None


def test_snapshot_accepts_zero_position_timestamp(
    api: AeroplanesAPI, session: Mock
) -> None:
    state = state_vector()
    state[3] = 0
    session.get.side_effect = [
        country_response(),
        response({"states": [state]}),
    ]
    assert api.get_snapshot("Spain").observations[0].position_time == 0


def test_snapshot_reuses_country_cache_and_retries_opensky(
    api: AeroplanesAPI, session: Mock, fake_clock: FakeClock
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"states": [state_vector()]}),
        requests.Timeout("slow"),
        response({"states": [state_vector()]}),
    ]
    original = api.get_aeroplanes("Spain")
    snapshot = api.get_snapshot(" spain ")
    assert snapshot.observations[0].plane.to_dict() == original[0].to_dict()
    assert session.get.call_count == 4
    assert fake_clock.waits == [1.0]


def test_snapshot_still_rejects_malformed_core_aircraft(
    api: AeroplanesAPI, session: Mock
) -> None:
    malformed = state_vector()
    malformed[0] = "invalid"
    session.get.side_effect = [
        country_response(),
        response({"states": [state_vector(), malformed]}),
    ]
    with pytest.raises(APIResponseError):
        api.get_snapshot("Spain")


def test_core_aircraft_path_ignores_optional_map_fields(
    api: AeroplanesAPI, session: Mock
) -> None:
    state = state_vector()
    state[3], state[5], state[6] = {}, True, ["invalid"]
    session.get.side_effect = [
        country_response(),
        response({"time": [], "states": [state]}),
    ]
    aircraft = api.get_aeroplanes("Spain")
    assert len(aircraft) == 1
    assert aircraft[0].to_dict() == {
        "icao24": "abc123",
        "callsign": "IBE123",
        "origin_country": "Spain",
        "velocity": 268.79,
        "altitude": 10203.18,
        "on_ground": False,
    }


def test_snapshot_and_observation_are_immutable(
    api: AeroplanesAPI, session: Mock
) -> None:
    session.get.side_effect = [
        country_response(),
        response({"states": [state_vector()]}),
    ]
    snapshot = api.get_snapshot("Spain")
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot, "country", "France")
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot.observations[0], "latitude", 0)
