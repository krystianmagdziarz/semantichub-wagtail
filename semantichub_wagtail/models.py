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


class IngestPublication(models.Model):
    result_id = models.UUIDField(unique=True)
    revision = models.PositiveIntegerField()
    payload_hash = models.CharField(max_length=64)
    image_url = models.URLField(blank=True)
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    en_page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    pl_page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.result_id} rev {self.revision}"


class IngestDelivery(models.Model):
    delivery_id = models.CharField(max_length=255, unique=True)
    payload_hash = models.CharField(max_length=64)
    publication = models.ForeignKey(
        IngestPublication,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.delivery_id
