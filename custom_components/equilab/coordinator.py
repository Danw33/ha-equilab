"""Per-device deadlines with account discovery and serialized refreshes."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pyequilab import (
    AccessError,
    AuthError,
    EquilabError,
    MissingError,
    Training,
    active_ids,
    horse_from_data,
    rider_from_data,
    stable_from_data,
)

from .const import CONF_DEVICE_INTERVALS, CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class SyncState:
    attempt: datetime | None = None
    success: datetime | None = None
    failure: datetime | None = None
    ok: bool = True
    incomplete: bool = False


class EquilabCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=1),
            always_update=True,
        )
        self.client = client
        self.entry = entry
        self.profiles = {}
        self.sync = {}
        self.forced = set()
        self._device_refresh_lock = asyncio.Lock()

    def device_keys(self):
        return set(self.data or {}) | set(self.profiles)

    def device(self, key):
        return (self.data or {}).get(key) or self.profiles.get(key)

    def interval(self, key):
        default = (
            1440
            if key.startswith("stable:")
            else self.entry.options.get(CONF_POLL_MINUTES, DEFAULT_POLL_MINUTES)
        )
        return self.entry.options.get(CONF_DEVICE_INTERVALS, {}).get(key, default)

    def due(self, key, now):
        state = self.sync.get(key)
        return (
            key in self.forced
            or state is None
            or state.attempt is None
            or now >= state.attempt + timedelta(minutes=self.interval(key))
        )

    async def async_sync_device(self, key):
        self.forced.add(key)
        await self.async_refresh()
        state = self.sync.get(key)
        if (
            not self.last_update_success
            or state is None
            or not state.ok
            or self.device(key) is None
        ):
            raise HomeAssistantError("Equilab device sync failed; check diagnostics")

    async def _trainings(self, ids, cache, field, identifier):
        result, skipped = [], 0
        for key in sorted(ids):
            if key not in cache:
                try:
                    cache[key] = await self.client.async_get_training(key)
                except (MissingError, AccessError):
                    cache[key] = None
            data = cache[key]
            if data is None or data.get(field) != identifier:
                skipped += 1
            else:
                result.append(Training.parse(key, data))
        return tuple(result), skipped

    async def _async_update_data(self):
        async with self._device_refresh_lock:
            return await self._refresh_devices()

    async def _refresh_devices(self):
        now = dt_util.utcnow()
        rider_key = f"rider:{self.client.uid}"
        known = self.device_keys() | {rider_key}
        targets = {key for key in known if self.due(key, now)}
        if not targets:
            return self.data or {}
        try:
            user = await self.client.async_get_user()
        except EquilabError as err:
            for key in targets:
                state = self.sync.setdefault(key, SyncState())
                state.attempt = state.failure = now
                state.ok = False
            self.forced.difference_update(targets)
            if isinstance(err, AuthError):
                raise ConfigEntryAuthFailed("Equilab sign-in required") from err
            raise UpdateFailed(str(err)) from err
        owned = active_ids(user.get("ownedHorses")) | active_ids(user.get("owned_horses"))
        horse_ids = active_ids(user.get("horses")) | owned
        stable_ids = active_ids(user.get("stables")) | active_ids(user.get("groups"))
        result = {key: item for key, item in (self.data or {}).items() if key in horse_ids}
        cache = {}
        work = [*sorted(horse_ids), rider_key]
        for key in work:
            if not self.due(key, now):
                continue
            state = self.sync.setdefault(key, SyncState())
            state.attempt = now
            self.forced.discard(key)
            try:
                if key == rider_key:
                    trainings, skipped = await self._trainings(
                        active_ids(user.get("trainings")), cache, "user", self.client.uid
                    )
                    try:
                        notifications = await self.client.async_get_latest_notification()
                        inbox_missing = False
                    except (MissingError, AccessError):
                        notifications, inbox_missing = [], True
                    self.profiles[key] = rider_from_data(
                        self.client.uid, user, trainings, skipped, notifications
                    )
                    state.incomplete = bool(skipped or inbox_missing)
                else:
                    data = await self.client.async_get_horse(key)
                    trainings, skipped = await self._trainings(
                        active_ids(data.get("trainings")), cache, "horse", key
                    )
                    result[key] = horse_from_data(key, data, key in owned, trainings, skipped)
                    state.incomplete = bool(skipped)
                state.success = dt_util.utcnow()
                state.ok = True
            except AuthError as err:
                state.failure, state.ok = dt_util.utcnow(), False
                raise ConfigEntryAuthFailed("Equilab sign-in required") from err
            except EquilabError as err:
                state.failure, state.ok = dt_util.utcnow(), False
                if isinstance(err, (AccessError, MissingError)):
                    result.pop(key, None)
                _LOGGER.warning("A device refresh failed (%s)", type(err).__name__)
        for item in result.values():
            if identifier := item.profile.get("stable_id"):
                stable_ids.add(identifier)
        active_profiles = {rider_key} | {f"stable:{key}" for key in stable_ids}
        self.profiles = {key: item for key, item in self.profiles.items() if key in active_profiles}
        for identifier in sorted(stable_ids):
            key = f"stable:{identifier}"
            if not self.due(key, now):
                continue
            state = self.sync.setdefault(key, SyncState())
            state.attempt = now
            self.forced.discard(key)
            try:
                data = await self.client.async_get_stable(identifier)
                self.profiles[key] = stable_from_data(identifier, data)
                state.success, state.ok, state.incomplete = dt_util.utcnow(), True, False
            except AuthError as err:
                state.failure, state.ok = dt_util.utcnow(), False
                raise ConfigEntryAuthFailed("Equilab sign-in required") from err
            except EquilabError as err:
                state.failure, state.ok = dt_util.utcnow(), False
                if isinstance(err, (AccessError, MissingError)):
                    self.profiles.pop(key, None)
                _LOGGER.warning("A group refresh failed (%s)", type(err).__name__)
        removed = known - set(result) - set(self.profiles)
        for key in removed:
            state = self.sync.setdefault(key, SyncState())
            state.ok = False
            state.failure = now
        self.forced.difference_update(removed)
        return result
