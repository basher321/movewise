"""The read-only audit list for the super admin (spec B09). No route changes audit rows, and the
database blocks UPDATE and DELETE on audit_log."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.audit import Actor
from app.auth.deps import require_super_admin
from app.db.engine import get_conn
from app.errors import ApiError

router = APIRouter()

PAGE_SIZE = 50


@router.get("/admin/audit")
def list_audit(
    q: str = "", page: int = 1, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    if page < 1:
        raise ApiError("VALIDATION", 422, "Page must be 1 or more.")
    where = "TRUE"
    params: dict[str, Any] = {}
    search = q.strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where = "(by_name ILIKE :q OR action ILIKE :q OR detail ILIKE :q OR COALESCE(ip, '') ILIKE :q)"
    total = int(conn.execute(text(f"SELECT count(*) FROM audit_log WHERE {where}"), params).scalar_one())
    rows = conn.execute(
        text(f"SELECT * FROM audit_log WHERE {where} ORDER BY at DESC, created_at DESC, id LIMIT :l OFFSET :o"),
        {**params, "l": PAGE_SIZE, "o": (page - 1) * PAGE_SIZE},
    ).mappings()
    return {
        "rows": [
            {
                "id": str(r["id"]),
                "at": r["at"].isoformat(),
                "by_name": r["by_name"],
                "by_role": r["by_role"],
                "action": r["action"],
                "detail": r["detail"],
                "ip": r["ip"],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
    }
