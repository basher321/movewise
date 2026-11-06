"""Make a signed licence key (software owner only). Prints the key only.

Every key made is also added to the licence register (see register.py), by default
licence_register.csv next to the private key. The register must be outside the project folder.

Usage (with the backend virtual environment):
  python tools/licence/make_key.py --private-key <path> --holder "<company>"
      --modules course,study,job,visa,remote [--expires YYYY-MM-DD]
      [--note "<invoice, contact, ...>"] [--register <register.csv>]
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.licence import MODULES, make_key, today_dhaka  # noqa: E402
from new_keypair import inside_project  # noqa: E402
from register import append_row, default_register_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_key.py", description="Make a signed licence key.")
    parser.add_argument("--private-key", required=True, help="path to the private key file")
    parser.add_argument("--holder", required=True, help="company name the licence is for")
    parser.add_argument("--modules", required=True, help="comma list of: course, study, job, visa, remote")
    parser.add_argument("--expires", help="last valid day, YYYY-MM-DD (omit for no expiry)")
    parser.add_argument("--note", default="", help="your own note for the register (invoice no., contact)")
    parser.add_argument("--register", help="register CSV file (default: licence_register.csv next to the private key)")
    args = parser.parse_args(argv)

    holder = args.holder.strip()
    if not 1 <= len(holder) <= 200:
        parser.error("--holder must be 1 to 200 characters")

    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    if not modules or len(set(modules)) != len(modules) or any(m not in MODULES for m in modules):
        parser.error("--modules must be one or more of: course, study, job, visa, remote (no repeats)")

    issued = today_dhaka()
    expires: date | None = None
    if args.expires:
        try:
            expires = date.fromisoformat(args.expires)
        except ValueError:
            parser.error("--expires must be a date like 2027-12-31")
        if expires < issued:
            parser.error("--expires is in the past")

    note = " ".join(args.note.split())
    if len(note) > 500:
        parser.error("--note must be at most 500 characters")

    # The register is checked before any key is made, so a key never exists without its row.
    register = Path(args.register).expanduser() if args.register else default_register_path(Path(args.private_key))
    if inside_project(register):
        parser.error("--register must be outside the project folder (it lists all your customers)")
    if not register.parent.is_dir():
        parser.error(f"the register folder {register.parent} does not exist")

    try:
        private_key = serialization.load_pem_private_key(
            Path(args.private_key).read_bytes(), password=None
        )
    except (OSError, ValueError, TypeError):
        parser.error("--private-key could not be read as a private key")
    if not isinstance(private_key, Ed25519PrivateKey):
        parser.error("--private-key is not an Ed25519 private key")

    key = make_key(private_key, holder, modules, issued, expires)
    try:
        append_row(
            register,
            {
                "issued": issued.isoformat(),
                "holder": holder,
                "modules": ",".join(m for m in MODULES if m in modules),
                "expires": expires.isoformat() if expires else "",
                "key_end": key[-6:],
                "note": note,
                "key": key,
            },
        )
    except OSError:
        print(f"Could not write the register {register}; no key was given out.", file=sys.stderr)
        return 1

    print(key)
    print(f"Added to the register {register}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
