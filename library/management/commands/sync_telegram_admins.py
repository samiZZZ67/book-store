import json

from django.core.management.base import BaseCommand, CommandError

from library.telegram import register_admin_from_update, telegram_api_call


class Command(BaseCommand):
    help = "Read recent Telegram bot updates and register chat IDs for allowed admin usernames."

    def handle(self, *args, **options):
        result = telegram_api_call(
            "getUpdates",
            {
                "timeout": "0",
                "allowed_updates": json.dumps(["message", "edited_message"]),
            },
        )
        if not result or not result.get("ok"):
            raise CommandError(f"Could not read Telegram updates: {result}")

        updates = result.get("result", [])
        registered = 0
        max_update_id = None
        for update in updates:
            if register_admin_from_update(update):
                registered += 1
            max_update_id = update.get("update_id", max_update_id)

        if max_update_id is not None:
            telegram_api_call("getUpdates", {"offset": str(max_update_id + 1), "timeout": "0"})

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(updates)} update(s), registered {registered} admin chat(s)."
            )
        )
