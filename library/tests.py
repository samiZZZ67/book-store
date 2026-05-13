import json
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import AccessRequest, PDFBook, TelegramAdmin, UserProfile


class BookAccessTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.settings_override.enable()

        self.user = User.objects.create_user(
            username="reader",
            email="reader@example.com",
            password="password123",
        )
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="password123",
            is_staff=True,
        )
        self.book = self.create_book("Database Systems", "database.pdf")

    def tearDown(self):
        self.settings_override.disable()
        self.media_root.cleanup()

    def create_book(self, title, filename):
        return PDFBook.objects.create(
            title=title,
            pdf_file=SimpleUploadedFile(
                filename,
                b"%PDF-1.4\n% test pdf\n",
                content_type="application/pdf",
            ),
            original_filename=filename,
            uploaded_by=self.admin,
        )

    def thumbnail_file(self, filename="cover.png"):
        image_file = BytesIO()
        image = Image.new("RGB", (1800, 2400), "#2c6f83")
        image.save(image_file, format="PNG")
        image_file.seek(0)
        return SimpleUploadedFile(
            filename,
            image_file.getvalue(),
            content_type="image/png",
        )

    def test_global_profile_approval_does_not_grant_book_access(self):
        UserProfile.objects.create(
            user=self.user,
            access_status=UserProfile.ACCESS_APPROVED,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("viewer", args=[self.book.id]))

        self.assertRedirects(response, reverse("request_access"))

    def test_book_request_can_be_approved_and_read(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("request_book_access", args=[self.book.id]))
        self.assertRedirects(response, reverse("home"))

        access_request = AccessRequest.objects.get(user=self.user, book=self.book)
        self.assertEqual(access_request.status, AccessRequest.STATUS_PENDING)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse(
                "decide_request",
                args=[access_request.id, AccessRequest.STATUS_APPROVED],
            )
        )
        self.assertRedirects(response, reverse("admin_dashboard"))

        self.client.force_login(self.user)
        response = self.client.get(reverse("viewer", args=[self.book.id]))
        self.assertEqual(response.status_code, 200)

        token_data = self.client.session["pdf_tokens"][str(self.book.id)]
        response = self.client.get(
            reverse("pdf_stream", args=[self.book.id]),
            {"token": token_data["token"]},
        )
        self.assertEqual(response.status_code, 200)

    def test_book_approval_does_not_apply_to_other_books(self):
        other_book = self.create_book("Python Basics", "python.pdf")
        AccessRequest.objects.create(
            user=self.user,
            book=self.book,
            status=AccessRequest.STATUS_APPROVED,
            decided_by=self.admin,
        )
        self.client.force_login(self.user)

        approved_response = self.client.get(reverse("viewer", args=[self.book.id]))
        blocked_response = self.client.get(reverse("viewer", args=[other_book.id]))

        self.assertEqual(approved_response.status_code, 200)
        self.assertRedirects(blocked_response, reverse("request_access"))

    def test_admin_can_upload_and_serve_book_thumbnail(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("update_book_thumbnail", args=[self.book.id]),
            {"thumbnail": self.thumbnail_file()},
        )

        self.assertRedirects(response, reverse("admin_dashboard"))
        self.book.refresh_from_db()
        self.assertEqual(self.book.thumbnail_filename, "cover.jpg")

        with self.book.thumbnail.open("rb") as thumbnail:
            image = Image.open(thumbnail)
            self.assertEqual(image.size, (480, 640))
            self.assertEqual(image.format, "JPEG")

        response = self.client.get(reverse("book_thumbnail", args=[self.book.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        response.close()

    @override_settings(TELEGRAM_BOT_TOKEN="token", TELEGRAM_ADMIN_USERNAMES=[])
    def test_book_request_sends_telegram_notification(self):
        TelegramAdmin.objects.create(username="siteadmin", chat_id=123456)
        self.client.force_login(self.user)

        with patch("library.telegram.telegram_api_call", return_value={"ok": True}) as api_call:
            response = self.client.post(reverse("request_book_access", args=[self.book.id]))

        self.assertRedirects(response, reverse("home"))
        api_call.assert_called()
        self.assertEqual(api_call.call_args.args[0], "sendMessage")

    @override_settings(
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_WEBHOOK_SECRET="secret",
        TELEGRAM_ADMIN_USERNAMES=[],
    )
    def test_telegram_webhook_registers_allowed_admin_chat_id(self):
        TelegramAdmin.objects.create(username="siteadmin")
        payload = {
            "message": {
                "from": {
                    "username": "siteadmin",
                    "first_name": "Site",
                    "last_name": "Admin",
                },
                "chat": {"id": 987654},
                "text": "/start",
            }
        }

        with patch("library.telegram.telegram_api_call", return_value={"ok": True}):
            response = self.client.post(
                reverse("telegram_webhook", args=["secret"]),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        telegram_admin = TelegramAdmin.objects.get(username="siteadmin")
        self.assertEqual(telegram_admin.chat_id, 987654)
