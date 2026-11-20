"""The finished CV as neutral blocks (spec B28): header, then sections in the country's order.

render_pdf and render_docx both draw from these blocks, and the preview is the PDF itself, so
preview, PDF and DOCX always carry the same content. Sensitive personal fields appear only when
the country allows them AND the person turned them on; a passport number is never in the data.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.cv.countries import SENSITIVE, CountryRules
from app.cv.schema import CvData, Experience

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TEMPLATE_FONT = {
    "modern": "carlito", "corporate": "carlito", "minimalist": "carlito", "technical": "carlito",
    "academic": "tinos", "europass": "carlito", "international": "tinos",
}


@dataclass
class Entry:
    title: str
    subtitle: str = ""
    dates: str = ""
    bullets: list[str] = field(default_factory=list)


@dataclass
class Section:
    key: str
    title: str
    kind: Literal["paragraph", "entries", "lines"]
    text: str = ""
    entries: list[Entry] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


@dataclass
class CvLayout:
    template: str
    font: str
    name: str
    contact: str
    details: str
    sections: list[Section]
    language: str


def fmt_date(value: str, style: str) -> str:
    if not value:
        return ""
    year, _, month = value.partition("-")
    if not month:
        return year
    return f"{MONTHS[int(month) - 1]} {year}" if style == "MMM YYYY" else f"{month}/{year}"


def date_range(start: str, end: str, current: bool, style: str) -> str:
    a, b = fmt_date(start, style), "Present" if current else fmt_date(end, style)
    if a and b:
        return f"{a} – {b}"
    return a or b


def titles(template: str, rules: CountryRules) -> dict[str, str]:
    us = rules.spelling == "en-US"
    base = {
        "summary": "Professional Summary", "experience": "Work Experience", "education": "Education",
        "skills": "Skills", "languages": "Languages", "certifications": "Certifications and Licenses" if us else "Certifications and Licences",
        "training": "Training", "achievements": "Achievements", "references": "References",
    }
    if template == "europass" or rules.country == "Europass":
        base.update({"summary": "About Me", "education": "Education and Training", "languages": "Language Skills",
                     "skills": "Digital and Other Skills"})
    if template == "academic":
        base.update({"summary": "Profile", "achievements": "Awards and Publications"})
    if template == "technical":
        base.update({"skills": "Technical Skills"})
    return base


def _order(template: str, rules: CountryRules) -> list[str]:
    order = list(rules.section_order)
    if template == "academic" and "education" in order:
        order.remove("education")
        order.insert(1, "education")
    if template == "technical" and "skills" in order:
        order.remove("skills")
        order.insert(1, "skills")
    return order


def _personal_details(data: CvData, rules: CountryRules) -> str:
    labels = {"nationality": "Nationality", "date_of_birth": "Date of birth", "gender": "Gender",
              "marital_status": "Marital status", "religion": "Religion"}
    parts = []
    for name in SENSITIVE:
        value = getattr(data.personal, name)
        if value and name in data.personal.show and rules.allows(name):
            parts.append(f"{labels[name]}: {value}")
    return " | ".join(parts)


def _job(x: Experience, style: str) -> Entry:
    title = " – ".join(p for p in (x.job_title, x.employer) if p)
    return Entry(title=title, subtitle=x.location, dates=date_range(x.start_date, x.end_date, x.current, style),
                 bullets=list(x.bullets))


def build(data: CvData, rules: CountryRules, template: str) -> CvLayout:
    style = rules.date_format
    t = titles(template, rules)
    hidden = set(data.hidden_sections)
    sections: list[Section] = []
    for key in _order(template, rules):
        if key in hidden:
            continue
        if key == "summary" and data.professional_summary:
            sections.append(Section(key, t["summary"], "paragraph", text=data.professional_summary))
        elif key == "experience" and data.experience:
            sections.append(Section(key, t["experience"], "entries", entries=[_job(x, style) for x in data.experience]))
        elif key == "education" and data.education:
            entries = []
            for e in data.education:
                head = e.degree + (f" in {e.field}" if e.field and e.field.lower() not in e.degree.lower() else "")
                sub = ", ".join(p for p in (e.institution, e.location) if p)
                bullets = ([f"Result: {e.grade}"] if e.grade else []) + list(e.details)
                entries.append(Entry(title=head or e.institution, subtitle=sub if head else e.location,
                                     dates=date_range(e.start_date, e.end_date, False, style), bullets=bullets))
            sections.append(Section(key, t["education"], "entries", entries=entries))
        elif key == "skills" and (data.skills.technical or data.skills.soft):
            lines = []
            if data.skills.technical:
                lines.append(("Technical: " if data.skills.soft else "") + ", ".join(data.skills.technical))
            if data.skills.soft:
                lines.append(("Personal: " if data.skills.technical else "") + ", ".join(data.skills.soft))
            sections.append(Section(key, t["skills"], "lines", lines=lines))
        elif key == "languages" and data.languages:
            lines = [" – ".join(p for p in (l.language, l.level, l.test_score) if p) for l in data.languages if l.language]
            sections.append(Section(key, t["languages"], "lines", lines=lines))
        elif key == "certifications" and data.certifications:
            lines = []
            for c in data.certifications:
                extra = ", ".join(p for p in (c.issuer, fmt_date(c.date, style)) if p)
                lines.append(c.name + (f" ({extra})" if extra else ""))
            sections.append(Section(key, t["certifications"], "lines", lines=lines))
        elif key == "training" and data.training:
            lines = []
            for tr in data.training:
                extra = ", ".join(p for p in (tr.provider, fmt_date(tr.date, style)) if p)
                lines.append(tr.name + (f" ({extra})" if extra else ""))
            sections.append(Section(key, t["training"], "lines", lines=lines))
        elif key == "achievements" and data.achievements:
            sections.append(Section(key, t["achievements"], "lines", lines=[a.text for a in data.achievements if a.text]))
        elif key == "references":
            if data.references and not data.references_on_request:
                lines = [", ".join(p for p in (r.name, r.title, r.organisation, r.contact) if p) for r in data.references]
                sections.append(Section(key, t["references"], "lines", lines=lines))
            elif data.references_on_request:
                sections.append(Section(key, t["references"], "paragraph", text="Available on request."))
        elif key == "custom":
            for c in data.custom_sections:
                if c.title and c.items:
                    sections.append(Section("custom", c.title, "lines", lines=list(c.items)))
    p = data.personal
    place = ", ".join(x for x in (p.city, p.country) if x)
    contact = " | ".join(x for x in (place, p.phone, p.email, p.linkedin, p.website) if x)
    return CvLayout(template=template, font=TEMPLATE_FONT.get(template, "carlito"), name=p.full_name, contact=contact,
                    details=_personal_details(data, rules), sections=sections, language=rules.spelling)
