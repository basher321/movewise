"""The signed-in applicant's own profile and password (per module)."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.audit import Actor, write_audit
from app.auth.accounts import APPLICANT_COLUMNS, applicant_view, is_unique_violation
from app.auth.deps import Applicant, current_applicant
from app.auth.inputs import check_name, check_password, check_phone, check_text, optional_email, optional_phone
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import end_applicant_sessions
from app.db.engine import get_conn
from app.errors import ApiError, parse_body

router = APIRouter()

_UPDATE_PROFILE = text(
    "UPDATE applicant_accounts SET name = :name, phone = :phone, country = :country, education = :education, "
    "email = :email "
    f"WHERE id = :id RETURNING {', '.join(APPLICANT_COLUMNS)}"
)
_SELECT_PASSWORD = text("SELECT password_hash FROM applicant_accounts WHERE id = :id")
_SET_PASSWORD = text("UPDATE applicant_accounts SET password_hash = :password_hash WHERE id = :id")


class ProfileIn(BaseModel):
    name: str
    phone: str
    country: str = ""
    education: str = ""
    # Optional and not verified; left out = unchanged, "" = remove.
    email: str | None = None


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.patch("/me/{module}/profile")
async def update_profile(
    request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(ProfileIn, await request.body())
    values = {
        "id": me.account["id"],
        "name": check_name(body.name),
        "phone": optional_phone(body.phone) if me.account["username"] else check_phone(body.phone),
        "country": check_text(body.country, "Country"),
        "education": check_text(body.education, "Education / work"),
        "email": me.account["email"] if body.email is None else optional_email(body.email),
    }
    if values["email"] is None and not me.account["username"]:
        raise ApiError("VALIDATION", 422, "Please keep an email: you sign in with it.")
    try:
        with conn.begin_nested():
            row = conn.execute(_UPDATE_PROFILE, values).mappings().one()
    except IntegrityError as exc:
        if is_unique_violation(exc, "applicant_accounts_module_email_key"):
            raise ApiError("CONFLICT", 409, "This email is already used by another account.") from None
        raise
    actor = Actor(id=row["id"], name=row["name"], role="applicant", ip=me.actor.ip)
    write_audit(conn, actor, "applicant.profile_updated", row["public_id"])
    return applicant_view(row)


@router.post("/me/{module}/password")
async def change_password(
    request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, bool]:
    body = parse_body(PasswordIn, await request.body())
    check_password(body.new_password, "New password")

    stored = conn.execute(_SELECT_PASSWORD, {"id": me.account["id"]}).scalar_one()
    if not verify_password(stored, body.current_password):
        raise ApiError("FORBIDDEN", 403, "Your current password is not right.")
    conn.execute(_SET_PASSWORD, {"id": me.account["id"], "password_hash": hash_password(body.new_password)})
    end_applicant_sessions(conn, me.account["id"], keep=me.session_hash)
    write_audit(conn, me.actor, "applicant.password_changed", me.account["public_id"])
    return {"ok": True}
