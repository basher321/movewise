"""Documents (spec B06): applicant upload and viewing, admin list, viewing, verify and reject.

The applicant reaches only their own documents (others are 404). Staff need the section of the
application's module. Every change writes exactly one audit row; each admin view of a file
writes "Document viewed".
"""

from datetime import date, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, RowMapping
from starlette.datastructures import UploadFile

from app.applications import add_event, item_title, item_row, notify_applicant, parse_id
from app.audit import Actor, write_audit
from app.auth.deps import Applicant, current_applicant, ensure_section, get_current_actor
from app.db.engine import get_conn
from app.documents import EXPIRING_DAYS, document_view, file_response
from app.errors import ApiError, parse_body
from app.files import MAX_FILE_BYTES, SavedFile, check_file, clean_name, read_file, remove_saved, save_file
from app.licence import read_licence, today_dhaka
from app.stages import APP_MODULES, DOCUMENT_TYPES, AppModule

router = APIRouter()

MAX_UPLOADS_PER_HOUR = 20
MAX_DOCS_PER_APPLICATION = 60
MAX_REASON = 500
PAGE_SIZE = 50


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _doc_not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Document not found.")


def _app_module(module: str) -> AppModule:
    if module not in APP_MODULES:
        raise ApiError("NOT_FOUND", 404, "Not found.")
    return cast(AppModule, module)


def _cleanup_on_rollback(conn: Connection, saved: SavedFile) -> None:
    """If the transaction is rolled back later (for example at commit), remove the new file."""
    state = {"committed": False}

    def on_commit(_: Connection) -> None:
        state["committed"] = True

    def on_rollback(_: Connection) -> None:
        if not state["committed"]:
            remove_saved(saved)

    event.listen(conn, "commit", on_commit, once=True)
    event.listen(conn, "rollback", on_rollback, once=True)


# ---------------------------------------------------------------- applicant

_OWN_APP_LOCKED = text(
    "SELECT * FROM applications WHERE id = :id AND applicant_id = :applicant AND module = :module FOR UPDATE"
)
_UPLOADS_LAST_HOUR = text(
    "SELECT count(*) FROM documents WHERE applicant_id = :applicant AND uploaded_at > now() - interval '1 hour'"
)
_DOCS_OF_APP = text("SELECT count(*) FROM documents WHERE application_id = :id")
_REPLACE_OLDER = text(
    "UPDATE documents SET status = 'replaced' WHERE application_id = :app AND type = :type "
    "AND status IN ('pending', 'verified', 'rejected')"
)
_INSERT_DOC = text(
    "INSERT INTO documents (application_id, applicant_id, type, original_name, stored_name, mime, size_bytes, sha256) "
    "VALUES (:app, :applicant, :type, :name, :stored, :mime, :size, :sha) RETURNING *"
)


async def _form_parts(request: Request) -> tuple[str, str, bytes]:
    try:
        form = await request.form(max_files=1, max_fields=5)
    except Exception:
        raise _invalid("Please send the document as a file upload.") from None
    doc_type = form.get("type")
    upload = form.get("file")
    if not isinstance(doc_type, str) or not isinstance(upload, UploadFile):
        raise _invalid("Please choose the document type and a file.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    return doc_type.strip(), clean_name(upload.filename or ""), data


@router.post("/me/{module}/applications/{app_id}/documents")
async def upload_document(
    module: str,
    app_id: str,
    request: Request,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    app_module = _app_module(module)
    uid = parse_id(app_id)
    app = conn.execute(
        _OWN_APP_LOCKED, {"id": uid, "applicant": me.account["id"], "module": app_module}
    ).mappings().one_or_none()
    if app is None:
        raise ApiError("NOT_FOUND", 404, "Application not found.")
    doc_type, name, data = await _form_parts(request)
    if doc_type not in DOCUMENT_TYPES[app_module]:
        raise _invalid("Please choose one of the required document types.")
    mime = check_file(data)
    if app["self_apply"]:
        raise ApiError("CONFLICT", 409, "A Self Apply has no documents to upload.")
    if app["status"] != "active":
        raise ApiError("CONFLICT", 409, "Documents can only be uploaded while the application is active.")
    if int(conn.execute(_UPLOADS_LAST_HOUR, {"applicant": me.account["id"]}).scalar_one()) >= MAX_UPLOADS_PER_HOUR:
        raise ApiError("TOO_MANY_TRIES", 429, "Too many uploads. Please try again in an hour.")
    if int(conn.execute(_DOCS_OF_APP, {"id": app["id"]}).scalar_one()) >= MAX_DOCS_PER_APPLICATION:
        raise _invalid("This application already has the most documents allowed. Please contact us.")

    saved = save_file(data, mime)
    try:
        conn.execute(_REPLACE_OLDER, {"app": app["id"], "type": doc_type})
        row = conn.execute(
            _INSERT_DOC,
            {
                "app": app["id"],
                "applicant": me.account["id"],
                "type": doc_type,
                "name": name,
                "stored": saved.stored_name,
                "mime": saved.mime,
                "size": saved.size_bytes,
                "sha": saved.sha256,
            },
        ).mappings().one()
        add_event(conn, app["id"], me.actor, f"Uploaded {doc_type}")
        write_audit(conn, me.actor, "document.uploaded", f"{app['ref']} · {doc_type}")
    except BaseException:
        remove_saved(saved)
        raise
    _cleanup_on_rollback(conn, saved)
    return document_view(row, "applicant", app_module)


_OWN_DOC = text(
    "SELECT d.* FROM documents d JOIN applications a ON a.id = d.application_id "
    "WHERE d.id = :id AND d.applicant_id = :applicant AND a.module = :module"
)


@router.get("/me/{module}/documents/{doc_id}/file")
def my_document_file(
    module: str, doc_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> Response:
    app_module = _app_module(module)
    try:
        uid = UUID(doc_id)
    except ValueError:
        raise _doc_not_found() from None
    row = conn.execute(_OWN_DOC, {"id": uid, "applicant": me.account["id"], "module": app_module}).mappings().one_or_none()
    if row is None:
        raise _doc_not_found()
    return file_response(read_file(row["stored_name"], row["id"]), row["mime"], row["original_name"])


# ---------------------------------------------------------------- admin

_ADMIN_DOC = text(
    "SELECT d.*, a.module, a.ref, a.status AS app_status, a.applicant_id AS a_applicant, a.university_id, "
    "a.vacancy_id, a.id AS app_id FROM documents d JOIN applications a ON a.id = d.application_id WHERE d.id = :id"
)


def _admin_doc(conn: Connection, actor: Actor, doc_id: str, lock: bool) -> RowMapping:
    try:
        uid = UUID(doc_id)
    except ValueError:
        raise _doc_not_found() from None
    row = conn.execute(_ADMIN_DOC, {"id": uid}).mappings().one_or_none()
    if row is None:
        raise _doc_not_found()
    ensure_section(conn, actor, row["module"])
    if lock:
        conn.execute(text("SELECT 1 FROM documents WHERE id = :id FOR UPDATE"), {"id": uid})
        row = conn.execute(_ADMIN_DOC, {"id": uid}).mappings().one()
    return row


def _allowed_modules(conn: Connection, actor: Actor) -> list[AppModule]:
    licence = read_licence(conn)
    allowed: list[AppModule] = []
    for m in APP_MODULES:
        if not licence.licensed(m):
            continue
        if actor.role == "super_admin" or (actor.role == "admin" and m in actor.sections):
            allowed.append(m)
    return allowed


_FILTERS = {
    "all": "TRUE",
    "pending": "d.status = 'pending'",
    "rejected": "d.status = 'rejected'",
    "verified": "d.status = 'verified' AND (d.expiry IS NULL OR d.expiry > :soon)",
    "expiring": "d.status = 'verified' AND d.expiry >= :today AND d.expiry <= :soon",
    "expired": "d.status = 'verified' AND d.expiry < :today",
}


@router.get("/admin/documents")
def list_documents(
    filter: str = "pending",
    q: str = "",
    page: int = 1,
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    modules = _allowed_modules(conn, actor)
    if not modules:
        raise ApiError("FORBIDDEN", 403, "You do not have access to documents.")
    if filter not in _FILTERS:
        raise _invalid("Unknown filter.")
    if page < 1:
        raise _invalid("Page must be 1 or more.")
    today = today_dhaka()
    params: dict[str, Any] = {
        "modules": modules,
        "today": today,
        "soon": today + timedelta(days=EXPIRING_DAYS),
    }
    where = f"a.module = ANY(:modules) AND {_FILTERS[filter]}"
    search = q.strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where += (
            " AND (p.name ILIKE :q OR p.email ILIKE :q OR a.ref ILIKE :q OR d.type ILIKE :q "
            "OR COALESCE(u.name, v.title, vp.title) ILIKE :q)"
        )
    base = (
        "FROM documents d JOIN applications a ON a.id = d.application_id "
        "JOIN applicant_accounts p ON p.id = d.applicant_id "
        "LEFT JOIN universities u ON u.id = a.university_id LEFT JOIN vacancies v ON v.id = a.vacancy_id "
        "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id "
        f"WHERE {where}"
    )
    total = int(conn.execute(text(f"SELECT count(*) {base}"), params).scalar_one())
    rows = conn.execute(
        text(
            "SELECT d.*, a.module, a.ref, a.status AS app_status, p.name AS p_name, p.email AS p_email, "
            f"COALESCE(u.name, v.title, vp.title) AS item_title {base} "
            "ORDER BY d.uploaded_at DESC, d.id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE},
    ).mappings()
    items = [
        {
            **document_view(r, "admin", r["module"]),
            "module": r["module"],
            "applicant": {"name": r["p_name"], "email": r["p_email"]},
            "application_ref": r["ref"],
            "item_title": r["item_title"],
            "application_status": r["app_status"],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": PAGE_SIZE}


@router.get("/admin/documents/{doc_id}/file")
def admin_document_file(
    doc_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> Response:
    row = _admin_doc(conn, actor, doc_id, lock=False)
    data = read_file(row["stored_name"], row["id"])
    write_audit(conn, actor, "Document viewed", f"{row['ref']} · {row['type']} ({row['id']})")
    return file_response(data, row["mime"], row["original_name"])


class VerifyIn(BaseModel):
    expiry: date | None = None


class RejectIn(BaseModel):
    reason: str = Field(max_length=5000)


def _ensure_pending(row: RowMapping) -> None:
    if row["status"] != "pending":
        raise ApiError("CONFLICT", 409, "Only a document waiting for review can be verified or rejected.")


@router.post("/admin/documents/{doc_id}/verify")
async def verify_document(
    doc_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _admin_doc(conn, actor, doc_id, lock=True)
    body = parse_body(VerifyIn, await request.body())
    _ensure_pending(row)
    updated = conn.execute(
        text(
            "UPDATE documents SET status = 'verified', expiry = :expiry, reviewed_by = :by, reviewed_at = now() "
            "WHERE id = :id RETURNING *"
        ),
        {"expiry": body.expiry, "by": actor.id, "id": row["id"]},
    ).mappings().one()
    add_event(conn, row["app_id"], actor, f"{row['type']} verified")
    write_audit(conn, actor, "document.verified", f"{row['ref']} · {row['type']}")
    return document_view(updated, "admin", row["module"])


@router.post("/admin/documents/{doc_id}/reject")
async def reject_document(
    doc_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _admin_doc(conn, actor, doc_id, lock=True)
    reason = parse_body(RejectIn, await request.body()).reason.strip()
    if not reason:
        raise _invalid("Please give a reason.")
    if len(reason) > MAX_REASON:
        raise _invalid(f"The reason must be at most {MAX_REASON} characters.")
    _ensure_pending(row)
    updated = conn.execute(
        text(
            "UPDATE documents SET status = 'rejected', note = :note, reviewed_by = :by, reviewed_at = now() "
            "WHERE id = :id RETURNING *"
        ),
        {"note": reason, "by": actor.id, "id": row["id"]},
    ).mappings().one()
    add_event(conn, row["app_id"], actor, f"{row['type']} rejected", reason)
    app = conn.execute(text("SELECT * FROM applications WHERE id = :id"), {"id": row["app_id"]}).mappings().one()
    title = item_title(row["module"], item_row(conn, app))
    notify_applicant(
        conn,
        app,
        "document_rejected",
        f"Please upload your {row['type']} again",
        f"Your {row['type']} for {title} ({row['ref']}) could not be accepted.\n\nReason: {reason}\n\n"
        "Please upload it again from your profile.",
    )
    write_audit(conn, actor, "document.rejected", f"{row['ref']} · {row['type']}")
    return document_view(updated, "admin", row["module"])
