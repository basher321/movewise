"""Settings, read only from environment variables and backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[1]

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ConfigError(RuntimeError):
    """A setting is missing or unsafe. The message names the setting, never a value."""


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(min_length=1)
    frontend_origin: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)
    test_database_url: str = ""
    app_env: Literal["development", "production"] = "development"
    # Owner account, used only by the migration runner; falls back to DATABASE_URL in development.
    migrate_database_url: str = ""
    # Production only: the first admin sign-up must bring this code.
    setup_token: str = ""
    # Uploaded documents (B06). Empty means backend/storage. Never inside a web root.
    storage_dir: str = ""
    # B07: the backend address the gateways call back, and the site the payer returns to.
    # Empty means the local development addresses.
    public_api_url: str = ""
    public_site_url: str = ""
    # B08: "off" stops the notification worker (tests always run with it off).
    notify_worker: str = "on"

    @property
    def api_base(self) -> str:
        return (self.public_api_url or "http://localhost:8000").rstrip("/")

    @property
    def site_base(self) -> str:
        return (self.public_site_url or self.frontend_origin).rstrip("/")

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir).resolve() if self.storage_dir else BACKEND_DIR / "storage"


def load_settings() -> AppSettings:
    try:
        settings = AppSettings()
    except ValidationError as exc:
        names = sorted({str(err["loc"][0]).upper() for err in exc.errors() if err["loc"]})
        raise ConfigError("Missing required setting: " + ", ".join(names)) from None
    if settings.test_database_url and same_database(settings.database_url, settings.test_database_url):
        raise ConfigError("DATABASE_URL and TEST_DATABASE_URL point to the same database.")
    return settings


@lru_cache
def get_settings() -> AppSettings:
    return load_settings()


def _identity(name: str, url: str) -> tuple[str, int, str]:
    try:
        parsed = make_url(url)
        port = parsed.port or 5432
    except (ArgumentError, ValueError):
        raise ConfigError(f"{name} is not a valid database URL.") from None
    host = (parsed.host or "localhost").lower()
    return ("localhost" if host in _LOCAL_HOSTS else host, port, parsed.database or "")


def database_name(name: str, url: str) -> str:
    return _identity(name, url)[2]


def same_database(database_url: str, test_database_url: str) -> bool:
    return _identity("DATABASE_URL", database_url) == _identity("TEST_DATABASE_URL", test_database_url)


def ensure_safe_test_database(database_url: str, test_database_url: str) -> None:
    """Refuse a test database whose name does not end in _test, or that is the main database."""
    if not test_database_url:
        raise ConfigError("Missing required setting: TEST_DATABASE_URL")
    if not database_name("TEST_DATABASE_URL", test_database_url).endswith("_test"):
        raise ConfigError('TEST_DATABASE_URL must point to a database whose name ends with "_test".')
    if same_database(database_url, test_database_url):
        raise ConfigError("DATABASE_URL and TEST_DATABASE_URL point to the same database.")
