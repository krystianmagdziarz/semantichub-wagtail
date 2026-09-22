# semantichub-wagtail

Wagtail integration for [SemanticHub](https://semantichub.app). It receives
finished articles from SemanticHub over webhooks and turns them into Wagtail
pages that wait for editorial approval — nothing goes live behind the
editor's back.

## What SemanticHub is

SemanticHub watches the sources you care about (news portals, RSS feeds,
industry sites), filters incoming articles against the goals you define,
clusters related pieces into topics and writes article drafts from those
topics through configurable workflows. When a draft is accepted, SemanticHub
delivers it to your site as a webhook. This package is the receiving end of
that delivery for Wagtail sites.

## What this package does

- Exposes a single `POST` endpoint for SemanticHub deliveries.
- Authenticates every request with a shared bearer token, an HMAC request
  signature, or both.
- Creates an unpublished page from each delivery and submits it to your
  Wagtail moderation workflow. Draft-only and direct-publish policies are
  available, and direct publish additionally requires an explicit Wagtail
  `publish` permission — a webhook alone can never put content live.
- Handles redeliveries: the same `Idempotency-Key` updates the existing page
  in place (through a new revision, never by overwriting the live version)
  instead of creating duplicates.
- Renders the markdown body to HTML with raw HTML escaped, so model output
  cannot inject markup. Deliveries that already contain HTML are passed
  through unchanged.
- Downloads the cover image into the Wagtail image library — HTTPS sources
  only, with size and time limits, deduplicated by content hash. A broken
  image never fails the delivery.
- Applies tags from the delivery, falling back to the topic's semantic
  groups.

The package does not know your page models. You describe them once in a small
adapter and keep full control over where pages land and how fields map.

## Installation

```bash
pip install git+https://github.com/krystianmagdziarz/semantichub-wagtail
```

Add the app and route:

```python
INSTALLED_APPS = [
    # ...
    "semantichub_wagtail",
]
```

```python
urlpatterns = [
    # ...
    path("api/semantichub/", include("semantichub_wagtail.urls")),
]
```

Run migrations:

```bash
python manage.py migrate semantichub_wagtail
```

## Adapter

Point `SEMANTICHUB_INGEST_ADAPTER` at a class describing your page models:

```python
from semantichub_wagtail.adapters import ArticleAdapter
from myapp.models import BlogIndexPage, BlogPostPage


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

`article` is a parsed delivery with `title`, `lead`, `body` (rendered HTML),
`tags`, `publish_date`, `cover` (a `wagtailimages.Image` or `None`),
`slug_base`, `cluster` (the topic dict) and `data` (the raw payload). The
package picks a slug that is unique among the parent's children and keeps the
page unpublished; your adapter only maps fields.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `SEMANTICHUB_INGEST_ADAPTER` | — (required) | Dotted path to your `ArticleAdapter` subclass. |
| `SEMANTICHUB_INGEST_TOKEN` | `""` | Shared bearer token checked against `Authorization: Bearer <token>`. |
| `SEMANTICHUB_INGEST_SECRET` | `""` | HMAC secret for signed requests (`X-SH-Signature` over `X-SH-Timestamp` + body, 5 minute clock skew). |
| `SEMANTICHUB_INGEST_PUBLISH_MODE` | `"moderation"` | What to do with an accepted delivery: `moderation`, `draft` or `publish`. |

At least one of the token or the secret must be configured; with neither set,
every request is rejected. When both are set, either mechanism authorizes a
request. A `publish_mode` sent in the payload (the goal's webhook settings in
SemanticHub) takes precedence over the Django setting; unknown values fall
back to `moderation`.

## Publish policy

Every delivery is attributed to a `semantichub` system account, created
inactive and without a usable password. In `publish` mode the page only goes
live if that account is active and holds the `publish` permission on the
target branch — grant both in the Wagtail admin to opt in. Without them the
delivery falls back to moderation. Redeliveries of an already live page never
touch the published version; changes land in a new revision that goes through
the same policy.

## Endpoint

`POST <prefix>/inbound/` accepts the SemanticHub webhook payload (v2 and v3)
and responds with:

- `201` `{"status": "created", "page_id": ..., "slug": ..., "outcome": ..., "live": ...}`
- `200` `{"status": "updated", ...}` for a redelivery of a known
  `Idempotency-Key`
- `200` `{"status": "duplicate", ...}` when the page for that key was deleted
- `400` for payloads that are not generated articles
- `401` for missing or invalid credentials
- `500` when the adapter cannot provide a parent page (SemanticHub retries
  the delivery)

`outcome` is one of `moderation`, `draft`, `published`.

## Language-pair endpoint

`POST <prefix>/pair/` receives a signed delivery carrying both language
versions of one article (`result_id`, `revision`, `locales.en`, `locales.pl`)
and hands it to a second adapter configured via
`SEMANTICHUB_INGEST_PAIR_ADAPTER` — a class with a single
`upsert(publication, data, revision)` method that creates or updates both
pages and returns the publication record. This endpoint accepts HMAC-signed
requests only; the bearer token never authorizes it.

Transport rules are stricter than on the article endpoint:

- every request must carry an `X-SH-Delivery` id; replaying it returns
  `200 duplicate`, reusing it with a different payload returns `409`
- a `revision` lower than the stored one returns `409`, so late retries can
  never roll a publication back
- redelivering the current revision with an identical payload is a `duplicate`;
  the same revision with different content is a `409`

## Development

```bash
uv sync
uv run pytest
```

The test suite runs against a throwaway Wagtail project in `tests/` with an
example adapter in `tests/testapp`.

## License

MIT
