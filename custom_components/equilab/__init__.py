"""Equilab read-only integration."""

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyequilab import EquilabClient

from .const import CONF_REFRESH_TOKEN, CONF_UID, PLATFORMS
from .coordinator import EquilabCoordinator


async def async_setup_entry(hass, entry):
    def save_token(token):
        if token != entry.data[CONF_REFRESH_TOKEN]:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_REFRESH_TOKEN: token}
            )

    client = EquilabClient(
        async_get_clientsession(hass),
        uid=entry.data[CONF_UID],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        on_token=save_token,
    )
    coordinator = EquilabCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device_entry):
    coordinator = entry.runtime_data
    active = {(entry.domain, f"{entry.unique_id}_{key}") for key in coordinator.device_keys()}
    return not active.intersection(device_entry.identifiers)
