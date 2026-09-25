# semantichub-wagtail

[![CI](https://github.com/krystianmagdziarz/semantichub-wagtail/actions/workflows/ci.yml/badge.svg)](https://github.com/krystianmagdziarz/semantichub-wagtail/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

<img width="1600" height="395" alt="semantichub-logo" src="https://github.com/user-attachments/assets/62a8d7fe-19c6-4737-bedb-a13ba09ec8b2" />

Wagtail integration for [SemanticHub](https://semantichub.app). It receives
finished articles from SemanticHub over webhooks and turns them into Wagtail
pages that wait for editorial approval. Nothing goes live behind the editor's
back.

## What SemanticHub is

SemanticHub watches the sources you care about (news portals, RSS feeds,
industry sites), filters incoming articles against the goals you define,
clusters related pieces into topics and writes article drafts from those
topics through configurable workflows. When a draft is accepted, SemanticHub
delivers it to your site as a webhook. This package is the receiving end of
that delivery for Wagtail sites.

<img width="2047" height="1158" alt="semantichub-dashboard" src="https://github.com/user-attachments/assets/3688f962-5be6-4229-97b8-37b32923e30c" />

## Features

- Two `POST` endpoints: one for single articles, one for signed
  language pairs (English and Polish versions of the same article).
- Shared bearer token and HMAC request signatures.
- New pages are created unpublished and submitted to your Wagtail moderation
  workflow. Draft-only and direct-publish policies are available, and direct
  publish also needs an explicit Wagtail `publish` permission, so a webhook
  alone can never put content live.
- Redeliveries are idempotent: the same `Idempotency-Key` updates the page
  it created through a new revision instead of creating a duplicate, and
  pair deliveries carry a revision number that can never go backwards.
- Markdown bodies are rendered with raw HTML escaped; HTML bodies are
  sanitised against an allowlist.
- Cover images are downloaded into the Wagtail image library from public
  HTTPS hosts only, with size, time and redirect limits, deduplicated by
  content hash. A broken image never fails a delivery.
- Your page models stay yours: a small adapter decides where pages land and
  how fields map.

## Requirements

- Python 3.10+
- Django 5.2+
- Wagtail 8.0+
- Django REST framework (installed with Wagtail)

## Installation

```bash
pip install git+https://github.com/krystianmagdziarz/semantichub-wagtail
```

Add the app and its routes:

```python
INSTALLED_APPS = [
    # ...
    "semantichub_wagtail",
]
```

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("api/semantichub/", include("semantichub_wagtail.urls")),
]
```

Configure the adapter and at least one credential, then run migrations:

```python
SEMANTICHUB_INGEST_ADAPTER = "blog.semantichub.BlogArticleAdapter"
SEMANTICHUB_INGEST_SECRET = env("SEMANTICHUB_INGEST_SECRET")
```

```bash
python manage.py migrate semantichub_wagtail
```

In SemanticHub, point the goal's HTTP action at
`https://your-site.example/api/semantichub/inbound/` and use the same secret.

## Article adapter

`SEMANTICHUB_INGEST_ADAPTER` points at a subclass of
`semantichub_wagtail.adapters.ArticleAdapter`:

```python
from semantichub_wagtail.adapters import ArticleAdapter

from blog.models import BlogIndexPage, BlogPostPage


class BlogArticleAdapter(ArticleAdapter):
    def get_parent(self, article):
        return BlogIndexPage.objects.first()

    def build(self, article):
        return BlogPostPage(
            title=article.title,
            excerpt=article.lead,
            body=article.body,
            publish_date=article.publish_date,
            cover_image=article.cover,
        )

    def update(self, page, article):
        page.title = article.title
        page.excerpt = article.lead
        page.body = article.body
        page.publish_date = article.publish_date
        if article.cover is not None:
            page.cover_image = article.cover

    def apply_tags(self, page, tags):
        page.tags.set(tags)
```

| Method | Required | Called with | Must |
| --- | --- | --- | --- |
| `get_parent(article)` | yes | every new delivery | return the parent page, or `None` to answer `500` so SemanticHub retries |
| `build(article)` | yes | every new delivery | return an unsaved page instance; the package sets the slug, adds it under the parent and saves a revision |
| `update(page, article)` | yes | a redelivery of a known `Idempotency-Key` | copy fields onto `page` without saving |
| `apply_tags(page, tags)` | no | when the delivery has tags | attach the tag names to `page` |

`article` is a `semantichub_wagtail.payload.Article`:

| Attribute | Type | Source |
| --- | --- | --- |
| `title` | `str` | `title`, falling back to the topic name, at most 255 characters |
| `lead` | `str` | `lead`, falling back to the topic description |
| `body` | `str` | `llm_response` rendered to safe HTML |
| `tags` | `list[str]` | `tags`, falling back to the topic's semantic groups, at most 10 |
| `publish_date` | `date` | `executed_at`, falling back to today |
| `publish_mode` | `str \| None` | `publish_mode` as sent |
| `cover` | `Image \| None` | the downloaded `image.url` |
| `slug_base` | `str` | slugified `url_slug` or topic name |
| `cluster` | `dict` | the first entry of `clusters` |
| `data` | `dict` | the raw payload |

All adapter calls for one delivery run inside a single database transaction,
so an exception leaves no half-created page behind.

## Pair adapter

The pair endpoint hands both language versions to
`SEMANTICHUB_INGEST_PAIR_ADAPTER`, a subclass of
`semantichub_wagtail.adapters.PairAdapter` with one method:

```python
from semantichub_wagtail.adapters import PairAdapter
from semantichub_wagtail.models import IngestPublication


class BlogPairAdapter(PairAdapter):
    def upsert(self, publication, data, revision):
        publication = publication or IngestPublication()
        publication.en_page = ...  # create or update from data["locales"]["en"]
        publication.pl_page = ...  # create or update from data["locales"]["pl"]
        return publication
```

`publication` is the stored `IngestPublication` for the delivery's
`result_id`, or `None` the first time. Return it (saved or not); the package
then sets `result_id`, `revision`, `payload_hash` and `image_url` and saves it.
The adapter decides how pages are published and may keep the downloaded
cover in `publication.image`; compare `publication.image_url` with the
incoming `data["image"]["url"]` to skip downloading the same cover twice.
`semantichub_wagtail.images.fetch_image(data["image"], title)` applies the
same download rules as the article endpoint. `upsert` runs inside the
transaction that holds the row lock, so raising an exception rolls everything
back and answers `500`.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `SEMANTICHUB_INGEST_ADAPTER` | required for `inbound/` | Dotted path to your `ArticleAdapter` subclass. |
| `SEMANTICHUB_INGEST_PAIR_ADAPTER` | required for `pair/` | Dotted path to your `PairAdapter` subclass. |
| `SEMANTICHUB_INGEST_TOKEN` | `""` | Shared bearer token checked against `Authorization: Bearer <token>`. Article endpoint only. |
| `SEMANTICHUB_INGEST_SECRET` | `""` | HMAC secret for signed requests. Required by the pair endpoint. |
| `SEMANTICHUB_INGEST_PUBLISH_MODE` | `"moderation"` | Default for accepted articles: `moderation`, `draft` or `publish`. |

With neither the token nor the secret set, every request is rejected. When
both are set, either one authorizes an article delivery. Use long random
values for both, for example `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Publish policy

Every delivery is attributed to a `semantichub` system account, created
inactive and without a usable password. The mode comes from the payload's
`publish_mode` when present (unknown values fall back to `moderation`),
otherwise from `SEMANTICHUB_INGEST_PUBLISH_MODE`.

- `moderation` saves a revision and starts the page's Wagtail workflow. When
  no workflow applies, the page stays a draft.
- `draft` saves a revision and stops.
- `publish` publishes the revision only if the system account is active and
  holds the `publish` permission on the target branch. Grant both in the
  Wagtail admin to opt in; without them the delivery falls back to
  moderation.

Redeliveries of a page that is already live never touch the published
version; the change lands in a new revision that goes through the same
policy.

## Endpoints

### `POST <prefix>/inbound/`

Accepts the SemanticHub article payload (versions 2 and 3). Authorized by
the bearer token or an HMAC signature.

| Status | Body | When |
| --- | --- | --- |
| `201` | `{"status": "created", "page_id", "slug", "outcome", "live"}` | a new page was created |
| `200` | `{"status": "updated", "page_id", "slug", "outcome", "live"}` | redelivery of a known `Idempotency-Key` |
| `200` | `{"status": "duplicate", "page_id"}` | the page for that key was deleted, or a concurrent delivery with the same key won |
| `400` | `{"detail"}` | invalid JSON, not a generated article, or an `Idempotency-Key` over 255 characters |
| `401` | `{"detail"}` | missing or invalid credentials |
| `415` | `{"detail"}` | the body is not `application/json` |
| `500` | `{"detail"}` | the adapter returned no parent page |

`outcome` is one of `moderation`, `draft` or `published`.

Payload fields read by the package:

| Field | Notes |
| --- | --- |
| `mode` | must be `article` |
| `llm_response` | article body, markdown (v3) or HTML (v2); required |
| `clusters` | non-empty list; the first entry provides `name`, `description`, `url_slug` and `semantic_groups` |
| `title`, `lead` | optional, fall back to the topic |
| `tags` | optional list of strings |
| `executed_at` | optional ISO 8601 timestamp |
| `publish_mode` | optional, `moderation`, `draft` or `publish` |
| `image.url` | optional HTTPS cover URL |

### `POST <prefix>/pair/`

Accepts a signed delivery carrying both language versions of one result.
Only HMAC signatures authorize it; the bearer token never does.

```json
{
  "result_id": "6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b",
  "revision": 2,
  "published_at": "2026-09-20T10:00:00+00:00",
  "image": {"url": "https://cdn.example.com/cover.jpg", "alt": "Cover"},
  "locales": {
    "en": {"title": "...", "slug": "...", "lead": "...", "body": "...", "seo_description": "..."},
    "pl": {"title": "...", "slug": "...", "lead": "...", "body": "...", "seo_description": "..."}
  }
}
```

The package validates `result_id` (a UUID), `revision` (an integer from 1),
`locales.en` and `locales.pl` (objects) and `image` (an object, optional).
Everything else is passed to the adapter untouched.

| Status | Body | When |
| --- | --- | --- |
| `201` | `{"status": "published", "result_id", "revision"}` | the adapter ran for a new result or a newer revision |
| `200` | `{"status": "duplicate", "result_id"}` | a replayed `X-SH-Delivery`, or the current revision redelivered with identical bytes |
| `400` | `{"detail"}` | invalid payload, or a missing or overlong `X-SH-Delivery` header |
| `401` | `{"detail"}` | missing or invalid signature |
| `409` | `{"detail", "revision"}` | an older revision than the stored one, or the stored revision with different content; `revision` is the stored one |
| `409` | `{"detail"}` | an `X-SH-Delivery` id reused with a different payload |

## Security model

- **Signatures.** `X-SH-Signature` is `sha256=` followed by the hex
  HMAC-SHA256 of `X-SH-Timestamp`, a literal `.`, and the raw request body,
  keyed with `SEMANTICHUB_INGEST_SECRET`. The timestamp is Unix seconds and
  must be within 5 minutes of the server clock. All comparisons are
  constant-time.
- **Replays.** A signed request can be replayed inside the 5 minute window.
  The pair endpoint absorbs that through `X-SH-Delivery` and the stored
  payload hash per revision. On the article endpoint a replay with the same
  `Idempotency-Key` only saves another revision of the same page, while a
  delivery without that header always creates a new page, so its replay adds
  a duplicate draft.
- **Isolation from project settings.** The views use their own
  authentication, JSON-only parsing and no throttling, so project-wide
  `REST_FRAMEWORK` defaults (session or JWT authentication, form parsers,
  anonymous throttles) do not apply to them. Request size is bounded by
  Django's `DATA_UPLOAD_MAX_MEMORY_SIZE`.
- **Content.** Markdown is rendered with raw HTML escaped and unsafe link
  schemes dropped. HTML bodies are cleaned with
  [nh3](https://github.com/messense/nh3): scripts, iframes, event handlers,
  inline styles and `javascript:` URLs are removed.
- **Cover images.** Only `https` URLs without credentials are fetched. The
  host is resolved first and refused unless every address is public; the
  connection is then pinned to the checked address, so DNS rebinding cannot
  redirect it. Redirects are followed manually (at most three, each hop
  checked the same way). Bodies are streamed with a 12 MiB and 15 second cap,
  and only JPEG, PNG, GIF, WebP and AVIF are accepted, both by content type
  and by the decoded file. SVG is never stored.
- **Service account.** The `semantichub` account is created inactive with an
  unusable password and holds no permissions until you grant them.
- **Errors.** Response bodies carry short, fixed messages; unexpected errors
  propagate to Django, which answers `500` without details when `DEBUG` is
  off. SemanticHub retries `5xx` responses.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The test suite runs against a throwaway Wagtail project in `tests/` with
example adapters in `tests/testapp`.

## License

[MIT](LICENSE)
