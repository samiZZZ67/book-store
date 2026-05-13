from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0003_telegramadmin"),
    ]

    operations = [
        migrations.AddField(
            model_name="pdfbook",
            name="thumbnail",
            field=models.FileField(blank=True, null=True, upload_to="book_thumbnails/"),
        ),
        migrations.AddField(
            model_name="pdfbook",
            name="thumbnail_filename",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
