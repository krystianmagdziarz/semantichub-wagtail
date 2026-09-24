import hashlib
import hmac
import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from rest_framework import status
from wagtail.models import GroupPagePermission, WorkflowState

from semantichub_wagtail.models import IngestReceipt
from tests.test_payload import make_payload
from tests.testapp.models import ArticlePage

INBOUND_URL = "/api/semantichub/inbound/"
TOKEN = "test-ingest-secret"


@pytest.fixture(autouse=True)
def _ingest_token(settings):
    settings.SEMANTICHUB_INGEST_TOKEN = TOKEN


def post(client, payload=None, token=TOKEN, idem_key="idem-1", headers=None):
    extra = dict(headers or {})
    if token is not None:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    if idem_key is not None:
        extra["HTTP_IDEMPOTENCY_KEY"] = idem_key
    return client.post(
        INBOUND_URL,
        payload if payload is not None else make_payload(),
        format="json",
        **extra,
    )


def grant_publish(parent):
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="semantichub")
    user.is_active = True
    user.save(update_fields=["is_active"])
    group, _ = Group.objects.get_or_create(name="SemanticHub ingest")
    user.groups.add(group)
    GroupPagePermission.objects.get_or_create(
        group=group,
        page=parent,
        permission=Permission.objects.get(
            content_type__app_label="wagtailcore",
            codename="publish_page",
        ),
    )
    return user


@pytest.mark.django_db
class TestInboundArticle:
    def test_valid_payload_creates_page(self, api_client, article_index):
        response = post(api_client)
        assert response.status_code == status.HTTP_201_CREATED
        assert ArticlePage.objects.filter(slug="passive-income").exists()

    def test_page_is_mapped_from_payload(self, api_client, article_index):
        post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert page.title == "Editor title"
        assert page.excerpt == "Editor lead."
        assert "<h2>Intro</h2>" in page.body
        assert str(page.publish_date) == "2026-07-21"

    def test_page_is_unpublished_and_in_moderation(self, api_client, article_index):
        post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert page.live is False
        assert page.current_workflow_state is not None
        assert page.current_workflow_state.status == WorkflowState.STATUS_IN_PROGRESS

    def test_tags_are_applied(self, api_client, article_index):
        post(api_client, payload=make_payload(tags=["seo", "google", "seo"]))
        page = ArticlePage.objects.get(slug="passive-income")
        assert sorted(t.name for t in page.tags.all()) == ["google", "seo"]

    def test_missing_token_returns_401(self, api_client, article_index):
        response = post(api_client, token=None)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert not ArticlePage.objects.exists()

    def test_wrong_token_returns_401(self, api_client, article_index):
        response = post(api_client, token="nope")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert not ArticlePage.objects.exists()

    def test_hmac_signature_authorizes_delivery(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = ""
        settings.SEMANTICHUB_INGEST_SECRET = "hmac-secret"
        body = json.dumps(make_payload()).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(
            b"hmac-secret", timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        response = api_client.post(
            INBOUND_URL,
            body,
            content_type="application/json",
            HTTP_X_SH_TIMESTAMP=timestamp,
            HTTP_X_SH_SIGNATURE=f"sha256={digest}",
            HTTP_IDEMPOTENCY_KEY="idem-hmac",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_non_article_mode_returns_400(self, api_client, article_index):
        response = post(api_client, payload=make_payload(mode="cluster", llm_response=None))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not ArticlePage.objects.exists()

    def test_missing_clusters_returns_400(self, api_client, article_index):
        response = post(api_client, payload=make_payload(clusters=[]))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_parent_returns_500(self, api_client, db):
        response = post(api_client)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_slug_collision_gets_a_counter(self, api_client, article_index):
        post(api_client, idem_key="k1")
        post(api_client, idem_key="k2")
        assert ArticlePage.objects.filter(slug="passive-income").exists()
        assert ArticlePage.objects.filter(slug="passive-income-2").exists()


@pytest.mark.django_db
class TestRepeatDelivery:
    def test_same_key_updates_the_same_page(self, api_client, article_index):
        first = post(api_client, idem_key="dup-key")
        assert first.status_code == status.HTTP_201_CREATED
        second = post(
            api_client,
            payload=make_payload(title="Corrected title", llm_response="<p>Corrected body.</p>"),
            idem_key="dup-key",
        )
        assert second.status_code == status.HTTP_200_OK
        assert second.data["status"] == "updated"
        assert second.data["page_id"] == first.data["page_id"]
        assert ArticlePage.objects.count() == 1
        page = ArticlePage.objects.get(pk=first.data["page_id"])
        assert page.title == "Corrected title"
        assert "Corrected body." in page.body

    def test_update_of_live_page_stays_in_revision(self, api_client, article_index, settings):
        grant_publish(article_index)
        first = post(api_client, payload=make_payload(publish_mode="publish"), idem_key="live-key")
        page = ArticlePage.objects.get(pk=first.data["page_id"])
        assert page.live is True
        post(
            api_client,
            payload=make_payload(title="Silent edit"),
            idem_key="live-key",
        )
        page.refresh_from_db()
        assert page.title != "Silent edit"
        assert page.get_latest_revision_as_object().title == "Silent edit"

    def test_repeat_for_deleted_page_reports_duplicate(self, api_client, article_index):
        first = post(api_client, idem_key="gone-key")
        ArticlePage.objects.get(pk=first.data["page_id"]).delete()
        second = post(api_client, idem_key="gone-key")
        assert second.status_code == status.HTTP_200_OK
        assert second.data["status"] == "duplicate"

    def test_distinct_keys_create_two_pages(self, api_client, article_index):
        post(api_client, idem_key="k1")
        post(api_client, idem_key="k2")
        assert ArticlePage.objects.count() == 2

    def test_receipt_is_stored(self, api_client, article_index):
        post(api_client, idem_key="stored-key")
        assert IngestReceipt.objects.filter(idempotency_key="stored-key").exists()


@pytest.mark.django_db
class TestPublishModes:
    def test_default_goes_to_moderation(self, api_client, article_index):
        response = post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert response.data["outcome"] == "moderation"
        assert page.live is False

    def test_draft_mode_skips_moderation(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "draft"
        response = post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert response.data["outcome"] == "draft"
        assert page.live is False
        assert page.current_workflow_state is None

    def test_publish_mode_with_permission_goes_live(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "publish"
        grant_publish(article_index)
        response = post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert response.data["outcome"] == "published"
        assert response.data["live"] is True
        assert page.live is True

    def test_publish_mode_without_permission_falls_back(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "publish"
        response = post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert response.data["outcome"] == "moderation"
        assert page.live is False

    def test_unknown_mode_falls_back_to_moderation(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "whatever"
        grant_publish(article_index)
        response = post(api_client)
        assert response.data["outcome"] == "moderation"

    def test_payload_mode_wins_over_settings(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "moderation"
        response = post(api_client, payload=make_payload(publish_mode="draft"))
        page = ArticlePage.objects.get(pk=response.data["page_id"])
        assert response.data["outcome"] == "draft"
        assert page.current_workflow_state is None

    def test_payload_publish_needs_permission(self, api_client, article_index):
        response = post(api_client, payload=make_payload(publish_mode="publish"))
        assert response.data["outcome"] == "moderation"
        assert response.data["live"] is False

    def test_payload_publish_goes_live_with_permission(self, api_client, article_index):
        grant_publish(article_index)
        response = post(api_client, payload=make_payload(publish_mode="publish"))
        assert response.data["outcome"] == "published"
        assert response.data["live"] is True

    def test_unknown_payload_mode_falls_back(self, api_client, article_index, settings):
        settings.SEMANTICHUB_INGEST_PUBLISH_MODE = "publish"
        grant_publish(article_index)
        response = post(api_client, payload=make_payload(publish_mode="publissh"))
        assert response.data["outcome"] == "moderation"


@pytest.mark.django_db
class TestIngestUser:
    def test_account_is_created_inactive(self, api_client, article_index):
        post(api_client)
        User = get_user_model()
        user = User.objects.get(username="semantichub")
        assert user.is_active is False
        assert not user.has_usable_password()

    def test_moderation_request_is_attributed_to_it(self, api_client, article_index):
        post(api_client)
        page = ArticlePage.objects.get(slug="passive-income")
        assert page.current_workflow_state.requested_by.username == "semantichub"


@pytest.mark.django_db
class TestProjectDefaultsDoNotLeakIn:
    def test_unrelated_authorization_scheme_does_not_block_signed_delivery(
        self, api_client, article_index, settings
    ):
        settings.SEMANTICHUB_INGEST_TOKEN = ""
        settings.SEMANTICHUB_INGEST_SECRET = "hmac-secret"
        body = json.dumps(make_payload()).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(
            b"hmac-secret", timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        response = api_client.post(
            INBOUND_URL,
            body,
            content_type="application/json",
            HTTP_AUTHORIZATION="Basic !!not-base64!!",
            HTTP_X_SH_TIMESTAMP=timestamp,
            HTTP_X_SH_SIGNATURE=digest,
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_form_encoded_body_is_refused(self, api_client, article_index):
        response = api_client.post(
            INBOUND_URL,
            {"mode": "article", "clusters": "x", "llm_response": "text"},
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert not ArticlePage.objects.exists()
