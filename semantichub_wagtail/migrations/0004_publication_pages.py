"""Reversing this migration restores the en_page/pl_page columns empty; existing page links are not copied back."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_pages(apps, schema_editor):
    IngestPublication = apps.get_model("semantichub_wagtail", "IngestPublication")
    IngestPublicationPage = apps.get_model("semantichub_wagtail", "IngestPublicationPage")
    for pub in IngestPublication.objects.all():
        for code, page_id in (("en", pub.en_page_id), ("pl", pub.pl_page_id)):
            if page_id:
                IngestPublicationPage.objects.get_or_create(
                    publication=pub,
                    language_code=code,
                    defaults={"page_id": page_id},
                )


class Migration(migrations.Migration):

    dependencies = [
        ("semantichub_wagtail", "0003_widen_image_url"),
        migrations.swappable_dependency(settings.WAGTAIL_PAGE_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IngestPublicationPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language_code", models.CharField(max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("page", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.WAGTAIL_PAGE_MODEL)),
                ("publication", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pages", to="semantichub_wagtail.ingestpublication")),
            ],
        ),
        migrations.AddConstraint(
            model_name="ingestpublicationpage",
            constraint=models.UniqueConstraint(fields=("publication", "language_code"), name="uq_ingest_publication_page_language"),
        ),
        migrations.RunPython(copy_pages, migrations.RunPython.noop),
        migrations.RemoveField(model_name="ingestpublication", name="en_page"),
        migrations.RemoveField(model_name="ingestpublication", name="pl_page"),
    ]
