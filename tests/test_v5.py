import hashlib
import hmac
import json
import time

import pytest
from rest_framework import status

from semantichub_wagtail import views
from semantichub_wagtail.models import (
    IngestDelivery,
    IngestPublication,
    IngestPublicationPage,
)
from tests.test_payload import make_payload, make_v5_payload
from tests.testapp.models import ArticlePage

INBOUND_URL = "/api/semantichub/inbound/"
TOKEN = "test-ingest-secret"
SECRET = "pair-secret"
RESULT_ID = "6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b"


@pytest.fixture(autouse=True)
def _creds(settings):
    settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
    settings.SEMANTICHUB_INGEST_SECRET = SECRET


def post_v5(
    client,
    payload=None,
    delivery_id="dl-1",
    bearer=True,
    signed=False,
    body=None,
    idempotency_key=None,
):
    body = body if body is not None else json.dumps(payload or make_v5_payload()).encode()
    headers = {}
    if bearer:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {TOKEN}"
    if signed:
        ts = str(int(time.time()))
        digest = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        headers["HTTP_X_SH_TIMESTAMP"] = ts
        headers["HTTP_X_SH_SIGNATURE"] = f"sha256={digest}"
    if delivery_id is not None:
        headers["HTTP_X_SH_DELIVERY"] = delivery_id
    if idempotency_key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
    return client.post(INBOUND_URL, body, content_type="application/json", **headers)


@pytest.mark.django_db
class TestV5Delivery:
    def test_test_delivery_is_ignored_without_any_record(self, api_client, article_index):
        r = post_v5(api_client, make_v5_payload(test_delivery=True))
        assert r.status_code == status.HTTP_200_OK, r.content
        assert r.json() == {"status": "ignored", "reason": "test_delivery"}
        assert not IngestPublication.objects.exists()
        assert not IngestPublicationPage.objects.exists()
        assert not IngestDelivery.objects.exists()
        assert not ArticlePage.objects.exists()

    def test_empty_source_title_and_lead_publish_with_cluster_fallbacks(
        self, api_client, article_index
    ):
        data = make_v5_payload(title="", lead="")
        data["locales"] = {"pl": dict(data["locales"]["pl"], title="", lead="", slug="")}
        r = post_v5(api_client, data)
        assert r.status_code == status.HTTP_201_CREATED, r.content
        page = IngestPublication.objects.get(result_id=RESULT_ID).page_for("pl").specific
        assert page.title == "How to build passive income"
        assert page.excerpt == "A practical guide."

    def test_two_languages_create_two_pages_under_their_indexes(
        self, api_client, article_index, article_index_en
    ):
        r = post_v5(api_client)
        assert r.status_code == status.HTTP_201_CREATED, r.content
        body = r.json()
        assert body["status"] == "published" and body["revision"] == 1
        assert set(body["pages"]) == {"pl", "en"}
        pub = IngestPublication.objects.get(result_id=RESULT_ID)
        assert pub.page_for("pl").get_parent().id == article_index.id
        assert pub.page_for("en").get_parent().id == article_index_en.id
        assert pub.page_for("pl").specific.title == "Tytuł PL"
        assert pub.page_for("en").specific.body.startswith("<h2>Intro</h2>")
        assert not pub.page_for("pl").live  # moderation policy, not live
        assert IngestDelivery.objects.filter(delivery_id="dl-1").exists()

    def test_single_language_creates_one_page(self, api_client, article_index):
        data = make_v5_payload()
        data["locales"] = {"pl": data["locales"]["pl"]}
        r = post_v5(api_client, data)
        assert r.status_code == 201
        assert list(r.json()["pages"]) == ["pl"]
        assert IngestPublicationPage.objects.count() == 1

    def test_without_locales_creates_one_page_keyed_by_source_language(
        self, api_client, article_index
    ):
        data = make_v5_payload()
        del data["locales"]
        body = json.dumps(data).encode()
        r = post_v5(api_client, body=body)
        assert r.status_code == 201, r.content
        assert list(r.json()["pages"]) == ["pl"]
        pub = IngestPublication.objects.get()
        assert pub.page_for("pl").specific.title == "Editor title"
        again = post_v5(api_client, body=body, delivery_id="dl-2")
        assert again.status_code == 200 and again.json()["status"] == "duplicate"
        assert ArticlePage.objects.count() == 1

    def test_without_locales_and_source_language_uses_the_default_language(
        self, api_client, article_index
    ):
        data = make_v5_payload(source_lang="", pair_source_lang="")
        del data["locales"]
        r = post_v5(api_client, data)
        assert r.status_code == 201, r.content
        assert list(r.json()["pages"]) == ["pl"]
        assert "" not in set(IngestPublicationPage.objects.values_list("language_code", flat=True))

    def test_signed_without_bearer_is_accepted(self, api_client, article_index, article_index_en):
        r = post_v5(api_client, bearer=False, signed=True)
        assert r.status_code == 201

    def test_no_credentials_is_401(self, api_client, article_index):
        assert post_v5(api_client, bearer=False).status_code == 401

    def test_replay_same_bytes_is_duplicate(self, api_client, article_index, article_index_en):
        body = json.dumps(make_v5_payload()).encode()
        assert post_v5(api_client, body=body).status_code == 201
        r = post_v5(api_client, body=body)
        assert r.status_code == 200 and r.json()["status"] == "duplicate"
        assert r.json()["revision"] == 1
        assert ArticlePage.objects.count() == 2

    def test_same_revision_under_new_delivery_id_is_duplicate_and_recorded(
        self, api_client, article_index, article_index_en
    ):
        body = json.dumps(make_v5_payload()).encode()
        assert post_v5(api_client, body=body).status_code == 201
        r = post_v5(api_client, body=body, delivery_id="dl-2")
        assert r.status_code == 200 and r.json()["status"] == "duplicate"
        assert IngestDelivery.objects.filter(delivery_id="dl-2").exists()
        assert ArticlePage.objects.count() == 2

    def test_idempotency_key_is_accepted_as_delivery_id(
        self, api_client, article_index, article_index_en
    ):
        r = post_v5(api_client, delivery_id=None, idempotency_key="idem-1")
        assert r.status_code == 201
        assert IngestDelivery.objects.filter(delivery_id="idem-1").exists()

    def test_delivery_id_reuse_with_other_payload_is_409(
        self, api_client, article_index, article_index_en
    ):
        assert post_v5(api_client).status_code == 201
        other = make_v5_payload()
        other["locales"]["pl"]["title"] = "Inny"
        r = post_v5(api_client, other, delivery_id="dl-1")
        assert r.status_code == 409 and "delivery" in r.json()["detail"]
        assert r.json()["revision"] == 1 and r.json()["result_id"] == RESULT_ID

    def test_new_revision_updates_pages_and_stale_is_409_with_current_revision(
        self, api_client, article_index, article_index_en
    ):
        assert post_v5(api_client).status_code == 201
        rev2 = make_v5_payload(revision=2)
        rev2["locales"]["pl"]["title"] = "Tytuł PL v2"
        r = post_v5(api_client, rev2, delivery_id="dl-2")
        assert r.status_code == 200 and r.json()["status"] == "updated"
        pub = IngestPublication.objects.get()
        assert pub.revision == 2 and pub.page_for("pl").specific.title == "Tytuł PL v2"
        assert ArticlePage.objects.count() == 2
        stale = post_v5(api_client, make_v5_payload(revision=1), delivery_id="dl-3")
        assert stale.status_code == 409
        assert stale.json() == {
            "detail": "stale revision",
            "result_id": str(pub.result_id),
            "revision": 2,
        }

    def test_new_revision_adds_a_language_that_was_missing(
        self, api_client, article_index, article_index_en
    ):
        data = make_v5_payload()
        data["locales"] = {"pl": data["locales"]["pl"]}
        assert post_v5(api_client, data).status_code == 201
        r = post_v5(api_client, make_v5_payload(revision=2), delivery_id="dl-2")
        assert r.status_code == 200
        assert set(r.json()["pages"]) == {"pl", "en"}
        assert ArticlePage.objects.count() == 2

    def test_same_revision_other_content_is_409_with_revision(
        self, api_client, article_index, article_index_en
    ):
        assert post_v5(api_client).status_code == 201
        other = make_v5_payload()
        other["locales"]["pl"]["lead"] = "Zmieniona zajawka"
        r = post_v5(api_client, other, delivery_id="dl-2")
        assert r.status_code == 409 and r.json()["revision"] == 1

    def test_legacy_receipt_page_is_adopted_as_source_page(self, api_client, article_index):
        legacy = api_client.post(
            INBOUND_URL,
            make_payload(),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
            HTTP_IDEMPOTENCY_KEY=RESULT_ID,
        )
        assert legacy.status_code == 201
        page_id = legacy.json()["page_id"]
        data = make_v5_payload(revision=2)
        data["locales"] = {"pl": data["locales"]["pl"]}
        r = post_v5(api_client, data)
        assert r.status_code == 201 and r.json()["pages"]["pl"]["page_id"] == page_id
        assert ArticlePage.objects.count() == 1
        assert ArticlePage.objects.get().title == "Tytuł PL"

    def test_legacy_page_of_a_later_revision_is_adopted_by_workflow_execution(
        self, api_client, article_index
    ):
        revision_2_result = "0b9e2f55-3c1d-4f0e-8a77-2d4c6b8e9f10"
        root = api_client.post(
            INBOUND_URL,
            make_payload(title="Root page"),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
            HTTP_IDEMPOTENCY_KEY=RESULT_ID,
        )
        legacy = api_client.post(
            INBOUND_URL,
            make_payload(title="Revision 2 page"),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
            HTTP_IDEMPOTENCY_KEY=revision_2_result,
        )
        assert root.status_code == 201 and legacy.status_code == 201
        page_id = legacy.json()["page_id"]
        data = make_v5_payload(revision=2, workflow_execution=revision_2_result)
        data["locales"] = {"pl": data["locales"]["pl"]}
        r = post_v5(api_client, data)
        assert r.status_code == 201, r.content
        assert r.json()["pages"]["pl"]["page_id"] == page_id
        assert ArticlePage.objects.count() == 2

    def test_lost_insert_race_retries_and_answers_duplicate(
        self, api_client, article_index, article_index_en, monkeypatch
    ):
        body = json.dumps(make_v5_payload()).encode()
        assert post_v5(api_client, body=body).status_code == 201
        real = views.find_publication
        calls = []

        def blind_first_call(result_id):
            calls.append(result_id)
            return None if len(calls) == 1 else real(result_id)

        monkeypatch.setattr(views, "find_publication", blind_first_call)
        r = post_v5(api_client, body=body, delivery_id="dl-2")
        assert r.status_code == 200 and r.json()["status"] == "duplicate", r.content
        assert len(calls) == 2
        assert IngestPublication.objects.count() == 1
        assert ArticlePage.objects.count() == 2

    def test_revision_above_the_integer_limit_is_400(self, api_client, article_index):
        r = post_v5(api_client, make_v5_payload(revision=2**31))
        assert r.status_code == 400

    def test_missing_delivery_and_idempotency_headers_is_400(self, api_client, article_index):
        r = post_v5(api_client, delivery_id=None)
        assert r.status_code == 400

    def test_overlong_delivery_id_is_400(self, api_client, article_index):
        r = post_v5(api_client, delivery_id="d" * 256)
        assert r.status_code == 400

    def test_bad_shape_is_400_not_500(self, api_client, article_index, article_index_en):
        data = make_v5_payload()
        data["locales"] = "tekst"
        assert post_v5(api_client, data).status_code == 400
        data = make_v5_payload()
        data["image"] = "https://x.test/a.jpg"
        assert post_v5(api_client, data, delivery_id="dl-2").status_code in (201, 400)

    def test_missing_parent_for_a_language_rolls_everything_back(self, api_client, article_index):
        r = post_v5(api_client)
        assert r.status_code == 500
        assert not ArticlePage.objects.exists()
        assert not IngestPublication.objects.exists()
        assert not IngestDelivery.objects.exists()

    def test_publish_policy_applies_to_every_language(
        self, api_client, article_index, article_index_en, settings
    ):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "draft"
        r = post_v5(api_client)
        assert {p["outcome"] for p in r.json()["pages"].values()} == {"draft"}

    def test_pair_endpoint_is_gone(self, api_client):
        response = api_client.post("/api/semantichub/pair/", b"{}", content_type="application/json")
        assert response.status_code == 404
