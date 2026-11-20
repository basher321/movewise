"""Cover Letter Writer (spec B28 section 3.6): one page, tailored to the country and job advert.

Same rules and grounding as the Writer: a sentence with a number that is not in the person's
data, or a promise of a job or visa, is dropped.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection

from app.cv.ai_client import Caller, ask_json, prompt
from app.cv.countries import CountryRules
from app.cv.schema import CvData, clean
from app.cv.writer import _context, _fill, _user, allowed_numbers, grounded

MAX_WORDS = 360


class LetterOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    greeting: str = ""
    paragraphs: list[str] = Field(default_factory=list)
    closing: str = ""


def _clean_paragraph(text: str, allowed: set[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", clean(text, 2000))
    return " ".join(s for s in sentences if s and grounded(s, allowed))


def write_letter(conn: Connection, caller: Caller, project: Any, facts: CvData, rules: CountryRules) -> str:
    out = ask_json(conn, caller, "cover_letter", _fill(prompt("cover_letter"), _context(project, rules)),
                   _user(facts, project), LetterOut)
    allowed = allowed_numbers(facts)
    paragraphs = [p for p in (_clean_paragraph(x, allowed) for x in out.paragraphs[:5]) if p]
    words, kept = 0, []
    for p in paragraphs:
        words += len(p.split())
        if words > MAX_WORDS and kept:
            break
        kept.append(p)
    greeting = clean(out.greeting, 120) or "Dear Hiring Manager,"
    closing = clean(out.closing, 120) or ("Sincerely," if rules.spelling == "en-US" else "Yours faithfully,")
    name = facts.personal.full_name
    return "\n\n".join([greeting, *kept, f"{closing}\n{name}".strip()])
