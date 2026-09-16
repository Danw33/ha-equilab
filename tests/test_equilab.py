"""Offline regression tests using synthetic documents and real HA classes."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyequilab import (
    AccessError,
    AuthError,
    EquilabClient,
    EquilabError,
    Horse,
    MissingError,
    RateLimitError,
    Training,
    active_ids,
    horse_from_data,
    number,
    rider_from_data,
)
from pyequilab.api import AUTH_URL, ROOT, TOKEN_URL, decode

from custom_components.equilab.calendar import EquilabCalendar
from custom_components.equilab.coordinator import EquilabCoordinator
from custom_components.equilab.diagnostics import async_get_config_entry_diagnostics
from custom_components.equilab.sensor import (
    DESCRIPTIONS,
    PROFILE_FIELDS,
    EquilabSensor,
    ProfileSensor,
)


@asynccontextmanager
async def mocked_http():
    async with aiohttp.ClientSession() as session:
        with aioresponses() as mock:
            yield session, mock


def training(identifier="training", **changes):
    values = dict(
        id=identifier,
        start=datetime(2026, 9, 9, 12, tzinfo=UTC),
        kind="Dressage",
        duration=600.0,
        distance=1000.0,
        energy=2.0,
        gaits={"walk": 300.0},
    )
    values.update(changes)
    return Training(**values)


def horse(*items, skipped=0):
    return Horse(
        "horse", "Synthetic horse", "Breed", None, "pony", "Level", True, tuple(items), skipped
    )


def auth_payload(refresh=False, **changes):
    result = (
        {
            "user_id": "user",
            "id_token": "token-new",
            "refresh_token": "renew-new",
            "expires_in": "3600",
        }
        if refresh
        else {"localId": "user", "idToken": "token", "refreshToken": "renew", "expiresIn": "3600"}
    )
    return {**result, **changes}


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, None),
        (-1, None),
        (float("nan"), None),
        (float("inf"), None),
        (0, 0.0),
        (2.5, 2.5),
        ("3", None),
        (None, None),
    ],
)
def test_number(value, expected):
    assert number(value) == expected


def test_firestore_decode():
    assert decode({"integerValue": "12"}) == 12
    assert decode({"nullValue": None}) is None
    assert decode({"timestampValue": "2026-09-09T12:00:00Z"}).tzinfo is not None
    assert decode(
        {"mapValue": {"fields": {"array": {"arrayValue": {"values": [{"doubleValue": 2.0}]}}}}}
    ) == {"array": [2.0]}
    assert decode({"referenceValue": "secret"}) is None


def test_only_explicit_index_membership():
    assert active_ids({"a": True, "b": False, "c": None, "d": 1}) == {"a"}
    assert active_ids(None) == set()


def test_parse_minimal_and_optional():
    item = Training.parse(
        "id",
        {
            "date": datetime(2026, 9, 9, tzinfo=UTC),
            "total": {"time": 30, "distance": 10},
            "walk": {"time": 20},
            "trainingTypes": {"-KgsjZPxgZP7Nsj_cXvW": True, "secret": False},
        },
    )
    assert item.kind == "Dressage"
    assert item.duration == 30
    assert item.energy is None
    assert item.gaits["walk"] == 20
    assert item.end is not None
    assert Training.parse("id", {}).end is None
    assert Training.parse("id", {"date": datetime(2026, 1, 1)}).start is None


def test_profiles_do_not_retain_notes_or_tokens():
    item = horse_from_data(
        "id", {"name": "Horse", "note": "PRIVATE", "fcmTokens": {"SECRET": True}}, True, (), 0
    )
    assert "PRIVATE" not in repr(item)
    assert "SECRET" not in repr(item)


def test_latest_is_timestamp_order_not_id_order():
    later = training("a")
    older = training("z", start=datetime(2026, 9, 8, tzinfo=UTC))
    assert horse(older, later).latest is later


@pytest.mark.parametrize("period", ["week", "month"])
def test_aggregates_missing_is_not_zero(period):
    now = datetime(2026, 9, 10, tzinfo=UTC)
    assert horse().aggregate(period, "energy", now) == 0
    assert horse(training()).aggregate(period, "energy", now) == 2
    assert horse(training(energy=None)).aggregate(period, "energy", now) is None
    assert horse(training(), skipped=1).aggregate(period, "count", now) is None
    assert horse(training(start=None)).aggregate(period, "count", now) is None


def test_local_week_boundary_and_future_exclusion():
    zone = ZoneInfo("Europe/London")
    now = datetime(2026, 9, 7, 1, tzinfo=zone)
    monday_local = training(start=datetime(2026, 9, 6, 23, 30, tzinfo=UTC))
    sunday_local = training(start=datetime(2026, 9, 6, 22, 30, tzinfo=UTC))
    future = training(start=datetime(2026, 9, 8, tzinfo=UTC))
    assert horse(monday_local, sunday_local, future).aggregate("week", "count", now) == 1


async def test_login_read_and_rotation():
    rotations = []
    async with mocked_http() as (session, mock):
        mock.post(AUTH_URL, payload=auth_payload())
        mock.get(f"{ROOT}/users/user", status=401)
        mock.post(TOKEN_URL, payload=auth_payload(True))
        mock.get(f"{ROOT}/users/user", payload={"fields": {"name": {"stringValue": "Synthetic"}}})
        client = EquilabClient(session, on_token=rotations.append)
        await client.async_login("synthetic@example.invalid", "private")
        assert await client.async_get_user() == {"name": "Synthetic"}
        assert rotations == ["renew", "renew-new"]
        assert not hasattr(client, "password")


async def test_concurrent_refresh_once():
    async with mocked_http() as (session, mock):
        mock.post(TOKEN_URL, payload=auth_payload(True))
        for identifier in ("a", "b", "c"):
            mock.get(f"{ROOT}/horses/{identifier}", payload={"fields": {}})
        client = EquilabClient(session, uid="user", refresh_token="renew")
        await asyncio.gather(*(client.async_get_horse(key) for key in ("a", "b", "c")))
        assert (
            sum(len(calls) for (method, url), calls in mock.requests.items() if method == "POST")
            == 1
        )


@pytest.mark.parametrize(
    "status, error",
    [
        (403, AccessError),
        (404, MissingError),
        (429, RateLimitError),
        (500, EquilabError),
        (302, EquilabError),
    ],
)
async def test_safe_http_errors(status, error):
    async with mocked_http() as (session, mock):
        mock.get(f"{ROOT}/horses/id", status=status, body="PRIVATE_DATA")
        client = EquilabClient(session)
        with pytest.raises(error) as caught:
            await client._request("GET", f"{ROOT}/horses/id")
        assert "PRIVATE_DATA" not in str(caught.value)


async def test_invalid_credentials():
    async with mocked_http() as (session, mock):
        mock.post(AUTH_URL, status=400, payload={"error": {"message": "INVALID_LOGIN_CREDENTIALS"}})
        with pytest.raises(AuthError):
            await EquilabClient(session).async_login("x", "x")


@pytest.mark.parametrize(
    "message, error",
    [
        ("TOO_MANY_ATTEMPTS_TRY_LATER", RateLimitError),
        ("UNRECOGNIZED_AUTH_FAILURE", EquilabError),
    ],
)
async def test_safe_authentication_service_errors(message, error):
    async with mocked_http() as (session, mock):
        mock.post(AUTH_URL, status=400, payload={"error": {"message": message}})
        with pytest.raises(error):
            await EquilabClient(session).async_login("x", "x")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"expiresIn": "invalid"}, "Invalid authentication response"),
        ({"idToken": ""}, "Incomplete authentication response"),
        ({"expiresIn": "nan"}, "Invalid token lifetime"),
        ({"expiresIn": "0"}, "Invalid token lifetime"),
    ],
)
def test_invalid_authentication_payloads(changes, message):
    client = EquilabClient(None)
    with pytest.raises(EquilabError, match=message):
        client._tokens(auth_payload(**changes), refresh=False)


async def test_request_rejects_invalid_json_shape_and_network_failure():
    url = f"{ROOT}/horses/id"
    async with mocked_http() as (session, mock):
        mock.get(url, payload=[])
        with pytest.raises(EquilabError, match="Invalid cloud response"):
            await EquilabClient(session)._request("GET", url)
        mock.get(url, exception=aiohttp.ClientConnectionError("PRIVATE_DATA"))
        with pytest.raises(EquilabError, match="Could not communicate") as caught:
            await EquilabClient(session)._request("GET", url)
        assert "PRIVATE_DATA" not in str(caught.value)


async def test_missing_refresh_token_requires_sign_in():
    async with aiohttp.ClientSession() as session:
        with pytest.raises(AuthError, match="Sign in required"):
            await EquilabClient(session)._async_ensure_token()


@pytest.mark.parametrize("reader", ["document", "notification"])
async def test_second_rejected_token_is_not_retried(reader):
    async with mocked_http() as (session, mock):
        client = EquilabClient(session)
        client._tokens(auth_payload(), refresh=False)
        url = (
            f"{ROOT}/horses/id"
            if reader == "document"
            else f"{ROOT}/users/user/notifications?orderBy=date+desc&pageSize=1"
        )
        mock.get(url, status=401)
        mock.post(TOKEN_URL, payload=auth_payload(True))
        mock.get(url, status=401)
        with pytest.raises(AuthError):
            if reader == "document":
                await client.async_get_horse("id")
            else:
                await client.async_get_latest_notification()


@pytest.mark.parametrize("reader", ["document", "notification"])
async def test_malformed_firestore_collection_is_safe(reader):
    async with mocked_http() as (session, mock):
        client = EquilabClient(session)
        client._tokens(auth_payload(), refresh=False)
        if reader == "document":
            mock.get(f"{ROOT}/horses/id", payload={"fields": []})
            call = client.async_get_horse("id")
            message = "Invalid document data"
        else:
            mock.get(
                f"{ROOT}/users/user/notifications?orderBy=date+desc&pageSize=1",
                payload={"documents": [None]},
            )
            call = client.async_get_latest_notification()
            message = "Invalid notification data"
        with pytest.raises(EquilabError, match=message):
            await call


async def test_token_identity_guard():
    async with aiohttp.ClientSession() as session:
        client = EquilabClient(session, uid="expected")
        with pytest.raises(AuthError):
            client._tokens(auth_payload(True), refresh=True)


def test_training_end_overflow_and_invalid_birthday():
    overflowing = training(start=datetime.max.replace(tzinfo=UTC), duration=600)
    assert overflowing.end is None
    item = horse_from_data("id", {"birthDate": "not-a-date"}, True, (), 0)
    assert item.birthday is None


def coordinator_shell(documents):
    calls = []

    async def document(collection, identifier):
        calls.append((collection, identifier))
        result = documents[(collection, identifier)]
        if isinstance(result, Exception):
            raise result
        return result

    async def async_get_user():
        return await document("users", "user")

    async def async_get_horse(identifier):
        return await document("horses", identifier)

    async def async_get_training(identifier):
        return await document("trainings", identifier)

    async def async_get_stable(identifier):
        return await document("stables", identifier)

    async def async_get_latest_notification():
        return []

    shell = object.__new__(EquilabCoordinator)
    shell.client = SimpleNamespace(
        uid="user",
        calls=calls,
        async_get_user=async_get_user,
        async_get_horse=async_get_horse,
        async_get_training=async_get_training,
        async_get_stable=async_get_stable,
        async_get_latest_notification=async_get_latest_notification,
    )
    shell.entry = SimpleNamespace(options={})
    shell.data, shell.profiles, shell.sync, shell.forced = {}, {}, {}, set()
    shell._device_refresh_lock = asyncio.Lock()
    return shell


async def test_coordinator_discovery_skip_and_revocation():
    docs = {
        ("users", "user"): {
            "horses": {"shared": True, "revoked": True},
            "ownedHorses": {"horse": True},
        },
        ("horses", "horse"): {"name": "Horse", "trainings": {"a": True, "b": True}},
        ("horses", "shared"): {"name": "Shared"},
        ("horses", "revoked"): AccessError(),
        ("trainings", "a"): {"horse": "horse", "total": {"time": 1}},
        ("trainings", "b"): MissingError(),
    }
    result = await EquilabCoordinator._async_update_data(coordinator_shell(docs))
    assert set(result) == {"horse", "shared"}
    assert result["horse"].owned
    assert not result["shared"].owned
    assert result["horse"].skipped == 1


@pytest.mark.parametrize(
    "error, expected", [(AuthError(), ConfigEntryAuthFailed), (EquilabError(), UpdateFailed)]
)
async def test_coordinator_failure_translation(error, expected):
    shell = coordinator_shell({("users", "user"): error})
    with pytest.raises(expected):
        await EquilabCoordinator._async_update_data(shell)


def entity_context(item):
    return SimpleNamespace(data={"horse": item}, last_update_success=True), SimpleNamespace(
        unique_id="account"
    )


def test_sensor_unknown_and_account_scoped_identity():
    coordinator, entry = entity_context(horse(training(energy=None)))
    description = next(d for d in DESCRIPTIONS if d.key == "last_energy")
    sensor = EquilabSensor(coordinator, entry, "horse", description)
    assert sensor.native_value is None
    assert sensor.unique_id == "account_horse_last_energy"
    assert sensor.available
    coordinator.data = {}
    assert not sensor.available
    assert sensor.native_value is None


def test_sensors_handle_missing_and_incomplete_profile_data():
    entry = SimpleNamespace(unique_id="account")
    last_training = next(d for d in DESCRIPTIONS if d.key == "last_training")

    coordinator, _ = entity_context(horse())
    assert EquilabSensor(coordinator, entry, "horse", last_training).native_value is None
    coordinator.data["horse"] = horse(training(), skipped=1)
    assert EquilabSensor(coordinator, entry, "horse", last_training).native_value is None

    missing = coordinator_shell({})
    missing.last_update_success = True
    first_name = next(d for d in PROFILE_FIELDS if d.key == "firstName")
    rider = rider_from_data("user", {"firstName": "Synthetic"}, (), 0, [])
    missing.profiles["rider:user"] = rider
    profile_sensor = ProfileSensor(missing, entry, "rider:user", first_name)
    missing.profiles.clear()
    assert profile_sensor.native_value is None
    assert profile_sensor.extra_state_attributes is None

    missing.profiles["rider:user"] = rider
    assert ProfileSensor(missing, entry, "rider:user", last_training).native_value is None


async def test_calendar_intersection_and_read_only():
    coordinator, entry = entity_context(horse(training()))
    calendar = EquilabCalendar(coordinator, entry, "horse")
    events = await calendar.async_get_events(
        None, datetime(2026, 9, 9, 12, 5, tzinfo=UTC), datetime(2026, 9, 9, 13, tzinfo=UTC)
    )
    assert len(events) == 1
    assert events[0].summary == "Dressage"
    assert calendar.event is None
    assert not calendar.supported_features
    assert (
        await calendar.async_get_events(
            None, datetime(2026, 9, 9, 12, 10, tzinfo=UTC), datetime(2026, 9, 9, 13, tzinfo=UTC)
        )
        == []
    )


async def test_calendar_rejects_unavailable_and_skips_incomplete_training():
    coordinator, entry = entity_context(horse(training(start=None)))
    calendar = EquilabCalendar(coordinator, entry, "horse")
    events = await calendar.async_get_events(
        None, datetime(2026, 9, 9, tzinfo=UTC), datetime(2026, 9, 10, tzinfo=UTC)
    )
    assert events == []
    coordinator.last_update_success = False
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await calendar.async_get_events(
            None, datetime(2026, 9, 9, tzinfo=UTC), datetime(2026, 9, 10, tzinfo=UTC)
        )


async def test_diagnostics_never_include_identity():
    coordinator, _ = entity_context(horse(training()))
    entry = SimpleNamespace(runtime_data=coordinator, data={"refresh_token": "SECRET"})
    result = await async_get_config_entry_diagnostics(None, entry)
    assert result["horse_count"] == 1
    assert "SECRET" not in repr(result)
    assert "Synthetic horse" not in repr(result)
    assert "Dressage" not in repr(result)
