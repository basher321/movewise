"""Entry point for the cPanel Python app (spec B22).

cPanel (Passenger / LiteSpeed) speaks WSGI, so the FastAPI app is wrapped with a2wsgi.
a2wsgi does not run FastAPI's lifespan, so this file runs the same production start-up check
itself. Notifications are sent by the cron job (python -m app.notify.run --once), so the app
must run with NOTIFY_WORKER=off.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.engine import get_engine  # noqa: E402
from app.main import app as asgi_app  # noqa: E402
from app.production import check_production  # noqa: E402

_settings = get_settings()
if _settings.app_env == "production":
    with get_engine().connect() as _conn:
        check_production(_settings, _conn)

_wsgi = ASGIMiddleware(asgi_app)  # type: ignore[arg-type]


def application(environ, start_response):  # type: ignore[no-untyped-def]
    # The app is mounted at /api. Give FastAPI the full path (/api/...) with an empty root
    # path, because every route is declared with the /api prefix.
    environ["PATH_INFO"] = environ.get("SCRIPT_NAME", "") + environ.get("PATH_INFO", "")
    environ["SCRIPT_NAME"] = ""
    return _wsgi(environ, start_response)
