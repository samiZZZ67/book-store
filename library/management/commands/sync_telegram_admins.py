from django.core.management.base import BaseCommand, CommandError

from library.telegram import sync_pending_updates


class Command(BaseCommand):
    help = "Read recent Telegram bot updates and register chat IDs for allowed admin usernames."

    def handle(self, *args, **options):
        result = sync_pending_updates()
        if not result["ok"]:
            raise CommandError(f"Could not read Telegram updates: {result['error']}")

        self.stdout.write(
            self.style.SUCCESS(
                "Processed "
                f"{result['processed']} update(s), registered "
                f"{result['registered']} admin chat(s)."
            )
        )
