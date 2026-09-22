from django.db import models


class IngestReceipt(models.Model):
    idempotency_key = models.CharField(max_length=255, unique=True)
    page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.idempotency_key} -> page {self.page_id}"
