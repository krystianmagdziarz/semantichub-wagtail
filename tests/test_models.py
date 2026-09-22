import pytest
from django.db import IntegrityError

from semantichub_wagtail.models import IngestReceipt
from tests.testapp.models import ArticlePage


@pytest.mark.django_db
class TestIngestReceipt:
    def test_idempotency_key_is_unique(self, article_index):
        IngestReceipt.objects.create(idempotency_key="k1")
        with pytest.raises(IntegrityError):
            IngestReceipt.objects.create(idempotency_key="k1")

    def test_receipt_survives_page_deletion(self, article_index):
        page = article_index.add_child(
            instance=ArticlePage(title="A", slug="a")
        )
        receipt = IngestReceipt.objects.create(idempotency_key="k1", page=page)
        page.delete()
        receipt.refresh_from_db()
        assert receipt.page is None
