"""Allowlisted counts only: no raw keys, values, identifiers or tokens."""

from .const import VERSION


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "version": VERSION,
        "last_update_success": coordinator.last_update_success,
        "horse_count": len(coordinator.data),
        "profile_count": len(getattr(coordinator, "profiles", {})),
        "sync": [
            {
                "ok": s.ok,
                "incomplete": s.incomplete,
                "attempt": s.attempt,
                "success": s.success,
                "failure": s.failure,
            }
            for s in getattr(coordinator, "sync", {}).values()
        ],
        "rate_limits": getattr(getattr(coordinator, "client", None), "rate_limit_observations", {}),
        "horses": [
            {
                "relationship": "owned" if horse.owned else "shared",
                "readable_trainings": len(horse.trainings),
                "skipped_trainings": horse.skipped,
                "missing_energy": sum(t.energy is None for t in horse.trainings),
                "missing_date": sum(t.start is None for t in horse.trainings),
            }
            for horse in coordinator.data.values()
        ],
    }
