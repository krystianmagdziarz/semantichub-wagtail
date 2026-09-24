import hashlib

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from wagtail.models import Locale

from semantichub_wagtail.adapters import get_adapter
from semantichub_wagtail.auth import is_authorized
from semantichub_wagtail.content import unique_slug
from semantichub_wagtail.images import fetch_image
from semantichub_wagtail.models import (
    IngestDelivery,
    IngestPublication,
    IngestPublicationPage,
    IngestReceipt,
)
from semantichub_wagtail.payload import (
    InvalidPayload,
    article_for_locale,
    parse_article,
    parse_identity,
)
from semantichub_wagtail.publish import apply_policy, ingest_user, resolve_mode
from semantichub_wagtail.settings import allowed_languages

MAX_KEY_LENGTH = 255
MAX_IMAGE_URL_LENGTH = 2048


def find_publication(result_id):
    return IngestPublication.objects.select_for_update().filter(result_id=result_id).first()


def find_receipt(key):
    return IngestReceipt.objects.select_related("page").filter(idempotency_key=key).first()


def _page_response(state, outcome, http_status):
    return Response({"status": state, **outcome}, status=http_status)


def _duplicate(receipt):
    return Response(
        {"status": "duplicate", "page_id": receipt.page_id},
        status=status.HTTP_200_OK,
    )


def _v5_duplicate(result_id, revision):
    return Response(
        {"status": "duplicate", "result_id": str(result_id), "revision": int(revision)},
        status=status.HTTP_200_OK,
    )


def _conflict(detail, result_id, revision):
    return Response(
        {"detail": detail, "result_id": str(result_id), "revision": int(revision)},
        status=status.HTTP_409_CONFLICT,
    )


def _image_url(data):
    image = data.get("image")
    url = image.get("url") if isinstance(image, dict) else None
    if not isinstance(url, str) or len(url) > MAX_IMAGE_URL_LENGTH:
        return ""
    return url.strip()


def _default_language():
    """Site language used as the page key of a v5 delivery without any language."""
    allowed = allowed_languages()
    try:
        code = Locale.get_default().language_code
    except Locale.DoesNotExist:
        code = ""
    if code in allowed or not allowed:
        return code
    return allowed[0]


class InboundArticleView(APIView):
    """One endpoint for every delivery. A payload without result_id (v2/v3)
    is keyed by Idempotency-Key through IngestReceipt; a payload with
    result_id (v5) is keyed by result_id and revision, one page per language."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser,)
    throttle_classes = ()

    def post(self, request):
        if not is_authorized(request):
            return Response(
                {"detail": "invalid or missing credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            data = request.data
            identity = parse_identity(data)
            article = parse_article(data)
        except (InvalidPayload, AttributeError, TypeError) as error:
            return Response(
                {"detail": str(error) or "invalid payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        adapter = get_adapter()
        if identity is None:
            return self._legacy(request, article, adapter)
        return self._v5(request, data, identity, article, adapter)

    # v2/v3: Idempotency-Key and IngestReceipt

    def _legacy(self, request, article, adapter):
        idem_key = request.headers.get("Idempotency-Key", "").strip()
        if len(idem_key) > MAX_KEY_LENGTH:
            return Response(
                {"detail": f"Idempotency-Key is longer than {MAX_KEY_LENGTH} characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        receipt = find_receipt(idem_key) if idem_key else None
        if receipt is not None:
            if receipt.page is None:
                return _duplicate(receipt)
            article.cover = fetch_image(article.data.get("image"), article.title)
            with transaction.atomic():
                outcome = self._update_page(article, adapter, receipt.page.specific)
            return _page_response("updated", outcome, status.HTTP_200_OK)

        parent = adapter.get_parent(article)
        if parent is None:
            return Response(
                {"detail": "no parent page for incoming articles"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        article.cover = fetch_image(article.data.get("image"), article.title)
        try:
            with transaction.atomic():
                page, outcome = self._create_page(article, adapter, parent)
                if idem_key:
                    IngestReceipt.objects.create(idempotency_key=idem_key, page=page)
        except IntegrityError:
            receipt = find_receipt(idem_key) if idem_key else None
            if receipt is None:
                raise
            return _duplicate(receipt)

        return _page_response("created", outcome, status.HTTP_201_CREATED)

    # v5: result_id, revision and a delivery id

    def _v5(self, request, data, identity, article, adapter):
        delivery_id = (
            request.headers.get("X-SH-Delivery", "").strip()
            or request.headers.get("Idempotency-Key", "").strip()
        )
        if not delivery_id or len(delivery_id) > MAX_KEY_LENGTH:
            return Response(
                {
                    "detail": "X-SH-Delivery or Idempotency-Key is required, "
                    f"up to {MAX_KEY_LENGTH} characters"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        digest = hashlib.sha256(request.body).hexdigest()

        # A concurrent delivery of the same result can win the insert race;
        # one retry then sees its rows and answers duplicate or conflict.
        try:
            with transaction.atomic():
                return self._deliver(data, identity, article, adapter, delivery_id, digest)
        except IntegrityError:
            with transaction.atomic():
                return self._deliver(data, identity, article, adapter, delivery_id, digest)

    def _deliver(self, data, identity, article, adapter, delivery_id, digest):
        delivery = (
            IngestDelivery.objects.select_for_update()
            .select_related("publication")
            .filter(delivery_id=delivery_id)
            .first()
        )
        if delivery is not None:
            if delivery.payload_hash != digest:
                return _conflict(
                    "delivery ID reused with a different payload",
                    identity.result_id,
                    delivery.publication.revision,
                )
            return _v5_duplicate(identity.result_id, delivery.publication.revision)

        publication = find_publication(identity.result_id)
        if publication is not None and identity.revision < publication.revision:
            return _conflict("stale revision", identity.result_id, publication.revision)
        if publication is not None and identity.revision == publication.revision:
            if publication.payload_hash != digest:
                return _conflict(
                    "revision reused with a different payload",
                    identity.result_id,
                    publication.revision,
                )
            IngestDelivery.objects.create(
                delivery_id=delivery_id, payload_hash=digest, publication=publication
            )
            return _v5_duplicate(identity.result_id, publication.revision)

        source_lang = identity.source_lang or _default_language()
        created_now = publication is None
        if created_now:
            publication = IngestPublication.objects.create(
                result_id=identity.result_id, revision=identity.revision, payload_hash=digest
            )
            self._adopt_legacy_page(publication, data, identity, source_lang)

        image_url = _image_url(data)
        if image_url and image_url == publication.image_url and publication.image_id:
            cover = publication.image
        else:
            cover = fetch_image(data.get("image"), article.title)

        ordered = [source_lang] + [code for code in identity.locales if code != source_lang]
        pages = {}
        for code in ordered:
            if code == source_lang:
                loc_article = article
                loc_article.language = code
            else:
                loc_article = article_for_locale(data, code, identity.locales[code])
            loc_article.cover = cover
            existing = publication.page_for(code)
            if existing is not None:
                outcome = self._update_page(loc_article, adapter, existing.specific)
            else:
                parent = adapter.get_parent(loc_article)
                if parent is None:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": f"no parent page for language {code}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                page, outcome = self._create_page(loc_article, adapter, parent)
                IngestPublicationPage.objects.update_or_create(
                    publication=publication, language_code=code, defaults={"page": page}
                )
            pages[code] = outcome

        publication.revision = identity.revision
        publication.payload_hash = digest
        publication.image_url = image_url
        publication.image = cover
        publication.save()
        IngestDelivery.objects.create(
            delivery_id=delivery_id, payload_hash=digest, publication=publication
        )

        return Response(
            {
                "status": "published" if created_now else "updated",
                "result_id": str(identity.result_id),
                "revision": identity.revision,
                "pages": pages,
            },
            status=status.HTTP_201_CREATED if created_now else status.HTTP_200_OK,
        )

    def _adopt_legacy_page(self, publication, data, identity, source_lang):
        """A page created before v5 becomes the source-language page of the new
        publication instead of a duplicate. The old Idempotency-Key was the id
        of the delivered result, which v5 sends as workflow_execution; the
        chain root (result_id) is the fallback."""
        keys = [
            key
            for key in (data.get("workflow_execution"), str(identity.result_id))
            if isinstance(key, str) and key.strip()
        ]
        receipt = None
        for key in keys:
            found = find_receipt(key.strip())
            if found is not None and found.page_id:
                receipt = found
                break
        if receipt is not None:
            IngestPublicationPage.objects.get_or_create(
                publication=publication,
                language_code=source_lang,
                defaults={"page": receipt.page},
            )

    # shared page operations

    def _create_page(self, article, adapter, parent):
        page = adapter.build(article)
        page.slug = unique_slug(parent, article.slug_base)
        page.live = False
        page.has_unpublished_changes = True
        parent.add_child(instance=page)
        if article.tags:
            adapter.apply_tags(page, article.tags)
            page.save()
        revision = page.save_revision()
        outcome = apply_policy(page, revision, resolve_mode(article), ingest_user())
        return page, self._outcome(page, outcome)

    def _update_page(self, article, adapter, page):
        adapter.update(page, article)
        if article.tags:
            adapter.apply_tags(page, article.tags)
        if not page.live:
            page.save()
        revision = page.save_revision()
        outcome = apply_policy(page, revision, resolve_mode(article), ingest_user())
        return self._outcome(page, outcome)

    def _outcome(self, page, outcome):
        return {"page_id": page.id, "slug": page.slug, "outcome": outcome, "live": page.live}
