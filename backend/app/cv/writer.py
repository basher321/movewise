"""Writer (spec B28 section 3.4) and the section actions (Regenerate, Make shorter / stronger).

The AI only writes wording: the summary, the bullets of each job and the order of skills.
Employers, schools, job titles, dates and grades are always copied from the confirmed data by
the code. After the AI the code checks (grounding):
- every number in a summary or bullet must already be in the person's own data;
- every skill must be one of the person's own skills;
- no sentence may promise a job, visa or admission.
A bullet that fails keeps the person's original wording; a failing summary sentence is dropped.
Finally the CV is shortened, step by step, until it fits the chosen number of pages.
"""

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from app.cv.ai_client import Caller, ask_json, prompt
from app.cv.countries import CountryRules
from app.cv.layout import build
from app.cv.render_pdf import cv_pdf
from app.cv.schema import CvData, clean

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
PROMISE_RE = re.compile(r"\bguarantee|\bassured? (?:of )?(?:a )?(?:job|visa|admission|approval)|100\s?% success", re.I)
CV_TYPE_LABELS = {
    "new": "new", "update": "updated", "overseas": "overseas job", "immigration": "skilled migration",
    "student": "student (study application)", "graduate": "fresh graduate", "professional": "experienced professional",
    "academic": "academic", "europass": "Europass",
}
SectionAction = Literal["regenerate", "shorter", "stronger"]


class JobBullets(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = ""
    bullets: list[str] = Field(default_factory=list)


class WriterOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    professional_summary: str = ""
    experience: list[JobBullets] = Field(default_factory=list)
    skills_technical: list[str] = Field(default_factory=list)
    skills_soft: list[str] = Field(default_factory=list)
    ask_for: list[str] = Field(default_factory=list)


class SectionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    professional_summary: str = ""
    experience: list[JobBullets] = Field(default_factory=list)


# ---------------------------------------------------------------- grounding


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER_RE.findall(text)}


_NOT_FACTS = {"id", "source_file", "note", "confidence", "confirm", "sources", "confirm_fields", "show", "hidden_sections"}


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in _NOT_FACTS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def allowed_numbers(facts: CvData) -> set[str]:
    """Numbers written in the person's own data (not ids, file names or notes)."""
    return _numbers(json.dumps(_strip(facts.model_dump()), ensure_ascii=False))


def grounded(text: str, allowed: set[str]) -> bool:
    return _numbers(text) <= allowed and not PROMISE_RE.search(text)


def _grounded_summary(summary: str, allowed: set[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", clean(summary, 1200))
    return " ".join(s for s in sentences if s and grounded(s, allowed))


def _own(values: list[str], mine: list[str]) -> list[str]:
    """Only the person's own skills (case-insensitive), in the AI's order, then the rest."""
    lookup = {m.lower(): m for m in mine}
    picked = [lookup[v.strip().lower()] for v in values if v.strip().lower() in lookup]
    return list(dict.fromkeys(picked))


# ---------------------------------------------------------------- prompts


def _facts_json(facts: CvData) -> str:
    """The data the AI may use: no sources, notes, sensitive fields or contact details."""
    data = facts.model_dump(exclude={"hidden_sections"})
    data["personal"] = {"city": facts.personal.city, "country": facts.personal.country}
    for section in ("experience", "education", "languages", "certifications", "training", "achievements", "references"):
        for item in data[section]:
            for key in ("source_file", "confidence", "confirm", "note"):
                item.pop(key, None)
    data.pop("references", None)
    return json.dumps(data, ensure_ascii=False)


def _fill(template: str, values: dict[str, Any]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def _context(project: Any, rules: CountryRules) -> dict[str, Any]:
    pages = int(project["page_length"])
    return {
        "document_name": rules.document_name,
        "cv_type": CV_TYPE_LABELS.get(project["cv_type"] or "new", "new"),
        "country": project["country"] or "an international employer",
        "language": rules.language_name,
        "category": (project["category"] or "general").replace("_", " "),
        "pages": pages,
        "notes": rules.notes,
        "max_bullets": 4 if pages == 1 else 6,
        "summary_words": 50 if pages == 1 else 80,
    }


def _user(facts: CvData, project: Any) -> str:
    advert = (project["job_advert_text"] or "").strip()
    out = f"CV DATA:\n{_facts_json(facts)}"
    if advert:
        out += f"\n\nJOB ADVERT (use only keywords that genuinely match the CV DATA):\n{advert[:6000]}"
    return out


# ---------------------------------------------------------------- writing


def _apply_bullets(data: CvData, facts: CvData, jobs: list[JobBullets], allowed: set[str], most: int) -> None:
    by_id = {j.id: j for j in jobs}
    originals = {x.id: x.bullets for x in facts.experience}
    for x in data.experience:
        new = by_id.get(x.id)
        if new is None:
            continue
        kept = [clean(b, 300) for b in new.bullets if clean(b, 300) and grounded(b, allowed)]
        if kept:
            x.bullets = kept[:most]
        else:
            x.bullets = list(originals.get(x.id, x.bullets))[:most]


def write(conn: Connection, caller: Caller, project: Any, facts: CvData, rules: CountryRules) -> tuple[CvData, list[str]]:
    """(written CV, questions asking for measurable results)."""
    ctx = _context(project, rules)
    out = ask_json(conn, caller, "writer", _fill(prompt("writer"), ctx), _user(facts, project), WriterOut)
    allowed = allowed_numbers(facts)
    data = facts.model_copy(deep=True)
    summary = _grounded_summary(out.professional_summary, allowed)
    if summary:
        data.professional_summary = summary
    _apply_bullets(data, facts, out.experience, allowed, ctx["max_bullets"])
    technical = _own(out.skills_technical, facts.skills.technical)
    data.skills.technical = technical + [s for s in facts.skills.technical if s not in technical]
    soft = _own(out.skills_soft, facts.skills.soft)
    data.skills.soft = soft + [s for s in facts.skills.soft if s not in soft]
    questions = [clean(q, 200) for q in out.ask_for if clean(q, 200)][:4]
    return data, questions


def rewrite_section(
    conn: Connection, caller: Caller, project: Any, rules: CountryRules, current: CvData, facts: CvData,
    section: str, action: SectionAction, item_id: str | None,
) -> CvData:
    """Regenerate / shorter / stronger for the summary or the work experience (one job or all)."""
    if section not in ("summary", "experience"):
        raise ValueError("only summary and experience")
    ctx = _context(project, rules)
    if section == "summary":
        task = {
            "regenerate": "Write a new professional_summary (2 to 4 sentences).",
            "shorter": "Make the professional_summary shorter: at most 2 sentences.",
            "stronger": "Make the professional_summary stronger and more specific, using only the CV DATA.",
        }[action]
        task += f" CURRENT SUMMARY: {current.professional_summary}"
    else:
        jobs = [x for x in current.experience if item_id in (None, x.id)]
        listing = json.dumps([{"id": x.id, "job_title": x.job_title, "employer": x.employer, "bullets": x.bullets} for x in jobs])
        task = {
            "regenerate": "Rewrite the bullets of these jobs from scratch (2 to {n} each).",
            "shorter": "Make these bullets shorter: fewer bullets (2 or 3 each) and fewer words.",
            "stronger": "Make these bullets stronger: clear action verbs and concrete duties, using only the CV DATA.",
        }[action].replace("{n}", str(ctx["max_bullets"]))
        task += f" JOBS (return the same ids): {listing}"
    out = ask_json(conn, caller, "writer", _fill(prompt("section"), {**ctx, "task": task}), _user(facts, project), SectionOut)
    allowed = allowed_numbers(facts)
    data = current.model_copy(deep=True)
    if section == "summary":
        summary = _grounded_summary(out.professional_summary, allowed)
        if summary:
            data.professional_summary = summary
    else:
        _apply_bullets(data, facts, out.experience, allowed, ctx["max_bullets"])
    return data


# ---------------------------------------------------------------- fitting the page length


def pages(data: CvData, rules: CountryRules, template: str) -> int:
    return cv_pdf(build(data, rules, template), "CV")[1]


def fit(data: CvData, rules: CountryRules, template: str, page_length: int) -> tuple[CvData, int]:
    """Shortens step by step until the CV fits: fewer bullets on older jobs, then on all jobs,
    shorter lists, then optional sections. Returns (data, pages)."""
    data = data.model_copy(deep=True)
    count = pages(data, rules, template)
    steps = [
        lambda d: [setattr(x, "bullets", x.bullets[:3]) for x in d.experience[2:]],
        lambda d: [setattr(x, "bullets", x.bullets[:4]) for x in d.experience],
        lambda d: setattr(d, "achievements", d.achievements[:3]),
        lambda d: setattr(d, "training", d.training[:3]),
        lambda d: [setattr(x, "bullets", x.bullets[:2]) for x in d.experience[1:]],
        lambda d: [setattr(e, "details", []) for e in d.education],
        lambda d: setattr(d, "professional_summary", " ".join(re.split(r"(?<=[.!?])\s+", d.professional_summary)[:2])),
        lambda d: d.hidden_sections.append("references") if "references" not in d.hidden_sections else None,
        lambda d: setattr(d, "experience", d.experience[:6]),
    ]
    for step in steps:
        if count <= page_length:
            break
        step(data)
        count = pages(data, rules, template)
    return data, count
