from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from library.storage import CloudinaryRawStorage


class Command(BaseCommand):
    help = "Check Cloudinary media storage credentials and raw upload/delete access."

    def add_arguments(self, parser):
        parser.add_argument(
            "--write-test",
            action="store_true",
            help="Upload and delete a tiny raw test asset.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Cloudinary configuration")
        self.stdout.write(f"  Enabled: {settings.USE_CLOUDINARY_STORAGE}")
        self.stdout.write(f"  CLOUDINARY_URL: {'set' if settings.CLOUDINARY_URL else 'missing'}")
        self.stdout.write(f"  Prefix: {settings.CLOUDINARY_STORAGE_PREFIX or '(none)'}")

        if not settings.USE_CLOUDINARY_STORAGE:
            self.stdout.write(self.style.WARNING("  Cloudinary storage is not enabled."))
            return

        import cloudinary
        import cloudinary.api
        import cloudinary.exceptions

        config = cloudinary.config()
        self.stdout.write(f"  Cloud name: {config.cloud_name or '(missing)'}")
        self.stdout.write(f"  API key: {config.api_key or '(missing)'}")
        self.stdout.write(f"  API secret: {'set' if config.api_secret else 'missing'}")

        try:
            result = cloudinary.api.ping()
            if result.get("status") == "ok":
                self.stdout.write(self.style.SUCCESS("  Admin API ping: ok"))
            else:
                self.stdout.write(self.style.WARNING(f"  Admin API ping response: {result}"))
        except cloudinary.exceptions.Error as exc:
            self.stdout.write(self.style.ERROR(f"  Admin API ping failed: {exc}"))
            return

        if not options["write_test"]:
            self.stdout.write("  Run with --write-test to verify upload and delete.")
            return

        storage = CloudinaryRawStorage()
        name = "_diagnostics/cloudinary-delete-test.txt"
        try:
            if storage.exists(name):
                storage.delete(name)
            storage.save(name, ContentFile(b"cloudinary storage test\n"))
            storage.delete(name)
        except cloudinary.exceptions.Error as exc:
            self.stdout.write(self.style.ERROR(f"  Raw upload/delete test failed: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS("  Raw upload/delete test: ok"))
