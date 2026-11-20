"""Merger (spec B28 section 3.2): combines what was read from every document.

Plain code, no AI, so it never picks silently: duplicates are joined, and when two documents
disagree (a different date, grade or name) the item is kept once and marked "Please confirm"
with both values in its note. The person decides on the Step 5 screen.
"""

import re
from typing import TypeVar

from app.cv.schema import (
    Certification,
    CvData,
    Education,
    Experience,
    Item,
    Language,
    Personal,
    ordered,
)

T = TypeVar("T", bound=Item)
PERSONAL_FIELDS = (
    "full_name", "email", "phone", "city", "country", "linkedin", "website", "nationality", "date_of_birth",
    "gender", "marital_status", "religion",
)


def norm(value: str) -> str:
    """Lower case, letters and digits only: "Dhaka University," == "dhaka university"."""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _same_text(a: str, b: str) -> bool:
    x, y = norm(a), norm(b)
    return bool(x) and bool(y) and (x == y or x in y or y in x)


def _flag(item: Item, field: str, mine: str, theirs: str, their_file: str) -> None:
    item.confirm = True
    where = f"{item.source_file or 'one document'} and {their_file or 'another document'}"
    text = f"Different {field.replace('_', ' ')} in {where}: \"{mine}\" or \"{theirs}\"."
    item.note = (item.note + " " + text).strip()[:400]


def _join_item(keep: T, other: T, compare: tuple[str, ...]) -> None:
    """Fill empty fields of keep from other; flag fields where both have different values."""
    for field in compare:
        mine, theirs = str(getattr(keep, field, "") or ""), str(getattr(other, field, "") or "")
        if not mine and theirs:
            setattr(keep, field, getattr(other, field))
        elif mine and theirs and norm(mine) != norm(theirs):
            _flag(keep, field, mine, theirs, other.source_file)
    for list_field in ("bullets", "details"):
        if hasattr(keep, list_field):
            merged = list(getattr(keep, list_field))
            seen = {norm(b) for b in merged}
            for b in getattr(other, list_field):
                if norm(b) not in seen:
                    merged.append(b)
                    seen.add(norm(b))
            setattr(keep, list_field, merged[:12])
    if isinstance(keep, Experience) and isinstance(other, Experience):
        keep.current = keep.current or other.current
    order = {"low": 0, "medium": 1, "high": 2}
    if order[other.confidence] < order[keep.confidence]:
        keep.confidence = other.confidence
    keep.confirm = keep.confirm or other.confirm
    if other.note and other.note not in keep.note:
        keep.note = (keep.note + " " + other.note).strip()[:400]


def _merge_list(lists: list[list[T]], same: "callable", compare: tuple[str, ...]) -> list[T]:  # type: ignore[valid-type]
    out: list[T] = []
    for items in lists:
        for item in items:
            match = next((kept for kept in out if same(kept, item)), None)
            if match is None:
                out.append(item.model_copy(deep=True))
            else:
                _join_item(match, item, compare)
    return out


def _same_job(a: Experience, b: Experience) -> bool:
    return _same_text(a.employer, b.employer) and (_same_text(a.job_title, b.job_title) or not a.job_title or not b.job_title)


def _same_study(a: Education, b: Education) -> bool:
    return _same_text(a.institution, b.institution) and (_same_text(a.degree, b.degree) or not a.degree or not b.degree)


def _same_language(a: Language, b: Language) -> bool:
    return norm(a.language) == norm(b.language) and bool(norm(a.language))


def _same_name(a: Certification, b: Certification) -> bool:
    return _same_text(getattr(a, "name", ""), getattr(b, "name", ""))


def _merge_personal(people: list[Personal]) -> Personal:
    out = Personal()
    for person in people:
        for field in PERSONAL_FIELDS:
            mine, theirs = getattr(out, field), getattr(person, field)
            if not theirs:
                continue
            if not mine:
                setattr(out, field, theirs)
                if field in person.sources:
                    out.sources[field] = person.sources[field]
                if field in person.confirm_fields and field not in out.confirm_fields:
                    out.confirm_fields.append(field)
            elif norm(mine) != norm(theirs) and field not in out.confirm_fields:
                # Phone numbers and e-mail addresses may simply differ in spacing or case.
                if field in ("phone",) and re.sub(r"\D", "", mine)[-10:] == re.sub(r"\D", "", theirs)[-10:]:
                    continue
                out.confirm_fields.append(field)
    return out


def merge(parts: list[CvData]) -> CvData:
    if not parts:
        return CvData()
    merged = CvData(
        personal=_merge_personal([p.personal for p in parts]),
        professional_summary=next((p.professional_summary for p in parts if p.professional_summary), ""),
        experience=_merge_list([p.experience for p in parts], _same_job,
                               ("job_title", "employer", "location", "start_date", "end_date")),
        education=_merge_list([p.education for p in parts], _same_study,
                              ("degree", "field", "institution", "location", "start_date", "end_date", "grade")),
        languages=_merge_list([p.languages for p in parts], _same_language, ("level", "test_score")),
        certifications=_merge_list([p.certifications for p in parts], _same_name, ("issuer", "date", "expiry")),
        training=_merge_list([p.training for p in parts], _same_name, ("provider", "date")),
        achievements=_merge_list([p.achievements for p in parts], lambda a, b: norm(a.text) == norm(b.text), ()),
        references=_merge_list([p.references for p in parts], _same_name, ("title", "organisation", "contact")),
    )
    for part in parts:
        merged.skills.technical += part.skills.technical
        merged.skills.soft += part.skills.soft
    merged.skills = type(merged.skills).model_validate(merged.skills.model_dump())
    return ordered(merged)


def add_into(base: CvData, extra: CvData) -> CvData:
    """Merge newly read documents into data the person may already have edited."""
    return merge([base, extra])
