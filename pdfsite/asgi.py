import os

from django.core.asgi import get_asgi_application


env = os.environ.get("DJANGO_ENV") or (
    "production" if os.environ.get("DJANGO_DEBUG") == "0" else "development"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"pdfsite.settings.{env}")

application = get_asgi_application()
