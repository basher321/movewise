"""Success Stories: a public summary of finished journeys, made automatically from the cases.

A case counts as a success when it reaches Completed (its last stage); finished journeys are
Completed or Rejected (withdrawn, open and Self Apply cases are not counted). The public sees only
a short name (first name and the first letter of the last name), what the journey was for, the
country and when it was completed: never an email, phone, ID, reference or document.
Only licensed modules are shown.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.catalog import VISA_TYPES
from app.db.engine import get_conn
from app.licence import MODULE_LABELS, read_licence
from app.stages import APP_MODULES

router = APIRouter()

MAX_STORIES = 60

_SUMMARY = text(
    "SELECT module, count(*) FILTER (WHERE status = 'completed') AS completed, "
    "count(*) FILTER (WHERE status IN ('completed', 'rejected')) AS finished "
    "FROM applications WHERE NOT self_apply AND module = ANY(CAST(:modules AS text[])) GROUP BY module"
)

# When the journey finished: the case's last history event (the move to the final stage).
_STORIES = text(
    "SELECT a.id, a.module, p.name AS person, "
    "u.name AS u_name, u.country AS u_country, "
    "v.title AS v_title, v.employer AS v_employer, v.country AS v_country, "
    "vp.title AS vp_title, vp.visa_type AS vp_type, vp.country AS vp_country, "
    "COALESCE((SELECT max(e.at) FROM app_events e WHERE e.application_id = a.id), a.updated_at) AS completed_at "
    "FROM applications a JOIN applicant_accounts p ON p.id = a.applicant_id "
    "LEFT JOIN universities u ON u.id = a.university_id "
    "LEFT JOIN vacancies v ON v.id = a.vacancy_id "
    "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id "
    "WHERE a.status = 'completed' AND NOT a.self_apply AND a.module = ANY(CAST(:modules AS text[])) "
    "ORDER BY completed_at DESC, a.id LIMIT :limit"
)


def short_name(full: str) -> str:
    """'Rahim Uddin Khan' -> 'Rahim K.'; a single name stays as it is."""
    parts = full.split()
    if not parts:
        return "A client"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."


def _story(row: Any) -> dict[str, Any]:
    module = row.module
    if module == "study":
        title, detail, country = row.u_name, "Admission", row.u_country
    elif module == "visa":
        title, detail, country = row.vp_title, VISA_TYPES.get(row.vp_type, row.vp_type), row.vp_country
    else:
        title, detail, country = row.v_title, row.v_employer, row.v_country
    return {
        "id": str(row.id),
        "name": short_name(row.person),
        "module": module,
        "module_label": MODULE_LABELS[module],
        "title": title,
        "detail": detail,
        "country": country,
        "completed_at": row.completed_at.isoformat(),
    }


@router.get("/success-stories")
def success_stories(conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    licence = read_licence(conn)
    modules = [m for m in APP_MODULES if licence.licensed(m)]
    counts = {r.module: r for r in conn.execute(_SUMMARY, {"modules": modules})}
    summary = []
    for m in modules:
        row = counts.get(m)
        completed = int(row.completed) if row else 0
        finished = int(row.finished) if row else 0
        summary.append(
            {
                "module": m,
                "module_label": MODULE_LABELS[m],
                "completed": completed,
                "finished": finished,
                # Rounded half up; None while no journey has finished.
                "percent": (200 * completed + finished) // (2 * finished) if finished else None,
            }
        )
    stories = [_story(r) for r in conn.execute(_STORIES, {"modules": modules, "limit": MAX_STORIES})]
    return {"summary": summary, "stories": stories}
