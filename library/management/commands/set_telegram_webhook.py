from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from library.telegram import set_webhook


class Command(BaseCommand):
    help = "Register the Telegram webhook URL for this site."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", help="Public site URL, for example https://example.onrender.com")

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN is required.")
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError("TELEGRAM_WEBHOOK_SECRET is required.")

        base_url = (options.get("base_url") or settings.SITE_URL).rstrip("/")
        if not base_url:
            raise CommandError("Set SITE_URL or pass --base-url.")

        url = base_url + reverse(
            "telegram_webhook",
            kwargs={"secret": settings.TELEGRAM_WEBHOOK_SECRET},
        )
        result = set_webhook(url)

        if not result or not result.get("ok"):
            raise CommandError(f"Telegram rejected the webhook: {result}")

        self.stdout.write(self.style.SUCCESS(f"Telegram webhook set: {url}"))
