# semantichub-wagtail

Django/Wagtail package that receives SemanticHub webhooks and turns them into
Wagtail pages awaiting editorial approval. The public surface is the
`inbound/` view (v3 and v5 payloads), the `manifest/` view and the
`semantichub_push_manifest` command, the `ArticleAdapter` contract (including
`get_fields()` / `apply_fields()`), the `Article` dataclass, the
`SEMANTICHUB_*` settings and the response shapes documented in `README.md`.

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
| `views.py` | inbound (v3 legacy and v5 per-language) and manifest views, idempotency and revision guards |
| `payload.py`, `content.py` | payload validation, v5 identity and locales, markdown/HTML rendering, slugs, tags |
| `images.py` | SSRF-safe cover download pinned to a checked public address |
| `publish.py` | service account and moderation/draft/publish policy |
| `adapters.py` | `ArticleAdapter`, its loader and required receiver fields |
| `manifest.py`, `management/` | manifest build and push to SemanticHub |
| `settings.py` | typed access to `SEMANTICHUB_*` settings |
| `models.py` | `IngestReceipt`, `IngestPublication`, `IngestPublicationPage`, `IngestDelivery` |

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
  4xx (`400` malformed, `422` unsupported mode or missing required field).
  An unhandled `ValidationError`, `DataError` or `KeyError` reachable from
  the payload means endless retries.
- **Authentication first.** Nothing reads `request.data` or touches the
  database before `is_authorized`. Secret comparisons use
  `hmac.compare_digest`. The manifest push never raises inside request
  handling and never logs `SEMANTICHUB_AGENT_TOKEN`.
- **Idempotency.** Replays with the same `Idempotency-Key` (v3) or
  `X-SH-Delivery` (v5) never create pages; a stale or reused `revision`
  answers 409 with the stored revision; the `IntegrityError` retry paths
  still converge when two deliveries race; `test_delivery` never writes.
- **Transactions.** Guarded rows are read with `select_for_update` inside the
  same `transaction.atomic()`; new network calls stay outside transactions
  where the flow allows it.
- **Database limits.** Payload strings are bounded before they reach a
  `max_length` column; required Wagtail fields (`title`, `slug`) cannot end
  up empty; sibling slugs stay unique.
- **Publishing.** Pages are created unpublished; direct publish needs the
  inactive `semantichub` account's `publish` permission; payload fields never
  widen what the site owner configured; a live page changes only through
  `apply_policy`.
- **Public API.** Changes to adapters, `Article`, the manifest shape,
  settings names or response shapes need a CHANGELOG entry and a README
  update.
