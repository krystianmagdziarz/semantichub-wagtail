---
applyTo: "tests/**/*.py"
---

- Plain `pytest` classes with `@pytest.mark.django_db`; reuse the
  `api_client` and `article_index` fixtures from `tests/conftest.py` and the
  `make_payload` / `make_pair_payload` builders.
- Assert outcomes (status code, response body, page state, revisions,
  workflow state, stored rows), not only that code ran.
- Never hit the network: monkeypatch `semantichub_wagtail.images._download`
  or `_client`.
- Race and retry paths (`IntegrityError`, `select_for_update`) get a test that
  forces the path, as `tests/test_pair.py` does.
- Warnings fail the suite (`filterwarnings = ["error"]`); fix the cause rather
  than silencing it.
