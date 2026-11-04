"""Document rules shared by the applicant, admin and application endpoints (spec B06)."""

from datetime import date, timedelta
from typing import Any, Literal
from urllib.parse import quote

from fastapi.responses import Response
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection, RowMapping

from app.licence import today_dhaka
from app.stages import DOCUMENT_TYPES, AppModule

EXPIRING_DAYS = 60

Viewer = Literal["applicant", "admin"]


def shown_status(row: RowMapping, today: date | None = None) -> str:
    """'expiring' / 'expired' for a verified document by its expiry date; never stored."""
    day = today or today_dhaka()
    expiry: date | None = row["expiry"]
    if row["status"] == "verified" and expiry is not None:
        if expiry < day:
            return "expired"
        if expiry <= day + timedelta(days=EXPIRING_DAYS):
            return "expiring"
    return str(row["status"])


def file_url(row: RowMapping, viewer: Viewer, module: AppModule) -> str:
    if viewer == "admin":
        return f"/api/admin/documents/{row['id']}/file"
    return f"/api/me/{module}/documents/{row['id']}/file"


def document_view(row: RowMapping, viewer: Viewer, module: AppModule) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "application_id": str(row["application_id"]),
        "type": row["type"],
        "original_name": row["original_name"],
        "mime": row["mime"],
        "size_bytes": row["size_bytes"],
        "status": row["status"],
        "shown_status": shown_status(row),
        "expiry": row["expiry"].isoformat() if row["expiry"] else None,
        "note": row["note"],
        "uploaded_at": row["uploaded_at"].isoformat(),
        "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        "file_url": file_url(row, viewer, module),
    }


_CURRENT = text(
    "SELECT DISTINCT ON (application_id, type) * FROM documents "
    "WHERE application_id IN :ids AND status <> 'replaced' "
    "ORDER BY application_id, type, uploaded_at DESC, id DESC"
).bindparams(bindparam("ids", expanding=True))

# A required type counts as done while its current document is waiting or valid.
_DONE = {"pending", "verified", "expiring"}


def documents_part(
    conn: Connection, apps: list[RowMapping], viewer: Viewer
) -> dict[Any, dict[str, Any]]:
    """documents, required_types and missing_count for each application."""
    if not apps:
        return {}
    current: dict[Any, list[RowMapping]] = {a["id"]: [] for a in apps}
    for row in conn.execute(_CURRENT, {"ids": [a["id"] for a in apps]}).mappings():
        current[row["application_id"]].append(row)
    out = {}
    for app in apps:
        module: AppModule = app["module"]
        required = list(DOCUMENT_TYPES[module])
        docs = current[app["id"]]
        order = {t: i for i, t in enumerate(required)}
        docs.sort(key=lambda d: order.get(d["type"], len(order)))
        done = {d["type"] for d in docs if shown_status(d) in _DONE}
        out[app["id"]] = {
            "documents": [document_view(d, viewer, module) for d in docs],
            "required_types": required,
            "missing_count": sum(1 for t in required if t not in done),
        }
    return out


def file_response(data: bytes, mime: str, original_name: str) -> Response:
    ascii_name = original_name.encode("ascii", "ignore").decode("ascii").replace('"', "").replace("\\", "") or "document"
    disposition = f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(original_name)}"
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )
