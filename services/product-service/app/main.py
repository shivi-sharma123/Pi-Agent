#!/usr/bin/env python
"""
Product Service entrypoint.

Bootstraps Django, runs migrations, ensures the ES index exists,
and starts the Gunicorn/uvicorn WSGI server.
"""
import os
import sys
import django

# Configure Django settings before anything else
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config")

# Setup Django
django.setup()


def main():
    from django.core.management import call_command
    from app.models import ensure_index

    # Apply DB migrations
    call_command("migrate", "--run-syncdb", verbosity=0)
    print("DB migrations applied.")

    # Ensure Elasticsearch index exists
    try:
        ensure_index()
        print("Elasticsearch index ready.")
    except Exception as exc:
        print(f"WARN: Could not connect to ES at startup: {exc}")

    # Start the WSGI server
    port = os.getenv("PORT", "8003")
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()

    from gunicorn.app.base import BaseApplication

    class StandaloneApp(BaseApplication):
        def __init__(self, app, options=None):
            self.options = options or {}
            self.application = app
            super().__init__()

        def load_config(self):
            for key, value in self.options.items():
                self.cfg.set(key.lower(), value)

        def load(self):
            return self.application

    options = {
        "bind": f"0.0.0.0:{port}",
        "workers": int(os.getenv("GUNICORN_WORKERS", "2")),
        "worker_class": "sync",
        "timeout": 30,
        "accesslog": "-",
        "errorlog": "-",
        "loglevel": os.getenv("LOG_LEVEL", "info").lower(),
    }
    StandaloneApp(application, options).run()


if __name__ == "__main__":
    main()
