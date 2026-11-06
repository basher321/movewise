"""The licence: public view, masked full view, and applying a signed key."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.audit import Actor, write_audit
from app.auth.deps import require_super_admin
from app.db.engine import get_conn
from app.errors import parse_body
from app.licence import MODULES, mask_key, modules_text, public_view, read_licence, verify_key

router = APIRouter()

_UPDATE_LICENCE = text(
    "UPDATE licence SET key = :key, holder = :holder, "
    "module_course = :module_course, module_study = :module_study, module_job = :module_job, module_visa = :module_visa, "
    "module_remote = :module_remote, "
    "issued_at = :issued_at, expires_at = :expires_at, applied_at = now(), applied_by = :applied_by "
    "WHERE singleton = 'licence'"
)


class LicenceIn(BaseModel):
    key: str


@router.get("/licence")
def get_licence(conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    return public_view(read_licence(conn))


@router.get("/licence/full")
def get_licence_full(
    actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    state = read_licence(conn)
    return {**public_view(state), "key": mask_key(state.key) if state.key else None}


@router.put("/licence")
async def apply_licence(
    request: Request,
    actor: Actor = Depends(require_super_admin),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(LicenceIn, await request.body())
    payload = verify_key(body.key)
    key = body.key.strip()

    old = read_licence(conn)
    new_modules = {m: m in payload.modules for m in MODULES}
    if old.key != key:
        conn.execute(
            _UPDATE_LICENCE,
            {
                "key": key,
                "holder": payload.holder,
                **{f"module_{m}": on for m, on in new_modules.items()},
                "issued_at": payload.issued,
                "expires_at": payload.expires,
                "applied_by": actor.id,
            },
        )
    write_audit(
        conn,
        actor,
        "licence.changed",
        f"Licence changed ({modules_text(old.modules)} -> {modules_text(new_modules)})",
    )
    return public_view(read_licence(conn))
