"""The CV document (spec B28 section 5), stored as JSON in cv_versions.data.

Every list item carries an id (stable across versions), the file it came from, how sure the AI
was, and a "confirm" flag: items the AI was unsure about, or that conflict between documents,
must be confirmed by the person before the CV can be approved. Dates are "YYYY-MM" or "YYYY".
"""

import re
import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Confidence = Literal["high", "medium", "low"]
DATE_RE = re.compile(r"^(19|20)\d{2}(-(0[1-9]|1[0-2]))?$")
SHORT = 200
LONG = 1200


def new_id() -> str:
    return secrets.token_hex(4)


# Characters AIs like to write that the CV fonts do not have: non-breaking hyphens and spaces etc.
_PLAIN = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-", "\u00a0": " ", "\u202f": " ",
                        "\u2007": " ", "\u200b": "", "\u00ad": ""})


def clean(value: str, limit: int = SHORT) -> str:
    return " ".join(str(value).translate(_PLAIN).split())[:limit]


def clean_date(value: str) -> str:
    """A date as YYYY-MM or YYYY; anything else becomes "" (the gap form then asks for it)."""
    value = (value or "").strip()
    match = re.match(r"^((?:19|20)\d{2})[-/.](\d{1,2})", value)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return value if DATE_RE.fullmatch(value) else ""


class Item(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id, max_length=16)
    source_file: str = Field(default="", max_length=SHORT)
    confidence: Confidence = "high"
    confirm: bool = False
    # Why the item needs confirming, e.g. "Different dates in cv.pdf and letter.pdf".
    note: str = Field(default="", max_length=400)

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, v: object) -> str:
        value = str(v or "").strip().lower()
        return value if value in ("high", "medium", "low") else "medium"

    @field_validator("note", "source_file", mode="before")
    @classmethod
    def _cut(cls, v: object) -> str:
        return str(v or "")[:200]


def _text_list(values: list[str], limit: int = LONG, most: int = 12) -> list[str]:
    out = [clean(v, limit) for v in values if isinstance(v, str) and clean(v, limit)]
    return out[:most]


class Experience(Item):
    job_title: str = ""
    employer: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    current: bool = False
    bullets: list[str] = Field(default_factory=list)

    @field_validator("job_title", "employer", "location")
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v)

    @field_validator("start_date", "end_date")
    @classmethod
    def _date(cls, v: str) -> str:
        return clean_date(v)

    @field_validator("bullets")
    @classmethod
    def _bullets(cls, v: list[str]) -> list[str]:
        return _text_list(v, 400)


class Education(Item):
    degree: str = ""
    field: str = ""
    institution: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    details: list[str] = Field(default_factory=list)

    @field_validator("degree", "field", "institution", "location", "grade")
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v)

    @field_validator("start_date", "end_date")
    @classmethod
    def _date(cls, v: str) -> str:
        return clean_date(v)

    @field_validator("details")
    @classmethod
    def _details(cls, v: list[str]) -> list[str]:
        return _text_list(v, 300, 6)


class Language(Item):
    language: str = ""
    level: str = ""
    test_score: str = ""

    @field_validator("language", "level", "test_score")
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v, 100)


class Certification(Item):
    name: str = ""
    issuer: str = ""
    date: str = ""
    expiry: str = ""

    @field_validator("name", "issuer")
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v)

    @field_validator("date", "expiry")
    @classmethod
    def _date(cls, v: str) -> str:
        return clean_date(v)


class Training(Item):
    name: str = ""
    provider: str = ""
    date: str = ""
    details: str = ""

    @field_validator("name", "provider")
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v)

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        return clean_date(v)

    @field_validator("details")
    @classmethod
    def _details(cls, v: str) -> str:
        return clean(v, 300)


class Achievement(Item):
    text: str = ""

    @field_validator("text")
    @classmethod
    def _text(cls, v: str) -> str:
        return clean(v, 400)


class Reference(Item):
    name: str = ""
    title: str = ""
    organisation: str = ""
    contact: str = ""

    @field_validator("name", "title", "organisation", "contact")
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v)


class CustomSection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id, max_length=16)
    title: str = ""
    items: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return clean(v, 80)

    @field_validator("items")
    @classmethod
    def _items(cls, v: list[str]) -> list[str]:
        return _text_list(v, 400, 10)


class Personal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    country: str = ""
    linkedin: str = ""
    website: str = ""
    # Sensitive: shown only when the country allows it AND the person turns it on (show).
    nationality: str = ""
    date_of_birth: str = ""
    gender: str = ""
    marital_status: str = ""
    religion: str = ""
    show: list[Literal["nationality", "date_of_birth", "gender", "marital_status", "religion"]] = Field(default_factory=list)
    # Where each field came from, and fields that need confirming.
    sources: dict[str, str] = Field(default_factory=dict)
    confirm_fields: list[str] = Field(default_factory=list)

    @field_validator(
        "full_name", "email", "phone", "city", "country", "linkedin", "website", "nationality",
        "date_of_birth", "gender", "marital_status", "religion",
    )
    @classmethod
    def _short(cls, v: str) -> str:
        return clean(v)


class Skills(BaseModel):
    model_config = ConfigDict(extra="ignore")
    technical: list[str] = Field(default_factory=list)
    soft: list[str] = Field(default_factory=list)

    @field_validator("technical", "soft")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for s in v:
            if isinstance(s, str) and clean(s, 60):
                seen.setdefault(clean(s, 60).lower(), clean(s, 60))
        return list(seen.values())[:30]


SECTIONS = (
    "summary", "experience", "education", "skills", "languages", "certifications", "training",
    "achievements", "references", "custom",
)


class CvData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    personal: Personal = Field(default_factory=Personal)
    professional_summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    languages: list[Language] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    training: list[Training] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    references_on_request: bool = True
    custom_sections: list[CustomSection] = Field(default_factory=list)
    # Sections the person removed from the CV (the data stays, so "Remove" can be undone).
    hidden_sections: list[str] = Field(default_factory=list)
    # Optional questions the person left blank: not asked again, and that part stays off the CV.
    skipped_questions: list[str] = Field(default_factory=list)

    @field_validator("professional_summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        return clean(v, LONG)

    @field_validator("hidden_sections")
    @classmethod
    def _hidden(cls, v: list[str]) -> list[str]:
        return [s for s in dict.fromkeys(v) if s in SECTIONS]

    @field_validator("skipped_questions")
    @classmethod
    def _skipped(cls, v: list[str]) -> list[str]:
        return [k[:80] for k in dict.fromkeys(v) if isinstance(k, str)][:200]


LIST_SECTIONS: dict[str, type[Item]] = {
    "experience": Experience,
    "education": Education,
    "languages": Language,
    "certifications": Certification,
    "training": Training,
    "achievements": Achievement,
    "references": Reference,
}


def sort_key(item: Experience | Education) -> str:
    """Reverse-chronological order: current first, then by end date, then start date."""
    end = "9999-99" if getattr(item, "current", False) else (item.end_date or item.start_date or "0000")
    return f"{end}|{item.start_date}"


def ordered(data: CvData) -> CvData:
    data.experience.sort(key=sort_key, reverse=True)
    data.education.sort(key=sort_key, reverse=True)
    return data


def needs_confirming(data: CvData) -> list[str]:
    """Human labels of everything still marked "Please confirm"."""
    out = [f"Personal: {f.replace('_', ' ')}" for f in data.personal.confirm_fields]
    for section in LIST_SECTIONS:
        for item in getattr(data, section):
            if item.confirm:
                out.append(f"{section.title()}: {label_of(item)}")
    return out


def label_of(item: Item) -> str:
    for field in ("job_title", "degree", "language", "name", "text"):
        value = getattr(item, field, "")
        if value:
            extra = getattr(item, "employer", "") or getattr(item, "institution", "")
            return f"{value} ({extra})" if extra else str(value)
    return "item"
