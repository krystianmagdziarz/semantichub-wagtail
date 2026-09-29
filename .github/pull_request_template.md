## What changes

<!-- One or two sentences: the behaviour before and after. -->

## Why

<!-- Link the issue or explain the problem. -->

## Checklist

- [ ] Tests cover the change and fail without it
- [ ] `uv run pytest --cov`, `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] Migration added for model changes (`makemigrations --check` passes)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` for user-visible changes
- [ ] `README.md` updated if endpoints, settings or the adapter API changed
