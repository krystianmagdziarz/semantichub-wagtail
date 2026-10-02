import json
from pathlib import Path

import pytest
from django.core.cache import cache
from rest_framework import status
from wagtail.models import Site

from semantichub_wagtail.models import IngestPublication
from tests.test_inbound import grant_publish
from tests.test_v5 import post_v5
from tests.testapp.models import ArticlePage

CONTRACT_DIR = Path(__file__).parent / "contract" / "payload-v5"
CASES = sorted(
    (
        json.loads(path.read_text(encoding="utf-8"))
        for path in (CONTRACT_DIR / "cases").glob("*.json")
    ),
    key=lambda case: case["name"],
)
HTTP_CASES = [case for case in CASES if "http" in case["receivers"]]


@pytest.fixture(autouse=True)
def _creds(settings):
    settings.SEMANTICHUB_INGEST_TOKEN = "test-ingest-secret"
    settings.SEMANTICHUB_INGEST_SECRET = "pair-secret"


@pytest.fixture(autouse=True)
def _fresh_site_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def site(article_index):
    return Site.objects.create(
        hostname="blog.example.com",
        port=443,
        root_page=article_index,
        is_default_site=False,
    )


def test_contract_copy_has_http_cases():
    assert (CONTRACT_DIR / "schema.json").is_file()
    assert len(HTTP_CASES) >= 5


@pytest.mark.django_db
@pytest.mark.parametrize("case", HTTP_CASES, ids=[case["name"] for case in HTTP_CASES])
def test_contract_case(case, api_client, article_index, article_index_en):
    payload = case["payload"]
    expect = case["expect"]

    if expect.get("accepted") is False:
        r = post_v5(api_client, payload, delivery_id=f"{case['name']}-1")
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.content
        assert r.json() == {"detail": "unsupported"}
        assert not ArticlePage.objects.exists()
        return

    first_page_id = None
    if expect.get("updates_revision_1_of"):
        first = {k: v for k, v in payload.items() if k not in ("parent_execution", "new_articles")}
        first["revision"] = 1
        first["event"] = "workflow.action"
        r = post_v5(api_client, first, delivery_id=f"{case['name']}-rev1")
        assert r.status_code == status.HTTP_201_CREATED, r.content
        first_page_id = r.json()["page_id"]

    r = post_v5(api_client, payload, delivery_id=f"{case['name']}-1")
    assert r.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED), r.content
    body = r.json()
    assert body["result_id"] == expect["result_id"]
    assert body["revision"] == expect["revision"]
    assert body["post_status"] in ("draft", "pending")
    if first_page_id is not None:
        assert body["page_id"] == first_page_id

    publication = IngestPublication.objects.get(result_id=expect["result_id"])
    assert publication.revision == expect["revision"]
    page = publication.page_for(payload["source_lang"]).specific
    assert not page.live
    assert page.title == expect["title"]
    for needle in expect["content_contains"]:
        assert needle in page.body
    for needle in expect["content_excludes"]:
        assert needle not in page.body
    for needle in expect.get("content_once", []):
        assert page.body.count(needle) == 1
    assert bool(page.cover_image) is expect["image"]

    translation = expect.get("translation")
    if translation:
        translated = publication.page_for(translation["lang"]).specific
        assert translated.title == translation["title"]
        for needle in translation["content_contains"]:
            assert needle in translated.body


@pytest.mark.django_db
class TestPublishedLocation:
    def test_draft_reports_url_and_pending_or_draft(self, api_client, site):
        case = next(c for c in HTTP_CASES if c["name"] == "01-article-minimal")
        r = post_v5(api_client, case["payload"], delivery_id="loc-1")
        assert r.status_code == status.HTTP_201_CREATED, r.content
        body = r.json()
        page = ArticlePage.objects.get(id=body["page_id"])
        assert body["url"] == page.full_url
        assert body["url"].startswith("https://blog.example.com/")
        assert body["post_status"] in ("draft", "pending")

    def test_published_page_reports_publish(self, api_client, site, article_index):
        grant_publish(article_index)
        case = next(c for c in HTTP_CASES if c["name"] == "01-article-minimal")
        payload = dict(case["payload"], publish_mode="publish")
        r = post_v5(api_client, payload, delivery_id="loc-2")
        assert r.status_code == status.HTTP_201_CREATED, r.content
        body = r.json()
        assert body["post_status"] == "publish"
        assert body["url"].startswith("https://blog.example.com/")

    def test_page_outside_any_site_omits_url(self, api_client, article_index):
        case = next(c for c in HTTP_CASES if c["name"] == "01-article-minimal")
        r = post_v5(api_client, case["payload"], delivery_id="loc-3")
        assert r.status_code == status.HTTP_201_CREATED, r.content
        assert "url" not in r.json()
