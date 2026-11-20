"""Country rules of the CV Agent (spec B28 section 4), read from backend/config/countries/*.yaml.

The files are the only place the rules live: the code reads them, never hard-codes them.
A country without its own file uses default.yaml; the Europass CV type uses europass.yaml.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from app.config import BACKEND_DIR

RULES_DIR = BACKEND_DIR / "config" / "countries"
Permission = Literal["never", "optional", "common"]
SENSITIVE = ("nationality", "date_of_birth", "gender", "marital_status", "religion")
SECTIONS = ("summary", "experience", "education", "skills", "languages", "certifications", "training",
            "achievements", "references", "custom")
# Without work history these CV types do not need an experience section.
NO_EXPERIENCE_TYPES = ("student", "graduate")
EU = ("Germany", "France", "Italy", "Sweden", "Switzerland", "Finland", "Netherlands", "Denmark", "Ireland")


class CountryRules(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    country: str
    document_name: str
    spelling: Literal["en-US", "en-GB"]
    page_length_default: Literal[1, 2]
    photo: Permission
    date_of_birth: Permission
    marital_status: Permission
    nationality: Permission
    gender: Permission
    religion: Permission
    required_sections: tuple[str, ...]
    optional_sections: tuple[str, ...]
    section_order: tuple[str, ...]
    date_format: Literal["MMM YYYY", "MM/YYYY"]
    notes: str

    @field_validator("required_sections", "optional_sections", "section_order")
    @classmethod
    def _known(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [s for s in v if s not in SECTIONS]
        if unknown:
            raise ValueError(f"unknown sections {unknown}")
        return v

    def allows(self, field: str) -> bool:
        """A sensitive personal field may be shown (when the person also turns it on)."""
        return getattr(self, field, "never") != "never"

    def required_for(self, cv_type: str | None, category: str | None) -> tuple[str, ...]:
        if cv_type in NO_EXPERIENCE_TYPES or category == "student_admission":
            return tuple(s for s in self.required_sections if s != "experience")
        return self.required_sections

    @property
    def language_name(self) -> str:
        return "US English" if self.spelling == "en-US" else "British English"


@lru_cache(maxsize=1)
def _all_rules() -> dict[str, CountryRules]:
    rules: dict[str, CountryRules] = {}
    for path in sorted(Path(RULES_DIR).glob("*.yaml")):
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule = CountryRules.model_validate(data)
        rules[path.stem] = rule
    if "default" not in rules or "europass" not in rules:
        raise RuntimeError("CV country rules are missing default.yaml or europass.yaml")
    return rules


def rules_for(country: str | None, cv_type: str | None = None) -> CountryRules:
    rules = _all_rules()
    if cv_type == "europass":
        return rules["europass"]
    for rule in rules.values():
        if country and rule.country == country:
            return rule
    return rules["default"]


def all_country_rules() -> list[CountryRules]:
    return [r for key, r in _all_rules().items() if key not in ("default", "europass")]


def recommended_template(country: str | None, cv_type: str | None, category: str | None) -> str:
    if cv_type == "europass":
        return "europass"
    if cv_type == "academic" or category == "research":
        return "academic"
    if cv_type in ("overseas", "immigration"):
        return "europass" if country in EU else "international"
    if category == "it":
        return "technical"
    if cv_type in ("student", "graduate"):
        return "minimalist"
    if country in ("UK", "Ireland", "Australia", "New Zealand", "Malaysia", "Singapore"):
        return "corporate"
    return "modern"
