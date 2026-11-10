"""Matching and the rule-based agent replies (spec B04), ported from match(), sc() and fb()
in the reference.

Each check has a weight; match_percent = round(30 + 70 x passed weight / total weight),
rounded half up like JavaScript Math.round.
"""

import math
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.catalog import (
    ANY_COUNTRY,
    EDUCATION_LEVELS,
    ENGLISH_LEVELS,
    VISA_TYPES,
    default_fees,
    invalid,
    number_text,
    public_remote_jobs,
    public_universities,
    public_vacancies,
    public_visa_programs,
    university_view,
    usd,
    vacancy_view,
    visa_program_view,
)
from app.errors import ApiError
from app.stages import DOCUMENT_TYPES, STAGES

AgentModule = Literal["study", "job", "visa", "remote"]

STUDY_STAGE_COUNT = 9
JOB_STAGE_COUNT = 8
VISA_STAGE_COUNT = 8
REMOTE_STAGE_COUNT = 6
ANY_VISA_TYPE = "any"


@dataclass(frozen=True)
class StudyInput:
    level: str
    field: str
    gpa: float
    ielts: float
    budget_usd: float
    country: str = ""


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
class RemoteInput:
    """Remote Jobs: like a job match, with no passport or travel (the work is done from home)."""

    occupation: str
    country: str
    experience: float
    education: str
    english: str
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


def check_remote(data: RemoteInput) -> RemoteInput:
    if not data.occupation.strip():
        raise invalid("Please fill in: Your skill or role.")
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
    country = data.country.strip()
    results = []
    for u in public_universities(conn):
        if country and country != ANY_COUNTRY and u["country"] != country:
            continue
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
        checks: list[Check] = [
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
        ]
        results.append(_score(vacancy_view(v, fee), checks))
    results.sort(key=lambda r: -r["match_percent"])
    return results


def match_remote(conn: Connection, data: RemoteInput) -> list[dict[str, Any]]:
    """Remote Jobs: open remote roles for the skill (and the employer's country, or any)."""
    fee = default_fees(conn)["remote"]
    edu = EDUCATION_LEVELS.index(data.education)
    eng = ENGLISH_LEVELS.index(data.english)
    country = data.country.strip()
    goal = data.salary_goal_usd
    results = []
    for v in public_remote_jobs(conn):
        if v["occupation"] != data.occupation.strip():
            continue
        if country and country != ANY_COUNTRY and v["country"] != country:
            continue
        checks: list[Check] = [
            (
                data.experience >= v["min_experience"],
                f"Experience meets {v['min_experience']} yrs",
                f"Needs {v['min_experience']}+ yrs experience",
                2,
            ),
            (edu >= v["min_education"], "Education fits", f"Needs {EDUCATION_LEVELS[v['min_education']]}", 1.5),
            (eng >= v["min_english"], "English fits", f"Needs {ENGLISH_LEVELS[v['min_english']]} English", 1),
            (
                not goal or v["salary_usd"] >= goal,
                "Meets salary goal",
                f"Pays ~{usd(v['salary_usd'])}/month",
                1,
            ),
        ]
        results.append(_score(vacancy_view(v, fee), checks))
    results.sort(key=lambda r: -r["match_percent"])
    return results


# ---------------------------------------------------------------- agent

NEEDS_FORM = (
    "Please fill in the form first so I can match you. After that, ask me about fees, "
    "requirements, scholarships or the process."
)
# What each advisor can be asked about after the form (the same start as NEEDS_FORM).
_ASK_ABOUT: dict[str, str] = {
    "study": "fees, requirements, scholarships or the process",
    "job": "salary, requirements, fees or the process",
    "visa": "documents, fees, processing time or the process",
    "remote": "salary, requirements, fees or the process",
}
# (one, many) of what each module offers.
_NOUNS: dict[str, tuple[str, str]] = {
    "study": ("university", "universities"),
    "job": ("job", "jobs"),
    "visa": ("visa programme", "visa programmes"),
    "remote": ("remote job", "remote jobs"),
}
_FEE_WORDS = ("fee", "cost", "price", "charge", "taka", "pay")
_PROCESS_WORDS = ("process", "step", "stage", "how do", "how to", "how can", "apply")
_DOCUMENT_WORDS = ("document", "paper", "need to submit", "certificate")
_COUNTRY_WORDS = ("country", "countries", "where", "location")
_CONTACT_WORDS = ("contact", "phone", "call", "email", "office", "address", "talk", "advisor", "consult")
_LIST_WORDS = ("available", "open", "list", "show", "which", "what", "any ", "have", "offer", "role", "job", "universit", "programme")


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
                        country=str(inputs.get("country", "")),
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
        if module == "remote":
            return match_remote(
                conn,
                check_remote(
                    RemoteInput(
                        occupation=str(inputs.get("occupation", "")),
                        country=str(inputs.get("country", "")),
                        experience=_number(inputs.get("experience")),
                        education=str(inputs.get("education", "")),
                        english=str(inputs.get("english", "")),
                        salary_goal_usd=None if goal in (None, "") else _number(goal),
                    )
                ),
            )
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


def _public_items(conn: Connection, module: AgentModule) -> list[dict[str, Any]]:
    fee = default_fees(conn)[module]
    if module == "study":
        return [university_view(r, fee) for r in public_universities(conn)]
    if module == "visa":
        return [visa_program_view(r, fee) for r in public_visa_programs(conn)]
    rows = public_remote_jobs(conn) if module == "remote" else public_vacancies(conn)
    return [vacancy_view(r, fee) for r in rows]


def _item_label(module: AgentModule, item: dict[str, Any]) -> str:
    if module == "study":
        return f"{item['name']} ({item['country']})"
    if module == "visa":
        return f"{item['title']} ({item['country']})"
    return f"{item['title']} at {item['employer']} ({item['country']})"


def _named_item(module: AgentModule, q: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The item the question names (its full name, or the first word of it when that is 4+ letters)."""
    for item in items:
        name = str(item["name"] if module == "study" else item["title"]).lower()
        first = name.split()[0] if name.split() else ""
        if name in q or (len(first) >= 4 and first in q.split()):
            return item
    return None


def _contact_text(conn: Connection) -> str:
    row = conn.execute(text("SELECT name, phone, email FROM settings WHERE singleton = 'settings'")).one()
    parts = [p for p in (f"phone {row.phone}" if row.phone else "", f"email {row.email}" if row.email else "") if p]
    who = row.name or "us"
    return f"Contact {who}: {', '.join(parts)}." if parts else f"Please contact {who} through the Contact page."


def _overview_answer(conn: Connection, module: AgentModule, q: str, items: list[dict[str, Any]]) -> str:
    """A reply from the database without a form match: what is open, countries, fees, steps,
    documents or contact details. Never anything that is not stored."""
    from app.applications import money_text  # here, to keep app.match free of import cycles

    one, many = _NOUNS[module]
    contact = _contact_text(conn)
    if any(w in q for w in _CONTACT_WORDS):
        return contact
    if any(w in q for w in _DOCUMENT_WORDS):
        return f"The documents you need: {', '.join(DOCUMENT_TYPES[module])}. You upload them after you apply."
    if any(w in q for w in _PROCESS_WORDS):
        stages = STAGES[module]
        return f"After you apply, your file moves through {len(stages)} stages: {' → '.join(stages)}. You follow each stage in your profile."
    if not items:
        return f"We have no open {many} right now. Please check back soon. {contact}"
    if any(w in q for w in _FEE_WORDS):
        fees = sorted({int(i["fee_poisha"]) for i in items})
        if len(fees) == 1:
            return f"Our application fee is {money_text(fees[0])} for every open {one}. You pay it after you apply."
        return f"Our application fee is from {money_text(fees[0])} to {money_text(fees[-1])}, shown on each {one}'s page."
    if any(w in q for w in _COUNTRY_WORDS):
        countries = sorted({str(i["country"]) for i in items})
        return f"We have open {many} in: {', '.join(countries)}."
    if any(w in q for w in _LIST_WORDS):
        names = "; ".join(_item_label(module, i) for i in items[:5])
        more = f" and {len(items) - 5} more" if len(items) > 5 else ""
        return f"We have {len(items)} open {one if len(items) == 1 else many}: {names}{more}. Fill in the form to see your match."
    return f"Please fill in the form first so I can match you. After that, ask me about {_ASK_ABOUT[module]}."


def agent_answer(conn: Connection, module: AgentModule, question: str, inputs: dict[str, Any] | None) -> str:
    q = question.lower()
    results = _agent_matches(conn, module, inputs)
    if not results:
        # No form match: an item named in the question, or an overview from the database.
        items = _public_items(conn, module)
        named = _named_item(module, q, items)
        if named is None:
            return _overview_answer(conn, module, q, items)
        results = [{"item": named, "match_percent": None}]
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
    if module == "remote" and any(w in q for w in ("process", "step", "stage", "apply", "document", "letter")):
        return (
            f"After you apply, your file moves through {REMOTE_STAGE_COUNT} stages up to your offer letter and start. "
            "There is no visa or travel. You can follow each stage in your profile."
        )
    if any(w in q for w in ("visa", "process", "step", "stage", "apply", "document")):
        stages = STUDY_STAGE_COUNT if study else JOB_STAGE_COUNT
        return (
            f"After you apply, your file moves through {stages} stages up to visa and departure. "
            "You can follow each stage in your profile."
        )
    if top["match_percent"] is None:
        return f"{name} is open now. Open its page to see every condition, or ask about cost, requirements or the process."
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
    if top["match_percent"] is None:
        return f"{name} is open now. Open its page to see every condition, or ask about cost, documents or processing time."
    return (
        f"Your best match is {name} ({top['match_percent']}%). Select it to see every condition, "
        "or ask about cost, documents, processing time or the process."
    )
