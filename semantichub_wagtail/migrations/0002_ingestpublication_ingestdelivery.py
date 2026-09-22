import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('semantichub_wagtail', '0001_initial'),
        ('wagtailimages', '0027_image_description'),
        migrations.swappable_dependency(settings.WAGTAIL_PAGE_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IngestPublication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('result_id', models.UUIDField(unique=True)),
                ('revision', models.PositiveIntegerField()),
                ('payload_hash', models.CharField(max_length=64)),
                ('image_url', models.URLField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('en_page', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.WAGTAIL_PAGE_MODEL)),
                ('image', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='wagtailimages.image')),
                ('pl_page', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.WAGTAIL_PAGE_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='IngestDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('delivery_id', models.CharField(max_length=255, unique=True)),
                ('payload_hash', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('publication', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='semantichub_wagtail.ingestpublication')),
            ],
        ),
    ]
