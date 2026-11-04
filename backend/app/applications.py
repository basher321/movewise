"""Applications shared rules (spec B05): answers check, history events, applicant
notifications and the views used by the applicant and admin endpoints."""

import json
import secrets
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor
from app.catalog import default_fees, effective_fee, invalid, university_view, vacancy_view, visa_program_view
from app.errors import ApiError
from app.licence import DHAKA
from app.notify.outbox import queue_message
from app.stages import STAGES, AppModule, stage_count, stage_name

REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_ANSWERS_BYTES = 4096
# Key of the per-applicant lock used while starting an application.
APPLY_LOCK = 3_000_005

ANSWER_TYPES: dict[AppModule, dict[str, str]] = {
    "study": {"level": "text", "field": "text", "gpa": "number", "ielts": "number", "budget_usd": "number"},
    "job": {
        "occupation": "text",
        "country": "text",
        "experience": "number",
        "education": "text",
        "english": "text",
        "passport_ready": "bool",
        "salary_goal_usd": "number_or_null",
    },
    # B19: Immigration Processing.
    "visa": {
        "country": "text",
        "visa_type": "text",
        "purpose": "text",
        "travel_date": "text",
        "passport_ready": "bool",
        "refused_before": "bool",
    },
}

STATUS_LABELS = {
    "active": "Active",
    "on_hold": "On hold",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
    "completed": "Completed",
}


def not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Application not found.")


def check_answers(module: AppModule, answers: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(answers, ensure_ascii=False).encode("utf-8")) > MAX_ANSWERS_BYTES:
        raise invalid("Your answers are too long.")
    allowed = ANSWER_TYPES[module]
    for key, value in answers.items():
        kind = allowed.get(key)
        if kind is None:
            raise invalid(f"answers: unknown field {key}.")
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        ok = {
            "text": isinstance(value, str) and len(value) <= 200,
            "number": is_number,
            "number_or_null": value is None or is_number,
            "bool": isinstance(value, bool),
        }[kind]
        if not ok:
            raise invalid(f"answers: {key} has the wrong type.")
    return answers


def new_ref(conn: Connection) -> str:
    exists = text("SELECT 1 FROM applications WHERE ref = :ref")
    while True:
        ref = "APP-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
        if conn.execute(exists, {"ref": ref}).first() is None:
            return ref


_INSERT_EVENT = text(
    "INSERT INTO app_events (application_id, by_kind, by_id, by_name, text, note, public) "
    "VALUES (:application_id, :by_kind, :by_id, :by_name, :text, :note, :public)"
)


def add_event(
    conn: Connection, application_id: Any, actor: Actor | None, event_text: str, note: str = "", public: bool = True
) -> None:
    if actor is None:
        by_kind, by_id, by_name = "system", None, "System"
    else:
        by_kind = "applicant" if actor.role == "applicant" else "admin"
        by_id, by_name = actor.id, actor.name
    conn.execute(
        _INSERT_EVENT,
        {
            "application_id": application_id,
            "by_kind": by_kind,
            "by_id": by_id,
            "by_name": by_name,
            "text": event_text,
            "note": note,
            "public": public,
        },
    )


def notify_applicant(conn: Connection, app: RowMapping, event: str, subject: str, body: str) -> None:
    """Email to the applicant, and WhatsApp too when they gave a phone number."""
    person = conn.execute(
        text("SELECT name, email, phone FROM applicant_accounts WHERE id = :id"), {"id": app["applicant_id"]}
    ).one()
    module: AppModule = app["module"]
    queue_message(conn, person.name, person.email, person.phone or None, module, event, subject, body, app["id"])


def money_text(poisha: int) -> str:
    taka, rest = divmod(poisha, 100)
    return f"৳{taka:,}" if rest == 0 else f"৳{taka:,}.{rest:02d}"


def dhaka_text(value: datetime) -> str:
    return value.astimezone(DHAKA).strftime("%d %b %Y, %I:%M %p") + " (Dhaka time)"


def item_row(conn: Connection, app: RowMapping) -> RowMapping:
    if app["module"] == "study":
        return conn.execute(text("SELECT * FROM universities WHERE id = :id"), {"id": app["university_id"]}).mappings().one()
    if app["module"] == "visa":
        return conn.execute(
            text("SELECT * FROM visa_programs WHERE id = :id"), {"id": app["visa_program_id"]}
        ).mappings().one()
    return conn.execute(text("SELECT * FROM vacancies WHERE id = :id"), {"id": app["vacancy_id"]}).mappings().one()


def item_title(module: AppModule, item: RowMapping) -> str:
    return item["name"] if module == "study" else item["title"]


# Who a case email to the "provider" goes to, per module.
PROVIDER_LABEL: dict[AppModule, str] = {"study": "university", "job": "employer", "visa": "embassy"}


def provider_email(module: AppModule, item: RowMapping) -> str:
    key = {"study": "admissions_email", "job": "employer_email", "visa": "embassy_email"}[module]
    return str(item[key])


def fee_now(conn: Connection, module: AppModule, item: RowMapping) -> int:
    return effective_fee(item["fee_override_poisha"], default_fees(conn)[module])


def public_item(conn: Connection, module: AppModule, item: RowMapping) -> dict[str, Any]:
    fee = default_fees(conn)[module]
    if module == "visa":
        return visa_program_view(item, fee)
    return university_view(item, fee) if module == "study" else vacancy_view(item, fee)


def event_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "at": row["at"].isoformat(),
        "by_kind": row["by_kind"],
        "by_name": row["by_name"],
        "text": row["text"],
        "note": row["note"],
        "public": row["public"],
    }


def base_view(app: RowMapping) -> dict[str, Any]:
    module: AppModule = app["module"]
    return {
        "id": str(app["id"]),
        "ref": app["ref"],
        "module": module,
        "stage": app["stage"],
        "stage_name": stage_name(module, app["stage"]),
        "stage_count": stage_count(module),
        "status": app["status"],
        "fee_paid": app["fee_paid"],
        "deadline": app["deadline"].isoformat() if app["deadline"] else None,
        "created_at": app["created_at"].isoformat(),
        "updated_at": app["updated_at"].isoformat(),
    }


def interview_fields(app: RowMapping) -> dict[str, Any]:
    return {
        # Given and shown in Asia/Dhaka time.
        "interview_at": app["interview_at"].astimezone(DHAKA).isoformat() if app["interview_at"] else None,
        "interview_result": app["interview_result"],
        "offered_salary_usd": app["offered_salary_usd"],
    }


def stages_list(module: AppModule) -> list[str]:
    return list(STAGES[module])


def parse_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise not_found() from None
