"""HA config-flow, lifecycle and discovery contracts with mocked cloud I/O."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow
from pyequilab import AccessError, AuthError, EquilabError, RateLimitError

from custom_components.equilab import (
    async_remove_config_entry_device,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.equilab.config_flow import EquilabConfigFlow, EquilabOptionsFlow
from custom_components.equilab.entity import discover


def make_flow():
    flow = EquilabConfigFlow()
    flow.hass = Mock()
    flow.context = {"source": "user"}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    return flow


def client(error=None):
    return SimpleNamespace(
        uid="uid",
        refresh_token="renewal",
        async_login=AsyncMock(side_effect=error),
        async_get_user=AsyncMock(return_value={}),
    )


async def test_show_user_form():
    result = await make_flow().async_step_user()
    assert result["type"] == "form"
    assert set(str(key) for key in result["data_schema"].schema) == {"email", "password"}


async def test_setup_keeps_no_password():
    flow = make_flow()
    with (
        patch("custom_components.equilab.config_flow.async_get_clientsession"),
        patch("custom_components.equilab.config_flow.EquilabClient", return_value=client()),
    ):
        result = await flow.async_step_user({"email": "test@example.invalid", "password": "SECRET"})
    assert result["type"] == "create_entry"
    assert result["data"] == {"uid": "uid", "refresh_token": "renewal"}
    flow.async_set_unique_id.assert_awaited_once_with("uid")


@pytest.mark.parametrize(
    "error, key",
    [
        (AuthError(), "invalid_auth"),
        (AccessError(), "access_denied"),
        (EquilabError(), "cannot_connect"),
        (RateLimitError(), "rate_limited"),
    ],
)
async def test_flow_errors(error, key):
    flow = make_flow()
    with (
        patch("custom_components.equilab.config_flow.async_get_clientsession"),
        patch("custom_components.equilab.config_flow.EquilabClient", return_value=client(error)),
    ):
        result = await flow.async_step_user({"email": "test", "password": "SECRET"})
    assert result["errors"] == {"base": key}
    assert "SECRET" not in repr(result)


async def test_duplicate_guard():
    flow = make_flow()
    flow._abort_if_unique_id_configured.side_effect = AbortFlow("already_configured")
    with (
        patch("custom_components.equilab.config_flow.async_get_clientsession"),
        patch("custom_components.equilab.config_flow.EquilabClient", return_value=client()),
    ):
        with pytest.raises(AbortFlow):
            await flow.async_step_user({"email": "test", "password": "SECRET"})


async def test_reauth_wrong_identity():
    flow = make_flow()
    flow._get_reauth_entry = Mock(return_value=SimpleNamespace(unique_id="different"))
    with (
        patch("custom_components.equilab.config_flow.async_get_clientsession"),
        patch("custom_components.equilab.config_flow.EquilabClient", return_value=client()),
    ):
        result = await flow.async_step_reauth_confirm({"email": "test", "password": "SECRET"})
    assert result["reason"] == "wrong_account"


async def test_reauth_entry_step_shows_confirmation_form():
    result = await make_flow().async_step_reauth({})
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_success():
    flow = make_flow()
    entry = SimpleNamespace(unique_id="uid")
    flow._get_reauth_entry = Mock(return_value=entry)
    flow.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
    with (
        patch("custom_components.equilab.config_flow.async_get_clientsession"),
        patch("custom_components.equilab.config_flow.EquilabClient", return_value=client()),
    ):
        await flow.async_step_reauth_confirm({"email": "test", "password": "SECRET"})
    flow.async_update_reload_and_abort.assert_called_once_with(
        entry, data={"uid": "uid", "refresh_token": "renewal"}
    )


async def test_setup_refresh_before_platform_forward_and_rotation():
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=Mock(),
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        )
    )
    entry = SimpleNamespace(data={"uid": "uid", "refresh_token": "old"})
    coordinator = SimpleNamespace(async_config_entry_first_refresh=AsyncMock())
    with (
        patch("custom_components.equilab.async_get_clientsession"),
        patch("custom_components.equilab.EquilabClient") as constructor,
        patch("custom_components.equilab.EquilabCoordinator", return_value=coordinator),
    ):
        assert await async_setup_entry(hass, entry)
        callback = constructor.call_args.kwargs["on_token"]
        callback("rotated")
    hass.config_entries.async_update_entry.assert_called_once_with(
        entry, data={"uid": "uid", "refresh_token": "rotated"}
    )
    assert entry.runtime_data is coordinator
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    assert await async_unload_entry(hass, entry)


def test_dynamic_discovery_listener_cleanup_and_no_duplicates():
    coordinator = SimpleNamespace(
        data={"one": object()}, async_add_listener=Mock(return_value=lambda: None)
    )
    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=Mock())
    added = []
    discover(entry, lambda items: added.extend(items), lambda key: [key])
    listener = coordinator.async_add_listener.call_args.args[0]
    coordinator.data["two"] = object()
    listener()
    listener()
    assert added == ["one", "two"]
    entry.async_on_unload.assert_called_once()


def test_options_flow_factory():
    assert isinstance(EquilabConfigFlow.async_get_options_flow(None), EquilabOptionsFlow)


async def test_options_flow_defaults_and_merges_submission():
    flow = EquilabOptionsFlow()
    entry = SimpleNamespace(options={"existing": True, "poll_minutes": 120})
    with patch.object(EquilabOptionsFlow, "config_entry", new_callable=PropertyMock) as config:
        config.return_value = entry
        form = await flow.async_step_init()
        result = await flow.async_step_init({"poll_minutes": 60})
    assert form["type"] == "form"
    assert result["type"] == "create_entry"
    assert result["data"] == {"existing": True, "poll_minutes": 60}


async def test_device_removal_only_allows_stale_devices():
    entry = SimpleNamespace(
        domain="equilab",
        unique_id="account",
        runtime_data=SimpleNamespace(device_keys=lambda: {"horse", "rider:user"}),
    )
    active = SimpleNamespace(identifiers={("equilab", "account_horse")})
    stale = SimpleNamespace(identifiers={("equilab", "account_old")})
    assert not await async_remove_config_entry_device(None, entry, active)
    assert await async_remove_config_entry_device(None, entry, stale)
