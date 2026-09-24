import hashlib
import ipaddress
import socket
import time
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx
from django.core.files.base import ContentFile
from wagtail.images import get_image_model
from willow.image import Image as WillowImage

from semantichub_wagtail import __version__

MAX_BYTES = 12 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = 15.0
USER_AGENT = (
    f"semantichub-wagtail/{__version__} (+https://github.com/krystianmagdziarz/semantichub-wagtail)"
)
RASTER_FORMATS = {"avif", "gif", "jpeg", "png", "webp"}
EXTENSIONS = {
    "image/avif": ".avif",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class UnsafeURL(Exception):
    pass


def _client():
    return httpx.Client(timeout=TIMEOUT, follow_redirects=False)


def _headers(host_header):
    return {"Host": host_header, "User-Agent": USER_AGENT}


def _is_public(address):
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def _public_address(host, port):
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as error:
        raise UnsafeURL(f"cannot resolve {host}") from error
    addresses = [ipaddress.ip_address(answer[4][0].split("%")[0]) for answer in answers]
    if not addresses or not all(_is_public(address) for address in addresses):
        raise UnsafeURL(f"{host} does not resolve to public addresses only")
    return addresses[0]


def _pinned_request(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise UnsafeURL("only public https URLs are fetched")
    port = parts.port or 443
    address = _public_address(parts.hostname, port)
    literal = f"[{address}]" if address.version == 6 else str(address)
    pinned = parts._replace(netloc=f"{literal}:{port}").geturl()
    host_header = parts.hostname if port == 443 else f"{parts.hostname}:{port}"
    return pinned, host_header, parts.hostname


def _read_limited(response, deadline):
    declared = response.headers.get("Content-Length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        return None
    chunks = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_BYTES or time.monotonic() > deadline:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _download(url):
    deadline = time.monotonic() + TIMEOUT
    with _client() as client:
        for _ in range(MAX_REDIRECTS + 1):
            pinned, host_header, hostname = _pinned_request(url)
            with client.stream(
                "GET",
                pinned,
                headers=_headers(host_header),
                extensions={"sni_hostname": hostname},
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    continue
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";")[0]
                content_type = content_type.strip().lower()
                if content_type not in EXTENSIONS:
                    return None, None
                return content_type, _read_limited(response, deadline)
    return None, None


def fetch_image(image, title):
    if not isinstance(image, dict):
        return None
    url = image.get("url")
    if not isinstance(url, str) or not url.strip():
        return None

    try:
        content_type, payload = _download(url.strip())
    except Exception:
        return None
    if not payload:
        return None

    Image = get_image_model()
    digest = hashlib.sha256(payload).hexdigest()
    filename = f"semantichub-{digest[:16]}{EXTENSIONS[content_type]}"
    existing = Image.objects.filter(file__endswith=filename).first()
    if existing is not None:
        return existing
    try:
        willow = WillowImage.open(BytesIO(payload))
        if willow.format_name not in RASTER_FORMATS:
            return None
        width, height = willow.get_size()
    except Exception:
        return None

    wagtail_image = Image(title=(title or filename)[:255])
    wagtail_image.file.save(filename, ContentFile(payload), save=False)
    wagtail_image.width = width
    wagtail_image.height = height
    wagtail_image.save()
    return wagtail_image
