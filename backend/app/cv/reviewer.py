"""Reviewer (spec B28 section 6): quality checks with severity blocking / warning.

Code checks (always, free): page length, required sections, "Please confirm" items, sensitive
data the country does not allow, passport numbers, contact details, date problems (end before
start, overlaps, gaps over 6 months), date style, duplicates, weak or long bullets.
AI check (when asked): spelling and grammar, as warnings.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from app.cv.ai_client import Caller, ask_json, prompt
from app.cv.countries import SENSITIVE, CountryRules
from app.cv.layout import build
from app.cv.merger import norm
from app.cv.schema import CvData, Experience, label_of, needs_confirming

Severity = Literal["blocking", "warning"]
WEAK_STARTS = {"i", "my", "me", "responsible", "duties", "duty", "was", "were", "worked", "helped", "tasks", "involved"}
PASSPORT_RE = re.compile(r"\bpassport\b[^.\n]{0,25}\b[A-Z]{1,2}\d{6,8}\b|\b[A-Z]{2}\d{7}\b", re.I)
MAX_BULLET_WORDS = 30
SECTION_LABELS = {
    "summary": "Professional summary", "experience": "Work experience", "education": "Education", "skills": "Skills",
    "languages": "Languages", "certifications": "Certifications", "training": "Training",
    "achievements": "Achievements", "references": "References", "custom": "Other",
}


class Issue(BaseModel):
    severity: Severity
    section: str
    message: str
    item_id: str = ""


def _months(value: str) -> int | None:
    if not value:
        return None
    year, _, month = value.partition("-")
    return int(year) * 12 + (int(month) if month else 1)


def _date_issues(jobs: list[Experience]) -> list[Issue]:
    out: list[Issue] = []
    spans = []
    for x in jobs:
        start, end = _months(x.start_date), _months(x.end_date)
        if start and end and end < start:
            out.append(Issue(severity="blocking", section="experience", item_id=x.id,
                             message=f"{label_of(x)}: the end date is before the start date."))
        if start:
            spans.append((start, end if end else (10**6 if x.current else start), x))
    spans.sort(key=lambda s: s[0])
    for (a_start, a_end, a), (b_start, b_end, b) in zip(spans, spans[1:]):
        if b_start < a_end and a_end != 10**6:
            out.append(Issue(severity="warning", section="experience", item_id=b.id,
                             message=f"{label_of(a)} and {label_of(b)} overlap. That is fine for part-time work; otherwise check the dates."))
        elif b_start - a_end > 6 and a_end != 10**6:
            out.append(Issue(severity="warning", section="experience", item_id=b.id,
                             message=f"There is a gap of {b_start - a_end} months before {label_of(b)}. Employers may ask about it."))
    return out


def check(data: CvData, rules: CountryRules, template: str, page_length: int, pages: int, cv_type: str | None,
          category: str | None) -> list[Issue]:
    out: list[Issue] = []
    p = data.personal
    if not p.full_name:
        out.append(Issue(severity="blocking", section="personal", message="Your full name is missing."))
    if not p.email and not p.phone:
        out.append(Issue(severity="blocking", section="personal", message="Add at least an email address or a phone number."))
    if pages > page_length:
        out.append(Issue(severity="blocking", section="layout",
                         message=f"The CV is {pages} pages but you chose {page_length}. Use \"Make shorter\" or remove a section."))
    present = {s.key for s in build(data, rules, template).sections}
    for key in rules.required_for(cv_type, category):
        if key not in present:
            out.append(Issue(severity="blocking", section=key,
                             message=f"{SECTION_LABELS[key]} is required for {rules.country if rules.country != 'Other' else 'this'} CV."))
    for label in needs_confirming(data):
        out.append(Issue(severity="blocking", section="confirm", message=f"Please confirm: {label}."))
    for field in SENSITIVE:
        if field in p.show and getattr(p, field) and not rules.allows(field):
            out.append(Issue(severity="blocking", section="personal",
                             message=f"{field.replace('_', ' ').capitalize()} should not be on a CV for {rules.country}. Turn it off."))
    texts = [data.professional_summary] + [b for x in data.experience for b in x.bullets] + [c for s in data.custom_sections for c in s.items]
    if any(PASSPORT_RE.search(t) for t in texts if t):
        out.append(Issue(severity="blocking", section="personal", message="A passport number must never appear on a CV. Remove it."))
    out += _date_issues(data.experience)
    dated = [d for x in data.experience + data.education for d in (x.start_date, x.end_date) if d]  # type: ignore[operator]
    if dated and any("-" in d for d in dated) and any("-" not in d for d in dated):
        out.append(Issue(severity="warning", section="dates", message="Some dates have a month and some only a year. Use the same style everywhere."))
    seen: dict[str, str] = {}
    for x in data.experience:
        for b in x.bullets:
            key = norm(b)
            if key in seen and seen[key] != x.id:
                out.append(Issue(severity="warning", section="experience", item_id=x.id, message=f"The same bullet appears twice: \"{b[:60]}\"."))
            seen.setdefault(key, x.id)
            words = b.split()
            if words and words[0].lower().strip(",.:") in WEAK_STARTS:
                out.append(Issue(severity="warning", section="experience", item_id=x.id,
                                 message=f"Start with an action verb: \"{b[:60]}\"."))
            if len(words) > MAX_BULLET_WORDS:
                out.append(Issue(severity="warning", section="experience", item_id=x.id,
                                 message=f"This bullet is long ({len(words)} words). Keep bullets under {MAX_BULLET_WORDS} words."))
    return out


class SpellIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    section: str = ""
    text: str = ""
    suggestion: str = ""


class SpellOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    issues: list[SpellIssue] = Field(default_factory=list)


def spelling(conn: Connection, caller: Caller, data: CvData, rules: CountryRules, template: str) -> list[Issue]:
    layout = build(data, rules, template)
    body = "\n".join(
        f"[{s.title}] " + (s.text or " ".join(
            [e.title + ". " + " ".join(e.bullets) for e in s.entries] + list(s.lines)))
        for s in layout.sections
    )
    system = prompt("reviewer").replace("{{language}}", rules.language_name)
    out = ask_json(conn, caller, "reviewer", system, f"CV TEXT:\n{body[:12000]}", SpellOut)
    issues = []
    for i in out.issues[:15]:
        if i.text and i.suggestion and i.text.strip() != i.suggestion.strip():
            issues.append(Issue(severity="warning", section="spelling",
                                message=f"\"{i.text[:80]}\" → \"{i.suggestion[:80]}\""))
    return issues


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "blocking"]
