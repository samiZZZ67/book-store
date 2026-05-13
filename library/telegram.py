import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import TelegramAdmin


logger = logging.getLogger(__name__)
USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{5,32}$")


def normalize_telegram_username(username):
    return username.strip().lstrip("@").lower()


def is_valid_telegram_username(username):
    return bool(USERNAME_PATTERN.match(normalize_telegram_username(username)))


def configured_admin_usernames():
    usernames = []
    for username in settings.TELEGRAM_ADMIN_USERNAMES:
        normalized = normalize_telegram_username(username)
        if normalized and normalized not in usernames:
            usernames.append(normalized)
    return usernames[: settings.MAX_TELEGRAM_ADMINS]


def sync_configured_admins():
    for username in configured_admin_usernames():
        existing = TelegramAdmin.objects.filter(username=username).first()
        if existing:
            continue
        if TelegramAdmin.objects.filter(is_active=True).count() >= settings.MAX_TELEGRAM_ADMINS:
            break
        TelegramAdmin.objects.create(username=username)


def telegram_api_call(method, payload=None):
    if not settings.TELEGRAM_BOT_TOKEN:
        return None

    payload = payload or {}
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    data = urlencode(payload).encode("utf-8")
    request = Request(url, data=data, method="POST")

    try:
        with urlopen(request, timeout=settings.TELEGRAM_API_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        logger.warning("Telegram API call failed for %s: %s", method, exc)
        return None


def send_telegram_message(chat_id, text):
    return telegram_api_call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        },
    )


def allowed_admin_usernames():
    sync_configured_admins()
    return set(
        TelegramAdmin.objects.filter(is_active=True).values_list("username", flat=True)
    )


def registered_telegram_admins():
    sync_configured_admins()
    return TelegramAdmin.objects.filter(is_active=True).order_by("username")


def register_admin_from_update(update):
    message = update.get("message") or update.get("edited_message") or {}
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    username = normalize_telegram_username(sender.get("username", ""))
    chat_id = chat.get("id")

    if not username or not chat_id:
        return False

    if username not in allowed_admin_usernames():
        send_telegram_message(
            chat_id,
            "This Telegram username is not enabled for site notifications. Add it in the site admin dashboard first.",
        )
        return False

    now = timezone.now()
    TelegramAdmin.objects.update_or_create(
        username=username,
        defaults={
            "chat_id": chat_id,
            "first_name": sender.get("first_name", "")[:120],
            "last_name": sender.get("last_name", "")[:120],
            "is_active": True,
            "registered_at": now,
            "last_seen_at": now,
        },
    )
    send_telegram_message(
        chat_id,
        "Telegram notifications are connected for this PDF library.",
    )
    return True


def admin_dashboard_url(request=None):
    if request:
        return request.build_absolute_uri(reverse("admin_dashboard"))
    if settings.SITE_URL:
        return settings.SITE_URL.rstrip("/") + reverse("admin_dashboard")
    return reverse("admin_dashboard")


def notify_access_request(access_request, request=None):
    if not settings.TELEGRAM_BOT_TOKEN:
        return 0

    admins = registered_telegram_admins().exclude(chat_id__isnull=True)
    url = admin_dashboard_url(request)
    user = access_request.user
    book = access_request.book
    message = (
        "New book access request\n\n"
        f"User: {user.username}\n"
        f"Email: {user.email or 'No email'}\n"
        f"Book: {book.title if book else 'Unknown book'}\n"
        f"Status: {access_request.status.title()}\n\n"
        f"Review: {url}"
    )

    sent = 0
    for admin in admins:
        result = send_telegram_message(admin.chat_id, message)
        if result and result.get("ok"):
            sent += 1
    return sent
