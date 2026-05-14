import secrets
import json
import mimetypes
import logging
from io import BytesIO
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import get_valid_filename
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import AccessRequest, PDFBook, TelegramAdmin, UserProfile
from .storage import cloudinary_file_response, cloudinary_range_response
from .telegram import (
    configured_admin_usernames,
    is_valid_telegram_username,
    normalize_telegram_username,
    notify_access_request,
    register_admin_from_update,
    registered_telegram_admins,
    set_webhook,
    sync_configured_admins,
    sync_pending_updates,
    webhook_url,
)


logger = logging.getLogger(__name__)
PDF_TOKEN_MINUTES = 10
PDF_STREAM_CHUNK_SIZE = 64 * 1024
UNSATISFIABLE_RANGE = object()
THUMBNAIL_OUTPUT_SIZE = (480, 640)
THUMBNAIL_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}
THUMBNAIL_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def current_account(request):
    if not request.user.is_authenticated:
        return None

    profile = ensure_profile(request.user)
    return {
        "id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "is_admin": request.user.is_staff or request.user.is_superuser,
        "access_status": profile.access_status,
    }


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("Admin access required.")
        return view_func(request, *args, **kwargs)

    return wrapper


def is_admin_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def user_can_read(user, book):
    if not user.is_authenticated:
        return False
    if is_admin_user(user):
        return True
    return AccessRequest.objects.filter(
        user=user,
        book=book,
        status=AccessRequest.STATUS_APPROVED,
    ).exists()


def clean_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return ""


def wants_json_response(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def redirect_or_json(request, view_name):
    redirect_url = reverse(view_name)
    if wants_json_response(request):
        return JsonResponse({"redirect_url": redirect_url})
    return redirect(redirect_url)


def book_access_label(status, is_admin=False):
    if is_admin:
        return "Admin access"

    labels = {
        "login_required": "Login required",
        UserProfile.ACCESS_NONE: "Not requested",
        AccessRequest.STATUS_PENDING: "Pending approval",
        AccessRequest.STATUS_APPROVED: "Approved",
        AccessRequest.STATUS_REJECTED: "Rejected",
    }
    return labels.get(status, "Not requested")


def thumbnail_url_for(book):
    if not book.thumbnail:
        return ""
    return reverse("book_thumbnail", kwargs={"book_id": str(book.id)})


def validate_thumbnail(uploaded_file):
    if not uploaded_file:
        return True, ""

    if uploaded_file.size > settings.MAX_THUMBNAIL_SIZE:
        return False, "Thumbnail image is too large."

    filename = get_valid_filename(uploaded_file.name)
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    signatures = THUMBNAIL_SIGNATURES.get(extension)
    if not signatures:
        return False, "Thumbnail must be JPG, PNG, GIF, or WebP."

    header = uploaded_file.read(16)
    uploaded_file.seek(0)
    if not any(header.startswith(signature) for signature in signatures):
        return False, "Thumbnail file does not match its image type."

    if extension == ".webp" and header[8:12] != b"WEBP":
        return False, "Thumbnail file is not a valid WebP image."

    uploaded_file.name = filename
    return True, ""


def resized_thumbnail(uploaded_file):
    if not uploaded_file:
        return None, ""

    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        return None, "Install Pillow to resize thumbnail images."

    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        image = ImageOps.fit(
            image,
            THUMBNAIL_OUTPUT_SIZE,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    except (OSError, UnidentifiedImageError):
        uploaded_file.seek(0)
        return None, "Thumbnail image could not be processed."

    has_transparency = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_transparency:
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "#ffffff")
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    output = BytesIO()
    image.save(output, format="JPEG", quality=86, optimize=True, progressive=True)
    output.seek(0)

    base_name = get_valid_filename(uploaded_file.name).rsplit(".", 1)[0] or "thumbnail"
    return ContentFile(output.getvalue(), name=f"{base_name}.jpg"), ""


def delete_stored_file(file_field):
    if not file_field:
        return True, ""

    name = file_field.name
    try:
        file_field.delete(save=False)
    except Exception as exc:
        logger.warning("Could not delete stored file %s: %s", name, exc)
        return False, f"{name}: {exc}"

    return True, ""


def book_status_map(user, books):
    if not user or not user.is_authenticated or is_admin_user(user):
        return {}

    book_ids = [book.id for book in books]
    if not book_ids:
        return {}

    return dict(
        AccessRequest.objects.filter(user=user, book_id__in=book_ids).values_list(
            "book_id",
            "status",
        )
    )


def book_list(user=None):
    books = list(PDFBook.objects.all().order_by("title"))
    status_by_book = book_status_map(user, books)
    authenticated = bool(user and user.is_authenticated)
    admin = bool(user and is_admin_user(user))

    book_rows = []
    for book in books:
        if admin:
            access_status = AccessRequest.STATUS_APPROVED
        elif authenticated:
            access_status = status_by_book.get(book.id, UserProfile.ACCESS_NONE)
        else:
            access_status = "login_required"

        can_read = admin or access_status == AccessRequest.STATUS_APPROVED
        can_request = authenticated and not admin and access_status in {
            UserProfile.ACCESS_NONE,
            AccessRequest.STATUS_REJECTED,
        }

        book_rows.append(
            {
                "id": book.id,
                "title": book.title,
                "created_at": book.created_at,
                "thumbnail_url": thumbnail_url_for(book),
                "access_status": access_status,
                "access_label": book_access_label(access_status, admin),
                "can_read": can_read,
                "can_request": can_request,
                "request_button_label": (
                    "Request Again"
                    if access_status == AccessRequest.STATUS_REJECTED
                    else "Request Access"
                ),
            }
        )

    return book_rows


def request_list():
    requests = []
    cursor = AccessRequest.objects.select_related("user", "book").filter(
        book__isnull=False
    )
    for access_request in cursor:
        requests.append(
            {
                "id": access_request.id,
                "username": access_request.user.username,
                "email": access_request.user.email,
                "book_title": access_request.book.title,
                "status": access_request.status,
                "created_at": access_request.created_at,
                "decided_at": access_request.decided_at,
            }
        )
    return requests


def admin_book_list():
    return [
        {
            "id": book.id,
            "title": book.title,
            "filename": book.filename,
            "thumbnail_filename": book.cover_filename,
            "thumbnail_url": thumbnail_url_for(book),
            "created_at": book.created_at,
        }
        for book in PDFBook.objects.all().order_by("-created_at")
    ]


def telegram_admin_list():
    sync_configured_admins()
    configured_usernames = set(configured_admin_usernames())
    return [
        {
            "id": admin.id,
            "username": admin.username,
            "chat_id": admin.chat_id,
            "registered_at": admin.registered_at,
            "is_configured": admin.username in configured_usernames,
        }
        for admin in registered_telegram_admins()
    ]


def configure_telegram_webhook(request):
    if not settings.TELEGRAM_BOT_TOKEN:
        return False, "TELEGRAM_BOT_TOKEN is missing."
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        return False, "TELEGRAM_WEBHOOK_SECRET is missing."

    url = webhook_url(request)
    if not url.startswith("https://"):
        return (
            False,
            "Telegram requires a public HTTPS webhook URL. Deploy the site or set SITE_URL "
            "to your HTTPS domain, then set the webhook.",
        )

    result = set_webhook(url)
    if result and result.get("ok"):
        return True, f"Telegram webhook set to {url}"
    return False, f"Telegram rejected the webhook: {result}"


def home(request):
    return render(
        request,
        "library/home.html",
        {
            "current_user": current_account(request),
            "books": book_list(request.user),
        },
    )


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not username or not email or not password:
            messages.error(request, "Username, email, and password are required.")
            return redirect("signup")

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("signup")

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email already exists.")
            return redirect("signup")

        user = User.objects.create_user(username=username, email=email, password=password)
        UserProfile.objects.create(user=user)
        messages.success(request, "Sign up complete. Please log in.")
        return redirect("login")

    return render(request, "library/signup.html", {"current_user": current_account(request)})


def login_view(request):
    if request.method == "POST":
        login_id = request.POST.get("login", "").strip()
        password = request.POST.get("password", "")
        lookup = login_id.lower()
        user_record = User.objects.filter(username__iexact=lookup).first()

        if not user_record:
            user_record = User.objects.filter(email__iexact=lookup).first()

        user = None
        if user_record:
            user = authenticate(request, username=user_record.username, password=password)

        if not user:
            messages.error(request, "Invalid login details.")
            return redirect("login")

        login(request, user)
        messages.success(request, "Logged in.")

        next_url = clean_next_url(request)
        if next_url:
            return redirect(next_url)
        if user.is_staff or user.is_superuser:
            return redirect("admin_dashboard")
        return redirect("home")

    return render(
        request,
        "library/login.html",
        {"current_user": current_account(request), "next": clean_next_url(request)},
    )


def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def request_access(request):
    if request.method == "POST":
        messages.error(request, "Choose a book and use its request button.")
        return redirect("request_access")

    return render(
        request,
        "library/request_access.html",
        {
            "current_user": current_account(request),
            "books": book_list(request.user),
        },
    )


@require_POST
@login_required
def request_book_access(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)

    if is_admin_user(request.user):
        messages.info(request, "Admin access can already read this book.")
        return redirect("home")

    access_request = AccessRequest.objects.filter(user=request.user, book=book).first()
    if access_request and access_request.status == AccessRequest.STATUS_APPROVED:
        messages.info(request, "You are already approved to read this book.")
        return redirect("home")

    if access_request and access_request.status == AccessRequest.STATUS_PENDING:
        messages.info(request, "Your request for this book is already pending.")
        return redirect("home")

    if access_request:
        access_request.status = AccessRequest.STATUS_PENDING
        access_request.decided_by = None
        access_request.decided_at = None
        access_request.created_at = timezone.now()
        access_request.save(
            update_fields=["status", "decided_by", "decided_at", "created_at"]
        )
    else:
        access_request = AccessRequest.objects.create(user=request.user, book=book)

    notify_access_request(access_request, request)
    messages.success(request, f"Access request sent for {book.title}.")
    return redirect("home")


@admin_required
def admin_dashboard(request):
    return render(
        request,
        "library/admin_dashboard.html",
        {
            "current_user": current_account(request),
            "requests": request_list(),
            "books": admin_book_list(),
            "telegram_admins": telegram_admin_list(),
            "telegram_bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "telegram_webhook_configured": bool(settings.TELEGRAM_WEBHOOK_SECRET),
            "telegram_webhook_path": reverse(
                "telegram_webhook",
                kwargs={"secret": settings.TELEGRAM_WEBHOOK_SECRET or "your-secret"},
            ),
            "telegram_webhook_url": webhook_url(request),
            "max_telegram_admins": settings.MAX_TELEGRAM_ADMINS,
        },
    )


@require_POST
@admin_required
def add_telegram_admin(request):
    username = normalize_telegram_username(request.POST.get("telegram_username", ""))

    if not username or not is_valid_telegram_username(username):
        messages.error(request, "Enter a valid Telegram username without spaces.")
        return redirect("admin_dashboard")

    existing = TelegramAdmin.objects.filter(username=username).first()
    active_count = TelegramAdmin.objects.filter(is_active=True).count()
    would_add_active_slot = not existing or not existing.is_active
    if would_add_active_slot and active_count >= settings.MAX_TELEGRAM_ADMINS:
        messages.error(request, f"Only {settings.MAX_TELEGRAM_ADMINS} Telegram admins are allowed.")
        return redirect("admin_dashboard")

    TelegramAdmin.objects.update_or_create(
        username=username,
        defaults={"is_active": True},
    )
    webhook_ready, webhook_message = configure_telegram_webhook(request)
    if webhook_ready:
        messages.info(request, webhook_message)
    elif settings.TELEGRAM_BOT_TOKEN:
        messages.warning(request, webhook_message)

    messages.success(
        request,
        f"@{username} added. Ask this admin to send /start to the Telegram bot.",
    )
    return redirect("admin_dashboard")


@require_POST
@admin_required
def setup_telegram_webhook(request):
    webhook_ready, webhook_message = configure_telegram_webhook(request)
    if webhook_ready:
        messages.success(request, webhook_message)
    else:
        messages.error(request, webhook_message)
    return redirect("admin_dashboard")


@require_POST
@admin_required
def sync_telegram_updates(request):
    result = sync_pending_updates()
    if result["ok"]:
        messages.success(
            request,
            "Processed "
            f"{result['processed']} Telegram update(s), registered "
            f"{result['registered']} chat ID(s).",
        )
    else:
        messages.error(
            request,
            "Could not read Telegram updates. If a webhook is active, send /start again "
            f"after setting the webhook. Telegram response: {result['error']}",
        )
    return redirect("admin_dashboard")


@require_POST
@admin_required
def remove_telegram_admin(request, admin_id):
    admin = get_object_or_404(TelegramAdmin, pk=admin_id)
    if admin.username in configured_admin_usernames():
        messages.error(request, f"@{admin.username} is configured by environment variable. Remove it there first.")
        return redirect("admin_dashboard")

    admin.delete()
    messages.success(request, f"@{admin.username} removed from Telegram notifications.")
    return redirect("admin_dashboard")


@csrf_exempt
@require_POST
def telegram_webhook(request, secret):
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_WEBHOOK_SECRET:
        return HttpResponseForbidden("Telegram webhook is not configured.")

    if not secrets.compare_digest(secret, settings.TELEGRAM_WEBHOOK_SECRET):
        return HttpResponseForbidden("Invalid webhook secret.")

    try:
        update = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    register_admin_from_update(update)
    return JsonResponse({"ok": True})


@require_POST
@admin_required
def upload_pdf(request):
    title = request.POST.get("title", "").strip()
    uploaded_file = request.FILES.get("pdf")
    thumbnail_file = request.FILES.get("thumbnail")

    if not title or not uploaded_file:
        messages.error(request, "Title and PDF file are required.")
        return redirect_or_json(request, "admin_dashboard")

    if uploaded_file.size > settings.MAX_UPLOAD_SIZE:
        messages.error(request, "PDF file is too large.")
        return redirect_or_json(request, "admin_dashboard")

    filename = get_valid_filename(uploaded_file.name)
    if not filename.lower().endswith(".pdf"):
        messages.error(request, "Only PDF files are allowed.")
        return redirect_or_json(request, "admin_dashboard")

    first_bytes = uploaded_file.read(4)
    uploaded_file.seek(0)
    if first_bytes != b"%PDF":
        messages.error(request, "The uploaded file is not a valid PDF.")
        return redirect_or_json(request, "admin_dashboard")

    thumbnail_valid, thumbnail_error = validate_thumbnail(thumbnail_file)
    if not thumbnail_valid:
        messages.error(request, thumbnail_error)
        return redirect_or_json(request, "admin_dashboard")
    thumbnail_file, thumbnail_error = resized_thumbnail(thumbnail_file)
    if thumbnail_error:
        messages.error(request, thumbnail_error)
        return redirect_or_json(request, "admin_dashboard")

    uploaded_file.name = filename
    thumbnail_filename = thumbnail_file.name if thumbnail_file else ""
    PDFBook.objects.create(
        title=title[:150],
        pdf_file=uploaded_file,
        thumbnail=thumbnail_file,
        original_filename=filename,
        thumbnail_filename=thumbnail_filename,
        uploaded_by=request.user,
    )
    messages.success(request, "PDF uploaded.")
    return redirect_or_json(request, "admin_dashboard")


@require_POST
@admin_required
def update_book_thumbnail(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)
    thumbnail_file = request.FILES.get("thumbnail")

    if not thumbnail_file:
        messages.error(request, "Choose an image thumbnail to upload.")
        return redirect_or_json(request, "admin_dashboard")

    thumbnail_valid, thumbnail_error = validate_thumbnail(thumbnail_file)
    if not thumbnail_valid:
        messages.error(request, thumbnail_error)
        return redirect_or_json(request, "admin_dashboard")
    thumbnail_file, thumbnail_error = resized_thumbnail(thumbnail_file)
    if thumbnail_error:
        messages.error(request, thumbnail_error)
        return redirect_or_json(request, "admin_dashboard")

    if book.thumbnail:
        deleted, delete_error = delete_stored_file(book.thumbnail)
        if not deleted:
            messages.warning(
                request,
                "The old thumbnail was replaced, but the previous stored file could "
                f"not be deleted: {delete_error}",
            )

    book.thumbnail = thumbnail_file
    book.thumbnail_filename = thumbnail_file.name
    book.save(update_fields=["thumbnail", "thumbnail_filename", "updated_at"])
    messages.success(request, f"Thumbnail updated for {book.title}.")
    return redirect_or_json(request, "admin_dashboard")


@require_POST
@admin_required
def remove_book_thumbnail(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)
    if book.thumbnail:
        deleted, delete_error = delete_stored_file(book.thumbnail)
        if not deleted:
            messages.warning(
                request,
                "Thumbnail was removed from the library, but the stored file could "
                f"not be deleted: {delete_error}",
            )
    book.thumbnail = None
    book.thumbnail_filename = ""
    book.save(update_fields=["thumbnail", "thumbnail_filename", "updated_at"])
    messages.success(request, f"Thumbnail removed for {book.title}.")
    return redirect("admin_dashboard")


@require_POST
@admin_required
def decide_request(request, request_id, decision):
    if decision not in {AccessRequest.STATUS_APPROVED, AccessRequest.STATUS_REJECTED}:
        raise Http404("Not found")

    access_request = get_object_or_404(
        AccessRequest.objects.select_related("user", "book"),
        pk=request_id,
    )
    access_request.status = decision
    access_request.decided_at = timezone.now()
    access_request.decided_by = request.user
    access_request.save(update_fields=["status", "decided_at", "decided_by"])

    if access_request.book_id:
        messages.success(request, f"Request {decision} for {access_request.book.title}.")
    else:
        messages.success(request, f"Request {decision}.")
    return redirect("admin_dashboard")


@require_POST
@admin_required
def delete_book(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)
    cleanup_errors = []

    deleted, delete_error = delete_stored_file(book.pdf_file)
    if not deleted:
        cleanup_errors.append(delete_error)

    if book.thumbnail:
        deleted, delete_error = delete_stored_file(book.thumbnail)
        if not deleted:
            cleanup_errors.append(delete_error)

    book.delete()
    if cleanup_errors:
        messages.warning(
            request,
            "PDF deleted from the library, but Cloudinary/file cleanup failed. "
            "Check storage credentials. Details: " + " | ".join(cleanup_errors[:2]),
        )
    else:
        messages.success(request, "PDF deleted.")
    return redirect("admin_dashboard")


@never_cache
def book_thumbnail(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)
    if not book.thumbnail:
        raise Http404("Thumbnail not found")

    content_type = (
        THUMBNAIL_CONTENT_TYPES.get("." + book.thumbnail.name.rsplit(".", 1)[-1].lower())
        or mimetypes.guess_type(book.thumbnail.name)[0]
        or "application/octet-stream"
    )
    response = FileResponse(book.thumbnail.open("rb"), content_type=content_type)
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
def viewer(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)
    if not user_can_read(request.user, book):
        messages.error(request, "Access approval is required to read this book.")
        return redirect("request_access")

    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(minutes=PDF_TOKEN_MINUTES)
    tokens = request.session.get("pdf_tokens", {})
    tokens[str(book.id)] = {"token": token, "expires": expires_at.timestamp()}
    request.session["pdf_tokens"] = tokens
    request.session.modified = True

    stream_url = (
        reverse("pdf_stream", kwargs={"book_id": str(book.id)})
        + f"?token={token}#toolbar=0&navpanes=0&scrollbar=1"
    )
    return render(
        request,
        "library/viewer.html",
        {
            "current_user": current_account(request),
            "book": {"id": book.id, "title": book.title},
            "stream_url": stream_url,
        },
    )


def valid_pdf_token(request, book_id):
    token = request.GET.get("token", "")
    saved = request.session.get("pdf_tokens", {}).get(book_id)
    if not saved or not token or token != saved.get("token"):
        return False

    expires = saved.get("expires")
    return bool(expires and timezone.now().timestamp() <= expires)


def parse_byte_range(range_header, file_size):
    if not range_header or not range_header.startswith("bytes="):
        return None

    range_spec = range_header[len("bytes="):].split(",", 1)[0].strip()
    if "-" not in range_spec:
        return None

    start_text, end_text = range_spec.split("-", 1)
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                return None
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
    except ValueError:
        return None

    if start < 0 or end < start:
        return None
    if start >= file_size:
        return UNSATISFIABLE_RANGE

    return start, min(end, file_size - 1)


def stream_protected_file(book, start=0, length=None):
    file_handle = book.pdf_file.open("rb")
    try:
        if start:
            file_handle.seek(start)

        remaining = length
        while True:
            read_size = PDF_STREAM_CHUNK_SIZE
            if remaining is not None:
                if remaining <= 0:
                    break
                read_size = min(read_size, remaining)

            chunk = file_handle.read(read_size)
            if not chunk:
                break
            if remaining is not None:
                remaining -= len(chunk)
            yield chunk
    finally:
        file_handle.close()


def stream_remote_file(remote_response):
    try:
        while True:
            chunk = remote_response.read(PDF_STREAM_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        remote_response.close()


@never_cache
@login_required
def pdf_stream(request, book_id):
    book = get_object_or_404(PDFBook, pk=book_id)
    if not user_can_read(request.user, book):
        return HttpResponseForbidden("Access approval is required for this book.")

    if not valid_pdf_token(request, str(book_id)):
        return HttpResponseForbidden("Open the PDF from the website viewer.")

    file_size = book.pdf_file.size
    byte_range = parse_byte_range(request.META.get("HTTP_RANGE", ""), file_size)

    if byte_range is UNSATISFIABLE_RANGE:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Content-Length"] = "0"
    elif byte_range:
        start, end = byte_range
        content_length = end - start + 1
        if settings.USE_CLOUDINARY_STORAGE:
            remote_response, remote_headers = cloudinary_range_response(
                book.pdf_file.name,
                start,
                end,
            )
            if remote_response is None:
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{file_size}"
                response["Content-Length"] = "0"
            else:
                response = StreamingHttpResponse(
                    stream_remote_file(remote_response),
                    status=206,
                    content_type="application/pdf",
                )
                response["Content-Length"] = remote_headers.get(
                    "Content-Length",
                    str(content_length),
                )
                response["Content-Range"] = remote_headers.get(
                    "Content-Range",
                    f"bytes {start}-{end}/{file_size}",
                )
        else:
            response = StreamingHttpResponse(
                stream_protected_file(book, start=start, length=content_length),
                status=206,
                content_type="application/pdf",
            )
            response["Content-Length"] = str(content_length)
            response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    else:
        if settings.USE_CLOUDINARY_STORAGE:
            remote_response, remote_headers = cloudinary_file_response(book.pdf_file.name)
            response = StreamingHttpResponse(
                stream_remote_file(remote_response),
                content_type="application/pdf",
            )
            response["Content-Length"] = remote_headers.get("Content-Length", str(file_size))
        else:
            response = StreamingHttpResponse(
                stream_protected_file(book),
                content_type="application/pdf",
            )
            response["Content-Length"] = str(file_size)

    response["Content-Disposition"] = 'inline; filename="protected.pdf"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["Accept-Ranges"] = "bytes"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "frame-ancestors 'self'; default-src 'self'"
    return response
