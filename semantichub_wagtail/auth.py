import hashlib
import hmac
import time

from django.conf import settings

MAX_CLOCK_SKEW_SECONDS = 300


def _bearer_authorized(request, token):
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    return hmac.compare_digest(header[len(prefix):].strip(), token)


def _signature_authorized(request, secret):
    timestamp = request.headers.get("X-SH-Timestamp", "")
    signature = request.headers.get("X-SH-Signature", "")
    if not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + request.body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256=").strip(), expected)


def is_signed(request):
    secret = getattr(settings, "SEMANTICHUB_INGEST_SECRET", "") or ""
    return bool(secret) and _signature_authorized(request, secret)


def is_authorized(request):
    token = getattr(settings, "SEMANTICHUB_INGEST_TOKEN", "") or ""
    secret = getattr(settings, "SEMANTICHUB_INGEST_SECRET", "") or ""
    if secret and _signature_authorized(request, secret):
        return True
    if token and _bearer_authorized(request, token):
        return True
    return False
