import hashlib
import mimetypes
from io import BytesIO
from urllib.parse import urlparse

import httpx
from django.core.files.base import ContentFile
from wagtail.images import get_image_model
from willow.image import Image as WillowImage

MAX_BYTES = 12 * 1024 * 1024
TIMEOUT = 15.0


def fetch_image(image, title):
    if not isinstance(image, dict):
        return None
    url = (image.get("url") or "").strip()
    if not url or urlparse(url).scheme != "https":
        return None

    Image = get_image_model()
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
            if not content_type.startswith("image/"):
                return None
            payload = response.content
    except Exception:
        return None
    if not payload or len(payload) > MAX_BYTES:
        return None

    digest = hashlib.sha256(payload).hexdigest()
    extension = mimetypes.guess_extension(content_type) or ".jpg"
    filename = f"semantichub-{digest[:16]}{extension}"
    existing = Image.objects.filter(file__endswith=filename).first()
    if existing is not None:
        return existing
    try:
        width, height = WillowImage.open(BytesIO(payload)).get_size()
    except Exception:
        return None

    wagtail_image = Image(title=(title or filename)[:255])
    wagtail_image.file.save(filename, ContentFile(payload), save=False)
    wagtail_image.width = width
    wagtail_image.height = height
    wagtail_image.save()
    return wagtail_image
