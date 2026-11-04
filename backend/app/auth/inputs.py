"""Input rules shared by the sign-up, sign-in and profile endpoints (the same rules as the mock)."""

import re

from app.errors import ApiError

EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
PHONE_RE = re.compile(r"(?:(?:\+88)?01[3-9]\d{8}|\+\d{8,15})")

MAX_EMAIL = 254
MAX_TEXT = 200
MIN_PASSWORD = 6
MAX_PASSWORD = 128


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def clean_email(raw: str) -> str:
    """The form used for matching: spaces at both ends removed, lower case."""
    return raw.strip().lower()


def check_email(email: str) -> None:
    if len(email) > MAX_EMAIL or not EMAIL_RE.fullmatch(email):
        raise _invalid("Please enter a valid email.")


USERNAME_RE = re.compile(r"[a-z0-9._]{3,30}")


def check_username(raw: str) -> str:
    """Letters, digits, dots and underscores, 3 to 30 long; stored in lower case."""
    username = raw.strip().lower()
    if not username:
        raise _invalid("Please choose a username.")
    if not USERNAME_RE.fullmatch(username):
        raise _invalid("Username must be 3 to 30 letters, numbers, dots or underscores (no spaces).")
    return username


def optional_email(raw: str) -> str | None:
    """An email when one is given (not verified), else None."""
    email = raw.strip()
    if not email:
        return None
    check_email(email.lower())
    return email


def optional_phone(raw: str) -> str:
    return check_phone(raw) if raw.strip() else ""


def check_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise _invalid("Please enter your full name.")
    if len(name) > MAX_TEXT:
        raise _invalid(f"Name must be {MAX_TEXT} characters or fewer.")
    return name


def check_password(password: str, label: str = "Password") -> None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise _invalid(f"{label} must be {MIN_PASSWORD} to {MAX_PASSWORD} characters.")


def check_phone(raw: str) -> str:
    phone = re.sub(r"[\s-]", "", raw)
    if not phone:
        raise _invalid("Please enter your phone number.")
    if not PHONE_RE.fullmatch(phone):
        raise _invalid("Please enter a valid phone number.")
    return phone


def check_text(raw: str, label: str) -> str:
    value = raw.strip()
    if len(value) > MAX_TEXT:
        raise _invalid(f"{label} must be {MAX_TEXT} characters or fewer.")
    return value
