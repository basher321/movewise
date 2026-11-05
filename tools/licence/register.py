"""The licence register: the software owner's own record of every licence key issued.

It is a CSV file kept outside the project folder (by default next to the private key), because
it lists all customers and must never be shipped to a buyer or put in git. make_key.py adds one
row per key. This script lists the rows with their status.

Usage (with the backend virtual environment):
  python tools/licence/register.py <register.csv> [--holder "<company>"] [--keys]
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.licence import today_dhaka  # noqa: E402

REGISTER_NAME = "licence_register.csv"
FIELDS = ["issued", "holder", "modules", "expires", "key_end", "note", "key"]
SOON_DAYS = 30


def default_register_path(private_key_path: Path) -> Path:
    return private_key_path.expanduser().resolve().parent / REGISTER_NAME


def append_row(path: Path, row: dict[str, str]) -> None:
    """Add one row, writing the header first when the file is new."""
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({f: row.get(f, "") for f in FIELDS})


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{f: (r.get(f) or "") for f in FIELDS} for r in csv.DictReader(handle)]


def status(row: dict[str, str], replaced: bool, today: date) -> str:
    if replaced:
        return "replaced"
    if not row["expires"]:
        return "no expiry"
    days = (date.fromisoformat(row["expires"]) - today).days
    if days < 0:
        return "expired"
    if days <= SOON_DAYS:
        return f"expires in {days} day{'' if days == 1 else 's'}"
    return "active"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="register.py", description="List the licence register.")
    parser.add_argument("register", help="path to the register CSV file")
    parser.add_argument("--holder", help="show only this company (case-insensitive)")
    parser.add_argument("--keys", action="store_true", help="also print each full key, to resend it")
    args = parser.parse_args(argv)
    # Company names may be in Bengali; a Windows console would otherwise fail to print them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    path = Path(args.register).expanduser()
    if not path.is_file():
        print(f"No register at {path}.", file=sys.stderr)
        return 1

    rows = read_rows(path)
    # A key is "replaced" when a later row exists for the same holder (renewal or upgrade).
    last_index = {r["holder"].casefold(): i for i, r in enumerate(rows)}
    today = today_dhaka()
    wanted = args.holder.strip().casefold() if args.holder else None

    shown = 0
    for i, row in enumerate(rows):
        if wanted is not None and row["holder"].casefold() != wanted:
            continue
        replaced = last_index[row["holder"].casefold()] != i
        line = " | ".join(
            [
                row["issued"],
                row["holder"],
                row["modules"],
                "expires " + (row["expires"] or "never"),
                "key ..." + row["key_end"],
                status(row, replaced, today),
            ]
        )
        if row["note"]:
            line += " | " + row["note"]
        print(line)
        if args.keys:
            print("  " + row["key"])
        shown += 1

    if shown == 0:
        print("No matching rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
