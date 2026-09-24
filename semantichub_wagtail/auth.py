import hashlib
import hmac
import time

from django.conf import settings

MAX_CLOCK_SKEW_SECONDS = 300
MAX_TIMESTAMP_DIGITS = 12


def _equal(received, expected):
    return hmac.compare_digest(received.encode(), expected.encode())


def _bearer_authorized(request, token):
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    return _equal(header[len(prefix) :].strip(), token)


def _signature_authorized(request, secret):
    timestamp = request.headers.get("X-SH-Timestamp", "")
    signature = request.headers.get("X-SH-Signature", "")
    if not timestamp or not signature:
        return False
    if len(timestamp) > MAX_TIMESTAMP_DIGITS or not (timestamp.isascii() and timestamp.isdigit()):
        return False
    if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW_SECONDS:
        return False
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + request.body, hashlib.sha256
    ).hexdigest()
    return _equal(signature.removeprefix("sha256=").strip(), expected)


def is_signed(request):
    secret = getattr(settings, "SEMANTICHUB_INGEST_SECRET", "") or ""
    return bool(secret) and _signature_authorized(request, secret)


def is_authorized(request):
    token = getattr(settings, "SEMANTICHUB_INGEST_TOKEN", "") or ""
    if is_signed(request):
        return True
    return bool(token) and _bearer_authorized(request, token)
