# semantichub-wagtail

[![CI](https://github.com/krystianmagdziarz/semantichub-wagtail/actions/workflows/ci.yml/badge.svg)](https://github.com/krystianmagdziarz/semantichub-wagtail/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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

## Features

- One `POST` endpoint for both the v3 article payload and the v5 payload,
  which carries a result identity, a revision and one or more languages.
  Every language becomes its own page.
- Shared bearer token and HMAC request signatures.
- New pages are created unpublished and submitted to your Wagtail moderation
  workflow. Draft-only and direct-publish policies are available, and direct
  publish also needs an explicit Wagtail `publish` permission, so a webhook
  alone can never put content live.
- Redeliveries are idempotent: a v3 redelivery with the same
  `Idempotency-Key` updates the page it created through a new revision
  instead of creating a duplicate, and a v5 delivery carries a revision
  number that can never go backwards.
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
| `get_parent(article)` | yes | every new page, once per language | return the parent page, or `None` to answer `500` so SemanticHub retries |
| `build(article)` | yes | every new page, once per language | return an unsaved page instance; the package sets the slug, adds it under the parent and saves a revision |
| `update(page, article)` | yes | a redelivery of a known `Idempotency-Key` (v3), a newer revision of a known result (v5), or the first v5 delivery of a result whose page was created before v5 and is adopted for the source language | copy fields onto `page` without saving |
| `apply_tags(page, tags)` | no | when the delivery has tags | attach the tag names to `page` |

`article` is a `semantichub_wagtail.payload.Article`:

| Attribute | Type | Source |
| --- | --- | --- |
| `title` | `str` | v5: `locales.<lang>.title`; v3: `title`, falling back to the topic name; at most 255 characters |
| `lead` | `str` | v5: `locales.<lang>.lead`; v3: `lead`, falling back to the topic description |
| `body` | `str` | v5: `locales.<lang>.body_html` sanitised, falling back to `locales.<lang>.body` rendered from Markdown; v3: `llm_response` rendered to safe HTML |
| `language` | `str \| None` | the language code of this page (v5); `None` for a v3 delivery |
| `seo_description` | `str` | v5: `locales.<lang>.seo_description`, at most 255 characters; empty for v3 |
| `tags` | `list[str]` | `tags`, falling back to the topic's semantic groups, at most 10 |
| `publish_date` | `date` | `published_at` or `executed_at`, falling back to today |
| `publish_mode` | `str \| None` | `publish_mode` as sent |
| `cover` | `Image \| None` | the downloaded `image.url`, shared by every language of a delivery |
| `slug_base` | `str` | v5: slugified `locales.<lang>.slug` or title; v3: slugified `url_slug` or topic name |
| `cluster` | `dict` | the first entry of `clusters` |
| `data` | `dict` | the raw payload |

Use `article.language` in `get_parent` to put each language under its own
index page. All adapter calls for one delivery run inside a single database
transaction, so an exception leaves no half-created page behind.

## Publications and pages

A v5 delivery is stored as an `IngestPublication` keyed by `result_id`. It
holds the stored `revision`, the payload hash and one `IngestPublicationPage`
per language:

```python
from semantichub_wagtail.models import IngestPublication

publication = IngestPublication.objects.get(result_id=result_id)
english_page = publication.page_for("en")  # None when that language has no page
for link in publication.pages.all():  # one IngestPublicationPage per language
    print(link.language_code, link.page_id)
```

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `SEMANTICHUB_INGEST_ADAPTER` | required | Dotted path to your `ArticleAdapter` subclass. |
| `SEMANTICHUB_INGEST_LANGUAGES` | `("pl", "en")` | Language codes accepted in a v5 delivery. A language outside this list answers `400`. |
| `SEMANTICHUB_INGEST_TOKEN` | `""` | Shared bearer token checked against `Authorization: Bearer <token>`. |
| `SEMANTICHUB_INGEST_SECRET` | `""` | HMAC secret for signed requests. |
| `SEMANTICHUB_INGEST_PUBLISH_MODE` | `"moderation"` | Default for accepted articles: `moderation`, `draft` or `publish`. |

With neither the token nor the secret set, every request is rejected. When
both are set, either one authorizes a delivery. Use long random
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

Every page goes through the policy, in every language of a v5 delivery.
Redeliveries of a page that is already live never touch the published
version; the change lands in a new revision that goes through the same
policy.

## Endpoint

### `POST <prefix>/inbound/`

Accepts every SemanticHub delivery, authorized by the bearer token or an
HMAC signature. The payload decides the path:

- **Without `result_id` (v2 and v3).** One page per delivery, keyed by the
  `Idempotency-Key` header. A known key updates its page; a delivery without
  the header always creates a new page.
- **With `result_id` (v5).** One publication per `result_id`. The request
  needs an `X-SH-Delivery` header, or `Idempotency-Key` as a fallback, of at
  most 255 characters. `locales` holds one to N languages, each from
  `SEMANTICHUB_INGEST_LANGUAGES` (by default `pl` and `en`). The source
  language comes from `source_lang` (or `pair_source_lang`). When neither is
  sent and `locales` holds exactly one language, that language is the source.
  When `locales` is missing or empty and no source language is sent, the page
  gets the default language: the language of the Wagtail default `Locale` if
  it is in `SEMANTICHUB_INGEST_LANGUAGES`, otherwise the first entry of that
  setting. Each language gets its own page, and
  each page goes through the publish policy. A delivery without `locales`
  creates one page from `llm_response` under the source language. A page
  created before v5 for the same result is adopted instead of duplicated.

The receiver never requires a language pair; whether both languages are sent
is the sender's decision.

Responses for v2 and v3:

| Status | Body | When |
| --- | --- | --- |
| `201` | `{"status": "created", "page_id", "slug", "outcome", "live"}` | a new page was created |
| `200` | `{"status": "updated", "page_id", "slug", "outcome", "live"}` | redelivery of a known `Idempotency-Key` |
| `200` | `{"status": "duplicate", "page_id"}` | the page for that key was deleted, or a concurrent delivery with the same key won |
| `400` | `{"detail"}` | invalid JSON, not a generated article, or an `Idempotency-Key` over 255 characters |
| `401` | `{"detail"}` | missing or invalid credentials |
| `415` | `{"detail"}` | the body is not `application/json` |
| `500` | `{"detail"}` | the adapter returned no parent page |

Responses for v5:

| Status | Body | When |
| --- | --- | --- |
| `201` | `{"status": "published", "result_id", "revision", "pages"}` | the first delivery of a result |
| `200` | `{"status": "updated", "result_id", "revision", "pages"}` | a newer revision of a known result |
| `200` | `{"status": "duplicate", "result_id", "revision"}` | a replayed delivery id, or the stored revision redelivered with identical bytes |
| `400` | `{"detail"}` | invalid payload, a language outside `SEMANTICHUB_INGEST_LANGUAGES`, `revision` outside 1 to 2^31-1, or a missing or overlong delivery id |
| `401` | `{"detail"}` | missing or invalid credentials |
| `415` | `{"detail"}` | the body is not `application/json` |
| `409` | `{"detail", "result_id", "revision"}` | an older revision than the stored one, the stored revision with different content, or a delivery id reused with a different payload; `revision` is the stored one |
| `500` | `{"detail"}` | the adapter returned no parent page for one of the languages; nothing is saved |

`pages` maps each language code to `{"page_id", "slug", "outcome", "live"}`.
`outcome` is one of `moderation`, `draft` or `published`. SemanticHub bumps
`revision` on a 409 that carries `revision` and retries.

Payload fields read by the package:

| Field | Notes |
| --- | --- |
| `mode` | must be `article` |
| `llm_response` | article body, markdown (v3) or HTML (v2); required |
| `clusters` | non-empty list; the first entry provides `name`, `description`, `url_slug` and `semantic_groups` |
| `title`, `lead` | optional, fall back to the topic |
| `tags` | optional list of strings |
| `executed_at`, `published_at` | optional ISO 8601 timestamps |
| `publish_mode` | optional, `moderation`, `draft` or `publish` |
| `image.url` | optional HTTPS cover URL |
| `result_id` | v5: UUID of the result chain; its presence selects the v5 path |
| `revision` | v5: integer from 1 to 2^31-1, default 1 |
| `source_lang` | v5: source language code (`pair_source_lang` is accepted as an alias) |
| `locales` | v5: optional object keyed by language code; each entry needs `title` and may carry `slug`, `lead`, `body`, `body_html` and `seo_description` |
| `workflow_execution` | v5: id of the delivered result, used to adopt a page created before v5 |

## Security model

- **Signatures.** `X-SH-Signature` is `sha256=` followed by the hex
  HMAC-SHA256 of `X-SH-Timestamp`, a literal `.`, and the raw request body,
  keyed with `SEMANTICHUB_INGEST_SECRET`. The timestamp is Unix seconds and
  must be within 5 minutes of the server clock. All comparisons are
  constant-time.
- **Replays.** A signed request can be replayed inside the 5 minute window.
  A v5 delivery absorbs that through its delivery id and the stored payload
  hash per revision. A v3 replay with the same `Idempotency-Key` only saves
  another revision of the same page, while a v3 delivery without that header
  always creates a new page, so its replay adds a duplicate draft.
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
