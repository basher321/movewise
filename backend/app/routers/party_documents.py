"""Agreements and other documents of partner agents and partners (spec B21).

Files are stored on disk like applicant documents (app/files.py), up to 10 MB, PDF, JPG or PNG,
with the type decided by the file's first bytes. Rows are never deleted: an old document is
archived, and an archived document is final.

Who may do what follows the agent and partner pages:
- Agent documents: seen by the super admin and by admins with one of the agent's sections;
  uploaded and archived by the super admin only (only they edit agents).
- Partner documents: seen, uploaded and archived by the super admin and by admins of the
  partner's section (they edit partners). Finance never.

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Every change writes exactly one audit row in the same transaction; each view of a file writes one.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from starlette.datastructures import UploadFile

from app.audit import Actor, write_audit
from app.auth.deps import ensure_licensed, ensure_section, get_current_actor
from app.db.engine import get_conn
from app.documents import EXPIRING_DAYS, file_response
from app.errors import ApiError
from app.files import check_file, clean_name, read_file, remove_saved, save_file
from app.licence import Module, read_licence, today_dhaka
from app.routers.documents import _cleanup_on_rollback

router = APIRouter()

OwnerKind = Literal["agent", "partner"]

MAX_PARTY_FILE_BYTES = 10 * 1024 * 1024
MAX_DOCS_PER_OWNER = 200
MAX_TITLE = 120
MAX_NOTE = 500

DOC_TYPES = ("agreement", "trade_licence", "id_document", "bank_details", "other")
DOC_TYPE_LABELS = {
    "agreement": "Agreement",
    "trade_licence": "Trade licence",
    "id_document": "ID document",
    "bank_details": "Bank details",
    "other": "Other",
}


@dataclass(frozen=True)
class Owner:
    kind: OwnerKind
    id: UUID
    name: str


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _doc_not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Document not found.")


def _uuid(value: str, missing: ApiError) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise missing from None


# ---------------------------------------------------------------- who may do what


def _agent(conn: Connection, actor: Actor, agent_id: str, edit: bool) -> Owner:
    missing = ApiError("NOT_FOUND", 404, "Agent not found.")
    uid = _uuid(agent_id, missing)
    lock = " FOR UPDATE" if edit else ""
    row = conn.execute(
        text(f"SELECT id, name, sections FROM partner_agents WHERE id = :id{lock}"), {"id": uid}
    ).mappings().one_or_none()
    if row is None:
        raise missing
    licence = read_licence(conn)
    sections = [cast(Module, s) for s in row["sections"]]
    licensed = [s for s in sections if licence.licensed(s)]
    if not licensed:
        ensure_licensed(conn, sections[0] if sections else "study")
    if edit:
        if actor.role != "super_admin":
            raise ApiError("FORBIDDEN", 403, "Only the super admin can do this.")
    elif not (actor.role == "super_admin" or (actor.role == "admin" and set(licensed) & set(actor.sections))):
        raise ApiError("FORBIDDEN", 403, "You do not have access to this agent.")
    return Owner("agent", row["id"], row["name"])


def _partner(conn: Connection, actor: Actor, partner_id: str, edit: bool) -> Owner:
    missing = ApiError("NOT_FOUND", 404, "Partner not found.")
    uid = _uuid(partner_id, missing)
    lock = " FOR UPDATE" if edit else ""
    row = conn.execute(
        text(f"SELECT id, name, module FROM partners WHERE id = :id{lock}"), {"id": uid}
    ).mappings().one_or_none()
    if row is None:
        raise missing
    ensure_section(conn, actor, row["module"])
    return Owner("partner", row["id"], row["name"])


def _owner(conn: Connection, actor: Actor, kind: OwnerKind, owner_id: str, edit: bool) -> Owner:
    return _agent(conn, actor, owner_id, edit) if kind == "agent" else _partner(conn, actor, owner_id, edit)


# ---------------------------------------------------------------- views

_SELECT = (
    "SELECT d.*, u.name AS uploaded_by_name, z.name AS archived_by_name FROM party_documents d "
    "JOIN admin_users u ON u.id = d.uploaded_by LEFT JOIN admin_users z ON z.id = d.archived_by "
)


def shown_status(row: RowMapping, today: date | None = None) -> str:
    """'archived', or by the valid-until date 'expired' / 'expiring' / 'active'; never stored."""
    if row["status"] == "archived":
        return "archived"
    until: date | None = row["valid_until"]
    day = today or today_dhaka()
    if until is not None:
        if until < day:
            return "expired"
        if until <= day + timedelta(days=EXPIRING_DAYS):
            return "expiring"
    return "active"


def document_view(row: RowMapping, owner: Owner) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "doc_type": row["doc_type"],
        "title": row["title"],
        "original_name": row["original_name"],
        "mime": row["mime"],
        "size_bytes": row["size_bytes"],
        "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
        "note": row["note"],
        "status": row["status"],
        "shown_status": shown_status(row),
        "uploaded_at": row["created_at"].isoformat(),
        "uploaded_by_name": row["uploaded_by_name"],
        "archived_at": row["archived_at"].isoformat() if row["archived_at"] else None,
        "archived_by_name": row["archived_by_name"],
        "file_url": f"/api/admin/{owner.kind}s/{owner.id}/documents/{row['id']}/file",
    }


def _owner_column(kind: OwnerKind) -> str:
    return "agent_id" if kind == "agent" else "partner_id"


def _doc_row(conn: Connection, owner: Owner, doc_id: str, lock: bool = False) -> RowMapping:
    uid = _uuid(doc_id, _doc_not_found())
    where = f"WHERE d.id = :id AND d.{_owner_column(owner.kind)} = :owner"
    if lock:
        found = conn.execute(
            text(f"SELECT d.id FROM party_documents d {where} FOR UPDATE"), {"id": uid, "owner": owner.id}
        ).one_or_none()
        if found is None:
            raise _doc_not_found()
    row = conn.execute(text(_SELECT + where), {"id": uid, "owner": owner.id}).mappings().one_or_none()
    if row is None:
        raise _doc_not_found()
    return row


def _label(row: RowMapping | dict[str, Any]) -> str:
    title = row["title"] or row["original_name"]
    return f"{DOC_TYPE_LABELS[row['doc_type']]}: {title}"


# ---------------------------------------------------------------- shared work


def _list(conn: Connection, owner: Owner) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            _SELECT + f"WHERE d.{_owner_column(owner.kind)} = :owner "
            "ORDER BY (d.status = 'archived'), d.created_at DESC, d.id"
        ),
        {"owner": owner.id},
    ).mappings()
    return [document_view(r, owner) for r in rows]


def _text_field(form: Any, name: str) -> str:
    value = form.get(name)
    return value if isinstance(value, str) else ""


async def _upload(conn: Connection, actor: Actor, owner: Owner, request: Request) -> dict[str, Any]:
    try:
        form = await request.form(max_files=1, max_fields=6)
    except Exception:
        raise _invalid("Please send the document as a file upload.") from None
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise _invalid("Please choose a file.")
    doc_type = _text_field(form, "doc_type").strip()
    if doc_type not in DOC_TYPES:
        raise _invalid("Please choose the document type.")
    title = " ".join(_text_field(form, "title").split())
    if len(title) > MAX_TITLE:
        raise _invalid(f"The title must be at most {MAX_TITLE} characters.")
    note = _text_field(form, "note").strip()
    if len(note) > MAX_NOTE:
        raise _invalid(f"The note must be at most {MAX_NOTE} characters.")
    raw_until = _text_field(form, "valid_until").strip()
    valid_until: date | None = None
    if raw_until:
        try:
            valid_until = date.fromisoformat(raw_until)
        except ValueError:
            raise _invalid("Valid until must be a date like 2027-12-31.") from None
    name = clean_name(upload.filename or "")
    data = await upload.read(MAX_PARTY_FILE_BYTES + 1)
    mime = check_file(data, MAX_PARTY_FILE_BYTES)
    column = _owner_column(owner.kind)
    count = conn.execute(
        text(f"SELECT count(*) FROM party_documents WHERE {column} = :owner"), {"owner": owner.id}
    ).scalar_one()
    if int(count) >= MAX_DOCS_PER_OWNER:
        raise _invalid(f"This {owner.kind} already has {MAX_DOCS_PER_OWNER} documents, the most allowed.")

    saved = save_file(data, mime)
    try:
        new_id = conn.execute(
            text(
                f"INSERT INTO party_documents (owner_kind, {column}, doc_type, title, original_name, stored_name, "
                "mime, size_bytes, sha256, valid_until, note, uploaded_by) VALUES (:kind, :owner, :doc_type, :title, "
                ":name, :stored, :mime, :size, :sha, :until, :note, :by) RETURNING id"
            ),
            {
                "kind": owner.kind,
                "owner": owner.id,
                "doc_type": doc_type,
                "title": title,
                "name": name,
                "stored": saved.stored_name,
                "mime": saved.mime,
                "size": saved.size_bytes,
                "sha": saved.sha256,
                "until": valid_until,
                "note": note,
                "by": actor.id,
            },
        ).scalar_one()
        row = _doc_row(conn, owner, str(new_id))
        write_audit(conn, actor, f"{owner.kind}_document.uploaded", f"{owner.name} · {_label(row)}")
    except BaseException:
        remove_saved(saved)
        raise
    _cleanup_on_rollback(conn, saved)
    return document_view(row, owner)


def _file(conn: Connection, actor: Actor, owner: Owner, doc_id: str) -> Response:
    row = _doc_row(conn, owner, doc_id)
    data = read_file(row["stored_name"], row["id"])
    write_audit(conn, actor, f"{owner.kind}_document.viewed", f"{owner.name} · {_label(row)}")
    return file_response(data, row["mime"], row["original_name"])


def _archive(conn: Connection, actor: Actor, owner: Owner, doc_id: str) -> dict[str, Any]:
    row = _doc_row(conn, owner, doc_id, lock=True)
    if row["status"] == "archived":
        raise ApiError("CONFLICT", 409, "This document is already archived.")
    conn.execute(
        text("UPDATE party_documents SET status = 'archived', archived_at = now(), archived_by = :by WHERE id = :id"),
        {"by": actor.id, "id": row["id"]},
    )
    write_audit(conn, actor, f"{owner.kind}_document.archived", f"{owner.name} · {_label(row)}")
    return document_view(_doc_row(conn, owner, doc_id), owner)


# ---------------------------------------------------------------- endpoints


@router.get("/admin/agents/{agent_id}/documents")
def list_agent_documents(
    agent_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return _list(conn, _owner(conn, actor, "agent", agent_id, edit=False))


@router.post("/admin/agents/{agent_id}/documents")
async def upload_agent_document(
    agent_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return await _upload(conn, actor, _owner(conn, actor, "agent", agent_id, edit=True), request)


@router.get("/admin/agents/{agent_id}/documents/{doc_id}/file")
def agent_document_file(
    agent_id: str, doc_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> Response:
    return _file(conn, actor, _owner(conn, actor, "agent", agent_id, edit=False), doc_id)


@router.post("/admin/agents/{agent_id}/documents/{doc_id}/archive")
def archive_agent_document(
    agent_id: str, doc_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return _archive(conn, actor, _owner(conn, actor, "agent", agent_id, edit=True), doc_id)


@router.get("/admin/partners/{partner_id}/documents")
def list_partner_documents(
    partner_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return _list(conn, _owner(conn, actor, "partner", partner_id, edit=False))


@router.post("/admin/partners/{partner_id}/documents")
async def upload_partner_document(
    partner_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return await _upload(conn, actor, _owner(conn, actor, "partner", partner_id, edit=True), request)


@router.get("/admin/partners/{partner_id}/documents/{doc_id}/file")
def partner_document_file(
    partner_id: str, doc_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> Response:
    return _file(conn, actor, _owner(conn, actor, "partner", partner_id, edit=False), doc_id)


@router.post("/admin/partners/{partner_id}/documents/{doc_id}/archive")
def archive_partner_document(
    partner_id: str, doc_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return _archive(conn, actor, _owner(conn, actor, "partner", partner_id, edit=True), doc_id)
