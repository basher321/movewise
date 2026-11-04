"""b18: new_keypair.py refuses an output path inside the project folder.

The paths used point into a folder that does not exist, so even a faulty check could not
write a private key, and the public key file is checked to be untouched.
"""

import hashlib
import subprocess
import sys

import pytest

from conftest import PROJECT_DIR

NEW_KEYPAIR = PROJECT_DIR / "tools" / "licence" / "new_keypair.py"
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
