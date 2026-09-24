# Changelog

## 0.2.0 (2026-09-24)

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

## 0.1.0

- Initial release: inbound endpoint, publish policy, signed pair endpoint.
