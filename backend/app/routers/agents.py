"""Partner agents, the agent of each case, and agent commissions (spec B16).

Agents refer applicants (Student Consultancy, Job Processing). They never sign in and are never
deleted: active = false switches one off. A paid or cancelled commission is final.

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Every change writes exactly one audit row in the same transaction.
"""

from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from app.audit import Actor, write_audit
from app.auth.accounts import is_unique_violation
from app.auth.deps import ensure_licensed, ensure_section, get_current_actor
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULE_LABELS, Module, read_licence
from app.routers.admin_applications import _load, _one_view

router = APIRouter()

AgentSection = Literal["study", "job", "visa"]
SECTIONS: tuple[AgentSection, ...] = ("study", "job", "visa")
COMMISSION_STATUSES = ("due", "paid", "cancelled")
# Key of the transaction lock that makes agent changes on one case run one at a time.
AGENT_LOCK = 3_000_016

_AGENT_COLUMNS = (
    "a.id, a.name, a.firm, a.phone, a.email, a.country, a.address, a.sections, a.commission_type, "
    "a.commission_poisha, a.commission_percent_bp, a.notes, a.active, a.created_at"
)
_AGENT_TOTALS = (
    "(SELECT count(*) FROM applications x WHERE x.agent_id = a.id) AS referred, "
    "(SELECT COALESCE(sum(c.amount_poisha), 0) FROM agent_commissions c "
    " WHERE c.agent_id = a.id AND c.status = 'due') AS due_poisha, "
    "(SELECT COALESCE(sum(c.amount_poisha), 0) FROM agent_commissions c "
    " WHERE c.agent_id = a.id AND c.status = 'paid') AS paid_poisha"
)
_AGENT_SELECT = f"SELECT {_AGENT_COLUMNS}, {_AGENT_TOTALS} FROM partner_agents a "

_COMMISSION_SELECT = (
    "SELECT c.*, g.name AS agent_name, x.ref AS application_ref, x.module AS module, "
    "p.name AS applicant_name "
    "FROM agent_commissions c "
    "JOIN partner_agents g ON g.id = c.agent_id "
    "JOIN applications x ON x.id = c.application_id "
    "JOIN applicant_accounts p ON p.id = x.applicant_id "
)


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _agent_not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Agent not found.")


def _commission_not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Commission not found.")


def _uuid(value: str, missing: ApiError) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise missing from None


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _licensed_sections(conn: Connection) -> list[AgentSection]:
    licence = read_licence(conn)
    return [s for s in SECTIONS if licence.licensed(s)]


def _visible_sections(conn: Connection, actor: Actor) -> list[AgentSection]:
    """Licensed sections this person may see agents and commissions of."""
    licensed = _licensed_sections(conn)
    if actor.role in ("super_admin", "finance"):
        return licensed
    if actor.role == "admin":
        return [s for s in licensed if s in actor.sections]
    return []


def _require_agent_viewer(conn: Connection, actor: Actor) -> list[AgentSection]:
    """Super admin, or an admin with at least one licensed agent section."""
    if actor.role == "super_admin":
        return _licensed_sections(conn)
    if actor.role == "admin":
        sections = _visible_sections(conn, actor)
        if sections:
            return sections
    raise ApiError("FORBIDDEN", 403, "You do not have access to agents.")


def _require_super(actor: Actor) -> None:
    if actor.role != "super_admin":
        raise ApiError("FORBIDDEN", 403, "Only the super admin can do this.")


def agent_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "firm": row["firm"],
        "phone": row["phone"],
        "email": row["email"],
        "country": row["country"],
        "address": row["address"],
        "sections": [s for s in SECTIONS if s in row["sections"]],
        "commission_type": row["commission_type"],
        "commission_poisha": row["commission_poisha"],
        "commission_percent_bp": row["commission_percent_bp"],
        "notes": row["notes"],
        "active": row["active"],
        "created_at": row["created_at"].isoformat(),
        "referred": int(row["referred"]),
        "due_poisha": int(row["due_poisha"]),
        "paid_poisha": int(row["paid_poisha"]),
    }


def commission_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "agent_id": str(row["agent_id"]),
        "agent_name": row["agent_name"],
        "application_id": str(row["application_id"]),
        "application_ref": row["application_ref"],
        "module": row["module"],
        "applicant_name": row["applicant_name"],
        "amount_poisha": row["amount_poisha"],
        "status": row["status"],
        "paid_at": row["paid_at"].isoformat() if row["paid_at"] else None,
        "pay_reference": row["pay_reference"],
        "note": row["note"],
        "created_at": row["created_at"].isoformat(),
    }


def _agent_by_id(conn: Connection, agent_id: UUID) -> dict[str, Any]:
    row = conn.execute(text(_AGENT_SELECT + "WHERE a.id = :id"), {"id": agent_id}).mappings().one()
    return agent_view(row)


def _commission_by_id(conn: Connection, commission_id: UUID) -> dict[str, Any]:
    row = conn.execute(text(_COMMISSION_SELECT + "WHERE c.id = :id"), {"id": commission_id}).mappings().one()
    return commission_view(row)


# ---------------------------------------------------------------- agents


class AgentIn(BaseModel):
    name: str = Field(max_length=1000)
    firm: str = Field(default="", max_length=1000)
    phone: str = Field(default="", max_length=1000)
    email: str = Field(default="", max_length=1000)
    country: str = Field(default="", max_length=1000)
    address: str = Field(default="", max_length=1000)
    sections: list[str] = Field(default_factory=list, max_length=10)
    commission_type: str = "fixed"
    commission_poisha: StrictInt = 0
    commission_percent_bp: StrictInt = 0
    notes: str = Field(default="", max_length=5000)
    active: StrictBool = True


_TEXT_LIMITS = {"firm": 120, "phone": 40, "email": 254, "country": 80, "address": 300, "notes": 1000}
_TEXT_LABELS = {
    "firm": "Firm",
    "phone": "Phone",
    "email": "Email",
    "country": "Country",
    "address": "Address",
    "notes": "Notes",
}


def _agent_values(conn: Connection, body: AgentIn) -> dict[str, Any]:
    name = body.name.strip()
    if not name:
        raise _invalid("Please enter the agent's name.")
    if len(name) > 120:
        raise _invalid("Name must be at most 120 characters.")
    values: dict[str, Any] = {"name": name}
    for field, limit in _TEXT_LIMITS.items():
        value = str(getattr(body, field)).strip()
        if len(value) > limit:
            raise _invalid(f"{_TEXT_LABELS[field]} must be at most {limit} characters.")
        values[field] = value
    if values["email"] and ("@" not in values["email"] or " " in values["email"]):
        raise _invalid("Please enter a valid email address, or leave it empty.")
    sections = list(dict.fromkeys(body.sections))
    if any(s not in SECTIONS for s in sections):
        raise _invalid(
            "Sections can only be Student Consultancy (study), Job Processing (job) and Immigration Processing (visa)."
        )
    if not sections:
        raise _invalid("Please choose at least one section for the agent.")
    licensed = _licensed_sections(conn)
    for s in sections:
        if s not in licensed:
            ensure_licensed(conn, cast(Module, s))
    values["sections"] = [s for s in SECTIONS if s in sections]
    if body.commission_type not in ("fixed", "percent"):
        raise _invalid("Commission type must be fixed or percent.")
    values["commission_type"] = body.commission_type
    if body.commission_poisha < 0:
        raise _invalid("Commission amount cannot be below 0.")
    if body.commission_poisha > 10**13:
        raise _invalid("Commission amount is too large.")
    if not 0 <= body.commission_percent_bp <= 10000:
        raise _invalid("Commission percent must be between 0 and 100.")
    values["commission_poisha"] = body.commission_poisha
    values["commission_percent_bp"] = body.commission_percent_bp
    values["active"] = body.active
    return values


def _save_agent(conn: Connection, sql: str, values: dict[str, Any]) -> UUID:
    try:
        with conn.begin_nested():
            return cast(UUID, conn.execute(text(sql), values).scalar_one())
    except IntegrityError as exc:
        if is_unique_violation(exc, "partner_agents_email_key"):
            raise ApiError("CONFLICT", 409, "Another agent already has this email.") from None
        raise


_INSERT_AGENT = (
    "INSERT INTO partner_agents (name, firm, phone, email, country, address, sections, commission_type, "
    "commission_poisha, commission_percent_bp, notes, active) VALUES (:name, :firm, :phone, :email, :country, "
    ":address, CAST(:sections AS text[]), :commission_type, :commission_poisha, :commission_percent_bp, :notes, "
    ":active) RETURNING id"
)
_UPDATE_AGENT = (
    "UPDATE partner_agents SET name = :name, firm = :firm, phone = :phone, email = :email, country = :country, "
    "address = :address, sections = CAST(:sections AS text[]), commission_type = :commission_type, "
    "commission_poisha = :commission_poisha, commission_percent_bp = :commission_percent_bp, notes = :notes, "
    "active = :active WHERE id = :id RETURNING id"
)


@router.get("/admin/agents")
def list_agents(
    q: str = "",
    section: str = "",
    active: str = "",
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> list[dict[str, Any]]:
    visible = _require_agent_viewer(conn, actor)
    where = ["a.sections && CAST(:visible AS text[])"]
    params: dict[str, Any] = {"visible": visible}
    if section:
        if section not in SECTIONS:
            raise _invalid("Section must be study, job or visa.")
        ensure_section(conn, actor, cast(Module, section))
        where.append(":section = ANY(a.sections)")
        params["section"] = section
    if active in ("true", "false"):
        where.append("a.active = :active")
        params["active"] = active == "true"
    if q.strip():
        where.append("(a.name ILIKE :q OR a.firm ILIKE :q OR a.email ILIKE :q OR a.phone ILIKE :q OR a.country ILIKE :q)")
        params["q"] = _like(q.strip()[:100])
    sql = _AGENT_SELECT + "WHERE " + " AND ".join(where) + " ORDER BY a.active DESC, lower(a.name), a.id"
    return [agent_view(r) for r in conn.execute(text(sql), params).mappings()]


@router.post("/admin/agents")
async def create_agent(
    request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    _require_super(actor)
    body = parse_body(AgentIn, await request.body())
    values = _agent_values(conn, body)
    agent_id = _save_agent(conn, _INSERT_AGENT, values)
    write_audit(conn, actor, "agent.created", values["name"])
    return _agent_by_id(conn, agent_id)


@router.put("/admin/agents/{agent_id}")
async def update_agent(
    agent_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    _require_super(actor)
    uid = _uuid(agent_id, _agent_not_found())
    old = conn.execute(text("SELECT * FROM partner_agents WHERE id = :id FOR UPDATE"), {"id": uid}).mappings().one_or_none()
    if old is None:
        raise _agent_not_found()
    body = parse_body(AgentIn, await request.body())
    values = _agent_values(conn, body)
    _save_agent(conn, _UPDATE_AGENT, {**values, "id": uid})
    if old["active"] and not values["active"]:
        detail = f"{values['name']}: switched off"
    elif not old["active"] and values["active"]:
        detail = f"{values['name']}: switched on"
    else:
        detail = values["name"]
    write_audit(conn, actor, "agent.updated", detail)
    return _agent_by_id(conn, uid)


# ---------------------------------------------------------------- the agent of a case


class CaseAgentIn(BaseModel):
    agent_id: str | None


def _fee_paid(conn: Connection, app_id: UUID) -> int:
    return int(
        conn.execute(
            text(
                "SELECT COALESCE(sum(amount_poisha), 0) FROM payments "
                "WHERE ref_type = 'application' AND ref_id = :id AND status = 'paid'"
            ),
            {"id": app_id},
        ).scalar_one()
    )


def commission_amount(agent: RowMapping, fee_paid_poisha: int) -> int:
    """Fixed: the agent's amount. Percent: the paid fee x basis points / 10000, rounded down."""
    if agent["commission_type"] == "fixed":
        return int(agent["commission_poisha"])
    return fee_paid_poisha * int(agent["commission_percent_bp"]) // 10000


@router.put("/admin/applications/{app_id}/agent")
async def set_case_agent(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    body = parse_body(CaseAgentIn, await request.body())
    module: AgentSection = app["module"]
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": AGENT_LOCK})
    agent: RowMapping | None = None
    if body.agent_id is not None:
        try:
            agent_uid = UUID(body.agent_id)
        except ValueError:
            raise _invalid("Please choose an agent from the list.") from None
        agent = conn.execute(text("SELECT * FROM partner_agents WHERE id = :id"), {"id": agent_uid}).mappings().one_or_none()
        if agent is None or not agent["active"]:
            raise _invalid("Please choose an active agent.")
        if module not in agent["sections"]:
            raise _invalid(f"This agent does not work in {MODULE_LABELS[module]}.")
    new_id = agent["id"] if agent is not None else None
    if app["agent_id"] == new_id:
        return _one_view(conn, app["id"])
    live = conn.execute(
        text("SELECT * FROM agent_commissions WHERE application_id = :id AND status <> 'cancelled' FOR UPDATE"),
        {"id": app["id"]},
    ).mappings().one_or_none()
    if live is not None and live["status"] == "paid":
        raise ApiError("CONFLICT", 409, "The commission for this case is already paid.")
    if live is not None:
        conn.execute(
            text("UPDATE agent_commissions SET status = 'cancelled', note = :note WHERE id = :id"),
            {"id": live["id"], "note": "Agent changed" if agent is not None else "Case set to direct"},
        )
    conn.execute(text("UPDATE applications SET agent_id = :agent WHERE id = :id"), {"agent": new_id, "id": app["id"]})
    if agent is not None:
        conn.execute(
            text("INSERT INTO agent_commissions (agent_id, application_id, amount_poisha) VALUES (:agent, :app, :amount)"),
            {"agent": agent["id"], "app": app["id"], "amount": commission_amount(agent, _fee_paid(conn, app["id"]))},
        )
    write_audit(conn, actor, "application.agent_set", f"{app['ref']} -> {agent['name'] if agent is not None else 'Direct'}")
    return _one_view(conn, app["id"])


# ---------------------------------------------------------------- commissions


def _require_commission_viewer(conn: Connection, actor: Actor) -> list[AgentSection]:
    if actor.role in ("super_admin", "finance", "admin"):
        sections = _visible_sections(conn, actor)
        if sections or actor.role != "admin":
            return sections
    raise ApiError("FORBIDDEN", 403, "You do not have access to commissions.")


@router.get("/admin/agents/commissions")
def list_commissions(
    agent_id: str = "",
    status: str = "",
    module: str = "",
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> list[dict[str, Any]]:
    visible = _require_commission_viewer(conn, actor)
    where = ["x.module = ANY(CAST(:visible AS text[]))"]
    params: dict[str, Any] = {"visible": visible}
    if module:
        if module not in SECTIONS:
            raise _invalid("Module must be study, job or visa.")
        ensure_licensed(conn, cast(Module, module))
        if module not in visible:
            raise ApiError("FORBIDDEN", 403, f"You do not have access to the {MODULE_LABELS[cast(Module, module)]} section.")
        where.append("x.module = :module")
        params["module"] = module
    if status:
        if status not in COMMISSION_STATUSES:
            raise _invalid("Status must be due, paid or cancelled.")
        where.append("c.status = :status")
        params["status"] = status
    if agent_id:
        params["agent_id"] = _uuid(agent_id, _invalid("Please choose an agent from the list."))
        where.append("c.agent_id = :agent_id")
    sql = _COMMISSION_SELECT + "WHERE " + " AND ".join(where) + " ORDER BY c.created_at DESC, c.id DESC LIMIT 500"
    return [commission_view(r) for r in conn.execute(text(sql), params).mappings()]


def _load_commission(conn: Connection, commission_id: str) -> RowMapping:
    uid = _uuid(commission_id, _commission_not_found())
    row = conn.execute(
        text(
            "SELECT c.*, x.module AS module, x.ref AS application_ref FROM agent_commissions c "
            "JOIN applications x ON x.id = c.application_id WHERE c.id = :id FOR UPDATE OF c"
        ),
        {"id": uid},
    ).mappings().one_or_none()
    if row is None:
        raise _commission_not_found()
    ensure_licensed(conn, row["module"])
    return row


def _require_due(row: RowMapping) -> None:
    if row["status"] != "due":
        raise ApiError("CONFLICT", 409, f"This commission is already {row['status']}.")


class CommissionEditIn(BaseModel):
    amount_poisha: StrictInt
    note: str = Field(default="", max_length=1000)


class PayIn(BaseModel):
    pay_reference: str = Field(default="", max_length=1000)


class CancelIn(BaseModel):
    note: str = Field(default="", max_length=1000)


def _note(value: str, limit: int, label: str) -> str:
    value = value.strip()
    if len(value) > limit:
        raise _invalid(f"{label} must be at most {limit} characters.")
    return value


@router.put("/admin/agents/commissions/{commission_id}")
async def edit_commission(
    commission_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _load_commission(conn, commission_id)
    _require_super(actor)
    body = parse_body(CommissionEditIn, await request.body())
    if body.amount_poisha < 0 or body.amount_poisha > 10**13:
        raise _invalid("Commission amount must be 0 or more.")
    note = _note(body.note, 300, "Note")
    _require_due(row)
    conn.execute(
        text("UPDATE agent_commissions SET amount_poisha = :amount, note = :note WHERE id = :id"),
        {"amount": body.amount_poisha, "note": note, "id": row["id"]},
    )
    write_audit(conn, actor, "commission.updated", f"{row['application_ref']}: {body.amount_poisha} poisha")
    return _commission_by_id(conn, row["id"])


@router.post("/admin/agents/commissions/{commission_id}/pay")
async def pay_commission(
    commission_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _load_commission(conn, commission_id)
    if actor.role not in ("super_admin", "finance"):
        raise ApiError("FORBIDDEN", 403, "Only the super admin or finance can do this.")
    body = parse_body(PayIn, await request.body())
    reference = _note(body.pay_reference, 120, "Payment reference")
    _require_due(row)
    conn.execute(
        text(
            "UPDATE agent_commissions SET status = 'paid', paid_at = now(), paid_by = :by, pay_reference = :ref "
            "WHERE id = :id"
        ),
        {"by": actor.id, "ref": reference, "id": row["id"]},
    )
    write_audit(conn, actor, "commission.paid", f"{row['application_ref']}: {row['amount_poisha']} poisha")
    return _commission_by_id(conn, row["id"])


@router.post("/admin/agents/commissions/{commission_id}/cancel")
async def cancel_commission(
    commission_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _load_commission(conn, commission_id)
    _require_super(actor)
    body = parse_body(CancelIn, await request.body())
    note = _note(body.note, 300, "Note")
    _require_due(row)
    conn.execute(
        text("UPDATE agent_commissions SET status = 'cancelled', note = :note WHERE id = :id"),
        {"note": note, "id": row["id"]},
    )
    write_audit(conn, actor, "commission.cancelled", row["application_ref"])
    return _commission_by_id(conn, row["id"])
