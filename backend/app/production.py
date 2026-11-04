"""Start-up checks for APP_ENV=production. Each refusal names the problem, never a value."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import AppSettings, ConfigError

MIN_SECRET_KEY = 32

# B14: the setup code protects the Super Admin sign-up, so it is needed while no active Super Admin exists.
_NO_ADMIN = text("SELECT NOT EXISTS (SELECT 1 FROM admin_users WHERE role = 'super_admin' AND active)")
_IS_SUPERUSER = text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
_OWNS_TABLES = text(
    "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user)"
)


def check_production(settings: AppSettings, conn: Connection) -> None:
    """Raises ConfigError unless the settings and the database user are safe for production.

    The PUBLIC_SITE_URL / PUBLIC_API_URL https:// check is added with those settings (B07).
    """
    if len(settings.secret_key) < MIN_SECRET_KEY:
        raise ConfigError(f"SECRET_KEY must have at least {MIN_SECRET_KEY} characters in production.")
    if not settings.setup_token and conn.execute(_NO_ADMIN).scalar_one():
        raise ConfigError("SETUP_TOKEN must be set in production while no Super Admin exists.")
    if conn.execute(_IS_SUPERUSER).scalar_one():
        raise ConfigError("Database user must not be a superuser in production.")
    if conn.execute(_OWNS_TABLES).scalar_one():
        raise ConfigError("Database user must not own the tables in production.")
