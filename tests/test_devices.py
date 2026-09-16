"""Regression coverage for independent deadlines, profiles and measured units."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from pyequilab import (
    AccessError,
    AuthError,
    EquilabClient,
    EquilabError,
    Training,
    horse_from_data,
    rider_from_data,
    stable_from_data,
)
from pyequilab.api import ROOT
from test_equilab import coordinator_shell


def documents():
    return {
        ("users", "user"): {
            "firstName": "Synthetic",
            "ownedHorses": {"h1": True, "h2": True},
            "stables": {"s1": True},
            "trainings": {"t1": True},
            "totalTrainingDistance": 10000,
        },
        ("horses", "h1"): {"name": "First", "trainings": {"t1": True}},
        ("horses", "h2"): {"name": "Second"},
        ("stables", "s1"): {
            "name": "Stable",
            "type": "stable",
            "horses": {"h1": True},
            "lat": 51.5,
            "lon": -1.5,
        },
        ("trainings", "t1"): {
            "horse": "h1",
            "user": "user",
            "date": datetime(2026, 9, 10, tzinfo=UTC),
            "total": {"time": 600},
        },
    }


async def refresh(c):
    c.data = await c._async_update_data()


async def test_device_deadlines_manual_force_and_shared_reads():
    docs = documents()
    c = coordinator_shell(docs)
    await refresh(c)
    assert c.device_keys() == {"h1", "h2", "rider:user", "stable:s1"}
    assert c.client.calls.count(("trainings", "t1")) == 1
    initial_success = c.sync["h2"].success
    c.client.calls.clear()
    await refresh(c)
    assert c.client.calls == []
    c.forced.add("h1")
    await refresh(c)
    assert set(c.client.calls) == {
        ("users", "user"),
        ("horses", "h1"),
        ("trainings", "t1"),
    }
    assert c.sync["h2"].success == initial_success
    assert not c.forced
    c.client.calls.clear()
    c.entry.options = {"device_intervals": {"h2": 15}}
    c.sync["h2"].attempt -= timedelta(minutes=16)
    await refresh(c)
    assert set(c.client.calls) == {
        ("users", "user"),
        ("horses", "h2"),
    }


async def test_failures_preserve_last_success_and_recover():
    docs = documents()
    c = coordinator_shell(docs)
    await refresh(c)
    success = c.sync["h1"].success
    docs[("horses", "h1")] = EquilabError("Unavailable")
    c.forced.add("h1")
    await refresh(c)
    assert not c.sync["h1"].ok
    assert c.sync["h1"].success == success
    assert c.sync["h1"].failure is not None
    assert c.sync["h2"].ok
    docs[("horses", "h1")] = {"name": "First"}
    c.forced.add("h1")
    await refresh(c)
    assert c.sync["h1"].ok
    assert c.sync["h1"].success >= success
    assert c.sync["h1"].failure is not None


async def test_membership_revocation_removes_data_even_before_deadline():
    docs = documents()
    c = coordinator_shell(docs)
    await refresh(c)
    docs[("users", "user")]["ownedHorses"].pop("h1")
    docs[("users", "user")]["stables"] = {}
    c.forced.add("rider:user")
    await refresh(c)
    assert "h1" not in c.data
    assert "stable:s1" not in c.profiles
    assert not c.sync["h1"].ok


async def test_inbox_denial_does_not_hide_rider():
    c = coordinator_shell(documents())
    c.client.async_get_latest_notification = AsyncMock(side_effect=AccessError())
    await refresh(c)
    assert c.profiles["rider:user"].values["lastNotification"] is None
    assert c.sync["rider:user"].ok
    assert c.sync["rider:user"].incomplete


async def test_manual_sync_reports_an_unsuccessful_refresh():
    c = coordinator_shell(documents())
    c.async_refresh = AsyncMock()
    c.last_update_success = False
    with pytest.raises(HomeAssistantError, match="device sync failed"):
        await c.async_sync_device("h1")
    c.async_refresh.assert_awaited_once()


@pytest.mark.parametrize(
    "collection, identifier, key",
    [("horses", "h1", "h1"), ("stables", "s1", "stable:s1")],
)
async def test_device_auth_failure_requests_reauthentication(collection, identifier, key):
    docs = documents()
    docs[(collection, identifier)] = AuthError("expired")
    c = coordinator_shell(docs)
    with pytest.raises(ConfigEntryAuthFailed):
        await refresh(c)
    assert not c.sync[key].ok
    assert c.sync[key].failure is not None


async def test_inaccessible_stable_is_removed_without_losing_other_devices():
    docs = documents()
    c = coordinator_shell(docs)
    await refresh(c)
    docs[("stables", "s1")] = AccessError("revoked")
    c.forced.add("stable:s1")
    await refresh(c)
    assert "stable:s1" not in c.profiles
    assert not c.sync["stable:s1"].ok
    assert set(c.data) == {"h1", "h2"}


def test_measurement_normalization_and_profile_records():
    t = Training.parse(
        "training",
        {
            "user": "rider",
            "horse": "horse",
            "riderEnergy": 0,
            "walk": {"beat": 1.2, "pace": 1.5, "leftTurnsDuration": 30, "counter": 100},
            "weather": {"temperature": -4, "humidity": 0.46, "windSpeed": 2.5},
            "transitionData": {"walk": {"trot": 2}, "trot": {"walk": 1}},
        },
    )
    assert t.stats["walk_tempo"] == 72
    assert t.stats["walk_speed"] == 1.5
    assert t.stats["walk_left_rein"] == 30
    assert t.stats["weather_humidity"] == 46
    assert t.stats["weather_temperature"] == -4
    assert t.stats["transitions"] == 3
    assert t.rider_energy == 0
    assert t.horse_id == "horse" and t.rider_id == "rider"
    data = {
        "birthDate": "2010-04-12",
        "records": [
            {"type": "distance", "value": 2000},
            {"type": "distance", "value": 1000},
            {"type": "duration", "value": 3600},
            {"type": "speed", "value": float("nan")},
        ],
    }
    horse = horse_from_data("horse", data, True, (), 0)
    assert horse.birthday == "2010-04-12"
    assert horse.profile["record_distance"] == 2000
    rider = rider_from_data("rider", data, (), 0, [])
    assert rider.values["record_duration"] == 3600
    assert rider.values["record_speed"] is None
    assert stable_from_data("s", {"lat": 91, "lon": -2}).values["lat"] is None


async def test_api_notification_read_and_header_observations():
    from test_equilab import auth_payload, mocked_http

    async with mocked_http() as (session, mock):
        client = EquilabClient(session)
        client._tokens(auth_payload(), refresh=False)
        mock.get(
            f"{ROOT}/users/user/notifications?orderBy=date+desc&pageSize=1",
            payload={
                "documents": [
                    {
                        "fields": {
                            "date": {"timestampValue": "2026-09-10T12:00:00Z"},
                            "type": {"stringValue": "example"},
                        }
                    }
                ]
            },
            headers={"Retry-After": "60", "X-RateLimit-Remaining": "0", "Set-Cookie": "PRIVATE"},
        )
        result = await client.async_get_latest_notification()
        assert result[0]["date"] == datetime(2026, 9, 10, 12, tzinfo=UTC)
        assert client.rate_limit_observations["headers"] == {
            "retry-after": "60",
            "x-ratelimit-remaining": "0",
        }
        assert all(method == "GET" for method, _ in mock.requests)
        assert "PRIVATE" not in repr(client.rate_limit_observations)
