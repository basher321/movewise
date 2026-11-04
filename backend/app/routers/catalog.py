"""Public catalog, match, agent answers and form options (spec B04).

Every endpoint checks the module licence first (403 MODULE_NOT_LICENSED), then the input.
The public sees only published courses and universities, and only open vacancies whose
employer is verified. Staff-only fields (official apply link, admissions and employer
contacts, overrides) are never part of a public answer.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import TextClause, text
from sqlalchemy.engine import Connection, RowMapping

from app.ai import advisor
from app.countries import WORLD_COUNTRIES
from app.auth.deps import client_ip, current_applicant_row, ensure_licensed, require_module
from app.catalog import (
    ANY_COUNTRY,
    BASE_STUDY_LEVELS,
    COURSE_SELECT,
    EDUCATION_LEVELS,
    ENGLISH_LEVELS,
    PUBLIC_LIMIT,
    VISA_TYPES,
    course_view,
    default_fees,
    group_view,
    not_found,
    public_universities,
    public_vacancies,
    public_visa_programs,
    university_view,
    vacancy_view,
    visa_program_view,
)
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import read_licence
from app.match import (
    ANY_VISA_TYPE,
    JobInput,
    StudyInput,
    VisaInput,
    check_job,
    check_study,
    check_visa,
    match_job,
    match_study,
    match_visa,
)

router = APIRouter()

_PUBLIC_COURSES = text(
    f"{COURSE_SELECT} WHERE c.published AND g.active ORDER BY g.sort_order, g.name, c.created_at, c.id LIMIT :limit"
)
_PUBLIC_GROUPS = text("SELECT * FROM course_groups WHERE active ORDER BY sort_order, name, id")
_COURSE_BY_SLUG = text(f"{COURSE_SELECT} WHERE c.slug = :slug AND c.published AND g.active")
_UNIVERSITY_BY_SLUG = text("SELECT * FROM universities WHERE slug = :slug AND published")
_VACANCY_BY_SLUG = text(
    "SELECT * FROM vacancies WHERE slug = :slug AND NOT closed AND employer_verified"
)
# B05: a hidden, closed or unverified item stays readable for an applicant who applied to it.
_APPLIED_UNIVERSITY = text(
    "SELECT u.* FROM universities u WHERE u.slug = :slug AND EXISTS ("
    "SELECT 1 FROM applications a WHERE a.university_id = u.id AND a.applicant_id = :applicant)"
)
_APPLIED_VACANCY = text(
    "SELECT v.* FROM vacancies v WHERE v.slug = :slug AND EXISTS ("
    "SELECT 1 FROM applications a WHERE a.vacancy_id = v.id AND a.applicant_id = :applicant)"
)

_VISA_PROGRAM_BY_SLUG = text("SELECT * FROM visa_programs WHERE slug = :slug AND published")
_APPLIED_VISA_PROGRAM = text(
    "SELECT p.* FROM visa_programs p WHERE p.slug = :slug AND EXISTS ("
    "SELECT 1 FROM applications a WHERE a.visa_program_id = p.id AND a.applicant_id = :applicant)"
)

MAX_QUESTION = 500


class StudyIn(BaseModel):
    level: str = Field(max_length=120)
    field: str = Field(max_length=120)
    gpa: float
    ielts: float = 0
    budget_usd: float


class JobIn(BaseModel):
    occupation: str = Field(max_length=120)
    country: str = Field(default="", max_length=120)
    experience: float
    education: str = Field(max_length=60)
    english: str = Field(max_length=60)
    passport_ready: StrictBool
    salary_goal_usd: float | None = None


class VisaIn(BaseModel):
    country: str = Field(max_length=120)
    visa_type: str = Field(default=ANY_VISA_TYPE, max_length=40)
    passport_ready: StrictBool
    refused_before: StrictBool = False


class AgentIn(BaseModel):
    question: str = Field(max_length=MAX_QUESTION)
    inputs: dict[str, str | int | float | bool | None] | None = None


@router.get("/courses", dependencies=[Depends(require_module("course"))])
def list_courses(conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    courses = [course_view(r) for r in conn.execute(_PUBLIC_COURSES, {"limit": PUBLIC_LIMIT}).mappings()]
    groups = []
    for g in conn.execute(_PUBLIC_GROUPS).mappings():
        items = [c for c in courses if c["group_id"] == str(g["id"])]
        # A group with no published courses is not shown.
        if items:
            groups.append({**group_view(g), "courses": items})
    return groups


@router.get("/courses/{slug}", dependencies=[Depends(require_module("course"))])
def get_course(slug: str, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute(_COURSE_BY_SLUG, {"slug": slug}).mappings().one_or_none()
    if row is None:
        raise not_found("Course")
    return course_view(row)


def _applied_item(
    request: Request, conn: Connection, module: Literal["study", "job", "visa"], sql: TextClause, slug: str
) -> RowMapping | None:
    applicant = current_applicant_row(request, conn, module)
    if applicant is None:
        return None
    return conn.execute(sql, {"slug": slug, "applicant": applicant["id"]}).mappings().one_or_none()


@router.get("/universities", dependencies=[Depends(require_module("study"))])
def list_universities(conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    fee = default_fees(conn)["study"]
    return [university_view(r, fee) for r in public_universities(conn)]


@router.get("/universities/{slug}", dependencies=[Depends(require_module("study"))])
def get_university(slug: str, request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute(_UNIVERSITY_BY_SLUG, {"slug": slug}).mappings().one_or_none()
    if row is None:
        row = _applied_item(request, conn, "study", _APPLIED_UNIVERSITY, slug)
    if row is None:
        raise not_found("University")
    return university_view(row, default_fees(conn)["study"])


@router.get("/vacancies", dependencies=[Depends(require_module("job"))])
def list_vacancies(conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    fee = default_fees(conn)["job"]
    return [vacancy_view(r, fee) for r in public_vacancies(conn)]


@router.get("/vacancies/{slug}", dependencies=[Depends(require_module("job"))])
def get_vacancy(slug: str, request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute(_VACANCY_BY_SLUG, {"slug": slug}).mappings().one_or_none()
    if row is None:
        row = _applied_item(request, conn, "job", _APPLIED_VACANCY, slug)
    if row is None:
        raise not_found("Vacancy")
    return vacancy_view(row, default_fees(conn)["job"])


@router.get("/visa-programs", dependencies=[Depends(require_module("visa"))])
def list_visa_programs(conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    fee = default_fees(conn)["visa"]
    return [visa_program_view(r, fee) for r in public_visa_programs(conn)]


@router.get("/visa-programs/{slug}", dependencies=[Depends(require_module("visa"))])
def get_visa_program(slug: str, request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute(_VISA_PROGRAM_BY_SLUG, {"slug": slug}).mappings().one_or_none()
    if row is None:
        row = _applied_item(request, conn, "visa", _APPLIED_VISA_PROGRAM, slug)
    if row is None:
        raise not_found("Visa programme")
    return visa_program_view(row, default_fees(conn)["visa"])


@router.post("/match/visa", dependencies=[Depends(require_module("visa"))])
async def post_match_visa(request: Request, conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    body = parse_body(VisaIn, await request.body())
    data = check_visa(VisaInput(body.country, body.visa_type, body.passport_ready, body.refused_before))
    return match_visa(conn, data)


@router.post("/match/study", dependencies=[Depends(require_module("study"))])
async def post_match_study(request: Request, conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    body = parse_body(StudyIn, await request.body())
    data = check_study(StudyInput(body.level, body.field, body.gpa, body.ielts, body.budget_usd))
    return match_study(conn, data)


@router.post("/match/job", dependencies=[Depends(require_module("job"))])
async def post_match_job(request: Request, conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    body = parse_body(JobIn, await request.body())
    data = check_job(
        JobInput(
            body.occupation,
            body.country,
            body.experience,
            body.education,
            body.english,
            body.passport_ready,
            body.salary_goal_usd,
        )
    )
    return match_job(conn, data)


@router.post("/agent/{module}/ask")
async def ask_agent(module: str, request: Request, conn: Connection = Depends(get_conn)) -> dict[str, str]:
    if module not in ("study", "job", "visa"):
        raise ApiError("NOT_FOUND", 404, "Not found.")
    ensure_licensed(conn, module)  # type: ignore[arg-type]
    body = parse_body(AgentIn, await request.body())
    question = body.question.strip()
    if not question:
        raise ApiError("VALIDATION", 422, "Please type a question.")
    # B17: an AI answer from the database facts, or the rule-based reply when no AI provider works.
    # Provider calls block for up to 20 seconds each, so they run in a worker thread, never on the event loop.
    reply = await run_in_threadpool(advisor.answer, conn, module, question, body.inputs, client_ip(request))  # type: ignore[arg-type]
    return {"answer": reply}


def _merged(fixed: tuple[str, ...], found: list[str]) -> list[str]:
    extra = sorted({x for x in found if x not in fixed})
    return [*fixed, *extra]


@router.get("/catalog/options")
def catalog_options(conn: Connection = Depends(get_conn)) -> dict[str, list[str]]:
    """Choices for the agent forms, from published data plus the fixed lists.
    Lists of a module that is not licensed are empty."""
    licence = read_licence(conn)
    study = licence.licensed("study")
    job = licence.licensed("job")
    visa = licence.licensed("visa")
    universities = public_universities(conn) if study else []
    vacancies = public_vacancies(conn) if job else []
    programs = public_visa_programs(conn) if visa else []
    visa_types_used = {p["visa_type"] for p in programs}
    levels = [lv for u in universities for lv in u["levels"]]
    used_levels = [lv for lv in BASE_STUDY_LEVELS if lv in levels]
    return {
        "study_levels": _merged(tuple(used_levels), levels) if study else [],
        "study_fields": sorted({f for u in universities for f in u["fields"]}),
        "occupations": sorted({v["occupation"] for v in vacancies}),
        # Every country (plus any other country a vacancy uses), so applicants can pick any destination.
        "countries": [ANY_COUNTRY, *sorted(set(WORLD_COUNTRIES) | {v["country"] for v in vacancies}, key=str.casefold)] if job else [],
        "education_levels": list(EDUCATION_LEVELS) if job else [],
        "english_levels": list(ENGLISH_LEVELS) if job else [],
        # B19: every country (so any destination can be asked about) and the visa types in use.
        "visa_countries": [ANY_COUNTRY, *sorted(set(WORLD_COUNTRIES) | {p["country"] for p in programs}, key=str.casefold)]
        if visa
        else [],
        "visa_types": [t for t in VISA_TYPES if t in visa_types_used],
    }
