import os
from django.core.wsgi import get_wsgi_application

is_render_service = bool(
    os.environ.get("RENDER")
    or os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    or os.environ.get("RENDER_SERVICE_ID")
    or os.environ.get("RENDER_SERVICE_NAME")
)
env = os.environ.get("DJANGO_ENV") or (
    "production" if os.environ.get("DJANGO_DEBUG") == "0" or is_render_service else "development"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"pdfsite.settings.{env}")

application = get_wsgi_application()
