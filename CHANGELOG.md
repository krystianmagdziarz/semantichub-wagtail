# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Branch coverage reporting with a 95% gate, uploaded to Codecov from CI.
- CodeQL analysis, Dependabot updates, pre-commit hooks, issue and pull
  request templates, `SECURITY.md`, `CONTRIBUTING.md` and GitHub Copilot
  review instructions.

### Changed

- Tests treat warnings as errors and run with strict pytest markers and config.

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

[Unreleased]: https://github.com/krystianmagdziarz/semantichub-wagtail/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/krystianmagdziarz/semantichub-wagtail/releases/tag/v0.1.0
