import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="accessrequest",
            name="book",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="access_requests",
                to="library.pdfbook",
            ),
        ),
        migrations.AddConstraint(
            model_name="accessrequest",
            constraint=models.UniqueConstraint(
                fields=("user", "book"),
                name="unique_user_book_access_request",
            ),
        ),
    ]
