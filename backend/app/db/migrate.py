"""Apply new SQL files from db/migrations in filename order.

Usage (from backend/):
  python -m app.db.migrate          applies to MIGRATE_DATABASE_URL (the owner account of
                                    movewise); in development it falls back to DATABASE_URL
  python -m app.db.migrate --test   applies to TEST_DATABASE_URL (movewise_test)
Never drops, truncates or deletes anything.
"""

import argparse
import hashlib
import re
import sys
from collections.abc import Callable
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from app.config import AppSettings, ConfigError, ensure_safe_test_database, get_settings
from app.db.engine import libpq_url

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"

_URL_PASSWORD = re.compile(r"://[^:/@]*:([^@]*)@")


class MigrationError(RuntimeError):
    pass


def redact(message: str, url: str) -> str:
    """Remove the URL's password from a message before it is printed."""
    secrets = set(_URL_PASSWORD.findall(url))
    try:
        password = make_url(url).password
        if password:
            secrets.add(str(password))
    except Exception:
        pass
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            message = message.replace(secret, "***")
    return message


def checksum(path: Path) -> str:
    # Line endings are normalised so a git checkout on Windows does not count as an edit.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _applied(conn: psycopg.Connection) -> dict[str, str]:
    row = conn.execute("SELECT to_regclass('public.schema_migrations')").fetchone()
    if row is None or row[0] is None:
        return {}
    return {name: digest for name, digest in conn.execute("SELECT filename, checksum FROM schema_migrations")}


def run_migrations(
    url: str,
    migrations_dir: Path = MIGRATIONS_DIR,
    log: Callable[[str], None] = print,
) -> list[str]:
    """Apply every file not yet recorded, each in its own transaction. Returns the applied names."""
    files = sorted(migrations_dir.glob("*.sql"))
    applied_now: list[str] = []
    with psycopg.connect(libpq_url(url)) as conn:
        applied = _applied(conn)
        conn.commit()

        for path in files:
            if path.name in applied and applied[path.name] != checksum(path):
                raise MigrationError(
                    f"Applied migration {path.name} has changed. Add a new migration instead."
                )

        for path in files:
            if path.name in applied:
                continue
            try:
                conn.execute(path.read_text(encoding="utf-8"))  # type: ignore[call-overload]
                conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                    (path.name, checksum(path)),
                )
                conn.commit()
            except psycopg.Error as exc:
                conn.rollback()
                raise MigrationError(f"Migration {path.name} failed: {exc}") from None
            log(f"Applied {path.name}")
            applied_now.append(path.name)

    if not applied_now:
        log("Nothing to apply.")
    return applied_now


def migrate_url(settings: AppSettings) -> str:
    """MIGRATE_DATABASE_URL; in development DATABASE_URL when it is not set."""
    if settings.migrate_database_url:
        return settings.migrate_database_url
    if settings.app_env == "production":
        raise ConfigError("Missing required setting: MIGRATE_DATABASE_URL")
    return settings.database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db.migrate")
    parser.add_argument("--test", action="store_true", help="apply to TEST_DATABASE_URL")
    args = parser.parse_args(argv)
    url = ""
    try:
        settings = get_settings()
        if args.test:
            ensure_safe_test_database(settings.database_url, settings.test_database_url)
            url = settings.test_database_url
        else:
            url = migrate_url(settings)
        run_migrations(url)
    except (ConfigError, MigrationError) as exc:
        print(redact(str(exc), url), file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(redact(f"Could not connect to the database: {exc}", url), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
