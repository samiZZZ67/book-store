from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.core.management.base import BaseCommand, CommandError

from library.models import PDFBook
from library.storage import CloudinaryRawStorage


class Command(BaseCommand):
    help = "Copy local private_media PDF and thumbnail files to Cloudinary."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace matching Cloudinary assets that already exist.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be uploaded without writing to Cloudinary.",
        )

    def handle(self, *args, **options):
        if not settings.USE_CLOUDINARY_STORAGE:
            raise CommandError(
                "Cloudinary storage is not enabled. Set CLOUDINARY_URL or "
                "USE_CLOUDINARY_STORAGE=1 before running this command."
            )

        media_root = Path(settings.MEDIA_ROOT)
        storage = CloudinaryRawStorage()
        force = options["force"]
        dry_run = options["dry_run"]
        uploaded = 0
        skipped = 0

        for book in PDFBook.objects.all().order_by("title"):
            for label, field in (("PDF", book.pdf_file), ("thumbnail", book.thumbnail)):
                if not field:
                    continue

                target_name = field.name
                source_path = media_root / target_name
                if not source_path.exists():
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(f"Missing local {label}: {source_path}")
                    )
                    continue

                if not force and storage.exists(target_name):
                    skipped += 1
                    self.stdout.write(f"Already in Cloudinary: {target_name}")
                    continue

                if dry_run:
                    uploaded += 1
                    self.stdout.write(f"Would upload {label}: {target_name}")
                    continue

                if force:
                    storage.delete(target_name)

                with source_path.open("rb") as handle:
                    storage.save(target_name, File(handle))

                uploaded += 1
                self.stdout.write(self.style.SUCCESS(f"Uploaded {label}: {target_name}"))

        action = "would upload" if dry_run else "uploaded"
        self.stdout.write(
            self.style.SUCCESS(
                f"Cloudinary media migration complete: {uploaded} {action}, {skipped} skipped."
            )
        )
