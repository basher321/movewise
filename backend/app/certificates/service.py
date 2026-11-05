"""Certificates and completion letters (spec B20): what goes on the PDF, whether it is valid,
and the signed download links WhatsApp messages carry.

- Course certificate (Training): enrolments.certificate_id (CERT-), approved by staff (B09).
- Completion letter (Student Consultancy, Job Processing, Immigration Processing):
  case_letters.letter_id (LTR-), issued by staff for a completed case. Valid while the case is
  still completed.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.catalog import VISA_TYPES
from app.certificates.pdf import CertDoc
from app.config import get_settings
from app.licence import DHAKA, MODULE_LABELS

DocKind = Literal["certificate", "letter"]
LINK_DAYS = 30
ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass(frozen=True)
class Found:
    kind: DocKind
    ref: str  # CERT- or LTR- id
    module: str
    applicant_id: Any
    application_id: Any
    doc: CertDoc
    view: dict[str, Any]


def long_date(value: datetime | None) -> str:
    if value is None:
        return ""
    local = value.astimezone(DHAKA)
    return f"{local.day} {local.strftime('%B %Y')}"


def company(conn: Connection) -> tuple[str, bytes | None]:
    row = conn.execute(
        text(
            "SELECT s.name, b.bytes FROM settings s LEFT JOIN branding_images b ON b.id = s.logo_image_id "
            "WHERE s.singleton = 'settings'"
        )
    ).one()
    return str(row[0]), (bytes(row[1]) if row[1] is not None else None)


# ---------------------------------------------------------------- course certificates

_ENROLMENT = text(
    "SELECT e.*, c.title, c.duration, c.level, p.name AS p_name, p.public_id AS p_public_id "
    "FROM enrolments e JOIN courses c ON c.id = e.course_id JOIN applicant_accounts p ON p.id = e.applicant_id "
)


def enrolment_row(conn: Connection, *, enrolment_id: Any = None, certificate_id: str | None = None) -> RowMapping | None:
    if enrolment_id is not None:
        return conn.execute(text(_ENROLMENT.text + "WHERE e.id = :v"), {"v": enrolment_id}).mappings().one_or_none()
    return conn.execute(text(_ENROLMENT.text + "WHERE e.certificate_id = :v"), {"v": certificate_id}).mappings().one_or_none()


def course_found(conn: Connection, row: RowMapping) -> Found:
    name, logo = company(conn)
    approved = bool(row["certificate_approved"]) and row["status"] != "cancelled"
    issued = long_date(row["certificate_approved_at"] or row["created_at"])
    sub = " · ".join(x for x in (row["duration"], row["level"]) if x)
    doc = CertDoc(
        heading="Certificate of Completion",
        intro="This is to certify that",
        name=row["p_name"],
        line="has successfully completed the course",
        title=row["title"],
        sub=sub,
        issued="Issued " + issued,
        id_line=f"Certificate ID {row['certificate_id']} · Student {row['p_public_id']}",
        company=name,
        logo=logo,
        approved=approved,
    )
    view = {
        "kind": "certificate",
        "id": row["certificate_id"],
        "module": "course",
        "holder_name": row["p_name"],
        "account_id": row["p_public_id"],
        "title": row["title"],
        "subtitle": sub,
        "issued_at": row["certificate_approved_at"].isoformat() if row["certificate_approved_at"] else None,
        "approved": bool(row["certificate_approved"]),
        "valid": approved,
    }
    return Found("certificate", row["certificate_id"], "course", row["applicant_id"], None, doc, view)


# ---------------------------------------------------------------- completion letters

_CASE = text(
    "SELECT a.*, p.name AS p_name, p.public_id AS p_public_id, "
    "u.name AS u_name, u.country AS u_country, v.title AS v_title, v.employer AS v_employer, v.country AS v_country, "
    "vp.title AS vp_title, vp.visa_type AS vp_type, vp.country AS vp_country, "
    "l.letter_id, l.issued_at AS letter_issued_at, "
    "(SELECT max(e.at) FROM app_events e WHERE e.application_id = a.id AND e.text LIKE 'Stage -> %') AS last_stage_at "
    "FROM applications a JOIN applicant_accounts p ON p.id = a.applicant_id "
    "LEFT JOIN universities u ON u.id = a.university_id LEFT JOIN vacancies v ON v.id = a.vacancy_id "
    "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id LEFT JOIN case_letters l ON l.application_id = a.id "
)


def case_row(conn: Connection, *, application_id: Any = None, letter_id: str | None = None) -> RowMapping | None:
    if application_id is not None:
        return conn.execute(text(_CASE.text + "WHERE a.id = :v"), {"v": application_id}).mappings().one_or_none()
    return conn.execute(text(_CASE.text + "WHERE l.letter_id = :v"), {"v": letter_id}).mappings().one_or_none()


def _case_item(row: RowMapping) -> tuple[str, str]:
    """(what the case was for, the "for ..." phrase) per module."""
    module = row["module"]
    if module == "study":
        return row["u_name"], f"{row['u_name']}, {row['u_country']}"
    if module == "job":
        return row["v_title"], f"{row['v_title']} at {row['v_employer']}, {row['v_country']}"
    visa_type = VISA_TYPES.get(row["vp_type"], row["vp_type"])
    return row["vp_title"], f"{row['vp_title']} ({visa_type}), {row['vp_country']}"


def letter_found(conn: Connection, row: RowMapping) -> Found:
    name, logo = company(conn)
    module = row["module"]
    issued = row["letter_issued_at"] is not None
    valid = issued and row["status"] == "completed"
    title, phrase = _case_item(row)
    completed = long_date(row["last_stage_at"] or row["updated_at"])
    letter_id = row["letter_id"] or "LTR-DRAFT"
    doc = CertDoc(
        heading="Letter of Completion",
        intro="This is to certify that",
        name=row["p_name"],
        line=f"has completed the {MODULE_LABELS[module]} process with {name} for",
        title=phrase,
        sub=f"Reference {row['ref']} · Completed {completed}",
        issued="Issued " + long_date(row["letter_issued_at"] or datetime.now(DHAKA)),
        id_line=f"Letter ID {letter_id} · Client {row['p_public_id']}",
        company=name,
        logo=logo,
        approved=valid,
    )
    view = {
        "kind": "letter",
        "id": row["letter_id"],
        "module": module,
        "holder_name": row["p_name"],
        "account_id": row["p_public_id"],
        "title": title,
        "subtitle": phrase,
        "issued_at": row["letter_issued_at"].isoformat() if issued else None,
        "approved": issued,
        "valid": valid,
    }
    return Found("letter", letter_id, module, row["applicant_id"], row["id"], doc, view)


def new_letter_id(conn: Connection) -> str:
    exists = text("SELECT 1 FROM case_letters WHERE letter_id = :v")
    while True:
        value = "LTR-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
        if conn.execute(exists, {"v": value}).first() is None:
            return value


# ---------------------------------------------------------------- lookups by id


def find(conn: Connection, ref: str) -> Found | None:
    """The certificate or letter with this CERT-/LTR- id, valid or not; None when unknown."""
    value = ref.strip().upper()[:20]
    if value.startswith("CERT-"):
        row = enrolment_row(conn, certificate_id=value)
        return course_found(conn, row) if row is not None else None
    if value.startswith("LTR-"):
        row = case_row(conn, letter_id=value)
        return letter_found(conn, row) if row is not None else None
    return None


# ---------------------------------------------------------------- signed links


def _link_key() -> bytes:
    return hashlib.sha256(b"movewise certificate link\x00" + get_settings().secret_key.encode("utf-8")).digest()


def sign(ref: str, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + LINK_DAYS * 86400)
    mac = hmac.new(_link_key(), f"{ref}.{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{expires}.{mac}"


def check_token(ref: str, token: str, now: float | None = None) -> bool:
    try:
        expires_text, mac = token.split(".", 1)
        expires = int(expires_text)
    except ValueError:
        return False
    if expires < (now if now is not None else time.time()):
        return False
    expected = hmac.new(_link_key(), f"{ref}.{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, mac)


def download_link(ref: str) -> str:
    return f"{get_settings().site_base}/api/certificates/{ref}/pdf?t={sign(ref)}"


def file_name(found: Found) -> str:
    return f"{found.ref}.pdf"
