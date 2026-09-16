# Contributing

Thank you for helping improve this unofficial Equilab integration for Home Assistant.

## Before opening a change

- Keep cloud access read-only. Authentication and token refresh are the only expected POST requests.
- Do not add write, deletion, subscription, entitlement or notification-acknowledgement operations.
- Never commit account credentials, tokens, private API responses, GPS coordinates or recording files.
- Preserve existing entity and device unique IDs unless the change includes a tested migration.
- Add or update tests for behavioral changes.
- Make reusable cloud-client or domain-model changes in `Danw33/py-equilab`, then
  update this integration's exact dependency pin after publishing the library.

## Local checks

Use Python 3.13 and run:

```sh
python -m pip install -r requirements-test.txt
ruff format --check .
ruff check .
python -m pytest --cov=custom_components.equilab --cov-report=term-missing tests -q
```

Pull requests should explain the user-visible behavior, data provenance, privacy implications and how the
change was tested. Contributions are accepted under the Apache License 2.0.
