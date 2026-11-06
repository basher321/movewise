"""Admin catalog and fees (spec B04): super admin only, module licensed.

Order of checks: signed in -> module licensed -> super admin -> input valid -> do the work.
There is no DELETE endpoint: items are hidden (published = false) or closed.
Every create or update writes one audit row in the same transaction; changing
employer_verified writes its own row ("Employer verified" / "Employer unverified").
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.deps import ensure_licensed, get_current_actor, require_super_admin
from app.catalog import (
    COURSE_SELECT,
    MAX_LONG,
    UNI_SUCCESS,
    VAC_SUCCESS,
    VISA_SUCCESS,
    VISA_TYPES,
    changed_fields,
    check_colour,
    check_fee,
    check_icon,
    course_view,
    default_fees,
    group_view,
    invalid,
    lock_catalog,
    new_slug,
    not_found,
    opt_email,
    opt_text,
    parse_uuid,
    req_text,
    stored_override,
    text_list,
    university_view,
    vacancy_view,
    visa_program_view,
)
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULE_LABELS, Module, read_licence, today_dhaka

router = APIRouter()

MAX_TUITION = 1_000_000
MAX_SALARY = 1_000_000


def require_owner(module: Module) -> Callable[..., Actor]:
    """Signed in -> module licensed -> super admin."""

    def check(actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)) -> Actor:
        ensure_licensed(conn, module)
        if actor.role != "super_admin":
            raise ApiError("FORBIDDEN", 403, "Only the super admin can change the catalog.")
        return actor

    return check


# ---------------------------------------------------------------- bodies


class GroupIn(BaseModel):
    name: str = Field(max_length=500)
    description: str = Field(default="", max_length=2000)
    sort_order: StrictInt = 0
    active: StrictBool = True


class CourseIn(BaseModel):
    group_id: str = Field(max_length=64)
    title: str = Field(max_length=500)
    icon: str = Field(default="", max_length=64)
    colour: str = Field(max_length=16)
    price_poisha: StrictInt
    duration: str = Field(default="", max_length=500)
    level: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=10_000)
    learn_points: list[str] = Field(max_length=100)
    syllabus: list[str] = Field(max_length=100)
    published: StrictBool = True


class UniversityIn(BaseModel):
    name: str = Field(max_length=500)
    country: str = Field(max_length=500)
    city: str = Field(default="", max_length=500)
    levels: list[str] = Field(max_length=100)
    fields: list[str] = Field(max_length=100)
    tuition_usd: StrictInt
    min_gpa: float
    min_ielts: float
    intakes: str = Field(default="", max_length=500)
    deadline_text: str = Field(default="", max_length=500)
    scholarships: str = Field(default="", max_length=10_000)
    work_rights: str = Field(default="", max_length=10_000)
    conditions: str = Field(default="", max_length=10_000)
    apply_link: str = Field(default="", max_length=2000)
    admissions_email: str = Field(default="", max_length=500)
    fee_override_poisha: StrictInt | None = None
    self_apply_fee_poisha: StrictInt | None = None
    published: StrictBool = True


class VacancyIn(BaseModel):
    title: str = Field(max_length=500)
    employer: str = Field(max_length=500)
    country: str = Field(max_length=500)
    occupation: str = Field(max_length=500)
    min_experience: StrictInt
    min_education: StrictInt
    min_english: StrictInt
    salary_usd: StrictInt
    seats: StrictInt | None = None
    apply_by: date | None = None
    contract: str = Field(default="", max_length=10_000)
    benefits: str = Field(default="", max_length=10_000)
    conditions: str = Field(default="", max_length=10_000)
    employer_licence: str = Field(default="", max_length=500)
    employer_email: str = Field(default="", max_length=500)
    employer_verified: StrictBool = False
    closed: StrictBool = False
    fee_override_poisha: StrictInt | None = None


class VisaProgramIn(BaseModel):
    title: str = Field(max_length=500)
    country: str = Field(max_length=500)
    visa_type: str = Field(max_length=40)
    processing_time: str = Field(default="", max_length=500)
    validity: str = Field(default="", max_length=500)
    government_fee: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=10_000)
    eligibility: list[str] = Field(max_length=100)
    required_documents: list[str] = Field(max_length=100)
    conditions: str = Field(default="", max_length=10_000)
    official_link: str = Field(default="", max_length=2000)
    embassy_email: str = Field(default="", max_length=500)
    fee_override_poisha: StrictInt | None = None
    published: StrictBool = True


class FeesIn(BaseModel):
    study: dict[str, StrictInt | None] = Field(default_factory=dict)
    job: dict[str, StrictInt | None] = Field(default_factory=dict)
    visa: dict[str, StrictInt | None] = Field(default_factory=dict)
    remote: dict[str, StrictInt | None] = Field(default_factory=dict)


class ResetIn(BaseModel):
    scope: Literal["study", "job", "visa", "remote", "all"]


# ---------------------------------------------------------------- helpers


def _insert(conn: Connection, table: str, values: dict[str, Any]) -> RowMapping:
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    sql = text(f"INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING id")
    new_id = conn.execute(sql, values).scalar_one()
    return conn.execute(text(f"SELECT * FROM {table} WHERE id = :id"), {"id": new_id}).mappings().one()


def _update(conn: Connection, table: str, row_id: Any, values: dict[str, Any]) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in values)
    conn.execute(text(f"UPDATE {table} SET {sets} WHERE id = :id"), {**values, "id": row_id})


def _locked(conn: Connection, table: str, item_id: str, what: str) -> RowMapping:
    row = conn.execute(
        text(f"SELECT * FROM {table} WHERE id = :id FOR UPDATE"), {"id": parse_uuid(item_id, what)}
    ).mappings().one_or_none()
    if row is None:
        raise not_found(what)
    return row


def _detail(name: str, fields: list[str]) -> str:
    return f"{name}: {', '.join(fields)}"


# ---------------------------------------------------------------- course groups

_GROUPS = text(
    "SELECT g.*, (SELECT count(*) FROM courses c WHERE c.group_id = g.id) AS course_count "
    "FROM course_groups g ORDER BY g.sort_order, g.name, g.id"
)
_PUBLISHED_IN_GROUP = text("SELECT count(*) FROM courses WHERE group_id = :id AND published")


def _group_values(body: GroupIn) -> dict[str, Any]:
    return {
        "name": req_text(body.name, "Group name", 80),
        "description": opt_text(body.description, "Description", 300),
        "sort_order": body.sort_order,
        "active": body.active,
    }


def _admin_group(conn: Connection, group_id: Any) -> dict[str, Any]:
    for row in conn.execute(_GROUPS).mappings():
        if row["id"] == group_id:
            return {**group_view(row), "course_count": int(row["course_count"])}
    raise not_found("Course group")


@router.get("/admin/course-groups")
def list_groups(
    actor: Actor = Depends(require_owner("course")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return [{**group_view(r), "course_count": int(r["course_count"])} for r in conn.execute(_GROUPS).mappings()]


@router.post("/admin/course-groups")
async def create_group(
    request: Request, actor: Actor = Depends(require_owner("course")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    values = _group_values(parse_body(GroupIn, await request.body()))
    row = _insert(conn, "course_groups", values)
    write_audit(conn, actor, "catalog.group_saved", _detail(row["name"], ["added"]))
    return _admin_group(conn, row["id"])


@router.put("/admin/course-groups/{group_id}")
async def update_group(
    group_id: str,
    request: Request,
    actor: Actor = Depends(require_owner("course")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    values = _group_values(parse_body(GroupIn, await request.body()))
    before = _locked(conn, "course_groups", group_id, "Course group")
    if before["active"] and not values["active"]:
        if int(conn.execute(_PUBLISHED_IN_GROUP, {"id": before["id"]}).scalar_one()) > 0:
            raise ApiError(
                "CONFLICT", 409, "This group still has courses on the website. Hide those courses first."
            )
    changed = changed_fields(before, values)
    if changed:
        _update(conn, "course_groups", before["id"], values)
        write_audit(conn, actor, "catalog.group_saved", _detail(values["name"], changed))
    return _admin_group(conn, before["id"])


# ---------------------------------------------------------------- courses

_ADMIN_COURSES = text(f"{COURSE_SELECT} ORDER BY g.sort_order, g.name, c.created_at, c.id")
_COURSE_BY_ID = text(f"{COURSE_SELECT} WHERE c.id = :id")


def _course_values(conn: Connection, body: CourseIn) -> dict[str, Any]:
    title = req_text(body.title, "Title")
    if not body.group_id.strip():
        raise invalid("Please choose a course group.")
    try:
        group_id = parse_uuid(body.group_id, "Course group")
    except ApiError:
        raise invalid("Please choose a course group.") from None
    if conn.execute(text("SELECT 1 FROM course_groups WHERE id = :id"), {"id": group_id}).first() is None:
        raise invalid("Please choose a course group.")
    price = body.price_poisha
    if price <= 0 or price % 100 != 0:
        raise invalid("Price must be a whole number of taka above 0.")
    return {
        "group_id": group_id,
        "title": title,
        "icon": check_icon(body.icon),
        "colour": check_colour(body.colour),
        "price_poisha": price,
        "duration": opt_text(body.duration, "Duration", 120),
        "level": opt_text(body.level, "Level", 120),
        "description": opt_text(body.description, "Description", MAX_LONG),
        "learn_points": text_list(body.learn_points, "What you will learn", "point under What you will learn"),
        "syllabus": text_list(body.syllabus, "Syllabus", "syllabus module"),
        "published": body.published,
    }


def _admin_course(conn: Connection, course_id: Any) -> dict[str, Any]:
    return course_view(conn.execute(_COURSE_BY_ID, {"id": course_id}).mappings().one(), admin=True)


@router.get("/admin/courses")
def list_admin_courses(
    actor: Actor = Depends(require_owner("course")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return [course_view(r, admin=True) for r in conn.execute(_ADMIN_COURSES).mappings()]


@router.post("/admin/courses")
async def create_course(
    request: Request, actor: Actor = Depends(require_owner("course")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(CourseIn, await request.body())
    values = _course_values(conn, body)
    lock_catalog(conn)
    row = _insert(conn, "courses", {"slug": new_slug(conn, "courses", values["title"]), **values})
    write_audit(conn, actor, "catalog.course_saved", _detail(row["title"], ["added"]))
    return _admin_course(conn, row["id"])


@router.put("/admin/courses/{course_id}")
async def update_course(
    course_id: str,
    request: Request,
    actor: Actor = Depends(require_owner("course")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(CourseIn, await request.body())
    values = _course_values(conn, body)
    before = _locked(conn, "courses", course_id, "Course")
    changed = changed_fields(before, values)
    if changed:
        _update(conn, "courses", before["id"], values)
        write_audit(conn, actor, "catalog.course_saved", _detail(values["title"], changed))
    return _admin_course(conn, before["id"])


# ---------------------------------------------------------------- universities

# applied_count: applications that are not withdrawn (B05).
_UNI_COUNT = (
    "(SELECT count(*) FROM applications a WHERE a.university_id = universities.id AND a.status <> 'withdrawn')"
)
_ADMIN_UNIVERSITIES = text(f"SELECT *, {_UNI_COUNT} AS applied_count, {UNI_SUCCESS} FROM universities ORDER BY name, id")
_UNIVERSITY_BY_ID = text(f"SELECT *, {_UNI_COUNT} AS applied_count, {UNI_SUCCESS} FROM universities WHERE id = :id")


def _university_values(body: UniversityIn, default_fee: int) -> dict[str, Any]:
    name = req_text(body.name, "Name", 200)
    if not 0 <= body.tuition_usd <= MAX_TUITION:
        raise invalid("Tuition must be a whole number of US dollars from 0 to 1,000,000.")
    if not 0 <= body.min_gpa <= 4:
        raise invalid("Minimum GPA must be from 0 to 4.")
    if not 0 <= body.min_ielts <= 9 or (body.min_ielts * 2) != int(body.min_ielts * 2):
        raise invalid("Minimum IELTS must be from 0 to 9 in steps of 0.5.")
    link = opt_text(body.apply_link, "Application link", 2000)
    if link and not link.startswith("https://"):
        raise invalid("The application link must start with https://.")
    return {
        "name": name,
        "country": req_text(body.country, "Country"),
        "city": opt_text(body.city, "City", 120),
        "levels": text_list(body.levels, "Study levels", "study level"),
        "fields": text_list(body.fields, "Fields of study", "field of study"),
        "tuition_usd": body.tuition_usd,
        "min_gpa": Decimal(str(round(body.min_gpa, 2))),
        "min_ielts": Decimal(str(body.min_ielts)),
        "intakes": opt_text(body.intakes, "Intakes", 200),
        "deadline_text": opt_text(body.deadline_text, "Deadline", 200),
        "scholarships": opt_text(body.scholarships, "Scholarships"),
        "work_rights": opt_text(body.work_rights, "Work rights"),
        "conditions": opt_text(body.conditions, "Conditions"),
        "apply_link": link,
        "admissions_email": opt_email(body.admissions_email, "admissions email"),
        "fee_override_poisha": stored_override(check_fee(body.fee_override_poisha), default_fee),
        "self_apply_fee_poisha": check_fee(body.self_apply_fee_poisha),
        "published": body.published,
    }


def _admin_university(conn: Connection, uid: Any, fee: int) -> dict[str, Any]:
    return university_view(conn.execute(_UNIVERSITY_BY_ID, {"id": uid}).mappings().one(), fee, admin=True)


@router.get("/admin/universities")
def list_admin_universities(
    actor: Actor = Depends(require_owner("study")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    fee = default_fees(conn)["study"]
    return [university_view(r, fee, admin=True) for r in conn.execute(_ADMIN_UNIVERSITIES).mappings()]


@router.post("/admin/universities")
async def create_university(
    request: Request, actor: Actor = Depends(require_owner("study")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(UniversityIn, await request.body())
    fee = default_fees(conn)["study"]
    values = _university_values(body, fee)
    lock_catalog(conn)
    row = _insert(conn, "universities", {"slug": new_slug(conn, "universities", values["name"]), **values})
    write_audit(conn, actor, "catalog.university_saved", _detail(row["name"], ["added"]))
    return _admin_university(conn, row["id"], fee)


@router.put("/admin/universities/{university_id}")
async def update_university(
    university_id: str,
    request: Request,
    actor: Actor = Depends(require_owner("study")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(UniversityIn, await request.body())
    fee = default_fees(conn)["study"]
    values = _university_values(body, fee)
    before = _locked(conn, "universities", university_id, "University")
    changed = changed_fields(before, values)
    if changed:
        _update(conn, "universities", before["id"], values)
        write_audit(conn, actor, "catalog.university_saved", _detail(values["name"], changed))
    return _admin_university(conn, before["id"], fee)


# ---------------------------------------------------------------- vacancies

_VAC_COUNT = "(SELECT count(*) FROM applications a WHERE a.vacancy_id = vacancies.id AND a.status <> 'withdrawn')"
# Job Processing lists on-site vacancies (remote = false); Remote Jobs lists remote ones (remote = true).
_ADMIN_VACANCIES = text(
    f"SELECT *, {_VAC_COUNT} AS applied_count, {VAC_SUCCESS} FROM vacancies WHERE remote = :remote "
    "ORDER BY created_at DESC, id"
)
_VACANCY_BY_ID = text(f"SELECT *, {_VAC_COUNT} AS applied_count, {VAC_SUCCESS} FROM vacancies WHERE id = :id")


def _vacancy_values(body: VacancyIn, default_fee: int) -> dict[str, Any]:
    if not 0 <= body.min_experience <= 40:
        raise invalid("Minimum experience must be from 0 to 40 years.")
    if not 0 <= body.min_education <= 3:
        raise invalid("Please choose the minimum education.")
    if not 0 <= body.min_english <= 2:
        raise invalid("Please choose the minimum English level.")
    if not 0 < body.salary_usd <= MAX_SALARY:
        raise invalid("Salary must be a whole number of US dollars above 0.")
    if body.seats is not None and body.seats < 1:
        raise invalid("Seats must be 1 or more.")
    if body.apply_by is not None and not body.closed and body.apply_by < today_dhaka():
        raise invalid("Apply by must not be in the past for an open vacancy.")
    return {
        "title": req_text(body.title, "Job title"),
        "employer": req_text(body.employer, "Employer", 200),
        "country": req_text(body.country, "Country"),
        "occupation": req_text(body.occupation, "Occupation"),
        "min_experience": body.min_experience,
        "min_education": body.min_education,
        "min_english": body.min_english,
        "salary_usd": body.salary_usd,
        "seats": body.seats,
        "apply_by": body.apply_by,
        "contract": opt_text(body.contract, "Contract"),
        "benefits": opt_text(body.benefits, "Benefits"),
        "conditions": opt_text(body.conditions, "Conditions"),
        "employer_licence": opt_text(body.employer_licence, "Employer licence", 120),
        "employer_email": opt_email(body.employer_email, "employer email"),
        "employer_verified": body.employer_verified,
        "closed": body.closed,
        "fee_override_poisha": stored_override(check_fee(body.fee_override_poisha), default_fee),
    }


def _admin_vacancy(conn: Connection, vid: Any, fee: int) -> dict[str, Any]:
    return vacancy_view(conn.execute(_VACANCY_BY_ID, {"id": vid}).mappings().one(), fee, admin=True)


def _verified_audit(conn: Connection, actor: Actor, values: dict[str, Any]) -> None:
    action = "Employer verified" if values["employer_verified"] else "Employer unverified"
    write_audit(conn, actor, action, f"{values['employer']} · {values['title']}")


@router.get("/admin/vacancies")
def list_admin_vacancies(
    actor: Actor = Depends(require_owner("job")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    fee = default_fees(conn)["job"]
    return [vacancy_view(r, fee, admin=True) for r in conn.execute(_ADMIN_VACANCIES, {"remote": False}).mappings()]


@router.post("/admin/vacancies")
async def create_vacancy(
    request: Request, actor: Actor = Depends(require_owner("job")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(VacancyIn, await request.body())
    fee = default_fees(conn)["job"]
    return _create_vacancy(conn, actor, body, fee, remote=False)


def _create_vacancy(conn: Connection, actor: Actor, body: VacancyIn, fee: int, remote: bool) -> dict[str, Any]:
    values = _vacancy_values(body, fee)
    lock_catalog(conn)
    row = _insert(conn, "vacancies", {"slug": new_slug(conn, "vacancies", values["title"]), **values, "remote": remote})
    action = "catalog.remote_job_saved" if remote else "catalog.vacancy_saved"
    write_audit(conn, actor, action, _detail(row["title"], ["added"]))
    return _admin_vacancy(conn, row["id"], fee)


@router.put("/admin/vacancies/{vacancy_id}")
async def update_vacancy(
    vacancy_id: str,
    request: Request,
    actor: Actor = Depends(require_owner("job")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(VacancyIn, await request.body())
    return _update_vacancy(conn, actor, vacancy_id, body, default_fees(conn)["job"], remote=False)


def _update_vacancy(
    conn: Connection, actor: Actor, vacancy_id: str, body: VacancyIn, fee: int, remote: bool
) -> dict[str, Any]:
    values = _vacancy_values(body, fee)
    what = "Remote job" if remote else "Vacancy"
    before = _locked(conn, "vacancies", vacancy_id, what)
    # A vacancy stays in the section it was added in (Job Processing or Remote Jobs).
    if before["remote"] != remote:
        raise not_found(what)
    changed = changed_fields(before, values)
    if changed:
        _update(conn, "vacancies", before["id"], values)
        if "employer_verified" in changed:
            _verified_audit(conn, actor, values)
        others = [f for f in changed if f != "employer_verified"]
        if others:
            action = "catalog.remote_job_saved" if remote else "catalog.vacancy_saved"
            write_audit(conn, actor, action, _detail(values["title"], others))
    return _admin_vacancy(conn, before["id"], fee)


# ---------------------------------------------------------------- remote jobs (Remote Jobs module)


@router.get("/admin/remote-jobs")
def list_admin_remote_jobs(
    actor: Actor = Depends(require_owner("remote")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    fee = default_fees(conn)["remote"]
    return [vacancy_view(r, fee, admin=True) for r in conn.execute(_ADMIN_VACANCIES, {"remote": True}).mappings()]


@router.post("/admin/remote-jobs")
async def create_remote_job(
    request: Request, actor: Actor = Depends(require_owner("remote")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(VacancyIn, await request.body())
    return _create_vacancy(conn, actor, body, default_fees(conn)["remote"], remote=True)


@router.put("/admin/remote-jobs/{job_id}")
async def update_remote_job(
    job_id: str,
    request: Request,
    actor: Actor = Depends(require_owner("remote")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(VacancyIn, await request.body())
    return _update_vacancy(conn, actor, job_id, body, default_fees(conn)["remote"], remote=True)


# ---------------------------------------------------------------- visa programmes (B19)

_VISA_COUNT = (
    "(SELECT count(*) FROM applications a WHERE a.visa_program_id = visa_programs.id AND a.status <> 'withdrawn')"
)
_ADMIN_VISA_PROGRAMS = text(
    f"SELECT *, {_VISA_COUNT} AS applied_count, {VISA_SUCCESS} FROM visa_programs ORDER BY country, title, id"
)
_VISA_PROGRAM_BY_ID = text(f"SELECT *, {_VISA_COUNT} AS applied_count, {VISA_SUCCESS} FROM visa_programs WHERE id = :id")


def _visa_program_values(body: VisaProgramIn, default_fee: int) -> dict[str, Any]:
    if body.visa_type not in VISA_TYPES:
        raise invalid("Please choose a visa type.")
    link = opt_text(body.official_link, "Official link", 2000)
    if link and not link.startswith("https://"):
        raise invalid("The official link must start with https://.")
    return {
        "title": req_text(body.title, "Programme name", 200),
        "country": req_text(body.country, "Country"),
        "visa_type": body.visa_type,
        "processing_time": opt_text(body.processing_time, "Processing time", 200),
        "validity": opt_text(body.validity, "Validity", 200),
        "government_fee": opt_text(body.government_fee, "Government fee", 200),
        "description": opt_text(body.description, "Description", MAX_LONG),
        "eligibility": text_list(body.eligibility, "Eligibility", "eligibility point"),
        "required_documents": text_list(body.required_documents, "Required documents", "required document"),
        "conditions": opt_text(body.conditions, "Conditions", MAX_LONG),
        "official_link": link,
        "embassy_email": opt_email(body.embassy_email, "embassy email"),
        "fee_override_poisha": stored_override(check_fee(body.fee_override_poisha), default_fee),
        "published": body.published,
    }


def _admin_visa_program(conn: Connection, pid: Any, fee: int) -> dict[str, Any]:
    return visa_program_view(conn.execute(_VISA_PROGRAM_BY_ID, {"id": pid}).mappings().one(), fee, admin=True)


@router.get("/admin/visa-programs")
def list_admin_visa_programs(
    actor: Actor = Depends(require_owner("visa")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    fee = default_fees(conn)["visa"]
    return [visa_program_view(r, fee, admin=True) for r in conn.execute(_ADMIN_VISA_PROGRAMS).mappings()]


@router.post("/admin/visa-programs")
async def create_visa_program(
    request: Request, actor: Actor = Depends(require_owner("visa")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(VisaProgramIn, await request.body())
    fee = default_fees(conn)["visa"]
    values = _visa_program_values(body, fee)
    lock_catalog(conn)
    slug = new_slug(conn, "visa_programs", f"{values['country']} {values['title']}")
    row = _insert(conn, "visa_programs", {"slug": slug, **values})
    write_audit(conn, actor, "catalog.visa_program_saved", _detail(row["title"], ["added"]))
    return _admin_visa_program(conn, row["id"], fee)


@router.put("/admin/visa-programs/{program_id}")
async def update_visa_program(
    program_id: str,
    request: Request,
    actor: Actor = Depends(require_owner("visa")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    body = parse_body(VisaProgramIn, await request.body())
    fee = default_fees(conn)["visa"]
    values = _visa_program_values(body, fee)
    before = _locked(conn, "visa_programs", program_id, "Visa programme")
    changed = changed_fields(before, values)
    if changed:
        _update(conn, "visa_programs", before["id"], values)
        write_audit(conn, actor, "catalog.visa_program_saved", _detail(values["title"], changed))
    return _admin_visa_program(conn, before["id"], fee)


# ---------------------------------------------------------------- fees

# (table, name column, which rows): Job Processing and Remote Jobs share vacancies, split by remote.
_FEE_TABLES: dict[str, tuple[str, str, str]] = {
    "study": ("universities", "name", "true"),
    "job": ("vacancies", "title", "NOT remote"),
    "visa": ("visa_programs", "title", "true"),
    "remote": ("vacancies", "title", "remote"),
}


def _fee_items(conn: Connection, module: str, default: int) -> list[dict[str, Any]]:
    table, label, rows_of = _FEE_TABLES[module]
    rows = conn.execute(
        text(f"SELECT id, {label} AS name, fee_override_poisha FROM {table} WHERE {rows_of} ORDER BY {label}, id")
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "default_poisha": default,
            "override_poisha": r.fee_override_poisha,
            "effective_poisha": r.fee_override_poisha if r.fee_override_poisha is not None else default,
        }
        for r in rows
    ]


def _fees_view(conn: Connection) -> dict[str, Any]:
    licence = read_licence(conn)
    defaults = default_fees(conn)
    return {
        "defaults": defaults,
        "universities": _fee_items(conn, "study", defaults["study"]) if licence.licensed("study") else [],
        "vacancies": _fee_items(conn, "job", defaults["job"]) if licence.licensed("job") else [],
        "visa_programs": _fee_items(conn, "visa", defaults["visa"]) if licence.licensed("visa") else [],
        "remote_jobs": _fee_items(conn, "remote", defaults["remote"]) if licence.licensed("remote") else [],
    }


@router.get("/admin/fees")
def get_fees(actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    return _fees_view(conn)


@router.put("/admin/fees")
async def save_fees(
    request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(FeesIn, await request.body())
    defaults = default_fees(conn)
    lines: list[str] = []
    for module, changes in (("study", body.study), ("job", body.job), ("visa", body.visa), ("remote", body.remote)):
        if not changes:
            continue
        ensure_licensed(conn, module)  # type: ignore[arg-type]
        table, label, rows_of = _FEE_TABLES[module]
        what = {"study": "University", "job": "Vacancy", "visa": "Visa programme", "remote": "Remote job"}[module]
        for item_id, fee in changes.items():
            check_fee(fee)
            row = conn.execute(
                text(
                    f"SELECT id, {label} AS name, fee_override_poisha FROM {table} "
                    f"WHERE id = :id AND {rows_of} FOR UPDATE"
                ),
                {"id": parse_uuid(item_id, what)},
            ).one_or_none()
            if row is None:
                raise not_found(what)
            new = stored_override(fee, defaults[module])  # type: ignore[index]
            if new == row.fee_override_poisha:
                continue
            conn.execute(text(f"UPDATE {table} SET fee_override_poisha = :fee WHERE id = :id"), {"fee": new, "id": row.id})
            effective = new if new is not None else defaults[module]  # type: ignore[index]
            lines.append(f"{row.name} ৳{effective // 100:,}")
    if lines:
        write_audit(conn, actor, "fees.saved", ", ".join(lines))
    return _fees_view(conn)


@router.post("/admin/fees/reset")
async def reset_fees(
    request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(ResetIn, await request.body())
    licence = read_licence(conn)
    if body.scope == "all":
        modules = [m for m in ("study", "job", "visa", "remote") if licence.licensed(m)]  # type: ignore[arg-type]
    else:
        ensure_licensed(conn, body.scope)
        modules = [body.scope]
    for module in modules:
        table, _, rows_of = _FEE_TABLES[module]
        conn.execute(
            text(f"UPDATE {table} SET fee_override_poisha = NULL WHERE fee_override_poisha IS NOT NULL AND {rows_of}")
        )
    labels = ", ".join(MODULE_LABELS[m] for m in modules) or "none"  # type: ignore[index]
    write_audit(conn, actor, "fees.reset", labels)
    return _fees_view(conn)
