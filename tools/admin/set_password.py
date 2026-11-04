"""Set a new password for a staff account (super admin, admin or finance) from the command line.

Usage (with the backend virtual environment, from the project folder):
  python tools/admin/set_password.py <email>

The new password is typed twice and never shown. The change and one audit row are written
in the same database transaction. Uses DATABASE_URL from backend/.env, like the backend.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.audit import Actor, write_audit  # noqa: E402
from app.auth.inputs import MAX_PASSWORD, MIN_PASSWORD  # noqa: E402
from app.auth.passwords import hash_password  # noqa: E402
from app.db.engine import get_engine  # noqa: E402

_FIND = text("SELECT id, name, email, role FROM admin_users WHERE lower(email) = lower(:email)")
_UPDATE = text("UPDATE admin_users SET password_hash = :hash WHERE id = :id")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="set_password.py", description="Set a new password for a staff account.")
    parser.add_argument("email", help="the staff account's email")
    args = parser.parse_args(argv)

    password = getpass.getpass("New password (hidden): ")
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        print(f"Refusing: the password must be {MIN_PASSWORD} to {MAX_PASSWORD} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Type it again: ") != password:
        print("Refusing: the two passwords are not the same.", file=sys.stderr)
        return 1

    with get_engine().begin() as conn:
        row = conn.execute(_FIND, {"email": args.email.strip()}).mappings().first()
        if row is None:
            print(f"No staff account with the email {args.email}.", file=sys.stderr)
            return 1
        conn.execute(_UPDATE, {"hash": hash_password(password), "id": row["id"]})
        actor = Actor(id=row["id"], name=row["name"], role=row["role"])
        write_audit(conn, actor, "admin.password_set", row["email"] + " (command line)")

    print(f"Password changed for {row['email']} ({row['role']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
