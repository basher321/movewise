"""The database facts an advisor answer may use (spec B17).

Only published universities, open verified vacancies (on-site or, for Remote Jobs, remote) and
published visa programmes (the same rows the public pages show), with their success rates, the
application fee, the stage names, the required documents and the company contact details from
Settings. Each advisor gets only its own module's rows. Nothing about any applicant, no staff-only field (apply link, admissions, employer or
embassy email, employer licence, official link) and nothing from another module is ever included.
"""

import re
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import money_text
from app.catalog import (
    EDUCATION_LEVELS,
    ENGLISH_LEVELS,
    VISA_TYPES,
    default_fees,
    effective_fee,
    public_universities,
    public_remote_jobs,
    public_vacancies,
    public_visa_programs,
)
from app.ai.my_cases import my_cases
from app.match import _agent_matches
from app.catalog import success_rate
from app.stages import DOCUMENT_TYPES, STAGES

AgentModule = Literal["study", "job", "visa", "remote"]
MAX_ROWS = 8
MAX_TEXT = 600
_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
# Common words that would match almost every row.
_STOP = frozenset(
    {
        "the", "and", "for", "you", "your", "are", "can", "what", "which", "how", "with", "from", "about",
        "have", "has", "any", "all", "university", "universities", "job", "jobs", "study", "work", "want",
        "need", "please", "tell", "there", "that", "this", "does", "will", "they", "who", "where", "when",
    }
)


def _short(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[: MAX_TEXT - 1] + "…"
    return value


def _words(question: str) -> set[str]:
    return {w for w in (m.lower() for m in _WORD.findall(question)) if w not in _STOP}


def _university_fact(row: Any, fee_default: int) -> dict[str, Any]:
    return {
        "name": row["name"],
        "country": row["country"],
        "city": row["city"],
        "levels": list(row["levels"]),
        "fields": list(row["fields"]),
        "tuition_usd_per_year": row["tuition_usd"],
        "min_gpa": float(row["min_gpa"]),
        "min_ielts": float(row["min_ielts"]),
        "intakes": _short(row["intakes"]),
        "deadline": _short(row["deadline_text"]),
        "scholarships": _short(row["scholarships"]),
        "work_rights": _short(row["work_rights"]),
        "conditions": _short(row["conditions"]),
        "our_application_fee": money_text(effective_fee(row["fee_override_poisha"], fee_default)),
        "self_apply_fee": money_text(row["self_apply_fee_poisha"]) if row["self_apply_fee_poisha"] is not None else None,
        "success_rate": success_rate(row),
    }


def _vacancy_fact(row: Any, fee_default: int) -> dict[str, Any]:
    return {
        "title": row["title"],
        "employer": row["employer"],
        "country": row["country"],
        "occupation": row["occupation"],
        "min_experience_years": row["min_experience"],
        "min_education": EDUCATION_LEVELS[row["min_education"]],
        "min_english": ENGLISH_LEVELS[row["min_english"]],
        "salary_usd_per_month": row["salary_usd"],
        "seats": row["seats"],
        "apply_by": row["apply_by"].isoformat() if row["apply_by"] else None,
        "contract": _short(row["contract"]),
        "benefits": _short(row["benefits"]),
        "conditions": _short(row["conditions"]),
        "employer_verified": row["employer_verified"],
        "work_type": "Remote (work from home, no visa or travel)" if row["remote"] else "On-site abroad",
        "our_application_fee": money_text(effective_fee(row["fee_override_poisha"], fee_default)),
        "success_rate": success_rate(row),
    }


def _visa_fact(row: Any, fee_default: int) -> dict[str, Any]:
    return {
        "title": row["title"],
        "country": row["country"],
        "visa_type": VISA_TYPES.get(row["visa_type"], row["visa_type"]),
        "processing_time": _short(row["processing_time"]),
        "validity": _short(row["validity"]),
        "government_fee": _short(row["government_fee"]),
        "description": _short(row["description"]),
        "eligibility": [_short(x) for x in row["eligibility"]],
        "required_documents": [_short(x) for x in row["required_documents"]],
        "conditions": _short(row["conditions"]),
        "our_application_fee": money_text(effective_fee(row["fee_override_poisha"], fee_default)),
        "success_rate": success_rate(row),
    }


_SECTION = {
    "study": "Student Consultancy",
    "job": "Job Processing",
    "visa": "Immigration Processing",
    "remote": "Remote Jobs (work from home, no visa or travel)",
}
_ITEMS_KEY = {"study": "universities", "job": "jobs", "visa": "visa_programmes", "remote": "remote_jobs"}


def _rows(conn: Connection, module: AgentModule) -> list[Any]:
    if module == "study":
        return public_universities(conn)
    if module == "visa":
        return public_visa_programs(conn)
    if module == "remote":
        return public_remote_jobs(conn)
    return public_vacancies(conn)


def _searchable(module: AgentModule, row: Any) -> str:
    if module == "study":
        parts = [row["name"], row["country"], row["city"], *row["levels"], *row["fields"]]
    elif module == "visa":
        parts = [row["title"], row["country"], row["visa_type"], VISA_TYPES.get(row["visa_type"], "")]
    else:
        parts = [row["title"], row["employer"], row["country"], row["occupation"]]
    return " ".join(str(p) for p in parts).lower()


def _company(conn: Connection) -> dict[str, str]:
    row = conn.execute(
        text("SELECT name, phone, email, address, hours, website FROM settings WHERE singleton = 'settings'")
    ).mappings().one()
    return {k: str(v) for k, v in row.items() if v}


def build_facts(
    conn: Connection,
    module: AgentModule,
    question: str,
    inputs: dict[str, Any] | None,
    applicant: RowMapping | None = None,
) -> dict[str, Any]:
    fee_default = default_fees(conn)[module]
    rows = _rows(conn, module)
    by_id = {r["id"]: r for r in rows}

    chosen: list[Any] = []
    percent: dict[Any, int] = {}
    for m in _agent_matches(conn, module, inputs):
        rid = m["item"]["id"]
        for r in rows:
            if str(r["id"]) == rid:
                chosen.append(r["id"])
                percent[r["id"]] = m["match_percent"]
    words = _words(question)
    if words:
        for r in rows:
            haystack = _searchable(module, r)
            if r["id"] not in chosen and any(w in haystack for w in words):
                chosen.append(r["id"])
    specific = bool(chosen)
    if not chosen:
        # No match for the form or the question: a short overview of what is offered.
        chosen = [r["id"] for r in rows]
    make = {"study": _university_fact, "job": _vacancy_fact, "visa": _visa_fact, "remote": _vacancy_fact}[module]
    items = []
    for rid in chosen[:MAX_ROWS]:
        fact = make(by_id[rid], fee_default)
        if rid in percent:
            fact["match_percent_for_this_applicant"] = percent[rid]
        items.append(fact)

    facts: dict[str, Any] = {
        "section": _SECTION[module],
        "company": _company(conn),
        "default_application_fee": money_text(fee_default),
        "process_stages": list(STAGES[module]),
        "required_documents": list(DOCUMENT_TYPES[module]),
        "countries_offered": sorted({str(r["country"]) for r in rows}),
        "total_published": len(rows),
        "items_match_the_question": specific,
        "items_key": _ITEMS_KEY[module],
        _ITEMS_KEY[module]: items,
    }
    # B25 applicant mode: the signed-in applicant's own cases in this module (only theirs).
    if applicant is not None:
        facts["asker_is_signed_in_applicant"] = True
        facts["my_cases"] = my_cases(conn, applicant, module)
    return facts
