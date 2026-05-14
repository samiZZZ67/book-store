from django.conf import settings
from django.core.management.base import BaseCommand

from library.models import TelegramAdmin
from library.telegram import telegram_api_call, webhook_url


class Command(BaseCommand):
    help = "Show Telegram bot, webhook, and admin chat ID status."

    def handle(self, *args, **options):
        self.stdout.write("Telegram configuration")
        self.stdout.write(f"  Bot token: {'set' if settings.TELEGRAM_BOT_TOKEN else 'missing'}")
        self.stdout.write(
            f"  Webhook secret: {'set' if settings.TELEGRAM_WEBHOOK_SECRET else 'missing'}"
        )
        self.stdout.write(f"  SITE_URL: {settings.SITE_URL or '(not set)'}")
        self.stdout.write(f"  Expected webhook: {webhook_url() or '(not available)'}")

        if not settings.TELEGRAM_BOT_TOKEN:
            return

        bot = telegram_api_call("getMe")
        if bot and bot.get("ok"):
            result = bot.get("result", {})
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Bot: @{result.get('username', 'unknown')} ({result.get('first_name', 'unknown')})"
                )
            )
        else:
            self.stdout.write(self.style.ERROR(f"  getMe failed: {bot}"))

        webhook = telegram_api_call("getWebhookInfo")
        if webhook and webhook.get("ok"):
            result = webhook.get("result", {})
            self.stdout.write(f"  Telegram webhook URL: {result.get('url') or '(not set)'}")
            self.stdout.write(f"  Pending updates: {result.get('pending_update_count', 0)}")
            if result.get("last_error_message"):
                self.stdout.write(
                    self.style.ERROR(
                        f"  Last webhook error: {result.get('last_error_message')}"
                    )
                )
        else:
            self.stdout.write(self.style.ERROR(f"  getWebhookInfo failed: {webhook}"))

        admins = TelegramAdmin.objects.filter(is_active=True).order_by("username")
        if not admins:
            self.stdout.write("  Admins: none")
            return

        self.stdout.write("  Admins:")
        for admin in admins:
            chat_id = admin.chat_id or "waiting for /start"
            self.stdout.write(f"    @{admin.username}: {chat_id}")
