import hashlib
import json
from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from semantichub_wagtail.adapters import get_adapter, get_pair_adapter
from semantichub_wagtail.auth import is_authorized, is_signed
from semantichub_wagtail.content import unique_slug
from semantichub_wagtail.images import fetch_image
from semantichub_wagtail.models import IngestDelivery, IngestPublication, IngestReceipt
from semantichub_wagtail.payload import InvalidPayload, parse_article
from semantichub_wagtail.publish import apply_policy, ingest_user, resolve_mode

MAX_KEY_LENGTH = 255
MAX_REVISION = 2**31 - 1


def find_receipt(key):
    return IngestReceipt.objects.select_related("page").filter(idempotency_key=key).first()


def _page_response(state, page, outcome, http_status):
    return Response(
        {
            "status": state,
            "page_id": page.id,
            "slug": page.slug,
            "outcome": outcome,
            "live": page.live,
        },
        status=http_status,
    )


def _duplicate(receipt):
    return Response(
        {"status": "duplicate", "page_id": receipt.page_id},
        status=status.HTTP_200_OK,
    )


class InboundArticleView(APIView):
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
        idem_key = request.headers.get("Idempotency-Key", "").strip()
        if len(idem_key) > MAX_KEY_LENGTH:
            return Response(
                {"detail": f"Idempotency-Key is longer than {MAX_KEY_LENGTH} characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            article = parse_article(request.data)
        except InvalidPayload as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        adapter = get_adapter()

        receipt = find_receipt(idem_key) if idem_key else None
        if receipt is not None:
            if receipt.page is None:
                return _duplicate(receipt)
            return self._update(article, adapter, receipt.page.specific)

        parent = adapter.get_parent(article)
        if parent is None:
            return Response(
                {"detail": "no parent page for incoming articles"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        article.cover = fetch_image(article.data.get("image"), article.title)
        try:
            with transaction.atomic():
                page, outcome = self._create(article, adapter, parent)
                if idem_key:
                    IngestReceipt.objects.create(idempotency_key=idem_key, page=page)
        except IntegrityError:
            receipt = find_receipt(idem_key) if idem_key else None
            if receipt is None:
                raise
            return _duplicate(receipt)

        return _page_response("created", page, outcome, status.HTTP_201_CREATED)

    def _create(self, article, adapter, parent):
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
        return page, outcome

    def _update(self, article, adapter, page):
        article.cover = fetch_image(article.data.get("image"), article.title)
        with transaction.atomic():
            adapter.update(page, article)
            if article.tags:
                adapter.apply_tags(page, article.tags)
            if not page.live:
                page.save()
            revision = page.save_revision()
            outcome = apply_policy(page, revision, resolve_mode(article), ingest_user())
        return _page_response("updated", page, outcome, status.HTTP_200_OK)


def _parse_pair(body):
    try:
        data = json.loads(body)
    except (ValueError, RecursionError) as error:
        raise ValueError("body is not valid JSON") from error
    if not isinstance(data, dict):
        raise ValueError("payload must be an object")
    try:
        result_id = UUID(str(data["result_id"]))
        revision = data["revision"]
        locales = data["locales"]
    except KeyError as error:
        raise ValueError("missing field") from error
    if type(revision) is not int or not 1 <= revision <= MAX_REVISION:
        raise ValueError("revision out of range")
    if not isinstance(locales, dict) or not all(
        isinstance(locales.get(code), dict) for code in ("en", "pl")
    ):
        raise ValueError("locales.en and locales.pl must be objects")
    image = data.get("image")
    if image is not None and not isinstance(image, dict):
        raise ValueError("image must be an object")
    if image and not isinstance(image.get("url") or "", str):
        raise ValueError("image.url must be a string")
    return data, result_id, revision


class InboundPairView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser,)
    throttle_classes = ()

    def post(self, request):
        body = request.body
        if not is_signed(request):
            return Response(
                {"detail": "invalid or missing signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            data, result_id, revision = _parse_pair(body)
        except ValueError as error:
            return Response(
                {"detail": f"invalid pair payload: {error}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_id = request.headers.get("X-SH-Delivery", "").strip()
        if not delivery_id or len(delivery_id) > MAX_KEY_LENGTH:
            return Response(
                {"detail": f"X-SH-Delivery is required, up to {MAX_KEY_LENGTH} characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        digest = hashlib.sha256(body).hexdigest()

        with transaction.atomic():
            delivery = (
                IngestDelivery.objects.select_for_update().filter(delivery_id=delivery_id).first()
            )
            if delivery is not None:
                if delivery.payload_hash != digest:
                    return Response(
                        {"detail": "delivery ID reused with a different payload"},
                        status=status.HTTP_409_CONFLICT,
                    )
                return Response(
                    {"status": "duplicate", "result_id": str(result_id)},
                    status=status.HTTP_200_OK,
                )

            publication = (
                IngestPublication.objects.select_for_update().filter(result_id=result_id).first()
            )
            if publication is not None and revision < publication.revision:
                return Response(
                    {"detail": "stale revision", "revision": publication.revision},
                    status=status.HTTP_409_CONFLICT,
                )
            if publication is not None and revision == publication.revision:
                if publication.payload_hash != digest:
                    return Response(
                        {
                            "detail": "revision reused with a different payload",
                            "revision": publication.revision,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                IngestDelivery.objects.create(
                    delivery_id=delivery_id,
                    payload_hash=digest,
                    publication=publication,
                )
                return Response(
                    {"status": "duplicate", "result_id": str(result_id)},
                    status=status.HTTP_200_OK,
                )

            publication = get_pair_adapter().upsert(
                publication=publication, data=data, revision=revision
            )
            publication.result_id = result_id
            publication.revision = revision
            publication.payload_hash = digest
            publication.image_url = (data.get("image") or {}).get("url") or ""
            publication.save()
            IngestDelivery.objects.create(
                delivery_id=delivery_id,
                payload_hash=digest,
                publication=publication,
            )

        return Response(
            {
                "status": "published",
                "result_id": str(result_id),
                "revision": revision,
            },
            status=status.HTTP_201_CREATED,
        )
