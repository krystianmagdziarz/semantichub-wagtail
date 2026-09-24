# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/krystianmagdziarz/semantichub-wagtail/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/krystianmagdziarz/semantichub-wagtail/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/krystianmagdziarz/semantichub-wagtail/releases/tag/v0.1.0
