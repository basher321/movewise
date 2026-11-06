"""Checks that an AI answer keeps to the database facts (spec B17).

Every number in the answer (fees, salaries, tuition, GPA, IELTS, dates, seats, percentages, phone
numbers) must also be in the facts, the visitor's form inputs or the question. An answer with a
number from anywhere else is not used: the next provider is tried, and in the end the rule-based
reply (which is built only from the database) answers.
"""

import re

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Phone-like runs of digits with spaces, dashes or dots between them.
_PHONE = re.compile(r"\+?\d[\d\s().-]{5,}\d")
# "1. " or "2) " at the start of a line: list numbering, not a fact.
_LIST_MARK = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")
# A long number may be a part of a phone number written another way.
_PHONE_PART_MIN = 5


def _canonical(raw: str) -> str:
    value = raw.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {_canonical(m) for m in _NUMBER.findall(text)}


def _phones_in(text: str) -> list[str]:
    return [re.sub(r"\D", "", m) for m in _PHONE.findall(text)]


def is_grounded(answer: str, source: str) -> bool:
    """True when every number in the answer is found in the source text (facts, inputs, question)."""
    known = numbers_in(source)
    phones = _phones_in(source)
    for raw in _NUMBER.findall(_LIST_MARK.sub("", answer)):
        value = _canonical(raw)
        if value in known:
            continue
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= _PHONE_PART_MIN and any(digits in p for p in phones):
            continue
        return False
    return True
