"""AI CV Agent - reading, writing, review, preview and export (spec B28, phases 3-5).

All under /me/{module}/cv/projects/{id}/... for the signed-in owner of the CV.
Order of checks: signed in -> licensed service -> own project -> input -> AI allowance -> work.
Every change writes one audit row (AI call counts go to cv_ai_calls, never document text).
The CV data lives in cv_versions (append-only): every change is a new version, so Undo is a new
version made from the one before.
"""

import json
import re
import unicodedata
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictBool, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import write_audit
from app.auth.deps import Applicant, current_applicant
from app.cv import cover_letter, extractor, gap_checker, merger, reviewer, writer
from app.cv.ai_client import Caller, ensure_allowance
from app.cv.countries import recommended_template, rules_for
from app.cv.layout import build
from app.cv.options import TEMPLATES
from app.cv.reading import Unreadable, read_file
from app.cv.render_docx import cv_docx, letter_docx
from app.cv.render_pdf import cv_pdf, letter_pdf, pdf_pages_png
from app.cv.schema import SECTIONS, CvData, needs_confirming, ordered
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.routers.cv import _detail, _module, _own_project, _uuid, file_view

router = APIRouter()

FACT_REASONS = ("answers", "extracted", "edited", "restored", "removed")
WRITTEN_REASONS = ("generated", "regenerated", "shorter", "stronger")


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _caller(row: RowMapping) -> Caller:
    return Caller(project_id=row["id"], applicant_id=row["applicant_id"])


# ---------------------------------------------------------------- versions


def _latest(conn: Connection, project_id: Any, reasons: tuple[str, ...] | None = None) -> RowMapping | None:
    sql = "SELECT * FROM cv_versions WHERE project_id = :p"
    params: dict[str, Any] = {"p": project_id}
    if reasons:
        sql += " AND reason = ANY(:r)"
        params["r"] = list(reasons)
    return conn.execute(text(sql + " ORDER BY version DESC LIMIT 1"), params).mappings().one_or_none()


def current_data(conn: Connection, project_id: Any) -> CvData:
    row = _latest(conn, project_id)
    return CvData.model_validate(row["data"]) if row else CvData()


def facts_data(conn: Connection, project_id: Any) -> CvData:
    """The person-confirmed facts the Writer may use (grounding)."""
    row = _latest(conn, project_id, FACT_REASONS) or _latest(conn, project_id)
    return CvData.model_validate(row["data"]) if row else CvData()


def _meta(conn: Connection, project_id: Any) -> dict[str, Any]:
    row = _latest(conn, project_id)
    return dict((row["data"] or {}).get("_meta") or {}) if row else {}


def save_version(conn: Connection, project_id: Any, data: CvData, reason: str, meta: dict[str, Any] | None = None) -> int:
    number = int(conn.execute(
        text("SELECT COALESCE(max(version), 0) + 1 FROM cv_versions WHERE project_id = :p"), {"p": project_id}
    ).scalar_one())
    body = ordered(data).model_dump()
    if meta:
        body["_meta"] = meta
    conn.execute(
        text("INSERT INTO cv_versions (project_id, version, data, reason) VALUES (:p, :v, CAST(:d AS jsonb), :r)"),
        {"p": project_id, "v": number, "d": json.dumps(body, ensure_ascii=False), "r": reason},
    )
    conn.execute(text("UPDATE cv_projects SET status = 'draft' WHERE id = :p AND status = 'approved'"), {"p": project_id})
    return number


def unread_kinds(conn: Connection, row: RowMapping) -> frozenset[str]:
    """Document types the person ticked or uploaded that were not read: the agent asks about them."""
    files = conn.execute(
        text("SELECT doc_kind, extraction_status FROM cv_files WHERE project_id = :p AND deleted_at IS NULL"),
        {"p": row["id"]},
    ).all()
    read = {f.doc_kind for f in files if f.extraction_status == "done"}
    wanted = set(row["doc_kinds"] or []) | {f.doc_kind for f in files}
    return frozenset(wanted - read - {"cv", "other"})


def _missing(conn: Connection, row: RowMapping, data: CvData) -> list[gap_checker.Field_]:
    rules = rules_for(row["country"], row["cv_type"])
    return gap_checker.missing(data, rules, row["cv_type"], row["category"], unread_kinds(conn, row))


def _template(row: RowMapping) -> str:
    return row["template"] or recommended_template(row["country"], row["cv_type"], row["category"])


def _state(conn: Connection, row: RowMapping) -> dict[str, Any]:
    data = current_data(conn, row["id"])
    rules = rules_for(row["country"], row["cv_type"])
    version = _latest(conn, row["id"])
    fields = _missing(conn, row, data)
    letter = conn.execute(
        text("SELECT body, version FROM cover_letters WHERE project_id = :p ORDER BY version DESC LIMIT 1"), {"p": row["id"]}
    ).one_or_none()
    return {
        "project": _detail(conn, row["id"]),
        "data": data.model_dump(),
        "version": int(version["version"]) if version else 0,
        "written": bool(version and (version["reason"] in WRITTEN_REASONS or
                                     _latest(conn, row["id"], WRITTEN_REASONS) is not None)),
        "can_undo": bool(version and int(version["version"]) > 1),
        "missing": [f.model_dump() for f in fields],
        "confirm": needs_confirming(data),
        "ask_for": _meta(conn, row["id"]).get("ask_for", []),
        "rules": {
            "country": rules.country, "document_name": rules.document_name, "spelling": rules.spelling,
            "notes": rules.notes, "page_length_default": rules.page_length_default, "photo": rules.photo,
            "allows": [f for f in ("nationality", "date_of_birth", "gender", "marital_status", "religion") if rules.allows(f)],
        },
        "recommended_template": recommended_template(row["country"], row["cv_type"], row["category"]),
        "template": _template(row),
        "letter": {"body": letter.body, "version": int(letter.version)} if letter else None,
    }


def _project(conn: Connection, me: Applicant, module: str, project_id: str, lock: bool = True) -> RowMapping:
    return _own_project(conn, me, _module(module), project_id, lock=lock)


@router.get("/me/{module}/cv/projects/{project_id}/state")
def get_state(module: str, project_id: str, me: Applicant = Depends(current_applicant),
              conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    return _state(conn, _project(conn, me, module, project_id, lock=False))


# ---------------------------------------------------------------- Step 5: reading and missing info


@router.post("/me/{module}/cv/projects/{project_id}/files/{file_id}/extract")
def extract_file(module: str, project_id: str, file_id: str, me: Applicant = Depends(current_applicant),
                 conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    found = conn.execute(
        text("SELECT * FROM cv_files WHERE id = :id AND project_id = :p AND deleted_at IS NULL FOR UPDATE"),
        {"id": _uuid(file_id, ApiError("NOT_FOUND", 404, "File not found.")), "p": row["id"]},
    ).mappings().one_or_none()
    if found is None:
        raise ApiError("NOT_FOUND", 404, "File not found.")
    if found["extraction_status"] in ("done", "unsupported"):
        return file_view(found)
    if found["doc_kind"] == "passport" and "passport" not in (row["doc_kinds"] or []):
        status, extracted = "unsupported", None
    else:
        try:
            document = read_file(found["storage_path"], found["mime"])
        except Unreadable:
            document = None
        if document is None or (not document.text and not document.images):
            status, extracted = "unsupported", None
        else:
            try:
                data = extractor.extract(conn, _caller(row), found, document)
                status, extracted = "done", json.dumps(data.model_dump(), ensure_ascii=False)
            except ApiError as exc:
                if exc.status == 429:
                    raise
                status, extracted = "failed", None
    updated = conn.execute(
        text("UPDATE cv_files SET extraction_status = :s, extracted = CAST(:e AS jsonb) WHERE id = :id RETURNING *"),
        {"s": status, "e": extracted, "id": found["id"]},
    ).mappings().one()
    write_audit(conn, me.actor, "cv.file_read", f"{row['id']} · {found['doc_kind']} · {status}")
    return file_view(updated)


@router.post("/me/{module}/cv/projects/{project_id}/merge")
def merge_files(module: str, project_id: str, me: Applicant = Depends(current_applicant),
                conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    files = conn.execute(
        text("SELECT * FROM cv_files WHERE project_id = :p AND extraction_status = 'done' AND NOT merged "
             "AND extracted IS NOT NULL ORDER BY (doc_kind = 'cv') DESC, created_at, file_name, id FOR UPDATE"),
        {"p": row["id"]},
    ).mappings().all()
    if files:
        parts = [CvData.model_validate(f["extracted"]) for f in files]
        base = _latest(conn, row["id"])
        merged = merger.merge(([CvData.model_validate(base["data"])] if base else []) + parts)
        save_version(conn, row["id"], merged, "extracted")
        conn.execute(text("UPDATE cv_files SET merged = true WHERE id = ANY(:ids)"), {"ids": [f["id"] for f in files]})
        write_audit(conn, me.actor, "cv.merged", f"{row['id']} · {len(files)} files")
    if int(row["step"]) < 5:
        conn.execute(text("UPDATE cv_projects SET step = 5 WHERE id = :id"), {"id": row["id"]})
    return _state(conn, row)


class AnswersIn(BaseModel):
    answers: dict[str, Any] = Field(max_length=60)
    # Optional questions on the screen the person left blank.
    skip: list[str] = Field(default_factory=list, max_length=60)


@router.post("/me/{module}/cv/projects/{project_id}/answers")
async def give_answers(module: str, project_id: str, request: Request, me: Applicant = Depends(current_applicant),
                       conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    body = parse_body(AnswersIn, await request.body())
    before = current_data(conn, row["id"])
    optional = {f.key for f in _missing(conn, row, before) if not f.required}
    skip = [k for k in body.skip if k in optional and k not in body.answers]
    data = gap_checker.apply_answers(before, body.answers, skip)
    if "personal.email" in body.answers and data.personal.email and not re.fullmatch(r"\S+@\S+\.\S+", data.personal.email):
        raise _invalid("Please enter a valid email address.")
    save_version(conn, row["id"], data, "answers")
    write_audit(conn, me.actor, "cv.answers", f"{row['id']} · {len(body.answers)} answers")
    return _state(conn, row)


class DataIn(BaseModel):
    cv: dict[str, Any]
    reason: Literal["edited", "removed"] = "edited"


@router.put("/me/{module}/cv/projects/{project_id}/data")
async def save_data(module: str, project_id: str, request: Request, me: Applicant = Depends(current_applicant),
                    conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    body = parse_body(DataIn, await request.body())
    try:
        data = CvData.model_validate(body.cv)
    except ValidationError:
        raise _invalid("Some of the CV details are not valid. Please check them.") from None
    if len(json.dumps(data.model_dump())) > 200_000:
        raise _invalid("The CV is too long.")
    save_version(conn, row["id"], data, body.reason, _meta(conn, row["id"]))
    write_audit(conn, me.actor, "cv.edited", str(row["id"]))
    return _state(conn, row)


@router.post("/me/{module}/cv/projects/{project_id}/undo")
def undo(module: str, project_id: str, me: Applicant = Depends(current_applicant),
         conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    previous = conn.execute(
        text("SELECT data FROM cv_versions WHERE project_id = :p ORDER BY version DESC OFFSET 1 LIMIT 1"), {"p": row["id"]}
    ).one_or_none()
    if previous is None:
        raise ApiError("CONFLICT", 409, "There is nothing to undo.")
    data = dict(previous.data)
    meta = data.pop("_meta", None)
    save_version(conn, row["id"], CvData.model_validate(data), "restored", meta)
    write_audit(conn, me.actor, "cv.undo", str(row["id"]))
    return _state(conn, row)


# ---------------------------------------------------------------- Steps 6-7: writing


@router.post("/me/{module}/cv/projects/{project_id}/generate")
def generate(module: str, project_id: str, me: Applicant = Depends(current_applicant),
             conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    if not row["cv_type"] or not row["country"] or not row["category"]:
        raise ApiError("CONFLICT", 409, "Please choose the CV type, country and category first.")
    facts = facts_data(conn, row["id"])
    rules = rules_for(row["country"], row["cv_type"])
    if gap_checker.blocking_missing(_missing(conn, row, facts)):
        raise ApiError("CONFLICT", 409, "Please answer the missing questions first.")
    ensure_allowance(conn, _caller(row))
    template = _template(row)
    data, questions = writer.write(conn, _caller(row), row, facts, rules)
    data, pages = writer.fit(data, rules, template, int(row["page_length"]))
    save_version(conn, row["id"], data, "generated", {"ask_for": questions, "pages": pages})
    conn.execute(text("UPDATE cv_projects SET step = GREATEST(step, 7), template = :t WHERE id = :id"),
                 {"t": template, "id": row["id"]})
    write_audit(conn, me.actor, "cv.generated", str(row["id"]))
    return _state(conn, row)


class SectionIn(BaseModel):
    section: str = Field(max_length=30)
    action: Literal["regenerate", "shorter", "stronger", "remove", "restore"]
    item_id: str | None = Field(default=None, max_length=16)


SHORTER_LISTS = {"skills": 10, "achievements": 3, "training": 3, "certifications": 4, "references": 2}


@router.post("/me/{module}/cv/projects/{project_id}/section")
async def section_action(module: str, project_id: str, request: Request, me: Applicant = Depends(current_applicant),
                         conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    body = parse_body(SectionIn, await request.body())
    if body.section not in SECTIONS:
        raise _invalid("Unknown section.")
    data = current_data(conn, row["id"])
    rules = rules_for(row["country"], row["cv_type"])
    if body.action == "remove":
        if body.section not in data.hidden_sections:
            data.hidden_sections.append(body.section)
        reason = "removed"
    elif body.action == "restore":
        data.hidden_sections = [s for s in data.hidden_sections if s != body.section]
        reason = "edited"
    elif body.section in ("summary", "experience"):
        data = writer.rewrite_section(conn, _caller(row), row, rules, data, facts_data(conn, row["id"]),
                                      body.section, body.action, body.item_id)  # type: ignore[arg-type]
        reason = "regenerated" if body.action == "regenerate" else body.action
    elif body.action == "shorter" and body.section in SHORTER_LISTS:
        most = SHORTER_LISTS[body.section]
        if body.section == "skills":
            data.skills.technical, data.skills.soft = data.skills.technical[:most], data.skills.soft[:4]
        else:
            setattr(data, body.section, getattr(data, body.section)[:most])
        reason = "shorter"
    else:
        raise ApiError("CONFLICT", 409, "The AI rewrites the summary and work experience. Edit this section directly.")
    save_version(conn, row["id"], data, reason, _meta(conn, row["id"]))
    write_audit(conn, me.actor, f"cv.section_{body.action}", f"{row['id']} · {body.section}")
    return _state(conn, row)


@router.get("/me/{module}/cv/projects/{project_id}/preview", response_model=None)
def preview(module: str, project_id: str, page: int = 1, template: str = "", dpi: int = 90,
            me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)) -> Response:
    row = _project(conn, me, module, project_id, lock=False)
    if template and template not in TEMPLATES:
        raise _invalid("Unknown template.")
    data = current_data(conn, row["id"])
    rules = rules_for(row["country"], row["cv_type"])
    pdf, count = cv_pdf(build(data, rules, template or _template(row)), "CV")
    if not 1 <= page <= count:
        raise ApiError("NOT_FOUND", 404, "No such page.")
    png = pdf_pages_png(pdf, max(30, min(dpi, 150)))[page - 1]
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store", "X-Pages": str(count)})


@router.get("/me/{module}/cv/projects/{project_id}/pages")
def page_count(module: str, project_id: str, template: str = "", me: Applicant = Depends(current_applicant),
               conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id, lock=False)
    if template and template not in TEMPLATES:
        raise _invalid("Unknown template.")
    rules = rules_for(row["country"], row["cv_type"])
    return {"pages": writer.pages(current_data(conn, row["id"]), rules, template or _template(row))}


# ---------------------------------------------------------------- Step 7: review and approve


class ReviewIn(BaseModel):
    spelling: StrictBool = False


def _issues(conn: Connection, row: RowMapping, data: CvData) -> list[reviewer.Issue]:
    rules = rules_for(row["country"], row["cv_type"])
    template = _template(row)
    pages = writer.pages(data, rules, template)
    return reviewer.check(data, rules, template, int(row["page_length"]), pages, row["cv_type"], row["category"])


@router.post("/me/{module}/cv/projects/{project_id}/review")
async def review(module: str, project_id: str, request: Request, me: Applicant = Depends(current_applicant),
                 conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    body = parse_body(ReviewIn, await request.body())
    data = current_data(conn, row["id"])
    issues = _issues(conn, row, data)
    if body.spelling:
        rules = rules_for(row["country"], row["cv_type"])
        issues += reviewer.spelling(conn, _caller(row), data, rules, _template(row))
    return {"issues": [i.model_dump() for i in issues], "blocking": len(reviewer.blocking(issues))}


@router.post("/me/{module}/cv/projects/{project_id}/approve")
def approve(module: str, project_id: str, me: Applicant = Depends(current_applicant),
            conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    if _latest(conn, row["id"], WRITTEN_REASONS) is None:
        raise ApiError("CONFLICT", 409, "Please generate the CV first.")
    blocking = reviewer.blocking(_issues(conn, row, current_data(conn, row["id"])))
    if blocking:
        raise ApiError("CONFLICT", 409, f"Please fix {len(blocking)} problem(s) first: {blocking[0].message}")
    conn.execute(text("UPDATE cv_projects SET status = 'approved', step = 8 WHERE id = :id"), {"id": row["id"]})
    write_audit(conn, me.actor, "cv.approved", str(row["id"]))
    return _state(conn, row)


# ---------------------------------------------------------------- Step 8: cover letter and export


@router.post("/me/{module}/cv/projects/{project_id}/letter")
def make_letter(module: str, project_id: str, me: Applicant = Depends(current_applicant),
                conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    if not row["cv_type"] or not row["country"]:
        raise ApiError("CONFLICT", 409, "Please choose the CV type and country first.")
    rules = rules_for(row["country"], row["cv_type"])
    body = cover_letter.write_letter(conn, _caller(row), row, facts_data(conn, row["id"]), rules)
    _save_letter(conn, row["id"], body)
    write_audit(conn, me.actor, "cv.letter_generated", str(row["id"]))
    return _state(conn, row)


class LetterIn(BaseModel):
    body: str = Field(max_length=20000)


def _save_letter(conn: Connection, project_id: Any, body: str) -> None:
    conn.execute(
        text("INSERT INTO cover_letters (project_id, version, body) SELECT :p, COALESCE(max(version), 0) + 1, :b "
             "FROM cover_letters WHERE project_id = :p"),
        {"p": project_id, "b": body},
    )


@router.put("/me/{module}/cv/projects/{project_id}/letter")
async def edit_letter(module: str, project_id: str, request: Request, me: Applicant = Depends(current_applicant),
                      conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = _project(conn, me, module, project_id)
    body = parse_body(LetterIn, await request.body()).body.strip()
    if not body:
        raise _invalid("The cover letter is empty.")
    if len(body.split()) > 600:
        raise _invalid("A cover letter should fit on one page (at most about 400 words).")
    _save_letter(conn, row["id"], body)
    write_audit(conn, me.actor, "cv.letter_edited", str(row["id"]))
    return _state(conn, row)


def _ascii(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "_", plain).strip("_")


# Titles left out of the file name ("Md. Rafiul Karim (Rafi)" -> Rafiul_Karim).
NAME_TITLES = {"md", "mohammad", "mohammed", "muhammad", "mohd", "mst", "most", "mr", "mrs", "ms", "miss", "dr", "engr", "sk"}


def file_name(data: CvData, country: str | None, kind: str, ext: str) -> str:
    plain = re.sub(r"\([^)]*\)", " ", data.personal.full_name)
    parts = [p for p in plain.split() if _ascii(p) and _ascii(p).lower() not in NAME_TITLES]
    name = "_".join(_ascii(p) for p in ([parts[0], parts[-1]] if len(parts) > 1 else parts)) or "My"
    return f"{name}_{'CV' if kind == 'cv' else 'Cover_Letter'}_{_ascii(country or 'International') or 'International'}.{ext}"


@router.get("/me/{module}/cv/projects/{project_id}/export", response_model=None)
def export(module: str, project_id: str, format: Literal["pdf", "docx"] = "pdf", doc: Literal["cv", "letter"] = "cv",
           me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)) -> Response:
    row = _project(conn, me, module, project_id, lock=False)
    data = current_data(conn, row["id"])
    rules = rules_for(row["country"], row["cv_type"])
    layout = build(data, rules, _template(row))
    if doc == "cv":
        if row["status"] != "approved":
            raise ApiError("CONFLICT", 409, "Please approve the CV before downloading it.")
        content = cv_pdf(layout, f"{data.personal.full_name} CV")[0] if format == "pdf" else cv_docx(layout)
    else:
        letter = conn.execute(
            text("SELECT body FROM cover_letters WHERE project_id = :p ORDER BY version DESC LIMIT 1"), {"p": row["id"]}
        ).scalar_one_or_none()
        if not letter:
            raise ApiError("CONFLICT", 409, "Please create the cover letter first.")
        content = letter_pdf(layout, letter, "Cover letter") if format == "pdf" else letter_docx(layout, letter)
    name = file_name(data, row["country"], doc, format)
    mime = "application/pdf" if format == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(content, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
