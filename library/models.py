from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    ACCESS_NONE = "none"
    ACCESS_PENDING = "pending"
    ACCESS_APPROVED = "approved"
    ACCESS_REJECTED = "rejected"

    ACCESS_CHOICES = [
        (ACCESS_NONE, "None"),
        (ACCESS_PENDING, "Pending"),
        (ACCESS_APPROVED, "Approved"),
        (ACCESS_REJECTED, "Rejected"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    access_status = models.CharField(
        max_length=20,
        choices=ACCESS_CHOICES,
        default=ACCESS_NONE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.access_status}"


class AccessRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    book = models.ForeignKey(
        "PDFBook",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_access_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "book"],
                name="unique_user_book_access_request",
            )
        ]

    def __str__(self):
        book_title = self.book.title if self.book_id else "No book"
        return f"{self.user.username} - {book_title} - {self.status}"


class PDFBook(models.Model):
    title = models.CharField(max_length=150)
    pdf_file = models.FileField(upload_to="protected_pdfs/")
    thumbnail = models.FileField(
        upload_to="book_thumbnails/",
        null=True,
        blank=True,
    )
    original_filename = models.CharField(max_length=255)
    thumbnail_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_books",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    @property
    def filename(self):
        return self.original_filename

    @property
    def cover_filename(self):
        return self.thumbnail_filename

    def __str__(self):
        return self.title


class TelegramAdmin(models.Model):
    username = models.CharField(max_length=64, unique=True)
    chat_id = models.BigIntegerField(null=True, blank=True)
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    registered_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return f"@{self.username}"
