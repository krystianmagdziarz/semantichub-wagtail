import pytest
from django.db import IntegrityError

from semantichub_wagtail.models import (
    IngestPublication,
    IngestPublicationPage,
    IngestReceipt,
)
from tests.testapp.models import ArticlePage


@pytest.mark.django_db
class TestIngestReceipt:
    def test_idempotency_key_is_unique(self, article_index):
        IngestReceipt.objects.create(idempotency_key="k1")
        with pytest.raises(IntegrityError):
            IngestReceipt.objects.create(idempotency_key="k1")

    def test_receipt_survives_page_deletion(self, article_index):
        page = article_index.add_child(instance=ArticlePage(title="A", slug="a"))
        receipt = IngestReceipt.objects.create(idempotency_key="k1", page=page)
        page.delete()
        receipt.refresh_from_db()
        assert receipt.page is None


@pytest.mark.django_db
def test_publication_pages_are_unique_per_language(article_index):
    page = article_index.add_child(instance=ArticlePage(title="A", slug="a"))
    pub = IngestPublication.objects.create(
        result_id="6f1b0680-0f1c-4a1b-9a5c-1c2d3e4f5a6b",
        revision=1,
        payload_hash="x" * 64,
    )
    IngestPublicationPage.objects.create(publication=pub, language_code="pl", page=page)
    assert pub.page_for("pl").id == page.id
    assert pub.page_for("en") is None
    with pytest.raises(IntegrityError):
        IngestPublicationPage.objects.create(publication=pub, language_code="pl", page=page)
