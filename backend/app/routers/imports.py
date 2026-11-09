"""Excel upload of listings (spec B23).

Order of checks: signed in -> module licensed -> role and section -> input valid -> do the work.
The super admin may upload every licensed type; an admin only the types of their sections.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.engine import Connection
from starlette.datastructures import UploadFile

from app.audit import Actor
from app.auth.deps import ensure_section, get_current_actor
from app.catalog import invalid
from app.db.engine import get_conn
from app.errors import ApiError
from app.excel_import import KINDS, MAX_FILE_BYTES, XLSX_MIME, KindSpec, build_template, check_upload, commit, evaluate, report

router = APIRouter()


def _spec(kind: str) -> KindSpec:
    spec = KINDS.get(kind)
    if spec is None:
        raise ApiError("NOT_FOUND", 404, "Not found.")
    return spec


def _allowed(kind: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)) -> Actor:
    ensure_section(conn, actor, _spec(kind).module)
    return actor


async def _file_bytes(request: Request) -> bytes:
    try:
        form = await request.form(max_files=1, max_fields=1)
    except Exception:
        raise invalid("Please choose a file.") from None
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise invalid("Please choose a file.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    check_upload(data)
    return data


@router.get("/admin/import/{kind}/template")
def download_template(kind: str, actor: Actor = Depends(_allowed)) -> Response:
    spec = _spec(kind)
    return Response(
        content=build_template(spec),
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{spec.kind}-template.xlsx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/admin/import/{kind}/preview")
async def preview_import(
    kind: str, request: Request, actor: Actor = Depends(_allowed), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    spec = _spec(kind)
    data = await _file_bytes(request)
    return report(spec, evaluate(conn, spec, data, actor.role == "super_admin"))


@router.post("/admin/import/{kind}/commit")
async def commit_import(
    kind: str, request: Request, actor: Actor = Depends(_allowed), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    spec = _spec(kind)
    data = await _file_bytes(request)
    return report(spec, commit(conn, actor, spec, data))
