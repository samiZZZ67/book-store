import os
import sys


def default_environment():
    return os.environ.get("DJANGO_ENV") or (
        "production" if os.environ.get("WEBSITE_HOSTNAME") else "development"
    )


def main():
    env = default_environment()
    settings_module = f"pdfsite.settings.{env}"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(...) from exc
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
