"""B2B partners with their logo, shown per module (spec B18).

Every partner belongs to exactly one module (course, study, job or visa) and is shown only on that
module's page, never mixed. Contact details and the agreement are internal and never public.
Partners are switched off with active = false, never deleted; logo rows are only added.

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Every change writes exactly one audit row in the same transaction.
"""

import hashlib
from datetime import date
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from starlette.datastructures import UploadFile

from app.audit import Actor, write_audit
from app.auth.deps import ensure_licensed, ensure_section, get_current_actor
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.files import MAX_FILE_BYTES
from app.licence import MODULE_LABELS, MODULES, Module, read_licence
from app.routers.settings import _sniff_mime

router = APIRouter()

PARTNER_TYPES = (
    "university",
    "college",
    "employer",
    "recruitment_agency",
    "training_body",
    "exam_board",
    "visa_centre",
    "law_firm",
    "other",
)
EMAIL_CHARS = frozenset(" \t\r\n")

_SELECT = "SELECT p.*, l.sha256 AS logo_sha256 FROM partners p LEFT JOIN partner_logos l ON l.id = p.logo_id "


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Partner not found.")


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise _not_found() from None


def _module(value: str) -> Module:
    if value not in MODULES:
        raise _invalid("Please choose a module: course, study, job or visa.")
    return cast(Module, value)


def _logo_url(row: RowMapping) -> str | None:
    sha = row["logo_sha256"]
    return f"/api/partners/{row['id']}/logo?v={sha[:12]}" if sha else None


def public_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "partner_type": row["partner_type"],
        "country": row["country"],
        "website": row["website"],
        "description": row["description"],
        "logo_url": _logo_url(row),
    }


def admin_view(row: RowMapping) -> dict[str, Any]:
    view = public_view(row)
    view.update(
        {
            "module": row["module"],
            "contact_name": row["contact_name"],
            "contact_email": row["contact_email"],
            "contact_phone": row["contact_phone"],
            "agreement_ref": row["agreement_ref"],
            "agreement_until": row["agreement_until"].isoformat() if row["agreement_until"] else None,
            "show_on_site": row["show_on_site"],
            "sort_order": row["sort_order"],
            "active": row["active"],
            "created_at": row["created_at"].isoformat(),
        }
    )
    return view


def _by_id(conn: Connection, partner_id: UUID) -> dict[str, Any]:
    return admin_view(conn.execute(text(_SELECT + "WHERE p.id = :id"), {"id": partner_id}).mappings().one())


def _visible_modules(conn: Connection, actor: Actor) -> list[Module]:
    licence = read_licence(conn)
    licensed = [m for m in MODULES if licence.licensed(m)]
    if actor.role == "super_admin":
        return licensed
    if actor.role == "admin":
        return [m for m in licensed if m in actor.sections]
    return []


def _load(conn: Connection, actor: Actor, partner_id: str) -> RowMapping:
    uid = _uuid(partner_id)
    row = conn.execute(text("SELECT * FROM partners WHERE id = :id FOR UPDATE"), {"id": uid}).mappings().one_or_none()
    if row is None:
        raise _not_found()
    ensure_section(conn, actor, row["module"])
    return row


# ---------------------------------------------------------------- public


@router.get("/partners")
def list_public_partners(module: str = "", conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    m = _module(module)
    ensure_licensed(conn, m)
    rows = conn.execute(
        text(_SELECT + "WHERE p.module = :module AND p.active AND p.show_on_site ORDER BY p.sort_order, lower(p.name), p.id"),
        {"module": m},
    ).mappings()
    return [public_view(r) for r in rows]


@router.get("/partners/{partner_id}/logo")
def get_partner_logo(partner_id: str, request: Request, conn: Connection = Depends(get_conn)) -> Response:
    uid = _uuid(partner_id)
    row = conn.execute(
        text(
            "SELECT p.module, l.mime, l.sha256, l.bytes FROM partners p JOIN partner_logos l ON l.id = p.logo_id "
            "WHERE p.id = :id AND p.active AND p.show_on_site"
        ),
        {"id": uid},
    ).mappings().one_or_none()
    if row is None or not read_licence(conn).licensed(row["module"]):
        raise _not_found()
    etag = f'"{row["sha256"]}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=bytes(row["bytes"]), media_type=row["mime"], headers=headers)


# ---------------------------------------------------------------- admin


class PartnerIn(BaseModel):
    module: str
    partner_type: str
    name: str = Field(max_length=1000)
    country: str = Field(default="", max_length=1000)
    website: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=2000)
    contact_name: str = Field(default="", max_length=1000)
    contact_email: str = Field(default="", max_length=1000)
    contact_phone: str = Field(default="", max_length=1000)
    agreement_ref: str = Field(default="", max_length=1000)
    agreement_until: date | None = None
    show_on_site: StrictBool = False
    sort_order: StrictInt = 0
    active: StrictBool = True


_LIMITS = {
    "country": ("Country", 80),
    "website": ("Website", 300),
    "description": ("Description", 300),
    "contact_name": ("Contact name", 120),
    "contact_email": ("Contact email", 254),
    "contact_phone": ("Contact phone", 40),
    "agreement_ref": ("Agreement reference", 120),
}


def _values(body: PartnerIn) -> dict[str, Any]:
    if body.partner_type not in PARTNER_TYPES:
        raise _invalid("Please choose the partner type.")
    name = body.name.strip()
    if not name:
        raise _invalid("Please enter the partner's name.")
    if len(name) > 120:
        raise _invalid("Name must be at most 120 characters.")
    values: dict[str, Any] = {"name": name, "partner_type": body.partner_type}
    for field, (label, limit) in _LIMITS.items():
        value = str(getattr(body, field)).strip()
        if len(value) > limit:
            raise _invalid(f"{label} must be at most {limit} characters.")
        values[field] = value
    if values["website"] and (not values["website"].startswith("https://") or any(c in EMAIL_CHARS for c in values["website"])):
        raise _invalid("Website must start with https://, or leave it empty.")
    email = values["contact_email"]
    if email and ("@" not in email or any(c in EMAIL_CHARS for c in email)):
        raise _invalid("Please enter a valid contact email, or leave it empty.")
    if not -10000 <= body.sort_order <= 10000:
        raise _invalid("Order must be between -10000 and 10000.")
    values.update(
        {
            "agreement_until": body.agreement_until,
            "show_on_site": body.show_on_site,
            "sort_order": body.sort_order,
            "active": body.active,
        }
    )
    return values


_COLUMNS = (
    "module, partner_type, name, country, website, description, contact_name, contact_email, contact_phone, "
    "agreement_ref, agreement_until, show_on_site, sort_order, active"
)
_INSERT = text(
    f"INSERT INTO partners ({_COLUMNS}) VALUES (:module, :partner_type, :name, :country, :website, :description, "
    ":contact_name, :contact_email, :contact_phone, :agreement_ref, :agreement_until, :show_on_site, :sort_order, "
    ":active) RETURNING id"
)
_UPDATE = text(
    "UPDATE partners SET module = :module, partner_type = :partner_type, name = :name, country = :country, "
    "website = :website, description = :description, contact_name = :contact_name, contact_email = :contact_email, "
    "contact_phone = :contact_phone, agreement_ref = :agreement_ref, agreement_until = :agreement_until, "
    "show_on_site = :show_on_site, sort_order = :sort_order, active = :active WHERE id = :id"
)


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/admin/partners")
def list_admin_partners(
    module: str = "",
    q: str = "",
    active: str = "",
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> list[dict[str, Any]]:
    visible = _visible_modules(conn, actor)
    if not visible:
        raise ApiError("FORBIDDEN", 403, "You do not have access to partners.")
    where = ["p.module = ANY(CAST(:visible AS text[]))"]
    params: dict[str, Any] = {"visible": visible}
    if module:
        m = _module(module)
        ensure_section(conn, actor, m)
        where.append("p.module = :module")
        params["module"] = m
    if active in ("true", "false"):
        where.append("p.active = :active")
        params["active"] = active == "true"
    if q.strip():
        where.append("(p.name ILIKE :q OR p.country ILIKE :q OR p.contact_name ILIKE :q OR p.contact_email ILIKE :q)")
        params["q"] = _like(q.strip()[:100])
    sql = _SELECT + "WHERE " + " AND ".join(where) + " ORDER BY p.module, p.sort_order, lower(p.name), p.id"
    return [admin_view(r) for r in conn.execute(text(sql), params).mappings()]


@router.post("/admin/partners")
async def create_partner(
    request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    if actor.role not in ("super_admin", "admin"):
        raise ApiError("FORBIDDEN", 403, "You do not have access to partners.")
    body = parse_body(PartnerIn, await request.body())
    module = _module(body.module)
    ensure_section(conn, actor, module)
    values = _values(body)
    partner_id = conn.execute(_INSERT, {**values, "module": module}).scalar_one()
    write_audit(conn, actor, "partner.created", f"{MODULE_LABELS[module]}: {values['name']}")
    return _by_id(conn, partner_id)


@router.put("/admin/partners/{partner_id}")
async def update_partner(
    partner_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    old = _load(conn, actor, partner_id)
    body = parse_body(PartnerIn, await request.body())
    module = _module(body.module)
    if module != old["module"]:
        ensure_section(conn, actor, module)
    values = _values(body)
    conn.execute(_UPDATE, {**values, "module": module, "id": old["id"]})
    write_audit(conn, actor, "partner.updated", f"{MODULE_LABELS[module]}: {values['name']}")
    return _by_id(conn, old["id"])


@router.put("/admin/partners/{partner_id}/logo")
async def set_partner_logo(
    partner_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    old = _load(conn, actor, partner_id)
    form = await request.form(max_files=1, max_fields=1)
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise _invalid("file: Please choose a logo.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise _invalid("The logo must be 2 MB or smaller.")
    mime = _sniff_mime(data)
    if mime is None:
        raise _invalid("The logo must be a PNG, JPEG or WebP picture.")
    logo_id = conn.execute(
        text(
            "INSERT INTO partner_logos (mime, size_bytes, sha256, bytes) VALUES (:mime, :size, :sha, :bytes) RETURNING id"
        ),
        {"mime": mime, "size": len(data), "sha": hashlib.sha256(data).hexdigest(), "bytes": data},
    ).scalar_one()
    conn.execute(text("UPDATE partners SET logo_id = :logo WHERE id = :id"), {"logo": logo_id, "id": old["id"]})
    write_audit(conn, actor, "partner.logo_set", old["name"])
    return _by_id(conn, old["id"])


@router.post("/admin/partners/{partner_id}/logo/clear")
def clear_partner_logo(
    partner_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    old = _load(conn, actor, partner_id)
    # The old logo row stays in partner_logos; only the link is removed.
    conn.execute(text("UPDATE partners SET logo_id = NULL WHERE id = :id"), {"id": old["id"]})
    write_audit(conn, actor, "partner.logo_cleared", old["name"])
    return _by_id(conn, old["id"])
