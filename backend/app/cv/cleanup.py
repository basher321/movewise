"""Removes CV Agent file content after cv_file_days (spec B28). Runs in every round of the
scheduled worker (python -m app.notify.run --once, every minute on cPanel). The rows stay; only
the encrypted content on disk is removed. One audit row per round that removed something."""

import logging

from sqlalchemy import event, text
from sqlalchemy.engine import Connection

from app.audit import Actor, write_audit
from app.cv import storage

logger = logging.getLogger("app")

BATCH = 200
SYSTEM = Actor(id=None, name="System", role=None)


def remove_expired(conn: Connection) -> int:
    names = conn.execute(
        text(
            "WITH due AS (SELECT id, storage_path FROM cv_files WHERE deleted_at IS NULL AND delete_after <= now() "
            "ORDER BY delete_after LIMIT :n FOR UPDATE SKIP LOCKED) "
            "UPDATE cv_files f SET storage_path = NULL, deleted_at = now() FROM due WHERE f.id = due.id "
            "RETURNING due.storage_path"
        ),
        {"n": BATCH},
    ).scalars().all()
    if not names:
        return 0
    write_audit(conn, SYSTEM, "cv.files_expired", f"{len(names)} files removed after the keep period")

    def on_commit(_: Connection) -> None:
        for name in names:
            storage.remove(str(name))

    event.listen(conn, "commit", on_commit, once=True)
    return len(names)


def run_once() -> int:
    from app.db.engine import get_engine

    with get_engine().begin() as conn:
        return remove_expired(conn)
