import os
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

CURRENT_ENV = (
    os.environ.get("DJANGO_ENV")
    or ("production" if os.environ.get("DJANGO_DEBUG") == "0" else "development")
).lower()
SETTINGS_MODULE = os.environ.get("DJANGO_SETTINGS_MODULE", "")
IS_PRODUCTION = CURRENT_ENV == "production" or SETTINGS_MODULE.endswith(".production")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_optional_int(name, default=None):
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"", "0", "none", "unlimited"}:
        return None
    return int(value)


DEBUG = False if IS_PRODUCTION else env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-change-this-secret"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required in production.")

SITE_URL = os.environ.get("SITE_URL", "")
HAS_WHITENOISE = find_spec("whitenoise") is not None

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "library.apps.LibraryConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if HAS_WHITENOISE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "pdfsite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "pdfsite.wsgi.application"
ASGI_APPLICATION = "pdfsite.asgi.application"


def postgres_database_config(name, user, password, host, port="5432", sslmode="require"):
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": user,
        "PASSWORD": password,
        "HOST": host,
        "PORT": port or "5432",
    }
    if sslmode:
        config["OPTIONS"] = {"sslmode": sslmode}
    return config


DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=os.environ.get("DB_SSL_REQUIRE", "1") == "1",
        )
    }
elif os.environ.get("DB_ENGINE") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "simple_pdf_site"),
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
elif DEBUG or env_bool("ALLOW_SQLITE_IN_PRODUCTION", False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured(
        "A production database is required. Set DATABASE_URL, or explicitly set "
        "ALLOW_SQLITE_IN_PRODUCTION=1 for a temporary test deployment."
    )

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = os.environ.get("STATIC_URL", "/static/")
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "private_media"))
MEDIA_URL = os.environ.get("MEDIA_URL", "/media/")
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
cloudinary_storage_flag = os.environ.get("USE_CLOUDINARY_STORAGE", "")
USE_CLOUDINARY_STORAGE = cloudinary_storage_flag == "1" or (
    not cloudinary_storage_flag and bool(CLOUDINARY_URL)
)
CLOUDINARY_STORAGE_PREFIX = os.environ.get("CLOUDINARY_STORAGE_PREFIX", "pdf-library")
CLOUDINARY_DOWNLOAD_TIMEOUT = int(os.environ.get("CLOUDINARY_DOWNLOAD_TIMEOUT", "20"))
CLOUDINARY_UPLOAD_CHUNK_SIZE = int(os.environ.get("CLOUDINARY_UPLOAD_CHUNK_SIZE", str(6 * 1024 * 1024)))

if USE_CLOUDINARY_STORAGE:
    cloudinary_parts = {
        "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
        "API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
        "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
        "SECURE": True,
    }
    if not CLOUDINARY_URL and not all(
        cloudinary_parts[key] for key in ("CLOUD_NAME", "API_KEY", "API_SECRET")
    ):
        raise ImproperlyConfigured(
            "Cloudinary storage is enabled. Set CLOUDINARY_URL, or set "
            "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
        )
    try:
        import cloudinary
    except ImportError as exc:
        raise ImproperlyConfigured(
            "Cloudinary storage is enabled, but the cloudinary package is not installed."
        ) from exc

    if CLOUDINARY_URL:
        parsed_cloudinary_url = urlparse(CLOUDINARY_URL)
        if not (
            parsed_cloudinary_url.hostname
            and parsed_cloudinary_url.username
            and parsed_cloudinary_url.password
        ):
            raise ImproperlyConfigured(
                "CLOUDINARY_URL must look like cloudinary://API_KEY:API_SECRET@CLOUD_NAME."
            )
        cloudinary.config(
            cloud_name=parsed_cloudinary_url.hostname,
            api_key=unquote(parsed_cloudinary_url.username or ""),
            api_secret=unquote(parsed_cloudinary_url.password or ""),
            secure=True,
        )
    else:
        cloudinary.config(
            cloud_name=cloudinary_parts["CLOUD_NAME"],
            api_key=cloudinary_parts["API_KEY"],
            api_secret=cloudinary_parts["API_SECRET"],
            secure=True,
        )

STORAGES = {
    "default": {
        "BACKEND": (
            "library.storage.CloudinaryRawStorage"
            if USE_CLOUDINARY_STORAGE
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG and HAS_WHITENOISE
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
LOGIN_URL = "login"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    CSRF_TRUSTED_ORIGINS.append(f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}")

MAX_UPLOAD_SIZE = env_optional_int("MAX_UPLOAD_SIZE", None)
MAX_THUMBNAIL_SIZE = env_optional_int("MAX_THUMBNAIL_SIZE", 12 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_optional_int("DATA_UPLOAD_MAX_MEMORY_SIZE", None)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_optional_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 0) or 0
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_ADMIN_USERNAMES = env_list("TELEGRAM_ADMIN_USERNAMES", "")
MAX_TELEGRAM_ADMINS = int(os.environ.get("MAX_TELEGRAM_ADMINS", "2"))
TELEGRAM_API_TIMEOUT = int(os.environ.get("TELEGRAM_API_TIMEOUT", "8"))
