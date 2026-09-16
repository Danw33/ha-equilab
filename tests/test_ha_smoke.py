"""Load the custom integration through HA's actual config-entry/platform system."""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

from homeassistant import auth, loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry, device_registry, entity_registry
from pyequilab import EquilabClient


async def test_component_setup_entities_and_unload(tmp_path):
    source = Path(__file__).parents[1] / "custom_components"
    shutil.copytree(
        source, tmp_path / "custom_components", ignore=shutil.ignore_patterns("__pycache__")
    )
    hass = HomeAssistant(str(tmp_path))
    hass.config.time_zone = "Europe/London"
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await area_registry.async_load(hass)
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    hass.auth = await auth.auth_manager_from_config(hass, [], [])

    reads = []

    async def document(self, collection, identifier):
        reads.append((collection, identifier))
        if collection == "users":
            return {
                "ownedHorses": {"horse": True},
                "trainings": {"ride": True},
                "stables": {"stable": True},
                "firstName": "Synthetic rider",
                "totalTrainingDistance": 12000,
            }
        if collection == "horses":
            return {
                "name": "Synthetic horse",
                "horseBreed": "Synthetic breed",
                "trainings": {"ride": True},
                "stableId": "stable",
            }
        if collection == "stables":
            return {"name": "Synthetic stable", "type": "stable", "horses": {"horse": True}}
        if collection == "trainings":
            return {
                "horse": "horse",
                "user": "user",
                "date": datetime(2026, 9, 9, 12, tzinfo=UTC),
                "total": {"time": 600, "distance": 1000, "pace": 1.5},
                "weather": {"temperature": -4, "humidity": 0.46, "windSpeed": 2.5},
                "horseEnergyMj": 2,
                "trainingTypes": {"-KgsjZPxgZP7Nsj_cXvW": True},
            }
        raise AssertionError("Unexpected collection")

    async def get_user(self):
        return await document(self, "users", self.uid)

    async def get_horse(self, identifier):
        return await document(self, "horses", identifier)

    async def get_training(self, identifier):
        return await document(self, "trainings", identifier)

    async def get_stable(self, identifier):
        return await document(self, "stables", identifier)

    entry = ConfigEntry(
        domain="equilab",
        title="Test account",
        version=1,
        minor_version=1,
        data={"uid": "user", "refresh_token": "synthetic"},
        options={},
        unique_id="user",
        source="user",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    try:
        with (
            patch.object(EquilabClient, "async_get_user", get_user),
            patch.object(EquilabClient, "async_get_horse", get_horse),
            patch.object(EquilabClient, "async_get_training", get_training),
            patch.object(EquilabClient, "async_get_stable", get_stable),
            patch.object(
                EquilabClient, "async_get_latest_notification", new=AsyncMock(return_value=[])
            ),
            patch("custom_components.equilab.async_get_clientsession"),
            patch(
                "homeassistant.components.http.async_get_source_ip",
                new=AsyncMock(return_value="127.0.0.1"),
            ),
        ):
            await hass.config_entries.async_add(entry)
            await hass.async_block_till_done()
            assert entry.state is ConfigEntryState.LOADED
            registry = entity_registry.async_get(hass)
            entities = [
                entity
                for entity in registry.entities.values()
                if entity.config_entry_id == entry.entry_id
            ]
            assert len(entities) > 100
            assert any(e.domain == "number" for e in entities)
            assert any(e.domain == "button" and e.disabled_by is not None for e in entities)
            assert (
                hass.states.get("sensor.synthetic_rider_lifetime_training_distance").state == "12.0"
            )
            assert hass.states.get("sensor.synthetic_stable_horses").state == "1"
            assert hass.states.get("sensor.synthetic_horse_last_sync").state not in {
                "unknown",
                "unavailable",
            }
            interval_id = "number.synthetic_horse_sync_interval"
            assert hass.states.get(interval_id).state == "360"
            await hass.services.async_call(
                "number", "set_value", {"entity_id": interval_id, "value": 60}, blocking=True
            )
            assert entry.options["device_intervals"]["horse"] == 60
            button_id = "button.synthetic_horse_sync_now"
            registry.async_update_entity(button_id, disabled_by=None)
            states = hass.states.async_all()
            assert any(state.state == "Synthetic breed" for state in states)
            assert len([state for state in states if state.domain == "calendar"]) == 1
            duration_id = "sensor.synthetic_horse_last_training_duration"
            duration = hass.states.get(duration_id)
            assert duration.attributes["unit_of_measurement"] == "min"
            assert float(duration.state) == 10
            distance = hass.states.get("sensor.synthetic_horse_last_training_distance")
            assert distance.attributes["unit_of_measurement"] == "m"
            assert float(distance.state) == 1000
            assert float(hass.states.get("sensor.synthetic_horse_last_speed").state) == 5.4
            assert (
                float(hass.states.get("sensor.synthetic_horse_last_session_humidity").state) == 46
            )
            assert (
                float(hass.states.get("sensor.synthetic_horse_last_session_temperature").state)
                == -4
            )
            for period in ("week", "month"):
                for metric, unit in (("duration", "h"), ("distance", "km")):
                    state = hass.states.get(
                        f"sensor.synthetic_horse_training_{metric}_this_{period}"
                    )
                    assert state.attributes["unit_of_measurement"] == unit
            for gait in ("walk", "trot", "canter", "stand"):
                state = hass.states.get(f"sensor.synthetic_horse_last_{gait}_duration")
                assert state.attributes["unit_of_measurement"] == "min"

            registry.async_update_entity_options(
                duration_id, "sensor", {"unit_of_measurement": "s"}
            )
            await hass.async_block_till_done()
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            duration = hass.states.get(duration_id)
            assert duration.attributes["unit_of_measurement"] == "s"
            assert float(duration.state) == 600
            assert hass.states.get(interval_id).state == "60"
            reads.clear()
            await hass.services.async_call(
                "button", "press", {"entity_id": button_id}, blocking=True
            )
            assert reads == [("users", "user"), ("horses", "horse"), ("trainings", "ride")]
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": "calendar.synthetic_horse_training_history",
                    "start_date_time": "2026-09-09T00:00:00+00:00",
                    "end_date_time": "2026-09-10T00:00:00+00:00",
                },
                blocking=True,
                return_response=True,
            )
            events = response["calendar.synthetic_horse_training_history"]["events"]
            assert len(events) == 1
            assert events[0]["summary"] == "Dressage"
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
    finally:
        await hass.async_stop(force=True)
