# Changelog

## 0.0.5 — external Python library

- Move authentication, token renewal, bounded cloud reads, Firestore decoding and
  normalised domain models into the typed `equilab` 0.1.1 distribution.
- Inject Home Assistant's shared `aiohttp` session into the library and pin the
  dependency in the integration manifest.
- Raise the integration's combined coverage floor from 90% to 95%; the extracted
  integration suite covers 100% of statements and 99.6% including branches.
- Preserve entity IDs, config-entry data, authentication behavior, polling and all
  user-visible entities; no migration is required.
- Keep both repositories under Apache License 2.0 with matching ownership and
  independent `LICENSE` and `NOTICE` files.

## 0.0.4 — ownership, licensing and publication scaffold

- Add canonical documentation and issue-tracker metadata for the intended GitHub repository.
- Add GitHub Actions for Ruff, pytest coverage, Hassfest and HACS validation.
- Add Dependabot, contribution guidance, a security policy, HACS metadata and repository ignores.
- Enforce a truthful 90% coverage floor; current coverage is 99.7% for statements and 99.4% with branches.
- Make no runtime, entity, migration, authentication or polling behavior changes.

## 0.0.3 — devices, detailed measurements and independent sync

- Add the authenticated Rider and accessible Stable/Group/Club devices, retaining existing horse IDs.
- Add per-device Last sync diagnostics, disabled Sync now buttons and persisted Sync interval controls.
- Default to six-hour horse/rider and daily group refreshes; retain saved overrides.
- Add speed, tempo, stride statistics, gait distances, rein durations, session weather, rider energy,
  profile weights and source-reported personal bests with appropriate suggested units.
- Add rider profile/lifetime statistics, achievements/records counts and read-only notification metadata.
- Share training reads within refreshes; preserve last-success timestamps on failure.
- Capture allowlisted rate-limit headers/429 counts in diagnostics without a new limiter.
- Cross-account deduplication, charts/playback and unverified elevation semantics remain deferred.

## 0.0.2 — suggested measurement units

- Last session and gait durations suggest minutes; last session distance suggests metres.
- Weekly/monthly durations suggest hours; weekly/monthly distances suggest kilometres.
- Preserve native seconds/metres, stable IDs and explicit user unit preferences.
- No authentication, polling, calculation, colour or display-precision changes.

## 0.0.1 — initial alpha

- Read-only Firebase client with email/password login and refresh-token persistence.
- Config flow, reauthentication, multiple account entries and polling options.
- Account-scoped horse devices, 24 sensor definitions and one history calendar per horse.
- Optional-value handling, timezone-aware weekly/monthly totals and privacy-safe diagnostics.
- Synthetic-data tests including HA platform loading and calendar-service retrieval.
- Manual-install package, setup examples and explicit alpha limitations.
