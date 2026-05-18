import json
import tempfile
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import AccessRequest, PDFBook, TelegramAdmin, UserProfile
from .storage import CloudinaryDeliveryError, CloudinaryRawStorage, cloudinary_file_response
from .views import exceeds_size_limit


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

    def test_admin_can_open_pdf_in_browser_viewer(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("open_pdf", args=[self.book.id]))

        self.assertEqual(response.status_code, 302)
        redirect_url = urlparse(response["Location"])
        self.assertEqual(redirect_url.path, reverse("pdf_stream", args=[self.book.id]))
        token = parse_qs(redirect_url.query).get("token", [""])[0]
        self.assertTrue(token)
        self.assertEqual(
            self.client.session["pdf_tokens"][str(self.book.id)]["token"],
            token,
        )

    def test_approved_user_cannot_open_pdf_in_browser_viewer(self):
        AccessRequest.objects.create(
            user=self.user,
            book=self.book,
            status=AccessRequest.STATUS_APPROVED,
            decided_by=self.admin,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("open_pdf", args=[self.book.id]))

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("pdf_tokens", self.client.session)

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

    def test_thumbnail_delivery_failure_returns_controlled_error(self):
        self.book.thumbnail.name = "book_thumbnails/missing.jpg"
        self.book.thumbnail_filename = "missing.jpg"
        self.book.save(update_fields=["thumbnail", "thumbnail_filename", "updated_at"])

        with patch(
            "django.db.models.fields.files.FieldFile.open",
            side_effect=Exception("storage unavailable"),
        ):
            response = self.client.get(reverse("book_thumbnail", args=[self.book.id]))

        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Could not load this thumbnail", response.content)

    def test_admin_ajax_pdf_upload_returns_redirect_payload(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("upload_pdf"),
            {
                "title": "Operating Systems",
                "pdf": SimpleUploadedFile(
                    "operating-systems.pdf",
                    b"%PDF-1.4\n% uploaded pdf\n",
                    content_type="application/pdf",
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], reverse("admin_dashboard"))
        self.assertTrue(PDFBook.objects.filter(title="Operating Systems").exists())

    def test_admin_ajax_pdf_upload_returns_storage_error(self):
        self.client.force_login(self.admin)

        with patch(
            "library.views.PDFBook.objects.create",
            side_effect=Exception("Invalid Signature"),
        ):
            response = self.client.post(
                reverse("upload_pdf"),
                {
                    "title": "Operating Systems",
                    "pdf": SimpleUploadedFile(
                        "operating-systems.pdf",
                        b"%PDF-1.4\n% uploaded pdf\n",
                        content_type="application/pdf",
                    ),
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("PDF upload failed", response.json()["error"])
        self.assertIn("Invalid Signature", response.json()["error"])

    def test_upload_size_limit_can_be_disabled(self):
        uploaded_file = SimpleUploadedFile(
            "large.pdf",
            b"%PDF-1.4\n" + b"x" * 2048,
            content_type="application/pdf",
        )

        self.assertFalse(exceeds_size_limit(uploaded_file, None))
        self.assertFalse(exceeds_size_limit(uploaded_file, 0))
        self.assertTrue(exceeds_size_limit(uploaded_file, 1024))

    @override_settings(CLOUDINARY_UPLOAD_CHUNK_SIZE=6 * 1024 * 1024)
    def test_cloudinary_storage_uses_chunked_raw_upload(self):
        storage = CloudinaryRawStorage()

        with patch.object(storage, "exists", return_value=False), patch(
            "cloudinary.uploader.upload_large",
            return_value={"public_id": "ok"},
        ) as upload:
            saved_name = storage.save(
                "protected_pdfs/example.pdf",
                ContentFile(b"%PDF-1.4\n" + b"0" * 128),
            )

        self.assertEqual(saved_name, "protected_pdfs/example.pdf")
        upload.assert_called_once()
        _, kwargs = upload.call_args
        self.assertEqual(kwargs["resource_type"], "raw")
        self.assertEqual(kwargs["chunk_size"], 6 * 1024 * 1024)
        self.assertEqual(kwargs["public_id"], "pdf-library/protected_pdfs/example.pdf")

    def test_cloudinary_file_response_falls_back_to_signed_download(self):
        class FakeResponse:
            status = 200
            headers = {"Content-Length": "8"}

            def read(self, size=-1):
                return b""

            def close(self):
                pass

        forbidden = HTTPError("https://public.example/file.pdf", 403, "Forbidden", {}, None)
        fake_response = FakeResponse()

        with patch("library.storage.CloudinaryRawStorage.url", return_value="https://public.example/file.pdf"), patch(
            "cloudinary.utils.private_download_url",
            return_value="https://private.example/file",
        ), patch(
            "library.storage.open_cloudinary_url",
            side_effect=[forbidden, fake_response],
        ) as open_url:
            response, headers = cloudinary_file_response("protected_pdfs/example.pdf")

        self.assertIs(response, fake_response)
        self.assertEqual(headers["Content-Length"], "8")
        self.assertEqual(open_url.call_args_list[1].args[0], "https://private.example/file")

    def test_pdf_stream_supports_byte_range_requests(self):
        AccessRequest.objects.create(
            user=self.user,
            book=self.book,
            status=AccessRequest.STATUS_APPROVED,
            decided_by=self.admin,
        )
        self.client.force_login(self.user)
        self.client.get(reverse("viewer", args=[self.book.id]))
        token_data = self.client.session["pdf_tokens"][str(self.book.id)]

        response = self.client.get(
            reverse("pdf_stream", args=[self.book.id]),
            {"token": token_data["token"]},
            HTTP_RANGE="bytes=0-3",
        )
        body = b"".join(response.streaming_content)
        response.close()

        self.assertEqual(response.status_code, 206)
        self.assertEqual(body, b"%PDF")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(response["Content-Length"], "4")
        self.assertEqual(
            response["Content-Range"],
            f"bytes 0-3/{self.book.pdf_file.size}",
        )

    @override_settings(USE_CLOUDINARY_STORAGE=True)
    def test_pdf_stream_delivery_failure_returns_controlled_error(self):
        AccessRequest.objects.create(
            user=self.user,
            book=self.book,
            status=AccessRequest.STATUS_APPROVED,
            decided_by=self.admin,
        )
        self.client.force_login(self.user)
        self.client.get(reverse("viewer", args=[self.book.id]))
        token_data = self.client.session["pdf_tokens"][str(self.book.id)]

        with patch(
            "library.views.cloudinary_file_response",
            side_effect=CloudinaryDeliveryError("Cloudinary blocked PDF delivery"),
        ):
            response = self.client.get(
                reverse("pdf_stream", args=[self.book.id]),
                {"token": token_data["token"]},
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Cloudinary blocked PDF delivery", response.content)

    @override_settings(USE_CLOUDINARY_STORAGE=True)
    def test_pdf_stream_slices_cloudinary_full_response_for_range_request(self):
        class FakeRemoteResponse:
            status = 200

            def __init__(self, payload):
                self.payload = BytesIO(payload)

            def read(self, size=-1):
                return self.payload.read(size)

            def close(self):
                pass

        AccessRequest.objects.create(
            user=self.user,
            book=self.book,
            status=AccessRequest.STATUS_APPROVED,
            decided_by=self.admin,
        )
        self.client.force_login(self.user)
        self.client.get(reverse("viewer", args=[self.book.id]))
        token_data = self.client.session["pdf_tokens"][str(self.book.id)]
        payload = b"0123456789abcdef"

        with patch(
            "library.views.cloudinary_range_response",
            return_value=(FakeRemoteResponse(payload), {"Content-Length": str(len(payload))}),
        ):
            response = self.client.get(
                reverse("pdf_stream", args=[self.book.id]),
                {"token": token_data["token"]},
                HTTP_RANGE="bytes=5-8",
            )
            body = b"".join(response.streaming_content)
            response.close()

        self.assertEqual(response.status_code, 206)
        self.assertEqual(body, b"5678")
        self.assertEqual(response["Content-Length"], "4")
        self.assertEqual(response["Content-Range"], f"bytes 5-8/{self.book.pdf_file.size}")

    def test_delete_book_does_not_crash_when_storage_cleanup_fails(self):
        self.client.force_login(self.admin)

        with patch(
            "library.views.delete_stored_file",
            return_value=(False, "Invalid Signature"),
        ):
            response = self.client.post(reverse("delete_book", args=[self.book.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))
        self.assertFalse(PDFBook.objects.filter(id=self.book.id).exists())

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

    @override_settings(
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_WEBHOOK_SECRET="secret",
        TELEGRAM_ADMIN_USERNAMES=[],
    )
    def test_admin_can_set_telegram_webhook_from_dashboard(self):
        self.client.force_login(self.admin)

        with patch("library.views.set_webhook", return_value={"ok": True}) as set_webhook:
            response = self.client.post(reverse("setup_telegram_webhook"), secure=True)

        self.assertRedirects(response, reverse("admin_dashboard"))
        set_webhook.assert_called_once()
        self.assertEqual(
            set_webhook.call_args.args[0],
            "https://testserver/telegram/webhook/secret/",
        )

    @override_settings(TELEGRAM_BOT_TOKEN="token", TELEGRAM_ADMIN_USERNAMES=[])
    def test_admin_can_sync_pending_telegram_start_messages(self):
        self.client.force_login(self.admin)

        with patch(
            "library.views.sync_pending_updates",
            return_value={"ok": True, "processed": 1, "registered": 1, "error": None},
        ) as sync_updates:
            response = self.client.post(reverse("sync_telegram_updates"))

        self.assertRedirects(response, reverse("admin_dashboard"))
        sync_updates.assert_called_once()
