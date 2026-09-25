# Contributing

## Setup

```bash
uv sync
uv run pre-commit install
```

## Checks

```bash
uv run pytest --cov
uv run ruff check .
uv run ruff format --check .
uv run python -m django makemigrations --check --dry-run semantichub_wagtail
```

Warnings fail the test suite and branch coverage must stay at or above 95%.
CI runs the same checks on Python 3.10 to 3.14 and Django 5.2 to 6.1.

## Pull requests

- Keep each pull request to one change, with a test that fails without it.
- Add a migration for model changes; never edit an applied migration.
- Record user-visible changes under `## [Unreleased]` in `CHANGELOG.md`.
- Update `README.md` when endpoints, settings or the adapter API change.

Security issues go through [SECURITY.md](SECURITY.md), not public issues.
