import hashlib
import hmac
import json
import time
import uuid

import pytest
from rest_framework import status

from semantichub_wagtail.models import IngestDelivery, IngestPublication
from tests.testapp.models import ArticlePage

PAIR_URL = "/api/semantichub/pair/"
SECRET = "pair-secret"


@pytest.fixture(autouse=True)
def _pair_settings(settings):
    settings.SEMANTICHUB_INGEST_SECRET = SECRET
    settings.SEMANTICHUB_INGEST_PAIR_ADAPTER = "tests.testapp.adapter.ExamplePairAdapter"


def make_pair_payload(**overrides):
    payload = {
        "result_id": "6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b",
        "revision": 1,
        "published_at": "2026-09-20T10:00:00+00:00",
        "locales": {
            "en": {
                "title": "Passive income explained",
                "slug": "passive-income-explained",
                "lead": "A short guide.",
                "body": "## Intro\n\nBody text.\n",
                "seo_description": "Guide to passive income.",
            },
            "pl": {
                "title": "Dochod pasywny bez tajemnic",
                "slug": "dochod-pasywny-bez-tajemnic",
                "lead": "Krotki przewodnik.",
                "body": "## Wstep\n\nTresc.\n",
                "seo_description": "Przewodnik po dochodzie pasywnym.",
            },
        },
    }
    payload.update(overrides)
    return payload


def post_pair(client, payload=None, delivery_id="dl-1", secret=SECRET, body=None):
    body = (
        body
        if body is not None
        else json.dumps(payload if payload is not None else make_pair_payload()).encode()
    )
    headers = {}
    if secret is not None:
        timestamp = str(int(time.time()))
        digest = hmac.new(
            secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        headers["HTTP_X_SH_TIMESTAMP"] = timestamp
        headers["HTTP_X_SH_SIGNATURE"] = f"sha256={digest}"
    if delivery_id is not None:
        headers["HTTP_X_SH_DELIVERY"] = delivery_id
    return client.post(PAIR_URL, body, content_type="application/json", **headers)


@pytest.mark.django_db
class TestPairAuth:
    def test_unsigned_request_is_rejected(self, api_client, article_index):
        response = post_pair(api_client, secret=None)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_secret_is_rejected(self, api_client, article_index):
        response = post_pair(api_client, secret="other")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_bearer_token_does_not_authorize_pairs(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = "token"
        response = api_client.post(
            PAIR_URL,
            json.dumps(make_pair_payload()).encode(),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token",
            HTTP_X_SH_DELIVERY="dl-1",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPairValidation:
    def test_invalid_json_returns_400(self, api_client, article_index):
        response = post_pair(api_client, body=b"not json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_result_id_returns_400(self, api_client, article_index):
        payload = make_pair_payload()
        del payload["result_id"]
        response = post_pair(api_client, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_zero_revision_returns_400(self, api_client, article_index):
        response = post_pair(api_client, make_pair_payload(revision=0))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_locale_returns_400(self, api_client, article_index):
        payload = make_pair_payload()
        del payload["locales"]["pl"]
        response = post_pair(api_client, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_delivery_header_returns_400(self, api_client, article_index):
        response = post_pair(api_client, delivery_id=None)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPairDelivery:
    def test_delivery_creates_publication_and_pages(self, api_client, article_index):
        response = post_pair(api_client)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "published"
        publication = IngestPublication.objects.get()
        assert str(publication.result_id) == "6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b"
        assert publication.revision == 1
        assert publication.en_page is not None
        assert publication.pl_page is not None
        assert ArticlePage.objects.count() == 2
        assert IngestDelivery.objects.filter(delivery_id="dl-1").exists()

    def test_replayed_delivery_is_a_duplicate(self, api_client, article_index):
        post_pair(api_client, delivery_id="dl-1")
        response = post_pair(api_client, delivery_id="dl-1")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "duplicate"
        assert ArticlePage.objects.count() == 2

    def test_delivery_id_reuse_with_other_payload_conflicts(self, api_client, article_index):
        post_pair(api_client, delivery_id="dl-1")
        other = make_pair_payload(result_id=str(uuid.uuid4()))
        response = post_pair(api_client, other, delivery_id="dl-1")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_new_revision_updates_the_pair(self, api_client, article_index):
        post_pair(api_client, delivery_id="dl-1")
        updated = make_pair_payload(revision=2)
        updated["locales"]["pl"]["title"] = "Poprawiony tytul"
        updated["locales"]["en"]["title"] = "Corrected title"
        response = post_pair(api_client, updated, delivery_id="dl-2")
        assert response.status_code == status.HTTP_201_CREATED
        publication = IngestPublication.objects.get()
        assert publication.revision == 2
        assert ArticlePage.objects.count() == 2
        titles = set(ArticlePage.objects.values_list("title", flat=True))
        assert titles == {"Poprawiony tytul", "Corrected title"}

    def test_stale_revision_conflicts(self, api_client, article_index):
        post_pair(api_client, make_pair_payload(revision=2), delivery_id="dl-1")
        response = post_pair(api_client, make_pair_payload(revision=1), delivery_id="dl-2")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["revision"] == 2

    def test_same_revision_redelivery_is_a_duplicate(self, api_client, article_index):
        post_pair(api_client, delivery_id="dl-1")
        response = post_pair(api_client, delivery_id="dl-2")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "duplicate"
        assert IngestDelivery.objects.count() == 2
        assert ArticlePage.objects.count() == 2

    def test_same_revision_with_other_payload_conflicts(self, api_client, article_index):
        post_pair(api_client, delivery_id="dl-1")
        changed = make_pair_payload()
        changed["locales"]["pl"]["title"] = "Inny tytul"
        response = post_pair(api_client, changed, delivery_id="dl-2")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["revision"] == 1
