"""b07: start-up stops without DATABASE_URL. b08: unsafe test databases are refused.
Also: the database password never appears in migrate output.

All URLs below are made up and use port 1, where no database server listens,
so nothing here can reach a real database.
"""

import os
import subprocess
import sys

import pytest

from app.config import BACKEND_DIR, AppSettings, ConfigError, ensure_safe_test_database
from app.db import migrate

PLACEHOLDER_SECRET = "b07-placeholder-value"
MAIN = "postgresql+psycopg://someone:pw-main@127.0.0.1:1/movewise"
TEST = "postgresql+psycopg://someone:pw-test@127.0.0.1:1/movewise_test"
FAKE_ENV = {
    "DATABASE_URL": MAIN,
    "TEST_DATABASE_URL": TEST,
    "FRONTEND_ORIGIN": "http://localhost:3000",
    "SECRET_KEY": PLACEHOLDER_SECRET,
}


def _run(code_or_args: list[str], **overrides: str | None) -> subprocess.CompletedProcess[str]:
    # Environment values win over backend/.env; None removes a variable.
    env = dict(os.environ)
    env.update(FAKE_ENV)
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return subprocess.run(
        [sys.executable, *code_or_args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _start_app(**overrides: str | None) -> subprocess.CompletedProcess[str]:
    return _run(["-c", "import app.main"], **overrides)


def test_start_with_database_url_absent_names_it() -> None:
    code = 'import app.config as c; c.AppSettings.model_config["env_file"] = None; import app.main'
    result = _run(["-c", code], DATABASE_URL=None)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Missing required setting: DATABASE_URL" in output
    assert PLACEHOLDER_SECRET not in output and "pw-test" not in output


def test_start_with_database_url_empty_names_it() -> None:
    result = _start_app(DATABASE_URL="")
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Missing required setting: DATABASE_URL" in output
    assert PLACEHOLDER_SECRET not in output


def test_start_refuses_same_database_without_showing_password() -> None:
    result = _start_app(TEST_DATABASE_URL=MAIN.replace("pw-main", "pw-other"))
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "DATABASE_URL and TEST_DATABASE_URL point to the same database." in output
    assert "pw-main" not in output and "pw-other" not in output


def test_safe_test_database_is_accepted() -> None:
    ensure_safe_test_database(MAIN, TEST)


def test_test_database_name_must_end_in_test() -> None:
    with pytest.raises(ConfigError) as info:
        ensure_safe_test_database(MAIN, TEST.replace("movewise_test", "movewise_copy"))
    assert '"_test"' in str(info.value)
    assert "pw-" not in str(info.value)


def test_test_database_must_differ_from_main() -> None:
    main = MAIN.replace("/movewise", "/app_test")
    same_on_localhost = main.replace("127.0.0.1", "localhost").replace("pw-main", "pw-test")
    with pytest.raises(ConfigError) as info:
        ensure_safe_test_database(main, same_on_localhost)
    assert "same database" in str(info.value)
    assert "pw-" not in str(info.value)


def _run_pytest(**overrides: str) -> subprocess.CompletedProcess[str]:
    # Runs one database-free test; the run must be refused before it starts.
    return _run(
        [
            "-m", "pytest", "-p", "no:cacheprovider",
            "tests/test_config.py::test_safe_test_database_is_accepted",
        ],
        **overrides,
    )


def test_pytest_refuses_database_not_ending_in_test() -> None:
    result = _run_pytest(TEST_DATABASE_URL=TEST.replace("movewise_test", "movewise_copy"))
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Refusing to run tests" in output
    assert "passed" not in output


def test_pytest_refuses_same_database_as_main() -> None:
    main = MAIN.replace("/movewise", "/app_test")
    result = _run_pytest(DATABASE_URL=main, TEST_DATABASE_URL=main.replace("pw-main", "pw-test"))
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Refusing to run tests" in output and "same database" in output
    assert "passed" not in output
    assert "pw-main" not in output and "pw-test" not in output


def test_redact_removes_password() -> None:
    url = "postgresql+psycopg://someone:FakePw123@127.0.0.1:1/movewise_test"
    assert "FakePw123" not in migrate.redact(f"connection to {url} failed", url)


def test_migrate_output_never_shows_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_url = "postgresql+psycopg://someone:FakePw123@127.0.0.1:1/movewise_test?sslmode=bogus"
    settings = AppSettings.model_construct(
        database_url=MAIN,
        test_database_url=bad_url,
        frontend_origin="http://localhost:3000",
        secret_key=PLACEHOLDER_SECRET,
    )
    monkeypatch.setattr(migrate, "get_settings", lambda: settings)
    assert migrate.main(["--test"]) == 1
    captured = capsys.readouterr()
    assert "FakePw123" not in captured.out + captured.err
