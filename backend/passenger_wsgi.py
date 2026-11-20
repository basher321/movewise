"""Entry point for the cPanel Python app (spec B22).

cPanel (Passenger / LiteSpeed) speaks WSGI, so the FastAPI app is wrapped with a2wsgi.
a2wsgi does not run FastAPI's lifespan, so this file runs the same production start-up check
itself. Notifications are sent by the cron job (python -m app.notify.run --once), so the app
must run with NOTIFY_WORKER=off.
"""

import os
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
# LiteSpeed loads this file once and then forks worker processes. Database connections and the
# a2wsgi event-loop thread do not survive a fork, so the start-up connection is closed here and
# each worker makes its own a2wsgi wrapper (and pool) on its first request.
get_engine().dispose()

_wsgi = None
_wsgi_pid = 0


def _wrapper() -> ASGIMiddleware:
    global _wsgi, _wsgi_pid
    if _wsgi is None or _wsgi_pid != os.getpid():
        get_engine().dispose(close=False)
        _wsgi = ASGIMiddleware(asgi_app)  # type: ignore[arg-type]
        _wsgi_pid = os.getpid()
    return _wsgi


def application(environ, start_response):  # type: ignore[no-untyped-def]
    # The app is mounted at /api. Give FastAPI the full path (/api/...) with an empty root
    # path, because every route is declared with the /api prefix. Servers differ: some pass
    # SCRIPT_NAME=/api and PATH_INFO=/health, LiteSpeed may pass the full path in PATH_INFO.
    script = environ.get("SCRIPT_NAME", "")
    path = environ.get("PATH_INFO", "") or "/"
    full = path if script and path.startswith(script + "/") else script + path
    if full != "/api" and not full.startswith("/api/"):
        full = "/api" + full
    environ["PATH_INFO"] = full
    environ["SCRIPT_NAME"] = ""
    return _wrapper()(environ, start_response)
