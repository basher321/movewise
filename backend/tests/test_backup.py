"""g06: deploy/backup.sh in a temporary folder only, never against a real folder or movewise.

Rotation removes folders (rm -r) inside the temporary folder, so these tests run only when
MOVEWISE_RUN_BACKUP_TESTS=1 is set. The database test also needs pg_dump and uses
TEST_DATABASE_URL (movewise_test); its password goes to pg_dump in PGPASSWORD, never printed.
"""

import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from conftest import PROJECT_DIR

SCRIPT = PROJECT_DIR / "deploy" / "backup.sh"
BASH = shutil.which("bash")

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("MOVEWISE_RUN_BACKUP_TESTS") != "1",
        reason="Set MOVEWISE_RUN_BACKUP_TESTS=1 to run the backup tests (they remove folders in a temporary folder).",
    ),
    pytest.mark.skipif(BASH is None, reason="bash is not installed."),
]

FAKE_PG_DUMP = """#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  if [ "$1" = "--file" ]; then echo fake-dump > "$2"; fi
  shift
done
"""
FAILING_PG_DUMP = "#!/usr/bin/env bash\necho 'pg_dump: connection failed' >&2\nexit 1\n"


def _posix(path: Path) -> str:
    """A path bash understands (Git Bash on Windows needs /c/... paths)."""
    text = path.resolve().as_posix()
    if len(text) > 1 and text[1] == ":":
        text = "/" + text[0].lower() + text[2:]
    return text


def _tool(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def _run(root: Path, storage: Path, pg_dump: str, **env: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    full_env = {
        **os.environ,
        "BACKUP_ROOT": _posix(root),
        "BACKUP_ALLOW_TEST_ROOT": "1",
        "STORAGE_DIR": _posix(storage),
        "PG_DUMP": pg_dump,
        "DB_NAME": "movewise_test",
        **env,
    }
    return subprocess.run([BASH, _posix(SCRIPT)], env=full_env, capture_output=True, text=True, timeout=120)


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "backups"
    storage = tmp_path / "storage"
    tools = tmp_path / "tools"
    for folder in (root, storage, tools):
        folder.mkdir()
    (storage / "doc.pdf").write_bytes(b"%PDF-1.4 test")
    return root, storage, tools


def _fake_backup(root: Path, day: date, ok: bool = True) -> str:
    name = f"{day.isoformat()}_023000"
    (root / name).mkdir()
    (root / name / ("OK" if ok else "FAILED")).touch()
    return name


def _expected_kept(names: list[str]) -> set[str]:
    keep: set[str] = {max(names)}
    days: set[str] = set()
    weeks: set[tuple[int, int]] = set()
    for name in sorted(names, reverse=True):
        day = date.fromisoformat(name[:10])
        week = day.isocalendar()[:2]
        if name[:10] not in days and len(days) < 14:
            days.add(name[:10])
            keep.add(name)
        if week not in weeks and len(weeks) < 8:
            weeks.add(week)
            keep.add(name)
    return keep


def test_backup_against_movewise_test_makes_dump_and_archive(folders: tuple[Path, Path, Path], test_url: str) -> None:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        pytest.skip("pg_dump is not on PATH.")
    root, storage, _ = folders
    url = make_url(test_url)
    assert url.database == "movewise_test"
    result = _run(
        root,
        storage,
        _posix(Path(pg_dump)),
        PGHOST=url.host or "localhost",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=str(url.password or ""),
    )
    assert result.returncode == 0, result.stderr
    (backup,) = list(root.iterdir())
    assert (backup / "movewise.dump").read_bytes().startswith(b"PGDMP")
    assert (backup / "storage.tar.gz").stat().st_size > 0
    assert (backup / "OK").is_file()


def test_rotation_keeps_14_daily_and_8_weekly(folders: tuple[Path, Path, Path]) -> None:
    root, storage, tools = folders
    today = date.today()
    # 30 older backups, one every 3 days: about 13 weeks back.
    old = [_fake_backup(root, today - timedelta(days=3 * i)) for i in range(1, 31)]
    other = root / "keep-me"
    other.mkdir()
    failed = _fake_backup(root, today - timedelta(days=200), ok=False)

    result = _run(root, storage, _posix(_tool(tools, "pg_dump", FAKE_PG_DUMP)))
    assert result.returncode == 0, result.stderr

    left = {p.name for p in root.iterdir()}
    new = (left - set(old) - {"keep-me", failed}).pop()
    assert _expected_kept(old + [new]) | {"keep-me", failed} == left
    assert other.is_dir()


def test_failed_pg_dump_removes_nothing(folders: tuple[Path, Path, Path]) -> None:
    root, storage, tools = folders
    today = date.today()
    old = [_fake_backup(root, today - timedelta(days=i)) for i in range(1, 31)]

    result = _run(root, storage, _posix(_tool(tools, "pg_dump", FAILING_PG_DUMP)))
    assert result.returncode != 0
    assert "backup failed" in result.stderr

    left = {p.name for p in root.iterdir()}
    assert set(old) <= left
    (new,) = left - set(old)
    assert (root / new / "FAILED").is_file()
    assert not (root / new / "OK").exists()


def test_refuses_a_root_other_than_var_backups_movewise(folders: tuple[Path, Path, Path]) -> None:
    root, storage, tools = folders
    result = _run(root, storage, _posix(_tool(tools, "pg_dump", FAKE_PG_DUMP)), BACKUP_ALLOW_TEST_ROOT="")
    assert result.returncode != 0
    assert "BACKUP_ROOT must be /var/backups/movewise" in result.stderr
    assert list(root.iterdir()) == []
