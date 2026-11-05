"""b18: new_keypair.py refuses an output path inside the project folder.

The paths used point into a folder that does not exist, so even a faulty check could not
write a private key, and the public key file is checked to be untouched.
"""

import csv
import hashlib
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.licence import today_dhaka
from conftest import PROJECT_DIR

NEW_KEYPAIR = PROJECT_DIR / "tools" / "licence" / "new_keypair.py"
MAKE_KEY = PROJECT_DIR / "tools" / "licence" / "make_key.py"
REGISTER = PROJECT_DIR / "tools" / "licence" / "register.py"
PUBLIC_KEY = PROJECT_DIR / "backend" / "app" / "licence_public_key.pem"
NEVER_CREATED = PROJECT_DIR / "_b18_never_created"


def _public_key_fingerprint() -> str | None:
    return hashlib.sha256(PUBLIC_KEY.read_bytes()).hexdigest() if PUBLIC_KEY.exists() else None


@pytest.mark.parametrize(
    "target",
    [
        str(NEVER_CREATED / "private.pem"),
        str(PROJECT_DIR / "backend" / ".." / "_b18_never_created" / "private.pem"),
    ],
)
def test_new_keypair_refuses_path_inside_project(target: str) -> None:
    before = _public_key_fingerprint()
    result = subprocess.run(
        [sys.executable, str(NEW_KEYPAIR), target], capture_output=True, text=True, timeout=60
    )
    assert result.returncode != 0
    assert "outside the project folder" in result.stderr
    assert not NEVER_CREATED.exists()
    assert _public_key_fingerprint() == before


# The register: make_key.py adds one row per key; register.py lists them with a status.
# A throwaway key pair in pytest's temp folder (outside the project) signs the test keys.


def _private_key(folder: Path) -> Path:
    path = folder / "private.pem"
    path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, timeout=60, encoding="utf-8"
    )


def _make(private: Path, holder: str, modules: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return _run(MAKE_KEY, "--private-key", str(private), "--holder", holder, "--modules", modules, *extra)


def test_make_key_adds_a_register_row_next_to_the_private_key(tmp_path: Path) -> None:
    private = _private_key(tmp_path)
    expires = (today_dhaka() + timedelta(days=365)).isoformat()
    result = _make(private, "ABC Overseas Ltd", "job,study", "--expires", expires, "--note", "INV-101")
    assert result.returncode == 0, result.stderr
    key = result.stdout.strip()
    assert key.startswith("MW1.")

    with (tmp_path / "licence_register.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "issued": today_dhaka().isoformat(),
            "holder": "ABC Overseas Ltd",
            "modules": "study,job",
            "expires": expires,
            "key_end": key[-6:],
            "note": "INV-101",
            "key": key,
        }
    ]


def test_make_key_refuses_a_register_inside_the_project(tmp_path: Path) -> None:
    private = _private_key(tmp_path)
    target = PROJECT_DIR / "_register_never_created" / "licence_register.csv"
    result = _make(private, "ABC Overseas Ltd", "study", "--register", str(target))
    assert result.returncode != 0
    assert "outside the project folder" in result.stderr
    assert "MW1." not in result.stdout
    assert not target.parent.exists()


def test_register_lists_status_and_marks_older_keys_replaced(tmp_path: Path) -> None:
    private = _private_key(tmp_path)
    soon = (today_dhaka() + timedelta(days=10)).isoformat()
    assert _make(private, "ABC Overseas Ltd", "study", "--expires", soon).returncode == 0
    assert _make(private, "ABC Overseas Ltd", "study,job").returncode == 0
    assert _make(private, "Desh Travels", "course", "--expires", soon).returncode == 0

    result = _run(REGISTER, str(tmp_path / "licence_register.csv"))
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 3
    assert lines[0].endswith("| replaced")
    assert lines[1].endswith("| no expiry")
    assert lines[2].endswith("| expires in 10 days")

    only = _run(REGISTER, str(tmp_path / "licence_register.csv"), "--holder", "desh travels", "--keys")
    assert only.returncode == 0
    assert only.stdout.splitlines()[0].startswith(today_dhaka().isoformat() + " | Desh Travels")
    assert only.stdout.splitlines()[1].strip().startswith("MW1.")
