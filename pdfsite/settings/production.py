from .base import *

DEBUG = False


def append_unique(values, item):
    if item and item not in values:
        values.append(item)


def host_from_url(url):
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc


ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "")
for host in (
    os.environ.get("WEBSITE_HOSTNAME"),
    os.environ.get("RENDER_EXTERNAL_HOSTNAME"),
    host_from_url(SITE_URL),
):
    append_unique(ALLOWED_HOSTS, host)

# WhiteNoise serves collected static files directly from the Django app.
if HAS_WHITENOISE:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")
for host in ALLOWED_HOSTS:
    if host == "*":
        continue
    origin_host = f"*.{host.lstrip('.')}" if host.startswith(".") else host
    append_unique(CSRF_TRUSTED_ORIGINS, f"https://{origin_host}")

if SITE_URL and urlparse(SITE_URL).scheme and urlparse(SITE_URL).netloc:
    parsed_site = urlparse(SITE_URL)
    append_unique(
        CSRF_TRUSTED_ORIGINS,
        f"{parsed_site.scheme}://{parsed_site.netloc}",
    )
