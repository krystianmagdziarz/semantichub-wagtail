# semantichub-wagtail

Django/Wagtail package that receives SemanticHub webhooks and turns them into
Wagtail pages awaiting editorial approval. The public surface is two views
(`inbound/`, `pair/`), the `ArticleAdapter` / `PairAdapter` contracts, the
`Article` dataclass, the `SEMANTICHUB_INGEST_*` settings and the response
shapes documented in `README.md`.

## Commands

```bash
uv sync
uv run pytest --cov      # warnings are errors, branch coverage gate 95%
uv run ruff check . && uv run ruff format --check .
uv run python -m django makemigrations --check --dry-run semantichub_wagtail
```

`DJANGO_SETTINGS_MODULE=tests.settings`; the test Wagtail project and example
adapters live in `tests/` and `tests/testapp/`.

## Layout

| Module | Role |
| --- | --- |
| `auth.py` | bearer token and HMAC (`X-SH-Timestamp`, `X-SH-Signature`) checks |
| `views.py` | both endpoints, idempotency and revision guards |
| `payload.py`, `content.py` | payload validation, markdown/HTML rendering, slugs, tags |
| `images.py` | SSRF-safe cover download pinned to a checked public address |
| `publish.py` | service account and moderation/draft/publish policy |
| `adapters.py` | adapter base classes and loaders |
| `models.py` | `IngestReceipt`, `IngestPublication`, `IngestDelivery` |

## Conventions

- Match the surrounding code: small functions, no docstrings or comments
  unless the reason is not obvious, ruff-clean at line length 100.
- Every behaviour change ships with a test that fails without it. Mock the
  network through `semantichub_wagtail.images._download` or `_client`.
- Model changes need a migration; applied migrations are never edited.
- User-visible changes go under `## [Unreleased]` in `CHANGELOG.md`, and the
  status tables in `README.md` stay in sync with the views.

## Code review

When reviewing a pull request, report only problems you can tie to a line of
the diff, each with the concrete input that breaks it and the smallest fix.
Do not comment on formatting; ruff enforces it. Treat these as blocking:

- **Retries.** SemanticHub retries every 5xx, so invalid input must answer
  4xx. An unhandled `ValidationError`, `DataError` or `KeyError` reachable
  from the payload means endless retries.
- **Authentication first.** Nothing reads `request.data` or touches the
  database before `is_authorized` / `is_signed`. Secret comparisons use
  `hmac.compare_digest`. The pair endpoint accepts HMAC only.
- **Idempotency.** Replays with the same `Idempotency-Key` or `X-SH-Delivery`
  never create pages; a stale `revision` answers 409; the `IntegrityError`
  retry paths still converge when two deliveries race.
- **Transactions.** Guarded rows are read with `select_for_update` inside the
  same `transaction.atomic()`; network calls (image downloads) stay outside
  transactions.
- **Database limits.** Payload strings are bounded before they reach a
  `max_length` column; required Wagtail fields (`title`, `slug`) cannot end
  up empty; sibling slugs stay unique.
- **Publishing.** Pages are created unpublished; direct publish needs the
  inactive `semantichub` account's `publish` permission; payload fields never
  widen what the site owner configured; a live page changes only through
  `apply_policy`.
- **Public API.** Changes to adapters, `Article`, settings names or response
  shapes need a CHANGELOG entry and a README update.
