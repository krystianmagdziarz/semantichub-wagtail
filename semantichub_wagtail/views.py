import hashlib
import json
from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework import status
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


class InboundArticleView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        if not is_authorized(request):
            return Response(
                {"detail": "invalid or missing credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            article = parse_article(request.data)
        except InvalidPayload as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        adapter = get_adapter()

        idem_key = request.headers.get("Idempotency-Key")
        receipt = (
            IngestReceipt.objects.filter(idempotency_key=idem_key).first() if idem_key else None
        )
        if receipt is not None:
            if receipt.page is None:
                return Response(
                    {"status": "duplicate", "page_id": receipt.page_id},
                    status=status.HTTP_200_OK,
                )
            return self._update(article, adapter, receipt.page.specific)

        parent = adapter.get_parent(article)
        if parent is None:
            return Response(
                {"detail": "no parent page for incoming articles"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        article.cover = fetch_image(article.data.get("image"), article.title)
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

        if idem_key:
            try:
                with transaction.atomic():
                    IngestReceipt.objects.create(idempotency_key=idem_key, page=page)
            except IntegrityError:
                pass

        return Response(
            {
                "status": "created",
                "page_id": page.id,
                "slug": page.slug,
                "outcome": outcome,
                "live": page.live,
            },
            status=status.HTTP_201_CREATED,
        )

    def _update(self, article, adapter, page):
        article.cover = fetch_image(article.data.get("image"), article.title)
        adapter.update(page, article)
        if article.tags:
            adapter.apply_tags(page, article.tags)
        if not page.live:
            page.save()
        revision = page.save_revision()

        outcome = apply_policy(page, revision, resolve_mode(article), ingest_user())

        return Response(
            {
                "status": "updated",
                "page_id": page.id,
                "slug": page.slug,
                "outcome": outcome,
                "live": page.live,
            },
            status=status.HTTP_200_OK,
        )


class InboundPairView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        body = request.body
        if not is_signed(request):
            return Response(
                {"detail": "invalid or missing signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            data = json.loads(body)
            result_id = UUID(str(data["result_id"]))
            revision = int(data["revision"])
            locales = data["locales"]
            if (
                revision < 1
                or not isinstance(locales.get("en"), dict)
                or not isinstance(locales.get("pl"), dict)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return Response(
                {"detail": "invalid pair payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_id = request.headers.get("X-SH-Delivery", "").strip()
        if not delivery_id:
            return Response(
                {"detail": "X-SH-Delivery is required"},
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
            publication.image_url = (data.get("image") or {}).get("url", "")
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
