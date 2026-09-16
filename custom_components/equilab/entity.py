"""Shared device identity and dynamic discovery."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class HorseEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, horse_id, key):
        super().__init__(coordinator, context=horse_id)
        self.horse_id = horse_id
        self._attr_unique_id = f"{entry.unique_id}_{horse_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{horse_id}")},
            name=coordinator.data[horse_id].name,
            manufacturer="Equilab",
            model="Horse",
        )

    @property
    def horse(self):
        return self.coordinator.data.get(self.horse_id)

    @property
    def available(self):
        state = getattr(self.coordinator, "sync", {}).get(self.horse_id)
        return super().available and self.horse is not None and (state is None or state.ok)


def discover(entry, async_add_entities, factory):
    """Discover new horses after setup and release listeners on unload."""
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def add_new():
        new = set(coordinator.data) - seen
        seen.update(new)
        async_add_entities(entity for horse_id in sorted(new) for entity in factory(horse_id))

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class DeviceEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, device_key, key):
        super().__init__(coordinator, context=device_key)
        self.device_key = device_key
        item = coordinator.device(device_key)
        self._attr_unique_id = f"{entry.unique_id}_{device_key}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{device_key}")},
            name=item.name,
            manufacturer="Equilab",
            model=getattr(item, "model", "Horse"),
        )

    @property
    def available(self):
        state = self.coordinator.sync.get(self.device_key)
        return (
            super().available
            and self.coordinator.device(self.device_key) is not None
            and (state is None or state.ok)
        )


def discover_devices(entry, async_add_entities, factory):
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def add_new():
        new = coordinator.device_keys() - seen
        seen.update(new)
        async_add_entities(entity for key in sorted(new) for entity in factory(key))

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))
