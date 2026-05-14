#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput

if [[ -n "${DJANGO_ADMIN_USERNAME:-}" && -n "${DJANGO_ADMIN_EMAIL:-}" && -n "${DJANGO_ADMIN_PASSWORD:-}" ]]; then
  python manage.py create_admin \
    --username "$DJANGO_ADMIN_USERNAME" \
    --email "$DJANGO_ADMIN_EMAIL" \
    --password "$DJANGO_ADMIN_PASSWORD"
fi

gunicorn pdfsite.wsgi:application --bind 0.0.0.0:${PORT:-8000}
