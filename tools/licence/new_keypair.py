"""Make a new Ed25519 key pair for signing licence keys (software owner only).

Usage (with the backend virtual environment):
  python tools/licence/new_keypair.py <private-key-path>

The private key is written to <private-key-path>, which must be outside the project folder
and must not exist yet. The public key is written to backend/app/licence_public_key.pem.
Licence keys signed with an earlier private key stop working.
"""

import argparse
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROJECT_DIR = Path(__file__).resolve().parents[2]
PUBLIC_KEY_PATH = PROJECT_DIR / "backend" / "app" / "licence_public_key.pem"


def inside_project(path: Path) -> bool:
    target = os.path.normcase(str(path.resolve()))
    root = os.path.normcase(str(PROJECT_DIR))
    return target == root or target.startswith(root.rstrip(os.sep) + os.sep)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="new_keypair.py", description="Make a new key pair for signing licence keys."
    )
    parser.add_argument("private_key_path", help="where to save the private key (outside the project)")
    args = parser.parse_args(argv)
    private_path = Path(args.private_key_path).expanduser()

    # Checked before anything is generated or written.
    if inside_project(private_path):
        print(
            f"Refusing: the private key must be saved outside the project folder ({PROJECT_DIR}).",
            file=sys.stderr,
        )
        return 1
    if private_path.exists():
        print(f"Refusing: {private_path} already exists. Choose a new file name.", file=sys.stderr)
        return 1
    if not private_path.parent.is_dir():
        print(f"Refusing: the folder {private_path.parent} does not exist.", file=sys.stderr)
        return 1

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # The private key is written first; if that fails the public key is never touched.
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(private_pem)
    PUBLIC_KEY_PATH.write_bytes(public_pem)

    print(f"Private key saved to {private_path}. Keep it safe; never put it in the project or git.")
    print(f"Public key saved to {PUBLIC_KEY_PATH}.")
    print("Licence keys signed with an earlier private key no longer work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
