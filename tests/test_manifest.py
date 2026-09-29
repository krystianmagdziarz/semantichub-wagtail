import pytest
from rest_framework import status

from semantichub_wagtail import __version__
from semantichub_wagtail.manifest import build_manifest, is_configured, manifest_url, push_manifest

MANIFEST_URL = "/api/semantichub/manifest/"


def test_build_manifest_has_no_blocks_one_derived_section_and_version():
    manifest = build_manifest()
    assert manifest["blocks"] == []
    assert manifest["sections"] == [{"key": "seo", "name": "SEO meta"}]
    assert manifest["features"] == []
    assert manifest["source"] == "receiver"
    assert manifest["version"] == __version__
    assert manifest["fields"] == []


def test_build_manifest_includes_adapter_fields(monkeypatch):
    from tests.testapp.adapter import ExampleArticleAdapter

    field = {
        "key": "category",
        "label": "Category",
        "type": "text",
        "required": True,
        "multiple": False,
        "options": [],
    }
    monkeypatch.setattr(ExampleArticleAdapter, "get_fields", lambda self: [field])
    assert build_manifest()["fields"] == [field]


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeClient:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self.calls = []

    def put(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.status_code, self.text)


def test_is_configured_requires_all_three(settings):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = ""
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    assert is_configured() is False
    settings.SEMANTICHUB_AGENT_TOKEN = "tok"
    assert is_configured() is True


def test_manifest_url_joins_base_and_goal():
    from django.test import override_settings

    with override_settings(
        SEMANTICHUB_API_BASE_URL="https://example.test/",
        SEMANTICHUB_GOAL_ID="goal-1",
    ):
        assert manifest_url() == "https://example.test/api/goals/goal-1/target-manifest"


def test_push_manifest_skipped_without_configuration(settings):
    settings.SEMANTICHUB_API_BASE_URL = ""
    settings.SEMANTICHUB_AGENT_TOKEN = ""
    settings.SEMANTICHUB_GOAL_ID = ""
    client = FakeClient()
    assert push_manifest(client=client) is False
    assert client.calls == []


def test_push_manifest_sends_url_headers_and_body(settings):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test/"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok-123"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    client = FakeClient(status_code=200)
    assert push_manifest(client=client) is True
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://example.test/api/goals/goal-1/target-manifest"
    assert call["headers"]["Authorization"] == "Bearer tok-123"
    assert call["headers"]["User-Agent"] == f"SemanticHub-wagtail/{__version__}"
    assert call["json"]["source"] == "receiver"


def test_push_manifest_returns_false_on_http_error(settings):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok-123"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    client = FakeClient(status_code=422)
    assert push_manifest(client=client) is False


def test_push_manifest_refuses_plain_http(settings):
    settings.SEMANTICHUB_API_BASE_URL = "http://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok-123"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    client = FakeClient()
    assert push_manifest(client=client) is False
    assert client.calls == []


def test_rejected_push_does_not_log_the_response_body(settings, caplog):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok-123"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    client = FakeClient(status_code=500, text="Traceback: internal detail")
    with caplog.at_level("WARNING", logger="semantichub_wagtail.manifest"):
        assert push_manifest(client=client) is False
    assert "status=500" in caplog.text
    assert "internal detail" not in caplog.text


def test_push_manifest_swallows_transport_errors(settings):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok-123"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"

    class BrokenClient:
        def put(self, url, headers=None, json=None):
            raise RuntimeError("network is down")

    assert push_manifest(client=BrokenClient()) is False


@pytest.mark.django_db
class TestManifestView:
    def test_requires_authentication(self, api_client):
        response = api_client.get(MANIFEST_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_build_manifest(self, api_client, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = "test-ingest-secret"
        response = api_client.get(MANIFEST_URL, HTTP_AUTHORIZATION="Bearer test-ingest-secret")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["source"] == "receiver"
