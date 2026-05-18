import os
import sys


def default_environment():
    is_render_service = bool(
        os.environ.get("RENDER")
        or os.environ.get("RENDER_EXTERNAL_HOSTNAME")
        or os.environ.get("RENDER_SERVICE_ID")
        or os.environ.get("RENDER_SERVICE_NAME")
    )
    return os.environ.get("DJANGO_ENV") or (
        "production" if os.environ.get("DJANGO_DEBUG") == "0" or is_render_service else "development"
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
