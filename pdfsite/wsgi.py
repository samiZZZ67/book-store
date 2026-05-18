import os
from django.core.wsgi import get_wsgi_application

env = os.environ.get("DJANGO_ENV") or (
    "production" if os.environ.get("WEBSITE_HOSTNAME") else "development"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"pdfsite.settings.{env}")

application = get_wsgi_application()
