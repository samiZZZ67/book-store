from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0002_accessrequest_book_unique"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramAdmin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(max_length=64, unique=True)),
                ("chat_id", models.BigIntegerField(blank=True, null=True)),
                ("first_name", models.CharField(blank=True, max_length=120)),
                ("last_name", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("registered_at", models.DateTimeField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["username"],
            },
        ),
    ]
