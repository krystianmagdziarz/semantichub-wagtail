import hashlib
import hmac
import time

import pytest
from django.test import RequestFactory

from semantichub_wagtail.auth import is_authorized

TOKEN = "test-token"
SECRET = "test-secret"
BODY = b'{"mode": "article"}'


@pytest.fixture
def rf():
    return RequestFactory()


def _request(rf, headers=None):
    return rf.post(
        "/api/semantichub/inbound/",
        data=BODY,
        content_type="application/json",
        headers=headers or {},
    )


def _sign(body, secret=SECRET, timestamp=None):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    digest = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return timestamp, digest


class TestBearerToken:
    def test_valid_token_is_authorized(self, rf, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
        request = _request(rf, {"Authorization": f"Bearer {TOKEN}"})
        assert is_authorized(request) is True

    def test_wrong_token_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
        request = _request(rf, {"Authorization": "Bearer nope"})
        assert is_authorized(request) is False

    def test_missing_header_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
        assert is_authorized(_request(rf)) is False

    def test_non_bearer_scheme_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
        request = _request(rf, {"Authorization": f"Token {TOKEN}"})
        assert is_authorized(request) is False


class TestNoConfiguration:
    def test_everything_is_rejected_without_config(self, rf):
        request = _request(rf, {"Authorization": "Bearer anything"})
        assert is_authorized(request) is False


class TestHmacSignature:
    def test_valid_signature_is_authorized(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        timestamp, digest = _sign(BODY)
        request = _request(
            rf, {"X-SH-Timestamp": timestamp, "X-SH-Signature": digest}
        )
        assert is_authorized(request) is True

    def test_sha256_prefix_is_accepted(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        timestamp, digest = _sign(BODY)
        request = _request(
            rf, {"X-SH-Timestamp": timestamp, "X-SH-Signature": f"sha256={digest}"}
        )
        assert is_authorized(request) is True

    def test_wrong_signature_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        timestamp, _ = _sign(BODY)
        request = _request(
            rf, {"X-SH-Timestamp": timestamp, "X-SH-Signature": "0" * 64}
        )
        assert is_authorized(request) is False

    def test_signature_over_different_body_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        timestamp, digest = _sign(b'{"mode": "tampered"}')
        request = _request(
            rf, {"X-SH-Timestamp": timestamp, "X-SH-Signature": digest}
        )
        assert is_authorized(request) is False

    def test_stale_timestamp_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        timestamp, digest = _sign(BODY, timestamp=int(time.time()) - 3600)
        request = _request(
            rf, {"X-SH-Timestamp": timestamp, "X-SH-Signature": digest}
        )
        assert is_authorized(request) is False

    def test_garbage_timestamp_is_rejected(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        _, digest = _sign(BODY)
        request = _request(
            rf, {"X-SH-Timestamp": "yesterday", "X-SH-Signature": digest}
        )
        assert is_authorized(request) is False

    def test_bearer_does_not_satisfy_signature_only_config(self, rf, settings):
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        request = _request(rf, {"Authorization": "Bearer test-secret"})
        assert is_authorized(request) is False


class TestBothConfigured:
    def test_valid_bearer_passes(self, rf, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        request = _request(rf, {"Authorization": f"Bearer {TOKEN}"})
        assert is_authorized(request) is True

    def test_valid_signature_passes(self, rf, settings):
        settings.SEMANTICHUB_INGEST_TOKEN = TOKEN
        settings.SEMANTICHUB_INGEST_SECRET = SECRET
        timestamp, digest = _sign(BODY)
        request = _request(
            rf, {"X-SH-Timestamp": timestamp, "X-SH-Signature": digest}
        )
        assert is_authorized(request) is True
