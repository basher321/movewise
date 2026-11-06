"""Catalog rules shared by the public, admin, match and agent endpoints (spec B04).

Course groups and courses (Training), universities (Student Consultancy), vacancies
(Job Processing, and Remote Jobs when remote = true) and visa programmes (Immigration Processing, B19). Items are never deleted:
they are hidden (published = false) or closed.
All money is poisha (integers).
"""

import re
import secrets
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.errors import ApiError
from app.licence import today_dhaka

FeeModule = Literal["study", "job", "visa", "remote"]

# Fixed lists (the reference forms). Index order matters: vacancies store the index.
EDUCATION_LEVELS = ("Below SSC", "SSC / HSC", "Diploma", "Bachelor or higher")
ENGLISH_LEVELS = ("Basic", "Good", "Fluent")
BASE_STUDY_LEVELS = ("Foundation", "Diploma", "Bachelor", "Master", "PhD")
# Remote Jobs agent form: common remote skills, always offered (the skills of open remote roles are
# added after them). A remote role matches when its occupation is the chosen skill.
REMOTE_SKILLS = (
    "Software development",
    "Web development",
    "Mobile app development",
    "UI / UX design",
    "Graphic design",
    "Video editing",
    "Digital marketing",
    "Search engine optimisation (SEO)",
    "Social media management",
    "Content writing",
    "Translation",
    "Data entry",
    "Data analysis",
    "Accounting & bookkeeping",
    "Customer support",
    "Virtual assistant",
    "IT support",
    "Online tutoring",
    "Sales & lead generation",
    "Project management",
)
ANY_COUNTRY = "Any country"

# Visa programme types (B19), stored as text with a CHECK list in visa_programs.visa_type.
VISA_TYPES: dict[str, str] = {
    "visit": "Visit visa",
    "tourist": "Tourist visa",
    "business": "Business visa",
    "family": "Family visa",
    "spouse": "Spouse / partner visa",
    "work": "Work visa",
    "student": "Student visa",
    "permanent_residence": "Permanent residence",
    "citizenship": "Citizenship",
    "transit": "Transit visa",
    "medical": "Medical visa",
    "other": "Other",
}

PUBLIC_LIMIT = 500
# Key of the transaction lock that makes catalog creates run one at a time (unique slugs).
CATALOG_LOCK = 3_000_004

MAX_SHORT = 120
MAX_LONG = 4000
MAX_LIST = 40
MAX_LIST_ITEM = 300

_COLOUR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_SLUG_PART = re.compile(r"[a-z0-9]+")
_SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def not_found(what: str) -> ApiError:
    return ApiError("NOT_FOUND", 404, f"{what} not found.")


def parse_uuid(value: str, what: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise not_found(what) from None


# ---------------------------------------------------------------- input checks


def req_text(value: str, label: str, max_len: int = MAX_SHORT) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise invalid(f"Please fill in: {label}.")
    if len(cleaned) > max_len:
        raise invalid(f"{label} must be at most {max_len} characters.")
    return cleaned


def opt_text(value: str, label: str, max_len: int = MAX_LONG) -> str:
    cleaned = value.strip()
    if len(cleaned) > max_len:
        raise invalid(f"{label} must be at most {max_len} characters.")
    return cleaned


def text_list(values: list[str], label: str, singular: str) -> list[str]:
    cleaned = [v.strip() for v in values if v.strip()]
    if not cleaned:
        raise invalid(f"Please give at least one {singular}.")
    if len(cleaned) > MAX_LIST:
        raise invalid(f"{label}: at most {MAX_LIST} lines.")
    if any(len(v) > MAX_LIST_ITEM for v in cleaned):
        raise invalid(f"{label}: each line must be at most {MAX_LIST_ITEM} characters.")
    # Keep the order, drop repeats.
    return list(dict.fromkeys(cleaned))


def check_colour(value: str) -> str:
    cleaned = value.strip()
    if not _COLOUR_RE.fullmatch(cleaned):
        raise invalid("Colour must look like #4F46E5.")
    return cleaned.upper()


def check_icon(value: str) -> str:
    cleaned = value.strip()
    # One emoji: one visible symbol, which can be up to a few code points (skin tone, joiners).
    if len(cleaned) > 8 or any(ch.isalnum() and ch.isascii() for ch in cleaned):
        raise invalid("Icon must be one emoji.")
    return cleaned


def opt_email(value: str, label: str) -> str:
    cleaned = value.strip()
    if cleaned and (len(cleaned) > 254 or not _EMAIL_RE.fullmatch(cleaned)):
        raise invalid(f"Please enter a valid {label}.")
    return cleaned


def check_fee(value: int | None) -> int | None:
    if value is not None and value <= 0:
        raise invalid("Every fee must be a whole number above 0.")
    return value


def number_text(value: float | Decimal | int) -> str:
    """A number as JavaScript prints it: 3 -> "3", 3.50 -> "3.5"."""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def usd(value: int) -> str:
    return f"${value:,}"


# ---------------------------------------------------------------- slugs


def slug_base(name: str) -> str:
    parts = _SLUG_PART.findall(name.lower())
    base = "-".join(parts)[:60].strip("-")
    return base or "item"


def new_slug(conn: Connection, table: Literal["courses", "universities", "vacancies", "visa_programs"], name: str) -> str:
    """A slug made from the name; a short suffix when it is already taken. Call under CATALOG_LOCK."""
    base = slug_base(name)
    slug = base
    exists = text(f"SELECT 1 FROM {table} WHERE slug = :slug")
    while conn.execute(exists, {"slug": slug}).first() is not None:
        slug = f"{base}-{''.join(secrets.choice(_SLUG_ALPHABET) for _ in range(4))}"
    return slug


def lock_catalog(conn: Connection) -> None:
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CATALOG_LOCK})


# ---------------------------------------------------------------- fees


def default_fees(conn: Connection) -> dict[FeeModule, int]:
    row = conn.execute(
        text(
            "SELECT default_fee_study_poisha, default_fee_job_poisha, default_fee_visa_poisha, "
            "default_fee_remote_poisha FROM settings WHERE singleton = 'settings'"
        )
    ).one()
    return {"study": int(row[0]), "job": int(row[1]), "visa": int(row[2]), "remote": int(row[3])}


def effective_fee(override: int | None, default: int) -> int:
    return override if override is not None else default


def stored_override(value: int | None, default: int) -> int | None:
    """A fee equal to the module default is stored as no override."""
    return None if value is None or value == default else value


# ---------------------------------------------------------------- success rate


def success_columns(fk: str, ref: str) -> str:
    """SQL columns success_completed and success_finished for the item `ref` (table or alias).
    A finished journey is a case that reached Completed (success) or was Rejected. Withdrawn and
    open cases are not finished, and Self Apply cases are not handled by the agency."""
    base = f"FROM applications sr WHERE sr.{fk} = {ref}.id AND NOT sr.self_apply"
    return (
        f"(SELECT count(*) {base} AND sr.status = 'completed') AS success_completed, "
        f"(SELECT count(*) {base} AND sr.status IN ('completed', 'rejected')) AS success_finished"
    )


UNI_SUCCESS = success_columns("university_id", "universities")
VAC_SUCCESS = success_columns("vacancy_id", "vacancies")
VISA_SUCCESS = success_columns("visa_program_id", "visa_programs")


def success_rate(row: RowMapping) -> dict[str, int] | None:
    """The success rate from the row's success columns; None while no journey has finished."""
    finished = int(row.get("success_finished") or 0)
    if finished == 0:
        return None
    completed = int(row.get("success_completed") or 0)
    # Rounded half up, in whole numbers only.
    return {"percent": (200 * completed + finished) // (2 * finished), "completed": completed, "finished": finished}


# ---------------------------------------------------------------- views


def changed_fields(before: RowMapping, after: dict[str, Any]) -> list[str]:
    changed = []
    for key, value in after.items():
        old = before[key]
        if isinstance(old, Decimal):
            old = float(old)
        if isinstance(value, Decimal):
            value = float(value)
        if isinstance(old, (list, tuple)):
            old = list(old)
        if old != value:
            changed.append(key)
    return changed


def group_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "sort_order": row["sort_order"],
        "active": row["active"],
    }


def course_view(row: RowMapping, admin: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(row["id"]),
        "slug": row["slug"],
        "group_id": str(row["group_id"]),
        "group_name": row["group_name"],
        "title": row["title"],
        "icon": row["icon"],
        "colour": row["colour"],
        "price_poisha": int(row["price_poisha"]),
        "duration": row["duration"],
        "level": row["level"],
        "description": row["description"],
        "learn_points": list(row["learn_points"]),
        "syllabus": list(row["syllabus"]),
    }
    if admin:
        view["published"] = row["published"]
        view["applied_count"] = int(row.get("applied_count") or 0)
        view["updated_at"] = row["updated_at"].isoformat()
    return view


def university_view(row: RowMapping, default_fee: int, admin: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "country": row["country"],
        "city": row["city"],
        "levels": list(row["levels"]),
        "fields": list(row["fields"]),
        "tuition_usd": row["tuition_usd"],
        "min_gpa": float(row["min_gpa"]),
        "min_ielts": float(row["min_ielts"]),
        "intakes": row["intakes"],
        "deadline_text": row["deadline_text"],
        "scholarships": row["scholarships"],
        "work_rights": row["work_rights"],
        "conditions": row["conditions"],
        "fee_poisha": effective_fee(row["fee_override_poisha"], default_fee),
        # Self Apply: its own fee, set by staff; None while Self Apply is not offered.
        "self_apply_fee_poisha": row["self_apply_fee_poisha"],
        "success_rate": success_rate(row),
    }
    if admin:
        # The official link and admissions email are for staff only, never the public page.
        view["apply_link"] = row["apply_link"]
        view["admissions_email"] = row["admissions_email"]
        view["fee_override_poisha"] = row["fee_override_poisha"]
        view["published"] = row["published"]
        view["applied_count"] = int(row.get("applied_count") or 0)
        view["updated_at"] = row["updated_at"].isoformat()
    return view


def vacancy_view(row: RowMapping, default_fee: int, admin: bool = False) -> dict[str, Any]:
    apply_by: date | None = row["apply_by"]
    view: dict[str, Any] = {
        "id": str(row["id"]),
        "slug": row["slug"],
        "title": row["title"],
        "employer": row["employer"],
        "country": row["country"],
        "occupation": row["occupation"],
        "min_experience": row["min_experience"],
        "min_education": row["min_education"],
        "min_english": row["min_english"],
        "salary_usd": row["salary_usd"],
        "seats": row["seats"],
        "apply_by": apply_by.isoformat() if apply_by else None,
        "contract": row["contract"],
        "benefits": row["benefits"],
        "conditions": row["conditions"],
        "employer_verified": row["employer_verified"],
        "remote": row["remote"],
        "fee_poisha": effective_fee(row["fee_override_poisha"], default_fee),
        "success_rate": success_rate(row),
    }
    if admin:
        # Employer contact and licence number are for staff only.
        view["employer_licence"] = row["employer_licence"]
        view["employer_email"] = row["employer_email"]
        view["closed"] = row["closed"]
        view["fee_override_poisha"] = row["fee_override_poisha"]
        view["applied_count"] = int(row.get("applied_count") or 0)
        view["past_apply_by"] = bool(apply_by and not row["closed"] and apply_by < today_dhaka())
        view["updated_at"] = row["updated_at"].isoformat()
    return view


def visa_program_view(row: RowMapping, default_fee: int, admin: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(row["id"]),
        "slug": row["slug"],
        "title": row["title"],
        "country": row["country"],
        "visa_type": row["visa_type"],
        "visa_type_label": VISA_TYPES.get(row["visa_type"], row["visa_type"]),
        "processing_time": row["processing_time"],
        "validity": row["validity"],
        "government_fee": row["government_fee"],
        "description": row["description"],
        "eligibility": list(row["eligibility"]),
        "required_documents": list(row["required_documents"]),
        "conditions": row["conditions"],
        "fee_poisha": effective_fee(row["fee_override_poisha"], default_fee),
        "success_rate": success_rate(row),
    }
    if admin:
        # The official link and embassy email are for staff only.
        view["official_link"] = row["official_link"]
        view["embassy_email"] = row["embassy_email"]
        view["fee_override_poisha"] = row["fee_override_poisha"]
        view["published"] = row["published"]
        view["applied_count"] = int(row.get("applied_count") or 0)
        view["updated_at"] = row["updated_at"].isoformat()
    return view


# ---------------------------------------------------------------- queries

COURSE_SELECT = (
    "SELECT c.*, g.name AS group_name, 0 AS applied_count "
    "FROM courses c JOIN course_groups g ON g.id = c.group_id"
)
PUBLIC_UNIVERSITIES = text(
    f"SELECT *, {UNI_SUCCESS} FROM universities WHERE published ORDER BY name, id LIMIT :limit"
)
PUBLIC_VACANCIES = text(
    f"SELECT *, {VAC_SUCCESS} FROM vacancies WHERE NOT remote AND NOT closed AND employer_verified "
    "ORDER BY created_at DESC, id LIMIT :limit"
)
# Remote Jobs: remote roles are vacancies with remote = true, shown only in the Remote Jobs module.
PUBLIC_REMOTE_JOBS = text(
    f"SELECT *, {VAC_SUCCESS} FROM vacancies WHERE remote AND NOT closed AND employer_verified "
    "ORDER BY created_at DESC, id LIMIT :limit"
)


def public_universities(conn: Connection) -> list[RowMapping]:
    return list(conn.execute(PUBLIC_UNIVERSITIES, {"limit": PUBLIC_LIMIT}).mappings())


def public_vacancies(conn: Connection) -> list[RowMapping]:
    return list(conn.execute(PUBLIC_VACANCIES, {"limit": PUBLIC_LIMIT}).mappings())


def public_remote_jobs(conn: Connection) -> list[RowMapping]:
    return list(conn.execute(PUBLIC_REMOTE_JOBS, {"limit": PUBLIC_LIMIT}).mappings())


PUBLIC_VISA_PROGRAMS = text(
    f"SELECT *, {VISA_SUCCESS} FROM visa_programs WHERE published ORDER BY country, title, id LIMIT :limit"
)


def public_visa_programs(conn: Connection) -> list[RowMapping]:
    return list(conn.execute(PUBLIC_VISA_PROGRAMS, {"limit": PUBLIC_LIMIT}).mappings())
