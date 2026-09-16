"""Explicit per-device refresh controls."""

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import DeviceEntity, discover_devices

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    discover_devices(
        entry,
        async_add_entities,
        lambda key: [SyncButton(entry.runtime_data, entry, key, "sync_now")],
    )


class SyncButton(DeviceEntity, ButtonEntity):
    _attr_name = "Sync now"
    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def available(self):
        return self.coordinator.device(self.device_key) is not None

    async def async_press(self):
        await self.coordinator.async_sync_device(self.device_key)
