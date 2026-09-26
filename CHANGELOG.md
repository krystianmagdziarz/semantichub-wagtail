# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-09-26

- `ArticleAdapter.get_fields()` declares receiver fields: metadata the
  article content doesn't carry (category, department, a "sponsored" flag),
  in the shape SemanticHub's manifest expects. A required field missing
  from `payload["fields"]` (absent, `None`, `""` or an empty list)
  answers `422 {"detail": "missing_field:<key>"}` before any page,
  publication or receipt is saved, including for `test_delivery`.
  `ArticleAdapter.apply_fields(page, fields)` writes the values onto every
  language page of a delivery, at build and at update.
- `semantichub_wagtail.manifest.build_manifest()` reports this
  installation's `blocks` (none: the package never decomposes content into
  blocks), `sections` (`seo`, since `seo_description` is the only value
  routed outside `body`), `features`, `fields` (from the configured
  adapter) and `version`.
- `python manage.py semantichub_push_manifest` sends that manifest to
  `PUT {SEMANTICHUB_API_BASE_URL}/api/goals/{SEMANTICHUB_GOAL_ID}/target-manifest`
  with `Authorization: Bearer {SEMANTICHUB_AGENT_TOKEN}` and
  `User-Agent: SemanticHub-wagtail/<version>`. Missing configuration or a
  failed push exits 1 without raising inside request handling; the command
  is meant for a daily cron or systemd timer, and right after a
  `get_fields()` change.
- `GET <prefix>/manifest/` returns the same manifest under inbound
  authentication, for diagnostics.
- `mode` other than `article` now answers `422 {"detail": "unsupported"}`,
  not `400`.
- New settings: `SEMANTICHUB_API_BASE_URL`, `SEMANTICHUB_AGENT_TOKEN`,
  `SEMANTICHUB_GOAL_ID`, all defaulting to `""` (manifest push is a no-op
  without all three).

## [0.2.0] - 2026-09-25

- One inbound endpoint accepts both the v3 article payload and the v5 payload
  (`result_id`, `revision`, `locales`). The signed language-pair endpoint
  `/pair/` and `PairAdapter` are gone.
- A publication holds one page per language (`IngestPublicationPage`);
  `en_page`/`pl_page` columns are replaced (migration 0004).
- Every page, in every language, goes through the publish policy; the
  rendered body prefers `body_html` and falls back to Markdown.
- `409` responses carry the receiver's current `revision`.
- New setting `SEMANTICHUB_INGEST_LANGUAGES` (default `("pl", "en")`).
- Pages created before v5 are adopted by the delivery's `workflow_execution`
  (the old `Idempotency-Key`) or by the chain root.
- `revision` above 2^31-1 is rejected with 400.
- An empty `title` or `lead` in the source language of a v5 delivery falls
  back like v3 (topic name, topic description); another language with an
  empty `title` takes the source title.
- A delivery with `test_delivery: true` is answered `200` with
  `{"status": "ignored", "reason": "test_delivery"}` and saves nothing.

## [0.1.0]

First public release.

### Added

- `POST inbound/` endpoint for SemanticHub article deliveries (payload v2 and
  v3) with bearer token and HMAC signature authentication.
- `ArticleAdapter` contract for mapping deliveries onto your own page models.
- Moderation, draft and publish policies, with direct publish gated by the
  Wagtail `publish` permission of an inactive `semantichub` service account.
- Idempotent redeliveries through `Idempotency-Key` and `IngestReceipt`.
- `POST pair/` endpoint for signed English and Polish versions of one result,
  with `X-SH-Delivery` deduplication, a revision guard that returns the stored
  revision on `409`, and the `PairAdapter` contract.
- Markdown rendering with raw HTML escaped and nh3 sanitising of HTML bodies.
- Cover image downloads restricted to public HTTPS hosts, pinned to the
  resolved address, with redirect, size, time and file type limits.

[Unreleased]: https://github.com/krystianmagdziarz/semantichub-wagtail/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/krystianmagdziarz/semantichub-wagtail/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/krystianmagdziarz/semantichub-wagtail/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/krystianmagdziarz/semantichub-wagtail/releases/tag/v0.1.0
