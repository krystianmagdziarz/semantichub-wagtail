from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from semantichub_wagtail.adapters import get_adapter
from semantichub_wagtail.auth import is_authorized
from semantichub_wagtail.content import unique_slug
from semantichub_wagtail.images import fetch_image
from semantichub_wagtail.models import IngestReceipt
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
            IngestReceipt.objects.filter(idempotency_key=idem_key).first()
            if idem_key
            else None
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
