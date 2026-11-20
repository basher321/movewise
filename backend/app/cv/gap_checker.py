"""Gap Checker (spec B28 section 3.3): what is still missing for this CV type and country.

Plain code. Returns only the essentials, as small form fields (dropdowns, month pickers, chips
wherever possible); the screen shows at most 6 at a time. apply_answers() puts the answers into
the CV data. With no documents at all, the same questions build the CV from scratch.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.countries import WORLD_COUNTRIES
from app.cv.countries import CountryRules
from app.cv.schema import CvData, Education, Experience, Language, clean, clean_date

Kind = Literal["text", "email", "tel", "month", "select", "chips", "boolean", "url"]

DEGREES = ("SSC / O Level", "HSC / A Level", "Diploma", "Bachelor's degree", "Master's degree", "PhD", "Vocational certificate")
LEVELS = ("Native", "Fluent (C2)", "Advanced (C1)", "Upper intermediate (B2)", "Intermediate (B1)", "Basic (A2)")
LANGUAGES = ("English", "Bengali", "Hindi", "Urdu", "Arabic", "German", "French", "Italian", "Japanese", "Korean", "Malay", "Chinese")
SOFT_SKILLS = ("Teamwork", "Communication", "Problem solving", "Time management", "Adaptability", "Leadership",
               "Customer service", "Attention to detail", "Work ethic", "Reliability")
CATEGORY_SKILLS: dict[str, tuple[str, ...]] = {
    "skilled_worker": ("Health and safety", "Tool handling", "Blueprint reading", "Maintenance", "Quality control"),
    "it": ("Python", "JavaScript", "SQL", "Linux", "Git", "Networking", "Cloud services", "Technical support"),
    "healthcare": ("Patient care", "Vital signs monitoring", "Medication administration", "Infection control", "First aid / BLS"),
    "engineering": ("AutoCAD", "Project planning", "Technical drawing", "Site supervision", "Quality assurance"),
    "construction": ("Masonry", "Concrete work", "Scaffolding", "Reading drawings", "Site safety"),
    "hospitality": ("Food safety", "Guest service", "Housekeeping", "Food preparation", "POS systems"),
    "agriculture": ("Crop care", "Harvesting", "Machinery operation", "Livestock care", "Irrigation"),
    "manufacturing": ("Machine operation", "Assembly", "Quality inspection", "Packing", "5S / lean"),
    "driving": ("Defensive driving", "Route planning", "Vehicle checks", "Loading and unloading", "Logbooks"),
    "administration": ("MS Office", "Data entry", "Record keeping", "Scheduling", "Correspondence"),
    "business": ("Sales", "Market research", "Negotiation", "Reporting", "Customer relations"),
    "finance": ("Bookkeeping", "Excel", "Reconciliation", "Financial reporting", "Tally / accounting software"),
    "education": ("Lesson planning", "Classroom management", "Assessment", "Curriculum design", "E-learning tools"),
    "research": ("Research design", "Data analysis", "Academic writing", "Literature review", "Statistics"),
    "student_admission": ("MS Office", "Research", "Presentation", "Academic writing", "Data analysis"),
    "general": ("MS Office", "Customer service", "Data entry", "Cash handling", "Inventory"),
}


class Field_(BaseModel):
    key: str
    label: str
    kind: Kind
    section: str
    required: bool = True
    options: list[str] = Field(default_factory=list)
    value: Any = None
    hint: str = ""


def _f(key: str, label: str, kind: Kind, section: str, required: bool = True, options: tuple[str, ...] | list[str] = (),
       value: Any = None, hint: str = "") -> Field_:
    return Field_(key=key, label=label, kind=kind, section=section, required=required, options=list(options),
                  value=value, hint=hint)


def missing(data: CvData, rules: CountryRules, cv_type: str | None, category: str | None) -> list[Field_]:
    out: list[Field_] = []
    p = data.personal
    if not p.full_name:
        out.append(_f("personal.full_name", "Full name (as in your passport)", "text", "personal"))
    if not p.email:
        out.append(_f("personal.email", "Email address", "email", "personal"))
    if not p.phone:
        out.append(_f("personal.phone", "Mobile number with country code", "tel", "personal", hint="+8801XXXXXXXXX"))
    if not p.city:
        out.append(_f("personal.city", "City you live in now", "text", "personal"))
    if not p.country:
        out.append(_f("personal.country", "Country you live in now", "select", "personal", options=list(WORLD_COUNTRIES),
                      value="Bangladesh"))

    if not data.education:
        out += [
            _f("education.new.degree", "Your highest qualification", "select", "education", options=DEGREES),
            _f("education.new.field", "Subject / major", "text", "education"),
            _f("education.new.institution", "School, college or university", "text", "education"),
            _f("education.new.end_date", "Year and month you finished", "month", "education"),
            _f("education.new.grade", "Result / CGPA (optional)", "text", "education", required=False),
        ]
    for e in data.education:
        if e.institution and not e.end_date:
            out.append(_f(f"education.{e.id}.end_date", f"When did you finish at {e.institution}?", "month", "education"))

    needs_work = "experience" in rules.required_for(cv_type, category)
    if not data.experience and needs_work:
        out += [
            _f("experience.new.job_title", "Your latest job title", "text", "experience"),
            _f("experience.new.employer", "Employer (company name)", "text", "experience"),
            _f("experience.new.location", "City and country of that job", "text", "experience"),
            _f("experience.new.start_date", "Start month", "month", "experience"),
            _f("experience.new.current", "I still work there", "boolean", "experience", required=False, value=False),
            _f("experience.new.end_date", "End month (leave empty if you still work there)", "month", "experience", required=False),
            _f("experience.new.bullets", "Main duties (add one at a time)", "chips", "experience", required=False),
        ]
    for x in data.experience:
        if x.employer and not x.start_date:
            out.append(_f(f"experience.{x.id}.start_date", f"When did you start at {x.employer}?", "month", "experience"))
        if x.employer and not x.end_date and not x.current:
            out.append(_f(f"experience.{x.id}.end_date", f"When did you leave {x.employer}? (empty = still there)",
                          "month", "experience", required=False))

    if len(data.skills.technical) < 3:
        out.append(_f("skills.technical", "Your job skills (tap to choose, or add your own)", "chips", "skills",
                      options=CATEGORY_SKILLS.get(category or "general", CATEGORY_SKILLS["general"]),
                      value=list(data.skills.technical)))
    if len(data.skills.soft) < 2:
        out.append(_f("skills.soft", "Your personal strengths", "chips", "skills", required=False, options=SOFT_SKILLS,
                      value=list(data.skills.soft)))

    if not any(l.language.lower() == "english" for l in data.languages):
        out += [
            _f("languages.english.level", "Your English level", "select", "languages", options=LEVELS),
            _f("languages.english.test_score", "IELTS / TOEFL / PTE score (optional)", "text", "languages", required=False,
               hint="e.g. IELTS 6.5"),
        ]
    if not data.languages:
        out.append(_f("languages.mother.language", "Your mother tongue", "select", "languages", options=LANGUAGES,
                      value="Bengali"))
    return out


def blocking_missing(fields: list[Field_]) -> list[Field_]:
    return [f for f in fields if f.required]


def _text(value: Any, limit: int = 200) -> str:
    return clean(str(value), limit) if value is not None else ""


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(v, 300) for v in value if _text(v, 300)]
    if isinstance(value, str):
        return [_text(v, 300) for v in re.split(r"[\n;]", value) if _text(v, 300)]
    return []


def apply_answers(data: CvData, answers: dict[str, Any]) -> CvData:
    """Puts answers from the gap form into the data. Unknown keys are ignored."""
    new_edu: dict[str, Any] = {}
    new_job: dict[str, Any] = {}
    for key, value in answers.items():
        parts = key.split(".")
        if parts[0] == "personal" and len(parts) == 2 and parts[1] in Field_names_personal:
            setattr(data.personal, parts[1], _text(value))
            data.personal.sources[parts[1]] = "your answer"
            if parts[1] in data.personal.confirm_fields:
                data.personal.confirm_fields.remove(parts[1])
        elif parts[0] == "education" and len(parts) == 3:
            if parts[1] == "new":
                new_edu[parts[2]] = value
            else:
                for e in data.education:
                    if e.id == parts[1] and parts[2] in ("end_date", "start_date", "grade"):
                        setattr(e, parts[2], clean_date(str(value)) if "date" in parts[2] else _text(value))
        elif parts[0] == "experience" and len(parts) == 3:
            if parts[1] == "new":
                new_job[parts[2]] = value
            else:
                for x in data.experience:
                    if x.id == parts[1] and parts[2] in ("start_date", "end_date"):
                        setattr(x, parts[2], clean_date(str(value)))
                        if parts[2] == "end_date" and not value:
                            x.current = True
        elif key in ("skills.technical", "skills.soft"):
            setattr(data.skills, parts[1], _list(value))
        elif parts[0] == "languages" and len(parts) == 3:
            if parts[1] == "english":
                lang = next((l for l in data.languages if l.language.lower() == "english"), None)
                if lang is None:
                    lang = Language(language="English", source_file="your answer")
                    data.languages.append(lang)
                if parts[2] in ("level", "test_score"):
                    setattr(lang, parts[2], _text(value, 100))
            elif parts[1] == "mother" and parts[2] == "language" and _text(value, 100):
                if not any(l.language.lower() == _text(value, 100).lower() for l in data.languages):
                    data.languages.insert(0, Language(language=_text(value, 100), level="Native", source_file="your answer"))
    if any(_text(new_edu.get(k)) for k in ("degree", "institution")):
        data.education.append(Education(
            degree=_text(new_edu.get("degree")), field=_text(new_edu.get("field")),
            institution=_text(new_edu.get("institution")), end_date=clean_date(str(new_edu.get("end_date") or "")),
            grade=_text(new_edu.get("grade")), source_file="your answer"))
    if any(_text(new_job.get(k)) for k in ("job_title", "employer")):
        current = new_job.get("current") is True or (not new_job.get("end_date") and bool(new_job.get("start_date")))
        data.experience.append(Experience(
            job_title=_text(new_job.get("job_title")), employer=_text(new_job.get("employer")),
            location=_text(new_job.get("location")), start_date=clean_date(str(new_job.get("start_date") or "")),
            end_date="" if current else clean_date(str(new_job.get("end_date") or "")), current=current,
            bullets=_list(new_job.get("bullets")), source_file="your answer"))
    return data


Field_names_personal = ("full_name", "email", "phone", "city", "country", "linkedin", "website", "nationality",
                        "date_of_birth", "gender", "marital_status", "religion")
