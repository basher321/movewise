"""Matching and the rule-based agent replies (spec B04), ported from match(), sc() and fb()
in the reference.

Each check has a weight; match_percent = round(30 + 70 x passed weight / total weight),
rounded half up like JavaScript Math.round.
"""

import math
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.engine import Connection

from app.catalog import (
    ANY_COUNTRY,
    EDUCATION_LEVELS,
    ENGLISH_LEVELS,
    VISA_TYPES,
    default_fees,
    invalid,
    number_text,
    public_universities,
    public_vacancies,
    public_visa_programs,
    university_view,
    usd,
    vacancy_view,
    visa_program_view,
)
from app.errors import ApiError

AgentModule = Literal["study", "job", "visa"]

STUDY_STAGE_COUNT = 9
JOB_STAGE_COUNT = 8
VISA_STAGE_COUNT = 8
ANY_VISA_TYPE = "any"


@dataclass(frozen=True)
class StudyInput:
    level: str
    field: str
    gpa: float
    ielts: float
    budget_usd: float


@dataclass(frozen=True)
class JobInput:
    occupation: str
    country: str
    experience: float
    education: str
    english: str
    passport_ready: bool
    salary_goal_usd: float | None


@dataclass(frozen=True)
class VisaInput:
    country: str
    visa_type: str
    passport_ready: bool
    refused_before: bool


Check = tuple[bool, str, str, float]


def _score(item: dict[str, Any], checks: list[Check]) -> dict[str, Any]:
    total = sum(weight for _, _, _, weight in checks)
    got = sum(weight for ok, _, _, weight in checks if ok)
    return {
        "item": item,
        "checks": [{"ok": ok, "label": yes if ok else no} for ok, yes, no, _ in checks],
        "match_percent": math.floor(30 + 70 * got / total + 0.5),
    }


def _in_range(value: float, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < low or value > high:
        raise invalid(f"{label} must be a number from {number_text(low)} to {number_text(high)}.")
    return value


def check_study(data: StudyInput) -> StudyInput:
    if not data.level.strip():
        raise invalid("Please fill in: Study level.")
    if not data.field.strip():
        raise invalid("Please fill in: Field of study.")
    _in_range(data.gpa, "GPA", 0, 4)
    _in_range(data.ielts, "IELTS", 0, 9)
    _in_range(data.budget_usd, "Budget", 0, 1_000_000)
    return data


def check_job(data: JobInput) -> JobInput:
    if not data.occupation.strip():
        raise invalid("Please fill in: Your occupation.")
    _in_range(data.experience, "Experience", 0, 40)
    if data.education not in EDUCATION_LEVELS:
        raise invalid("Please choose your education.")
    if data.english not in ENGLISH_LEVELS:
        raise invalid("Please choose your English level.")
    if data.salary_goal_usd is not None:
        _in_range(data.salary_goal_usd, "Salary goal", 0, 1_000_000)
    return data


def check_visa(data: VisaInput) -> VisaInput:
    if not data.country.strip():
        raise invalid("Please fill in: Destination country.")
    if data.visa_type != ANY_VISA_TYPE and data.visa_type not in VISA_TYPES:
        raise invalid("Please choose a visa type.")
    return data


def match_visa(conn: Connection, data: VisaInput) -> list[dict[str, Any]]:
    """B19: published programmes for the country (or any) and visa type (or any)."""
    fee = default_fees(conn)["visa"]
    country = data.country.strip()
    results = []
    for p in public_visa_programs(conn):
        if country != ANY_COUNTRY and p["country"] != country:
            continue
        if data.visa_type != ANY_VISA_TYPE and p["visa_type"] != data.visa_type:
            continue
        results.append(
            _score(
                visa_program_view(p, fee),
                [
                    (data.passport_ready, "Passport ready", "You need a valid passport first", 2),
                    (
                        not data.refused_before,
                        "No previous refusal",
                        "Previous refusal: your advisor reviews it first",
                        1,
                    ),
                    (
                        data.visa_type == ANY_VISA_TYPE or p["visa_type"] == data.visa_type,
                        f"{VISA_TYPES.get(p['visa_type'], 'Visa')} fits",
                        "Different visa type",
                        1,
                    ),
                ],
            )
        )
    results.sort(key=lambda r: -r["match_percent"])
    return results


def match_study(conn: Connection, data: StudyInput) -> list[dict[str, Any]]:
    fee = default_fees(conn)["study"]
    level, field = data.level.strip(), data.field.strip()
    results = []
    for u in public_universities(conn):
        if level not in u["levels"] or field not in u["fields"]:
            continue
        gpa, ielts = number_text(u["min_gpa"]), number_text(u["min_ielts"])
        results.append(
            _score(
                university_view(u, fee),
                [
                    (data.gpa >= float(u["min_gpa"]), f"GPA meets {gpa}", f"GPA below {gpa}", 2),
                    (
                        data.ielts >= float(u["min_ielts"]),
                        f"IELTS meets {ielts}",
                        f"IELTS below {ielts}" if data.ielts else f"IELTS {ielts} needed",
                        2,
                    ),
                    (
                        data.budget_usd >= u["tuition_usd"],
                        "Within budget",
                        f"Above budget (~{usd(u['tuition_usd'])})",
                        1.5,
                    ),
                ],
            )
        )
    results.sort(key=lambda r: -r["match_percent"])
    return results


def match_job(conn: Connection, data: JobInput) -> list[dict[str, Any]]:
    fee = default_fees(conn)["job"]
    edu = EDUCATION_LEVELS.index(data.education)
    eng = ENGLISH_LEVELS.index(data.english)
    country = data.country.strip()
    goal = data.salary_goal_usd
    results = []
    for v in public_vacancies(conn):
        if v["occupation"] != data.occupation.strip():
            continue
        if country and country != ANY_COUNTRY and v["country"] != country:
            continue
        results.append(
            _score(
                vacancy_view(v, fee),
                [
                    (
                        data.experience >= v["min_experience"],
                        f"Experience meets {v['min_experience']} yrs",
                        f"Needs {v['min_experience']}+ yrs experience",
                        2,
                    ),
                    (edu >= v["min_education"], "Education fits", f"Needs {EDUCATION_LEVELS[v['min_education']]}", 1.5),
                    (eng >= v["min_english"], "English fits", f"Needs {ENGLISH_LEVELS[v['min_english']]} English", 1),
                    (data.passport_ready, "Passport ready", "Passport must be valid 18+ months", 2),
                    (
                        not goal or v["salary_usd"] >= goal,
                        "Meets salary goal",
                        f"Pays ~{usd(v['salary_usd'])}/month",
                        1,
                    ),
                ],
            )
        )
    results.sort(key=lambda r: -r["match_percent"])
    return results


# ---------------------------------------------------------------- agent

NEEDS_FORM = (
    "Please fill in the form first so I can match you. After that, ask me about fees, "
    "requirements, scholarships or the process."
)


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError
    return float(value)


def _agent_matches(conn: Connection, module: AgentModule, inputs: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The matches for the inputs, or none when the inputs are missing or not valid."""
    if not inputs:
        return []
    try:
        if module == "study":
            return match_study(
                conn,
                check_study(
                    StudyInput(
                        level=str(inputs.get("level", "")),
                        field=str(inputs.get("field", "")),
                        gpa=_number(inputs.get("gpa")),
                        ielts=_number(inputs.get("ielts", 0)),
                        budget_usd=_number(inputs.get("budget_usd")),
                    )
                ),
            )
        if module == "visa":
            return match_visa(
                conn,
                check_visa(
                    VisaInput(
                        country=str(inputs.get("country", "")),
                        visa_type=str(inputs.get("visa_type", ANY_VISA_TYPE) or ANY_VISA_TYPE),
                        passport_ready=inputs.get("passport_ready") is True,
                        refused_before=inputs.get("refused_before") is True,
                    )
                ),
            )
        goal = inputs.get("salary_goal_usd")
        return match_job(
            conn,
            check_job(
                JobInput(
                    occupation=str(inputs.get("occupation", "")),
                    country=str(inputs.get("country", "")),
                    experience=_number(inputs.get("experience")),
                    education=str(inputs.get("education", "")),
                    english=str(inputs.get("english", "")),
                    passport_ready=inputs.get("passport_ready") is True,
                    salary_goal_usd=None if goal in (None, "") else _number(goal),
                )
            ),
        )
    except (ValueError, TypeError, ApiError):
        return []


def agent_answer(conn: Connection, module: AgentModule, question: str, inputs: dict[str, Any] | None) -> str:
    results = _agent_matches(conn, module, inputs)
    if not results:
        return NEEDS_FORM
    q = question.lower()
    top = results[0]
    item = top["item"]
    if module == "visa":
        return _visa_answer(q, top)
    study = module == "study"
    name = item["name"] if study else f"{item['title']} at {item['employer']}"
    if any(w in q for w in ("fee", "tuition", "cost", "salary", "pay", "taka")):
        if study:
            return f"{name} costs about {usd(item['tuition_usd'])} per year. Scholarships: {item['scholarships']}."
        return f"{name} pays about {usd(item['salary_usd'])} per month. Benefits: {item['benefits']}."
    if any(w in q for w in ("ielts", "gpa", "require", "eligib", "experience", "english")):
        if study:
            return (
                f"{name} needs GPA {number_text(item['min_gpa'])} and IELTS {number_text(item['min_ielts'])}. "
                "Open its page for all conditions."
            )
        return (
            f"{name} needs {item['min_experience']}+ years of experience and "
            f"{ENGLISH_LEVELS[item['min_english']]} English. Open its page for all conditions."
        )
    if any(w in q for w in ("visa", "process", "step", "stage", "apply", "document")):
        stages = STUDY_STAGE_COUNT if study else JOB_STAGE_COUNT
        return (
            f"After you apply, your file moves through {stages} stages up to visa and departure. "
            "You can follow each stage in your profile."
        )
    return (
        f"Your best match is {name} ({top['match_percent']}%). Select it to see every condition, "
        "or ask about cost, requirements or the process."
    )


def _visa_answer(q: str, top: dict[str, Any]) -> str:
    item = top["item"]
    name = f"{item['title']} ({item['country']})"
    if any(w in q for w in ("fee", "cost", "price", "pay", "taka")):
        gov = f" The government fee is {item['government_fee']}." if item["government_fee"] else ""
        return f"Our processing fee for {name} is shown on its page.{gov}"
    if any(w in q for w in ("time", "long", "days", "week", "month")):
        if item["processing_time"]:
            return f"{name} usually takes {item['processing_time']}."
        return f"Processing time for {name} depends on the embassy. Your advisor confirms it."
    if any(w in q for w in ("document", "paper", "require", "eligib", "need")):
        docs = ", ".join(item["required_documents"][:5])
        return f"{name} needs: {docs}. Open its page for every condition."
    if any(w in q for w in ("process", "step", "stage", "apply")):
        return (
            f"After you apply, your file moves through {VISA_STAGE_COUNT} stages up to the visa decision and travel. "
            "You can follow each stage in your profile."
        )
    return (
        f"Your best match is {name} ({top['match_percent']}%). Select it to see every condition, "
        "or ask about cost, documents, processing time or the process."
    )
