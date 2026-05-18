# pdfsite/settings/development.py
from .base import *

DEBUG = True
ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,0.0.0.0,::1,.onrender.com,book-store-b922.onrender.com",
)

# Optional: Use SQLite as default if DATABASE_URL is not set
if not DATABASE_URL and not os.environ.get("DB_ENGINE"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Make sure staticfiles storage uses non-compressed version for easier debugging
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Security relaxed for development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
