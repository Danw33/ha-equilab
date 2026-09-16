"""Read-only completed-training history; no fabricated upcoming plans."""

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .entity import HorseEntity, discover

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    discover(
        entry,
        async_add_entities,
        lambda horse_id: [EquilabCalendar(entry.runtime_data, entry, horse_id)],
    )


class EquilabCalendar(HorseEntity, CalendarEntity):
    _attr_name = "Training history"

    def __init__(self, coordinator, entry, horse_id):
        super().__init__(coordinator, entry, horse_id, "training_history")

    @property
    def event(self):
        # Recorded history is not a live-tracking or future-scheduling feed.
        return None

    async def async_get_events(self, hass, start_date, end_date):
        if not self.available:
            raise HomeAssistantError("Equilab training history is unavailable")
        start, end = dt_util.as_utc(start_date), dt_util.as_utc(end_date)
        events = []
        for training in self.horse.trainings:
            finish = training.end
            if training.start is None or finish is None:
                continue
            if training.start < end and finish > start:
                events.append(
                    CalendarEvent(
                        start=training.start,
                        end=finish,
                        summary=training.kind or "Training",
                        uid=training.id,
                    )
                )
        return sorted(events, key=lambda event: event.start)
