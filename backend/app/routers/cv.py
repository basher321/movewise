"""AI CV Agent - projects, auto-save and uploads (spec B28, phase 1).

Part of Core: any signed-in applicant of any service. The API follows the applicant pattern
/me/{module}/cv/...; module is the service the person is signed in to.
Order of checks: signed in -> licensed service -> own project -> input valid -> work.
Every change writes exactly one audit row in the same transaction. Files are removed from disk
only after the transaction commits.
"""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, RowMapping
from starlette.datastructures import UploadFile

from app.audit import write_audit
from app.auth.deps import Applicant, current_applicant
from app.cv import storage
from app.cv.options import (
    CATEGORIES,
    COUNTRIES,
    CV_TYPES,
    DOC_KINDS,
    FEATURED_COUNTRIES,
    MAX_ADVERT,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_PROJECTS,
    MAX_TITLE,
    MAX_UPLOADS_PER_HOUR,
    TEMPLATES,
)
from app.countries import WORLD_COUNTRIES
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.files import clean_name
from app.licence import MODULES, Module

router = APIRouter()

CONSENT_TEXT = "I confirm these documents are mine and I agree to AI processing."


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "CV not found.")


def _module(module: str) -> Module:
    if module not in MODULES:
        raise ApiError("NOT_FOUND", 404, "Not found.")
    return cast(Module, module)


def _uuid(value: str, error: ApiError) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise error from None


def remove_after_commit(conn: Connection, stored_names: list[str]) -> None:
    """Remove file content from disk once the change is committed (never on a rollback)."""
    if not stored_names:
        return

    def on_commit(_: Connection) -> None:
        for name in stored_names:
            storage.remove(name)

    event.listen(conn, "commit", on_commit, once=True)


def _keep_new_file_on_commit_only(conn: Connection, stored_name: str) -> None:
    state = {"committed": False}

    def on_commit(_: Connection) -> None:
        state["committed"] = True

    def on_rollback(_: Connection) -> None:
        if not state["committed"]:
            storage.remove(stored_name)

    event.listen(conn, "commit", on_commit, once=True)
    event.listen(conn, "rollback", on_rollback, once=True)


# ---------------------------------------------------------------- views


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def file_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "file_name": row["file_name"],
        "doc_kind": row["doc_kind"],
        "mime": row["mime"],
        "size_bytes": int(row["size_bytes"]),
        "extraction_status": row["extraction_status"],
        "removed": row["deleted_at"] is not None,
        "delete_after": row["delete_after"].isoformat(),
        "created_at": row["created_at"].isoformat(),
    }


def project_view(row: RowMapping, files: list[RowMapping] | None = None) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(row["id"]),
        "module": row["module"],
        "title": row["title"],
        "cv_type": row["cv_type"],
        "cover_letter": row["cover_letter"],
        "country": row["country"],
        "category": row["category"],
        "job_advert_text": row["job_advert_text"],
        "doc_kinds": list(row["doc_kinds"] or []),
        "consent": row["consent_at"] is not None,
        "template": row["template"],
        "page_length": int(row["page_length"]),
        "step": int(row["step"]),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
    if files is not None:
        view["files"] = [file_view(f) for f in files]
    return view


def _own_project(conn: Connection, me: Applicant, module: Module, project_id: str, lock: bool = False) -> RowMapping:
    row = conn.execute(
        text(
            "SELECT * FROM cv_projects WHERE id = :id AND applicant_id = :a AND module = :m AND status <> 'deleted'"
            + (" FOR UPDATE" if lock else "")
        ),
        {"id": _uuid(project_id, _not_found()), "a": me.account["id"], "m": module},
    ).mappings().one_or_none()
    if row is None:
        raise _not_found()
    return row


def _files(conn: Connection, project_id: Any) -> list[RowMapping]:
    return list(
        conn.execute(
            text("SELECT * FROM cv_files WHERE project_id = :p ORDER BY created_at, id"), {"p": project_id}
        ).mappings()
    )


def _detail(conn: Connection, project_id: Any) -> dict[str, Any]:
    row = conn.execute(text("SELECT * FROM cv_projects WHERE id = :id"), {"id": project_id}).mappings().one()
    return project_view(row, _files(conn, project_id))


# ---------------------------------------------------------------- options (public)


@router.get("/cv/options")
def cv_options() -> dict[str, Any]:
    return {
        "cv_types": list(CV_TYPES),
        "categories": list(CATEGORIES),
        "featured_countries": list(FEATURED_COUNTRIES),
        "countries": list(WORLD_COUNTRIES),
        "doc_kinds": list(DOC_KINDS),
        "templates": list(TEMPLATES),
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "consent_text": CONSENT_TEXT,
    }


# ---------------------------------------------------------------- projects


class ProjectIn(BaseModel):
    cv_type: str | None = Field(default=None, max_length=30)
    cover_letter: StrictBool = False


class ProjectChanges(BaseModel):
    title: str | None = Field(default=None, max_length=1000)
    cv_type: str | None = Field(default=None, max_length=30)
    cover_letter: StrictBool | None = None
    country: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=40)
    job_advert_text: str | None = Field(default=None, max_length=MAX_ADVERT + 1000)
    doc_kinds: list[str] | None = Field(default=None, max_length=20)
    template: str | None = Field(default=None, max_length=30)
    page_length: StrictInt | None = None
    step: StrictInt | None = None


@router.get("/me/{module}/cv/projects")
def list_projects(module: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    service = _module(module)
    rows = conn.execute(
        text(
            "SELECT * FROM cv_projects WHERE applicant_id = :a AND module = :m AND status <> 'deleted' "
            "ORDER BY updated_at DESC, id LIMIT 100"
        ),
        {"a": me.account["id"], "m": service},
    ).mappings()
    return {"items": [project_view(r) for r in rows]}


@router.post("/me/{module}/cv/projects")
async def create_project(
    module: str, request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    service = _module(module)
    body = parse_body(ProjectIn, await request.body())
    if body.cv_type is not None and body.cv_type not in CV_TYPES:
        raise _invalid("Please choose a CV type.")
    active = conn.execute(
        text("SELECT count(*) FROM cv_projects WHERE applicant_id = :a AND status <> 'deleted'"), {"a": me.account["id"]}
    ).scalar_one()
    if int(active) >= MAX_PROJECTS:
        raise ApiError("CONFLICT", 409, f"You can keep up to {MAX_PROJECTS} CVs. Please delete one first.")
    row = conn.execute(
        text(
            "INSERT INTO cv_projects (applicant_id, module, cv_type, cover_letter, step) "
            "VALUES (:a, :m, :t, :c, :s) RETURNING *"
        ),
        {"a": me.account["id"], "m": service, "t": body.cv_type, "c": body.cover_letter, "s": 2 if body.cv_type else 1},
    ).mappings().one()
    write_audit(conn, me.actor, "cv.created", str(row["id"]))
    return project_view(row, [])


@router.get("/me/{module}/cv/projects/{project_id}")
def get_project(
    module: str, project_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _own_project(conn, me, _module(module), project_id)
    return project_view(row, _files(conn, row["id"]))


def _changes(body: ProjectChanges) -> dict[str, Any]:
    """The columns to save, each checked. Only the fields the client sent."""
    sent = body.model_fields_set
    out: dict[str, Any] = {}
    if "title" in sent and body.title is not None:
        title = " ".join(body.title.split())
        if len(title) > MAX_TITLE:
            raise _invalid(f"The title must be at most {MAX_TITLE} characters.")
        out["title"] = title
    if "cv_type" in sent:
        if body.cv_type is not None and body.cv_type not in CV_TYPES:
            raise _invalid("Please choose a CV type.")
        out["cv_type"] = body.cv_type
    if "cover_letter" in sent and body.cover_letter is not None:
        out["cover_letter"] = body.cover_letter
    if "country" in sent:
        if body.country is not None and body.country not in COUNTRIES:
            raise _invalid("Please choose a country from the list.")
        out["country"] = body.country
    if "category" in sent:
        if body.category is not None and body.category not in CATEGORIES:
            raise _invalid("Please choose a category.")
        out["category"] = body.category
    if "job_advert_text" in sent and body.job_advert_text is not None:
        advert = body.job_advert_text.strip()
        if len(advert) > MAX_ADVERT:
            raise _invalid(f"The job advert must be at most {MAX_ADVERT} characters.")
        out["job_advert_text"] = advert
    if "doc_kinds" in sent and body.doc_kinds is not None:
        kinds = list(dict.fromkeys(body.doc_kinds))
        if any(k not in DOC_KINDS for k in kinds):
            raise _invalid("Please choose document types from the list.")
        out["doc_kinds"] = kinds
    if "template" in sent:
        if body.template is not None and body.template not in TEMPLATES:
            raise _invalid("Please choose a template.")
        out["template"] = body.template
    if "page_length" in sent and body.page_length is not None:
        if body.page_length not in (1, 2):
            raise _invalid("The CV can be 1 or 2 pages.")
        out["page_length"] = body.page_length
    if "step" in sent and body.step is not None:
        if not 1 <= body.step <= 8:
            raise _invalid("Unknown step.")
        out["step"] = body.step
    return out


@router.patch("/me/{module}/cv/projects/{project_id}")
async def save_project(
    module: str,
    project_id: str,
    request: Request,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    service = _module(module)
    row = _own_project(conn, me, service, project_id, lock=True)
    changes = _changes(parse_body(ProjectChanges, await request.body()))
    if not changes:
        return _detail(conn, row["id"])
    if row["status"] == "approved":
        # Any change to an approved CV makes it a draft again (it is approved after the next review).
        changes["status"] = "draft"
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    conn.execute(text(f"UPDATE cv_projects SET {sets} WHERE id = :id"), {**changes, "id": row["id"]})
    write_audit(conn, me.actor, "cv.saved", f"{row['id']} · {', '.join(sorted(changes))}")
    return _detail(conn, row["id"])


@router.post("/me/{module}/cv/projects/{project_id}/duplicate")
def duplicate_project(
    module: str, project_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    service = _module(module)
    row = _own_project(conn, me, service, project_id)
    active = conn.execute(
        text("SELECT count(*) FROM cv_projects WHERE applicant_id = :a AND status <> 'deleted'"), {"a": me.account["id"]}
    ).scalar_one()
    if int(active) >= MAX_PROJECTS:
        raise ApiError("CONFLICT", 409, f"You can keep up to {MAX_PROJECTS} CVs. Please delete one first.")
    title = (row["title"] + " (copy)")[:MAX_TITLE] if row["title"] else ""
    copy = conn.execute(
        text(
            "INSERT INTO cv_projects (applicant_id, module, title, cv_type, cover_letter, country, category, "
            "job_advert_text, doc_kinds, template, page_length, step) SELECT applicant_id, module, :title, cv_type, "
            "cover_letter, country, category, job_advert_text, doc_kinds, template, page_length, "
            "LEAST(step, 4) FROM cv_projects WHERE id = :id RETURNING *"
        ),
        {"id": row["id"], "title": title},
    ).mappings().one()
    latest = conn.execute(
        text("SELECT data FROM cv_versions WHERE project_id = :p ORDER BY version DESC LIMIT 1"), {"p": row["id"]}
    ).one_or_none()
    if latest is not None:
        conn.execute(
            text("INSERT INTO cv_versions (project_id, version, data, reason) VALUES (:p, 1, :d, 'restored')"),
            {"p": copy["id"], "d": latest.data},
        )
    write_audit(conn, me.actor, "cv.duplicated", f"{row['id']} -> {copy['id']}")
    return project_view(copy, [])


@router.post("/me/{module}/cv/projects/{project_id}/delete")
def delete_project(
    module: str, project_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _own_project(conn, me, _module(module), project_id, lock=True)
    removed = conn.execute(
        text(
            "WITH gone AS (SELECT id, storage_path FROM cv_files WHERE project_id = :p AND deleted_at IS NULL FOR UPDATE) "
            "UPDATE cv_files f SET storage_path = NULL, deleted_at = now() FROM gone WHERE f.id = gone.id "
            "RETURNING gone.storage_path"
        ),
        {"p": row["id"]},
    ).scalars().all()
    conn.execute(text("UPDATE cv_projects SET status = 'deleted', deleted_at = now() WHERE id = :id"), {"id": row["id"]})
    remove_after_commit(conn, [str(n) for n in removed if n])
    write_audit(conn, me.actor, "cv.deleted", f"{row['id']} · {len(removed)} files removed")
    return {"id": str(row["id"]), "status": "deleted"}


# ---------------------------------------------------------------- consent and files


class ConsentIn(BaseModel):
    agree: StrictBool


@router.post("/me/{module}/cv/projects/{project_id}/consent")
async def give_consent(
    module: str,
    project_id: str,
    request: Request,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    row = _own_project(conn, me, _module(module), project_id, lock=True)
    body = parse_body(ConsentIn, await request.body())
    if not body.agree:
        raise _invalid("Please tick the box to agree before uploading.")
    if row["consent_at"] is None:
        conn.execute(text("UPDATE cv_projects SET consent_at = now() WHERE id = :id"), {"id": row["id"]})
        write_audit(conn, me.actor, "cv.consent_given", str(row["id"]))
    return _detail(conn, row["id"])


async def _upload_parts(request: Request) -> tuple[str, str, bytes]:
    try:
        form = await request.form(max_files=1, max_fields=5)
    except Exception:
        raise _invalid("Please send the document as a file upload.") from None
    kind = form.get("doc_kind")
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise _invalid("Please choose a file.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    return (kind.strip() if isinstance(kind, str) else "other") or "other", clean_name(upload.filename or ""), data


@router.post("/me/{module}/cv/projects/{project_id}/files")
async def upload_file(
    module: str,
    project_id: str,
    request: Request,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    row = _own_project(conn, me, _module(module), project_id, lock=True)
    kind, name, data = await _upload_parts(request)
    if kind not in DOC_KINDS:
        raise _invalid("Please choose what kind of document this is.")
    if row["consent_at"] is None:
        raise ApiError("CONFLICT", 409, "Please tick the consent box before uploading.")
    mime = storage.check_upload(data, MAX_FILE_BYTES)
    active = conn.execute(
        text("SELECT count(*) FROM cv_files WHERE project_id = :p AND deleted_at IS NULL"), {"p": row["id"]}
    ).scalar_one()
    if int(active) >= MAX_FILES:
        raise _invalid(f"You can upload up to {MAX_FILES} files for one CV. Remove one first.")
    recent = conn.execute(
        text("SELECT count(*) FROM cv_files WHERE applicant_id = :a AND created_at > now() - interval '1 hour'"),
        {"a": me.account["id"]},
    ).scalar_one()
    if int(recent) >= MAX_UPLOADS_PER_HOUR:
        raise ApiError("TOO_MANY_TRIES", 429, "Too many uploads. Please try again in an hour.")
    if not storage.scan_for_viruses(data):
        raise _invalid("This file did not pass the safety check.")
    days = int(conn.execute(text("SELECT cv_file_days FROM settings WHERE singleton = 'settings'")).scalar_one())
    saved = storage.save(data, mime)
    try:
        conn.execute(
            text(
                "INSERT INTO cv_files (project_id, applicant_id, file_name, doc_kind, mime, size_bytes, sha256, "
                "storage_path, extraction_status, delete_after) VALUES (:p, :a, :n, :k, :mime, :size, :sha, :path, "
                ":status, now() + make_interval(days => :days))"
            ),
            {
                "p": row["id"], "a": me.account["id"], "n": name, "k": kind, "mime": mime, "size": saved.size_bytes,
                "sha": saved.sha256, "path": saved.stored_name,
                "status": "unsupported" if mime == storage.DOC else "waiting", "days": days,
            },
        )
        write_audit(conn, me.actor, "cv.file_uploaded", f"{row['id']} · {kind}")
    except BaseException:
        storage.remove(saved.stored_name)
        raise
    _keep_new_file_on_commit_only(conn, saved.stored_name)
    return _detail(conn, row["id"])


@router.post("/me/{module}/cv/projects/{project_id}/files/{file_id}/remove")
def remove_file(
    module: str,
    project_id: str,
    file_id: str,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    row = _own_project(conn, me, _module(module), project_id, lock=True)
    found = conn.execute(
        text("SELECT * FROM cv_files WHERE id = :id AND project_id = :p FOR UPDATE"),
        {"id": _uuid(file_id, ApiError("NOT_FOUND", 404, "File not found.")), "p": row["id"]},
    ).mappings().one_or_none()
    if found is None:
        raise ApiError("NOT_FOUND", 404, "File not found.")
    if found["deleted_at"] is None:
        conn.execute(
            text("UPDATE cv_files SET storage_path = NULL, deleted_at = now() WHERE id = :id"), {"id": found["id"]}
        )
        remove_after_commit(conn, [found["storage_path"]])
        write_audit(conn, me.actor, "cv.file_removed", f"{row['id']} · {found['doc_kind']}")
    return _detail(conn, row["id"])
