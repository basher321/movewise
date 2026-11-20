"""Easy licence maker: a simple menu around make_key.py and register.py (software owner only).

Start it by double-clicking tools/licence/Make-Licence.bat. It asks plain questions, makes the
signed key with make_key.py (so every key is also written to the register) and copies the key
to the clipboard, ready to paste into an email or into Admin -> Licence.
"""

import contextlib
import io
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_key  # noqa: E402
from app.licence import MODULE_LABELS, MODULES, today_dhaka  # noqa: E402
from register import default_register_path, read_rows, status  # noqa: E402

DEFAULT_PRIVATE_KEY = Path.home() / "movewise-licence-private.pem"


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit(0) from None


def ask_yes(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = ask(f"{prompt} [{hint}]: ").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please type y or n.")


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    for day in (start.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError("bad date")


def ask_expiry(start: date) -> date | None:
    """Return the last valid day, or None for a licence that never expires."""
    print("\nHow long should the licence last?")
    print(f"  1  1 year       (until {add_months(start, 12) - timedelta(days=1)})")
    print(f"  2  6 months     (until {add_months(start, 6) - timedelta(days=1)})")
    print(f"  3  1 month      (until {add_months(start, 1) - timedelta(days=1)})")
    print("  4  Never expires")
    print("  5  I will type the last day myself")
    while True:
        choice = ask("Choose 1-5: ")
        if choice in ("1", "2", "3"):
            return add_months(start, {"1": 12, "2": 6, "3": 1}[choice]) - timedelta(days=1)
        if choice == "4":
            return None
        if choice == "5":
            typed = ask("Last valid day, like 2027-12-31: ")
            try:
                day = date.fromisoformat(typed)
            except ValueError:
                print("  That is not a date like 2027-12-31.")
                continue
            if day < today_dhaka():
                print("  That day is already in the past.")
                continue
            return day
        print("  Please type a number from 1 to 5.")


def ask_modules(current: list[str] | None = None) -> list[str]:
    if current and ask_yes(f"Keep the same modules ({', '.join(MODULE_LABELS[m] for m in current)})?"):
        return current
    if ask_yes("Give ALL modules (" + ", ".join(MODULE_LABELS[m] for m in MODULES) + ")?"):
        return list(MODULES)
    while True:
        chosen = [m for m in MODULES if ask_yes(f"  {MODULE_LABELS[m]}?", default=False)]
        if chosen:
            return chosen
        print("  Choose at least one module.")


def copy_to_clipboard(key: str) -> bool:
    try:
        subprocess.run(["clip"], input=key.encode("ascii"), check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def show_key(key: str) -> None:
    print("\n" + "=" * 70)
    print("LICENCE KEY:\n")
    print(key)
    print("=" * 70)
    if copy_to_clipboard(key):
        print("The key is copied. Paste it (Ctrl+V) into an email, or into Admin -> Licence on the site.")
    else:
        print("Select the key above and copy it.")


def issue(private_key: Path, holder: str, modules: list[str], expires: date | None, note: str) -> None:
    print("\nPlease check:")
    print(f"  Company : {holder}")
    print(f"  Modules : {', '.join(MODULE_LABELS[m] for m in modules)}")
    print(f"  Valid to: {expires.isoformat() if expires else 'never expires'}")
    if note:
        print(f"  Note    : {note}")
    if not ask_yes("Make this licence key?"):
        print("Nothing was made.")
        return

    args = ["--private-key", str(private_key), "--holder", holder, "--modules", ",".join(modules)]
    if expires:
        args += ["--expires", expires.isoformat()]
    if note:
        args += ["--note", note]
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = make_key.main(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    if code != 0:
        print("Could not make the key: " + (err.getvalue().strip().splitlines() or ["unknown error"])[-1])
        return
    show_key(out.getvalue().strip())
    print("It is also saved in your customer list.")


def latest_per_company(register: Path) -> list[dict[str, str]]:
    if not register.is_file():
        return []
    latest: dict[str, dict[str, str]] = {}
    for row in read_rows(register):
        latest[row["holder"].casefold()] = row
    return sorted(latest.values(), key=lambda r: r["holder"].casefold())


def pick_company(register: Path) -> dict[str, str] | None:
    rows = latest_per_company(register)
    if not rows:
        print("\nNo licences made yet.")
        return None
    today = today_dhaka()
    print()
    for i, row in enumerate(rows, 1):
        print(f"  {i}  {row['holder']}  (until {row['expires'] or 'never'}, {status(row, False, today)})")
    while True:
        choice = ask("Choose a company number (or press Enter to go back): ")
        if not choice:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(rows):
            return rows[int(choice) - 1]
        print("  Please type one of the numbers above.")


def new_licence(private_key: Path) -> None:
    holder = ""
    while not 1 <= len(holder) <= 200:
        holder = " ".join(ask("\nCompany name (exactly as it should show on their site): ").split())
    modules = ask_modules()
    expires = ask_expiry(today_dhaka())
    note = ask("Your own note, like invoice number (or press Enter): ")
    issue(private_key, holder, modules, expires, note)


def renew_licence(private_key: Path, register: Path) -> None:
    row = pick_company(register)
    if row is None:
        return
    today = today_dhaka()
    start = today
    if row["expires"]:
        old_end = date.fromisoformat(row["expires"])
        if old_end >= today:
            start = old_end + timedelta(days=1)  # renewing early adds the time on top
    print(f"\nRenewing {row['holder']}. The new time starts on {start}.")
    modules = ask_modules(row["modules"].split(","))
    expires = ask_expiry(start)
    note = ask("Your own note, like invoice number (or press Enter): ")
    issue(private_key, row["holder"], modules, expires, note)


def list_licences(register: Path) -> None:
    rows = latest_per_company(register)
    if not rows:
        print("\nNo licences made yet.")
        return
    today = today_dhaka()
    print(f"\n{'Company':<35} {'Valid until':<12} {'Status':<22} Modules")
    print("-" * 100)
    for row in rows:
        modules = ", ".join(MODULE_LABELS[m] for m in row["modules"].split(",") if m in MODULE_LABELS)
        print(f"{row['holder'][:35]:<35} {row['expires'] or 'never':<12} {status(row, False, today):<22} {modules}")


def resend_key(register: Path) -> None:
    row = pick_company(register)
    if row is not None:
        show_key(row["key"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    private_key = DEFAULT_PRIVATE_KEY
    while not private_key.is_file():
        print(f"Your signing key file was not found at {private_key}.")
        typed = ask("Type the full path of your signing key file (or press Enter to quit): ").strip('"')
        if not typed:
            return 1
        private_key = Path(typed).expanduser()
    register = default_register_path(private_key)

    while True:
        print("\n========== LICENCE MAKER ==========")
        print("  1  Make a licence for a NEW customer")
        print("  2  RENEW or change a customer's licence")
        print("  3  See all customers and when they expire")
        print("  4  Show a customer's key again (to resend)")
        print("  0  Exit")
        choice = ask("Choose: ")
        if choice == "1":
            new_licence(private_key)
        elif choice == "2":
            renew_licence(private_key, register)
        elif choice == "3":
            list_licences(register)
        elif choice == "4":
            resend_key(register)
        elif choice == "0":
            return 0
        else:
            print("Please type 0, 1, 2, 3 or 4.")


if __name__ == "__main__":
    sys.exit(main())
