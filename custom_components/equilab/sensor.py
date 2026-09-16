"""Profile, last-session and complete calendar-period totals."""

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
from pyequilab import GAITS

from .entity import DeviceEntity, HorseEntity, discover, discover_devices

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EquilabSensorDescription(SensorEntityDescription):
    source: str = "profile"
    field: str = ""
    period: str = ""


DESCRIPTIONS = (
    [
        EquilabSensorDescription(key=key, name=name, field=key, icon="mdi:horse")
        for key, name in (
            ("breed", "Breed"),
            ("birthday", "Birthday"),
            ("category", "Category"),
            ("level", "Level"),
        )
    ]
    + [
        EquilabSensorDescription(key="relationship", name="Account relationship", field="owned"),
        EquilabSensorDescription(
            key="last_training",
            name="Last training",
            source="latest",
            field="start",
            device_class=SensorDeviceClass.TIMESTAMP,
        ),
        EquilabSensorDescription(
            key="last_type", name="Last training type", source="latest", field="kind"
        ),
        EquilabSensorDescription(
            key="last_duration",
            name="Last training duration",
            source="latest",
            field="duration",
            native_unit_of_measurement="s",
            suggested_unit_of_measurement="min",
            device_class=SensorDeviceClass.DURATION,
        ),
        EquilabSensorDescription(
            key="last_distance",
            name="Last training distance",
            source="latest",
            field="distance",
            native_unit_of_measurement="m",
            suggested_unit_of_measurement="m",
            device_class=SensorDeviceClass.DISTANCE,
        ),
        EquilabSensorDescription(
            key="last_energy",
            name="Last horse energy",
            source="latest",
            field="energy",
            native_unit_of_measurement="MJ",
            suggested_unit_of_measurement="MJ",
            device_class=SensorDeviceClass.ENERGY,
        ),
    ]
    + [
        EquilabSensorDescription(
            key=f"last_{gait}",
            name=f"Last {gait} duration",
            source="gait",
            field=gait,
            native_unit_of_measurement="s",
            suggested_unit_of_measurement="min",
            device_class=SensorDeviceClass.DURATION,
            entity_registry_enabled_default=gait not in {"tolt", "unknown"},
        )
        for gait in GAITS
    ]
    + [
        EquilabSensorDescription(
            key=f"{metric}_{period}",
            name=f"{name} this {period}",
            source="aggregate",
            field=metric,
            period=period,
            native_unit_of_measurement=unit,
            suggested_unit_of_measurement={
                "duration": "h",
                "distance": "km",
                "energy": "MJ",
                "rider_energy": "kcal",
            }.get(metric),
            device_class=device_class,
        )
        for period in ("week", "month")
        for metric, name, unit, device_class in (
            ("count", "Trainings", None, None),
            ("duration", "Training duration", "s", SensorDeviceClass.DURATION),
            ("distance", "Training distance", "m", SensorDeviceClass.DISTANCE),
            ("energy", "Horse energy", "MJ", SensorDeviceClass.ENERGY),
            ("rider_energy", "Rider energy", "kcal", SensorDeviceClass.ENERGY),
        )
    ]
)

# Native values retain their source units; HA handles user-selected conversions.
STAT_FIELDS = (
    ("distance", "distance", "m", "m", SensorDeviceClass.DISTANCE),
    ("speed", "speed", "m/s", "km/h", SensorDeviceClass.SPEED),
    ("top_speed", "top speed", "m/s", "km/h", SensorDeviceClass.SPEED),
    ("tempo", "tempo", "strides/min", None, None),
    ("strides", "strides", None, None, None),
    ("stride_length", "stride length", "m", "m", SensorDeviceClass.DISTANCE),
    ("left_rein", "left rein duration", "s", "min", SensorDeviceClass.DURATION),
    ("right_rein", "right rein duration", "s", "min", SensorDeviceClass.DURATION),
)
DESCRIPTIONS += [
    EquilabSensorDescription(
        key=f"last_{gait}_{metric}",
        name=f"Last {'' if gait == 'total' else gait + ' '}{name}",
        source="stat",
        field=f"{gait}_{metric}",
        native_unit_of_measurement=unit,
        suggested_unit_of_measurement=suggested,
        device_class=device_class,
        entity_registry_enabled_default=gait in {"total", "walk", "trot", "canter"},
    )
    for gait in ("total", *GAITS)
    for metric, name, unit, suggested, device_class in STAT_FIELDS
    if not (gait == "total" and metric == "distance")
]
DESCRIPTIONS += [
    EquilabSensorDescription(
        key="last_rider_energy",
        name="Last rider energy",
        source="latest",
        field="rider_energy",
        native_unit_of_measurement="kcal",
        suggested_unit_of_measurement="kcal",
        device_class=SensorDeviceClass.ENERGY,
    ),
    EquilabSensorDescription(
        key="last_transitions", name="Last gait transitions", source="stat", field="transitions"
    ),
]
DESCRIPTIONS += [
    EquilabSensorDescription(
        key=f"last_weather_{key}",
        name=f"Last session {name}",
        source="stat",
        field=f"weather_{key}",
        native_unit_of_measurement=unit,
        suggested_unit_of_measurement=suggested,
        device_class=device_class,
    )
    for key, name, unit, suggested, device_class in (
        ("temperature", "temperature", "°C", "°C", SensorDeviceClass.TEMPERATURE),
        (
            "apparentTemperature",
            "feels like temperature",
            "°C",
            "°C",
            SensorDeviceClass.TEMPERATURE,
        ),
        ("windSpeed", "wind speed", "m/s", "km/h", SensorDeviceClass.WIND_SPEED),
        ("humidity", "humidity", "%", None, SensorDeviceClass.HUMIDITY),
        ("pressure", "pressure", "hPa", "hPa", SensorDeviceClass.ATMOSPHERIC_PRESSURE),
    )
]
DESCRIPTIONS += [
    EquilabSensorDescription(
        key=key,
        name=name,
        source="profile_extra",
        field=key,
        native_unit_of_measurement="kg" if key in {"weight", "tack_weight"} else None,
        suggested_unit_of_measurement="kg" if key in {"weight", "tack_weight"} else None,
        device_class=SensorDeviceClass.WEIGHT if key in {"weight", "tack_weight"} else None,
    )
    for key, name in (
        ("weight", "Weight"),
        ("tack_weight", "Tack weight"),
        ("records_count", "Records count"),
    )
]

PROFILE_FIELDS = [
    EquilabSensorDescription(
        key=key,
        name=name,
        field=key,
        native_unit_of_measurement=unit,
        suggested_unit_of_measurement=suggested,
        device_class=dc,
    )
    for key, name, unit, suggested, dc in (
        ("firstName", "First name", None, None, None),
        ("lastName", "Last name", None, None, None),
        ("city", "City", None, None, None),
        ("discipline", "Discipline", None, None, None),
        ("totalTrainingCount", "Lifetime trainings", None, None, None),
        (
            "totalTrainingDistance",
            "Lifetime training distance",
            "m",
            "km",
            SensorDeviceClass.DISTANCE,
        ),
        ("totalTrainingTime", "Lifetime training duration", "s", "h", SensorDeviceClass.DURATION),
        ("unseenNotificationCount", "Unread notifications", None, None, None),
        ("lastNotification", "Last notification", None, None, SensorDeviceClass.TIMESTAMP),
        ("lastNotificationType", "Last notification type", None, None, None),
        ("achievementsCount", "Achievements count", None, None, None),
        ("recordsCount", "Records count", None, None, None),
    )
]
GROUP_FIELDS = [
    EquilabSensorDescription(key=key, name=name, field=key)
    for key, name in (("type", "Type"), ("privacy", "Privacy"), ("horseCount", "Horses"))
]

for metric, name, unit, suggested, dc in (
    ("distance", "Record distance", "m", "km", SensorDeviceClass.DISTANCE),
    ("duration", "Record duration", "s", "h", SensorDeviceClass.DURATION),
    ("speed", "Record speed", "m/s", "km/h", SensorDeviceClass.SPEED),
):
    for descriptions, source in ((DESCRIPTIONS, "profile_extra"), (PROFILE_FIELDS, "profile")):
        descriptions.append(
            EquilabSensorDescription(
                key="record_" + metric,
                name=name,
                source=source,
                field="record_" + metric,
                native_unit_of_measurement=unit,
                suggested_unit_of_measurement=suggested,
                device_class=dc,
            )
        )


async def async_setup_entry(hass, entry, async_add_entities):
    discover(
        entry,
        async_add_entities,
        lambda horse_id: [
            EquilabSensor(entry.runtime_data, entry, horse_id, description)
            for description in DESCRIPTIONS
        ],
    )

    def extra(key):
        entities = [
            SyncSensor(entry.runtime_data, entry, key, metric)
            for metric in ("success", "attempt", "failure")
        ]
        if key.startswith(("rider:", "stable:")):
            descriptions = PROFILE_FIELDS if key.startswith("rider:") else GROUP_FIELDS
            entities.extend(ProfileSensor(entry.runtime_data, entry, key, d) for d in descriptions)
            if key.startswith("rider:"):
                entities.extend(
                    ProfileSensor(entry.runtime_data, entry, key, d)
                    for d in DESCRIPTIONS
                    if d.source in {"aggregate", "latest", "stat", "gait"}
                )
        return entities

    discover_devices(entry, async_add_entities, extra)


class EquilabSensor(HorseEntity, SensorEntity):
    def __init__(self, coordinator, entry, horse_id, description):
        super().__init__(coordinator, entry, horse_id, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        horse = self.horse
        if horse is None:
            return None
        desc = self.entity_description
        if desc.source == "profile":
            value = getattr(horse, desc.field)
            if desc.field == "owned":
                return "Owned" if value else "Shared"
            return value[:255] if isinstance(value, str) else value
        if desc.source == "profile_extra":
            return horse.profile.get(desc.field)
        if desc.source == "aggregate":
            zone = dt_util.get_time_zone(self.hass.config.time_zone)
            return horse.aggregate(desc.period, desc.field, dt_util.now(zone))
        # If any reference is unreadable, we cannot guarantee the latest session.
        if horse.skipped or any(t.start is None for t in horse.trainings):
            return None
        latest = horse.latest
        if latest is None:
            return None
        if desc.source == "gait":
            return latest.gaits.get(desc.field)
        if desc.source == "stat":
            return latest.stats.get(desc.field)
        value = getattr(latest, desc.field)
        return value[:255] if isinstance(value, str) else value

    @property
    def extra_state_attributes(self):
        if self.entity_description.key != "last_training" or self.horse is None:
            return None
        latest = self.horse.latest
        return {
            "horse_id": self.horse.id,
            **self.horse.profile,
            "training_id": latest.id if latest else None,
            "rider_id": latest.rider_id if latest else None,
        }


class ProfileSensor(DeviceEntity, SensorEntity):
    def __init__(self, coordinator, entry, key, description):
        super().__init__(coordinator, entry, key, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        item = self.coordinator.profiles.get(self.device_key)
        if item is None:
            return None
        d = self.entity_description
        if d.source == "profile":
            value = item.values.get(d.field)
        elif d.source == "aggregate":
            zone = dt_util.get_time_zone(self.hass.config.time_zone)
            value = item.aggregate(d.period, d.field, dt_util.now(zone))
        else:
            latest = item.latest
            if latest is None or item.skipped or any(t.start is None for t in item.trainings):
                return None
            value = (
                latest.stats.get(d.field)
                if d.source == "stat"
                else latest.gaits.get(d.field)
                if d.source == "gait"
                else getattr(latest, d.field)
            )
        return value[:255] if isinstance(value, str) else value

    @property
    def extra_state_attributes(self):
        item = self.coordinator.profiles.get(self.device_key)
        if item is None:
            return None
        if self.entity_description.key == "type":
            return {
                "equilab_id": item.id,
                "latitude": item.values.get("lat"),
                "longitude": item.values.get("lon"),
            }
        if self.entity_description.key == "last_training":
            latest = item.latest
            return {
                "rider_id": item.id,
                "training_id": latest.id if latest else None,
                "horse_id": latest.horse_id if latest else None,
            }
        return None


class SyncSensor(DeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, key, metric):
        super().__init__(coordinator, entry, key, "last_sync_" + metric)
        self.metric = metric
        self._attr_name = {
            "success": "Last sync",
            "attempt": "Last sync attempt",
            "failure": "Last sync failure",
        }[metric]
        self._attr_entity_registry_enabled_default = metric == "success"

    @property
    def available(self):
        return self.device_key in self.coordinator.sync

    @property
    def native_value(self):
        state = self.coordinator.sync.get(self.device_key)
        return getattr(state, self.metric, None)

    @property
    def extra_state_attributes(self):
        state = self.coordinator.sync.get(self.device_key)
        return (
            {"last_attempt_successful": state.ok, "partial_data": state.incomplete}
            if state
            else None
        )
