"""Persisted per-device polling intervals, exposed as configuration entities."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_DEVICE_INTERVALS
from .entity import DeviceEntity, discover_devices

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    discover_devices(
        entry, async_add_entities, lambda key: [SyncInterval(entry.runtime_data, entry, key)]
    )


class SyncInterval(DeviceEntity, NumberEntity):
    _attr_name = "Sync interval"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = "min"
    _attr_native_min_value = 15
    _attr_native_max_value = 1440
    _attr_native_step = 15
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-sync-outline"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key, "sync_interval")
        self.entry = entry

    @property
    def available(self):
        return self.coordinator.device(self.device_key) is not None

    @property
    def native_value(self):
        return self.coordinator.interval(self.device_key)

    async def async_set_native_value(self, value):
        options = dict(self.entry.options)
        options[CONF_DEVICE_INTERVALS] = {
            **options.get(CONF_DEVICE_INTERVALS, {}),
            self.device_key: int(value),
        }
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.async_write_ha_state()
