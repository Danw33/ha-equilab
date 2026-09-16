# Equilab for Home Assistant — 0.0.5

[![CI](https://github.com/Danw33/ha-equilab/actions/workflows/ci.yml/badge.svg)](https://github.com/Danw33/ha-equilab/actions/workflows/ci.yml)
[![Validate](https://github.com/Danw33/ha-equilab/actions/workflows/validate.yml/badge.svg)](https://github.com/Danw33/ha-equilab/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Unofficial**, read-only alpha integration for Equilab email/password accounts.
Includes horse, authenticated rider and account-linked stable/group devices.
This is not an official Equilab API, HACS listing or certified HA Quality Scale
integration. Maintained by [Daniel Wilson](https://github.com/Danw33) ([danw.io](https://danw.io)). Tested with
HA Core 2025.12.0 and Python 3.13.9 using synthetic cloud responses. Cloud access
and domain normalisation are provided by the separately versioned, typed
[`equilab`](https://github.com/Danw33/py-equilab) distribution (imported as
`pyequilab`).

## Upgrade or install

1. Extract the ZIP on your computer.
2. Copy `custom_components/equilab` to `/config/custom_components/equilab` on HAOS.
3. Restart Home Assistant. Existing installations do not need removal or reauthentication.
4. For a first installation, add Equilab under Settings → Devices & services and
   enter your Equilab email/password. The password is not stored; a refresh token is.

Existing horse device and entity unique IDs are preserved, including your previous
unit overrides. New rider and stable/group devices should appear automatically.
Home Assistant installs the pinned `equilab` dependency automatically.

## Sync controls on every device

- **Last sync**: diagnostic timestamp of the latest completed device fetch. Its
  `partial_data` attribute identifies inaccessible training references or inbox
  data. A completed fetch can contain missing fields; it does not guarantee that
  all source records are available.
- **Last sync attempt / Last sync failure**: diagnostic timestamps, disabled by
  default. Last success is retained after failure; last failure is retained after
  recovery. Timestamps restart as unknown at HA startup until a fetch completes.
- **Sync now**: diagnostic button, disabled by default. Enable it under the device's
  entities, then press it to request an immediate refresh. Sync failures surface
  as action errors. The last-sync diagnostics remain readable during failures.
- **Sync interval**: configuration number on the device, in minutes, from 15 to
  1440. Values are saved in the config entry and survive restarts. Changing an
  interval makes it take effect at the next scheduler tick, within about a minute.

Default intervals are six hours for horses/riders and 24 hours for groups/stables.
An explicitly saved integration polling preference remains the default for
horses/riders; per-device settings take precedence. The integration options form
sets this account default without resetting device overrides.

The coordinator checks local deadlines once a minute; this is NOT a cloud poll
every minute. It reads the account membership document when any device is due,
then updates only due/new devices. A manual sync can also refresh other devices
whose deadlines have arrived. Training reads are shared within that update cycle.
Each scheduled device fetch currently rereads its complete referenced history,
so use longer intervals for large accounts. Retries after device failures use the
configured interval; the button allows an earlier retry. Successful devices remain
usable when another device has an ordinary network/access failure. Authentication
failure starts HA reauthentication. Revoked/deleted devices become unavailable;
their entity registry entries are not silently deleted.

New memberships are discovered on the next account read, or when Sync now is
pressed on an existing device. Sync timestamps describe fetching from Equilab,
not when a rider last saved a session or when the mobile app uploaded it.

## Entities

### Horse

Existing profile sensors, last session, gait durations, weekly/monthly totals and
training-history calendar remain. New sensors include:

- Horse and tack weight; personal-record count; reported best distance, duration
  and speed. Birthday supports both Firestore timestamps and ISO date strings.
- Last session's average speed, reported top speed, tempo, stride count, stride
  length and left/right rein durations; corresponding statistics by gait.
- Gait distances, total gait transitions and rider energy.
- Session temperature, feels-like temperature, wind speed, humidity and pressure.
- Rider-energy totals for this week and month.

Stand, tölt and unknown detailed gait sensors are disabled by default. The existing
stand-duration sensor remains enabled. New measurements remain numeric and support
HA unit selection where the sensor device class provides it.

The last-training timestamp includes source training, horse, rider, owner and
stable identifiers as attributes for associations. No full routes or large raw
profiles are stored in entity attributes.

### Rider

One Rider device per authenticated account, with first/last name, city, discipline,
Equilab lifetime training count/distance/duration, achievement and record counts,
reported best distance/duration/speed, unread notification count, and latest
notification timestamp/type. Notification messages are not exposed or marked read.
The device also has last-session statistics and weekly/monthly totals calculated
from the rider's own referenced training history, across horses.

Equilab lifetime totals and records are source-reported; they may cover more data
than the history accessible to the account. Locally calculated totals are clearly
separate. Other riders are linked by source IDs, not silently onboarded as new
authenticated devices. Achievement names/levels and arbitrary record types are
not inferred from unknown codes.

### Stable / Group / Club

Each accessible object in Equilab's `stables` collection becomes a device. Sensors
show the reported type, privacy and indexed horse count. The Type sensor includes
latitude/longitude and source ID attributes when supplied. Location describes
the stable/group profile, not the current position of a horse or rider. Group
member counts, group feeds and shared calendars are not exposed because their
routes/semantics have not yet been verified.

### Units

| Measurement | Native unit | Suggested unit |
| --- | --- | --- |
| Last session/gait/rein duration | seconds | minutes |
| Weekly/monthly/lifetime and record duration | seconds | hours |
| Last session/gait distance and stride length | metres | metres |
| Weekly/monthly/lifetime and record distance | metres | kilometres |
| Speed, top speed, record speed and wind | m/s | km/h |
| Tempo | strides/min | strides/min |
| Horse energy | MJ | MJ |
| Rider energy | kcal | kcal |
| Weight | kg | kg |
| Temperature | °C | °C |
| Humidity | % | % |
| Pressure | hPa | hPa |

Users can override convertible units in entity settings. Existing entities may
retain previously saved units after an upgrade. Native storage and calculations
remain unchanged. The API's `beat` is multiplied by 60 for tempo, and fractional
weather humidity is multiplied by 100. Temperatures may be negative.

## Data semantics and limits

- Weeks start Monday and calendar periods use HA's timezone. Entire sessions are
  assigned by their start time. Local scheduler ticks update period boundaries
  without requiring a cloud read.
- Missing values remain unknown, not zero. Unreadable training references or
  missing session dates prevent potentially misleading latest-session and period
  totals; `partial_data` and diagnostics help identify this condition.
- API-reported zero values are retained, including top speed and elevation values
  reported as zero despite tracked movement. We do not invent
  missing measurements from GPS. Elevation summaries are deferred until their
  meaning and validity can be verified; no elevation or route charts are included.
- Calendar entries cover completed training only. Their end is approximated by
  start plus reported duration; pauses may make it differ from wall-clock end.
- Period totals can decrease after corrections, deletions and period boundaries.
  They deliberately have no cumulative `state_class`; these are exercise metrics,
  not household energy meters. Individual-session states also have no numeric
  long-term statistic classification. HA records ordinary state history.
- Multiple accounts are supported and remain account-scoped in this release.
  The same shared horse/group can appear twice when both accounts are configured.
  Cross-account deduplication is deferred to a dedicated migration so existing
  dashboard references are preserved.
- No premium flags are changed, and no Equilab records are written. No automatic
  generation/export jobs, route downloads or live safety tracking are performed
  by the integration. Per-device interval writes change HA settings only.

The integration also captures the same allowlisted rate-limit headers and 429
counts in its diagnostics. No new rate limiter or inferred quota has been added.
An HTTP 429 is still surfaced as an upstream rate-limit error.

## Validation and development

See VALIDATION.md for exact tests and limitations. No cloud credentials were used
for automated tests. Python 3.13 and HA Core 2025.12.0 are the tested runtime.

```sh
python -m pip install -r requirements-test.txt
python -m pytest --cov=custom_components.equilab --cov-report=term-missing tests -q
ruff check .
ruff format --check .
```

GitHub Actions run these checks, Hassfest validation and HACS validation. Current
integration coverage is 100% for statements and 99.6% with branches included; CI
enforces a 95% combined floor. The dependency repository separately tests the API,
models, typing and package distributions.

This remains an alpha. Before publishing integration 0.0.5, publish `equilab`
0.1.1 to PyPI, then rerun CI from a clean environment. Wider real-account testing,
complete HA Quality Scale work and the permission/terms considerations documented
above also remain. Do not represent it as certified or official.

## Project and licence

Source, issues and release history are intended for
[Danw33/ha-equilab](https://github.com/Danw33/ha-equilab).
Contributions are welcome under the guidance in [CONTRIBUTING.md](CONTRIBUTING.md),
and security reports should follow [SECURITY.md](SECURITY.md).

Copyright © 2026 Daniel Wilson. Licensed under the
[Apache License 2.0](LICENSE). The separately distributed `equilab` dependency uses the same Apache
License 2.0 and carries its own `LICENSE` and `NOTICE` files.

## Licence

Copyright © 2026 Daniel Wilson ([@Danw33](https://github.com/Danw33))

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Equilab is a trademark of its respective owner;
this project is independent, unofficial and not endorsed by Equilab or Equestrian Insights AB.
