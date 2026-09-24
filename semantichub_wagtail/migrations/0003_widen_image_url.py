from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('semantichub_wagtail', '0002_ingestpublication_ingestdelivery'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ingestpublication',
            name='image_url',
            field=models.URLField(blank=True, max_length=2048),
        ),
    ]
