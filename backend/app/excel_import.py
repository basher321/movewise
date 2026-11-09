"""Excel upload of listings (spec B23): universities, vacancies and visa programmes.

Every row goes through the same models and value functions as the admin forms, so a row accepted
here is exactly what the form would accept. An item that already exists is skipped, never changed.
The uploaded file is read in memory and never stored. Money is converted to whole poisha without
floats.
"""

import io
import math
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.audit import Actor, write_audit
from app.catalog import (
    EDUCATION_LEVELS,
    ENGLISH_LEVELS,
    VISA_TYPES,
    default_fees,
    invalid,
    lock_catalog,
    new_slug,
)
from app.errors import ApiError
from app.licence import Module
from app.routers.admin_catalog import (
    UniversityIn,
    VacancyIn,
    VisaProgramIn,
    _insert,
    _university_values,
    _vacancy_values,
    _verified_audit,
    _visa_program_values,
)

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1000
# The largest size a workbook may expand to: refuses a small file that unpacks into a huge one.
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_WHOLE_NUMBER = 1_000_000
MAX_FEE_POISHA = 100_000_000_000
TEMPLATE_ROWS = 1000
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

UNREADABLE = "This file could not be read."

CellKind = Literal["text", "whole", "number", "taka", "comma_list", "line_list", "yes_no", "date", "choice"]
Status = Literal["new", "skipped", "error"]


@dataclass(frozen=True)
class Column:
    header: str
    key: str
    kind: CellKind = "text"
    required: bool = False
    help: str = ""
    choices: tuple[tuple[str, Any], ...] = ()
    owner_only: bool = False

    @property
    def title(self) -> str:
        return f"{self.header}*" if self.required else self.header


@dataclass(frozen=True)
class KindSpec:
    kind: str
    module: Module
    table: Literal["universities", "vacancies", "visa_programs"]
    sheet: str
    columns: tuple[Column, ...]
    model: type[BaseModel]
    values: Callable[[Any, int], dict[str, Any]]
    # Columns naming the item in the preview, and the columns that make it "the same item".
    label: tuple[str, ...]
    match: tuple[str, ...]
    match_sql: str
    audit_action: str
    name_key: str
    slug_of: Callable[[dict[str, Any]], str]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Outcome:
    row_number: int
    label: str
    status: Status
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    values: dict[str, Any] | None = None


class RowProblem(Exception):
    """One row is not valid; the message is shown on that row."""


_YES_NO = (("Yes", True), ("No", False))
_EDUCATION = tuple((label, index) for index, label in enumerate(EDUCATION_LEVELS))
_ENGLISH = tuple((label, index) for index, label in enumerate(ENGLISH_LEVELS))
_VISA_TYPES = tuple((label, code) for code, label in VISA_TYPES.items())
_HTTPS = "Must start with https://."

KINDS: dict[str, KindSpec] = {
    "university": KindSpec(
        kind="university",
        module="study",
        table="universities",
        sheet="Universities",
        columns=(
            Column("University name", "name", required=True),
            Column("Country", "country", required=True),
            Column("City", "city"),
            Column("Levels", "levels", "comma_list", True, "Separate with commas, for example: Bachelor, Master."),
            Column("Fields", "fields", "comma_list", True, "Separate with commas."),
            Column("Tuition per year USD", "tuition_usd", "whole", True, "Whole number of US dollars."),
            Column("Minimum GPA", "min_gpa", "number", True, "From 0 to 4."),
            Column("Minimum IELTS", "min_ielts", "number", True, "From 0 to 9 in steps of 0.5. Use 0 if not needed."),
            Column("Intakes", "intakes"),
            Column("Deadline", "deadline_text"),
            Column("Scholarships", "scholarships"),
            Column("Work rights", "work_rights"),
            Column("Other conditions", "conditions"),
            Column("Application link", "apply_link", help=_HTTPS),
            Column(
                "Self Apply fee taka",
                "self_apply_fee_poisha",
                "taka",
                help="Amount in taka. Empty means Self Apply is not offered. Super admin only.",
                owner_only=True,
            ),
            Column("Admissions email", "admissions_email", help="Never shown on the website."),
            Column("Hide from website", "hidden", "yes_no", help="Yes or No. Empty means No.", choices=_YES_NO),
        ),
        model=UniversityIn,
        values=_university_values,
        label=("University name", "Country"),
        match=("University name", "Country"),
        match_sql="SELECT name, country FROM universities",
        audit_action="catalog.university_saved",
        name_key="name",
        slug_of=lambda v: str(v["name"]),
    ),
    "vacancy": KindSpec(
        kind="vacancy",
        module="job",
        table="vacancies",
        sheet="Vacancies",
        columns=(
            Column("Job title", "title", required=True),
            Column("Employer", "employer", required=True),
            Column("Country", "country", required=True),
            Column("Occupation", "occupation", required=True),
            Column("Minimum experience years", "min_experience", "whole", True, "Whole number from 0 to 40."),
            Column("Minimum education", "min_education", "choice", True, "Choose from the list.", _EDUCATION),
            Column("Minimum English", "min_english", "choice", True, "Choose from the list.", _ENGLISH),
            Column("Salary USD per month", "salary_usd", "whole", True, "Whole number of US dollars above 0."),
            Column("Seats", "seats", "whole", help="Whole number, 1 or more. Empty means not limited."),
            Column("Apply by", "apply_by", "date", help="A date like 2027-12-31. Must not be in the past if open."),
            Column("Contract", "contract"),
            Column("Benefits", "benefits"),
            Column("Other conditions", "conditions"),
            Column("Employer licence", "employer_licence"),
            Column("Employer HR email", "employer_email", help="Never shown on the website."),
            Column(
                "Employer verified",
                "employer_verified",
                "yes_no",
                help="Yes or No. Only verified employers appear on the website. Super admin only.",
                choices=_YES_NO,
                owner_only=True,
            ),
            Column("Vacancy closed", "closed", "yes_no", help="Yes or No. Empty means No.", choices=_YES_NO),
        ),
        model=VacancyIn,
        values=_vacancy_values,
        label=("Job title", "Employer", "Country"),
        match=("Job title", "Employer", "Country"),
        match_sql="SELECT title, employer, country FROM vacancies WHERE NOT remote",
        audit_action="catalog.vacancy_saved",
        name_key="title",
        slug_of=lambda v: str(v["title"]),
        extra={"remote": False},
    ),
    "visa": KindSpec(
        kind="visa",
        module="visa",
        table="visa_programs",
        sheet="Visa programmes",
        columns=(
            Column("Programme name", "title", required=True),
            Column("Country", "country", required=True),
            Column("Visa type", "visa_type", "choice", True, "Choose from the list.", _VISA_TYPES),
            Column("Processing time", "processing_time"),
            Column("Validity", "validity"),
            Column("Government fee", "government_fee", help="Written as text, for example with its currency."),
            Column("Description", "description"),
            Column("Eligibility", "eligibility", "line_list", True, "One point per line, or separate with ;."),
            Column("Required documents", "required_documents", "line_list", True, "One per line, or separate with ;."),
            Column("Other conditions", "conditions"),
            Column("Official link", "official_link", help=_HTTPS + " Never shown on the website."),
            Column("Embassy email", "embassy_email", help="Never shown on the website."),
            Column("Hide from website", "hidden", "yes_no", help="Yes or No. Empty means No.", choices=_YES_NO),
        ),
        model=VisaProgramIn,
        values=_visa_program_values,
        label=("Programme name", "Country"),
        match=("Programme name", "Country", "Visa type"),
        match_sql="SELECT title, country, visa_type FROM visa_programs",
        audit_action="catalog.visa_program_saved",
        name_key="title",
        slug_of=lambda v: f"{v['country']} {v['title']}",
    ),
}


def _norm(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


def _header_key(value: Any) -> str:
    return _norm(str(value).replace("*", ""))


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


# ---------------------------------------------------------------- template


def build_template(spec: KindSpec) -> bytes:
    """The empty template: a header row with dropdowns, and an Instructions sheet. No sample rows."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = spec.sheet
    bold = Font(bold=True)
    for number, column in enumerate(spec.columns, start=1):
        cell = sheet.cell(row=1, column=number, value=column.title)
        cell.font = bold
        letter = get_column_letter(number)
        sheet.column_dimensions[letter].width = max(16, len(column.title) + 3)
        if column.choices:
            allowed = ",".join(label for label, _ in column.choices)
            rule = DataValidation(type="list", formula1=f'"{allowed}"', allow_blank=not column.required)
            rule.add(f"{letter}2:{letter}{TEMPLATE_ROWS + 1}")
            sheet.add_data_validation(rule)
        if column.kind == "text":
            # Stored as text, so Excel does not turn a value like "1 March" into a date.
            for row in range(2, TEMPLATE_ROWS + 2):
                sheet.cell(row=row, column=number).number_format = "@"
    sheet.freeze_panes = "A2"

    guide = book.create_sheet("Instructions")
    guide.append([f"Fill in the {spec.sheet} sheet, one item per row, then upload the file."])
    guide.append(["Columns marked with * must be filled in. Do not change the column names."])
    guide.append([f"At most {MAX_ROWS} rows in one file. An item that already exists is skipped, never changed."])
    guide.append([])
    guide.append(["Column", "Required", "How to fill it in", "Allowed values"])
    for cell in guide[5]:
        cell.font = bold
    for column in spec.columns:
        allowed = ", ".join(label for label, _ in column.choices)
        guide.append([column.header, "Yes" if column.required else "No", column.help, allowed])
    guide.column_dimensions["A"].width = 30
    guide.column_dimensions["B"].width = 10
    guide.column_dimensions["C"].width = 70
    guide.column_dimensions["D"].width = 50

    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


# ---------------------------------------------------------------- reading the file


def check_upload(data: bytes) -> None:
    if not 1 <= len(data) <= MAX_FILE_BYTES:
        raise invalid("The file must be from 1 byte to 5 MB.")
    if not data.startswith(b"PK\x03\x04"):
        raise invalid("Only .xlsx Excel files.")


def _read_sheet(data: bytes, spec: KindSpec) -> list[tuple[int, dict[str, Any]]]:
    """(row number, {column header: cell}) for every row that is not empty."""
    # openpyxl raises many different errors for a damaged file; all of them mean the same to the user.
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise invalid(UNREADABLE)
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            rows = book.worksheets[0].iter_rows(values_only=True)
            first = next(rows, ())
            positions: dict[str, int] = {}
            for index, cell in enumerate(first):
                if not _blank(cell):
                    positions.setdefault(_header_key(cell), index)
            for column in spec.columns:
                if column.required and _norm(column.header) not in positions:
                    raise invalid(f"This does not look like the right template. Missing column: {column.header}.")
            found: list[tuple[int, dict[str, Any]]] = []
            for number, row in enumerate(rows, start=2):
                cells: dict[str, Any] = {}
                for column in spec.columns:
                    position = positions.get(_norm(column.header))
                    cells[column.header] = row[position] if position is not None and position < len(row) else None
                if all(_blank(value) for value in cells.values()):
                    continue
                found.append((number, cells))
                if len(found) > MAX_ROWS:
                    raise invalid(f"At most {MAX_ROWS} rows in one file.")
        finally:
            book.close()
    except ApiError:
        raise
    except Exception:
        raise invalid(UNREADABLE) from None
    if not found:
        raise invalid("This file has no rows to import.")
    return found


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    # A text column Excel turned into a date: written out, so nothing is lost.
    if isinstance(value, (datetime, date)):
        return f"{value.day} {value:%B %Y}"
    return str(value).strip()


def _whole(value: Any, column: Column) -> int:
    number: int | None = None
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\d[\d,]*", value.strip()):
        number = int(value.strip().replace(",", ""))
    if number is None or number < 0:
        raise RowProblem(f"{column.header} must be a whole number.")
    if number > MAX_WHOLE_NUMBER:
        raise RowProblem(f"{column.header} is too large.")
    return number


def _number(value: Any, column: Column) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(str(value).strip())
    except ValueError:
        raise RowProblem(f"{column.header} must be a number.") from None
    if not math.isfinite(number):
        raise RowProblem(f"{column.header} must be a number.")
    return number


def _poisha(value: Any, column: Column) -> int:
    message = f"{column.header} must be an amount in taka above 0."
    if isinstance(value, bool):
        raise RowProblem(message)
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        raise RowProblem(message) from None
    if not amount.is_finite():
        raise RowProblem(message)
    poisha = amount * 100
    if poisha <= 0 or poisha != poisha.to_integral_value() or poisha > MAX_FEE_POISHA:
        raise RowProblem(message)
    return int(poisha)


def _yes_no(value: Any, column: Column) -> bool:
    if isinstance(value, bool):
        return value
    word = _norm(value)
    if word == "yes":
        return True
    if word == "no":
        return False
    raise RowProblem(f"{column.header} must be Yes or No.")


def _date(value: Any, column: Column) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise RowProblem(f"{column.header} must be a date like 2027-12-31.") from None


def _choice(value: Any, column: Column) -> Any:
    word = _norm(_text(value))
    for label, stored in column.choices:
        if _norm(label) == word:
            return stored
    raise RowProblem(f"{column.header} must be one of: {', '.join(label for label, _ in column.choices)}.")


def _empty_value(column: Column) -> Any:
    if column.kind == "text":
        return ""
    if column.kind == "yes_no":
        return False
    return None


def _cell_value(value: Any, column: Column) -> Any:
    if _blank(value):
        if column.required:
            raise RowProblem(f"Please fill in: {column.header}.")
        return _empty_value(column)
    if column.kind == "text":
        return _text(value)
    if column.kind == "whole":
        return _whole(value, column)
    if column.kind == "number":
        return _number(value, column)
    if column.kind == "taka":
        return _poisha(value, column)
    if column.kind == "comma_list":
        return [part.strip() for part in _text(value).split(",") if part.strip()]
    if column.kind == "line_list":
        return [part.strip() for part in re.split(r"[\r\n;]+", _text(value)) if part.strip()]
    if column.kind == "yes_no":
        return _yes_no(value, column)
    if column.kind == "date":
        return _date(value, column)
    return _choice(value, column)


# ---------------------------------------------------------------- checking the rows


def _ignored_for_admin(column: Column, value: Any) -> bool:
    """True when an admin filled in a super-admin column with something that would take effect."""
    if _blank(value):
        return False
    return not (column.kind == "yes_no" and _norm(_text(value)) == "no")


def _row_values(spec: KindSpec, cells: dict[str, Any], default_fee: int, is_owner: bool, warnings: list[str]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for column in spec.columns:
        value = cells[column.header]
        if column.owner_only and not is_owner:
            if _ignored_for_admin(column, value):
                warnings.append(f"{column.header} was ignored: only the super admin can set it.")
            body[column.key] = _empty_value(column)
            continue
        body[column.key] = _cell_value(value, column)
    if "hidden" in body:
        body["published"] = not body.pop("hidden")
    try:
        model = spec.model.model_validate(body)
    except ValidationError as exc:
        location = exc.errors()[0].get("loc", ("",))
        key = location[0] if location else ""
        header = next((c.header for c in spec.columns if c.key == key), "A value")
        raise RowProblem(f"{header} is too long or not valid.") from None
    return spec.values(model, default_fee)


def _item_key(spec: KindSpec, cells: dict[str, Any]) -> tuple[str, ...] | None:
    """What makes this row the same item as another; None while a part of it is missing or wrong."""
    columns = {column.header: column for column in spec.columns}
    parts: list[str] = []
    for header in spec.match:
        value = cells[header]
        if _blank(value):
            return None
        column = columns[header]
        if column.kind == "choice":
            try:
                value = _choice(value, column)
            except RowProblem:
                return None
        parts.append(_norm(_text(value)))
    return tuple(parts)


def _label(spec: KindSpec, number: int, cells: dict[str, Any]) -> str:
    parts = [_text(cells[header]) for header in spec.label if not _blank(cells[header])]
    return " · ".join(parts)[:200] or f"Row {number}"


def evaluate(conn: Connection, spec: KindSpec, data: bytes, is_owner: bool) -> list[Outcome]:
    """What would happen to every row of the file. Saves nothing."""
    rows = _read_sheet(data, spec)
    seen: dict[tuple[str, ...], str] = {
        tuple(_norm(part) for part in row): "Already in the system, left unchanged."
        for row in conn.execute(text(spec.match_sql))
    }
    default_fee = default_fees(conn)[spec.module]
    outcomes: list[Outcome] = []
    for number, cells in rows:
        label = _label(spec, number, cells)
        key = _item_key(spec, cells)
        if key is not None and key in seen:
            outcomes.append(Outcome(number, label, "skipped", seen[key]))
            continue
        warnings: list[str] = []
        try:
            values = _row_values(spec, cells, default_fee, is_owner, warnings)
        except RowProblem as problem:
            outcomes.append(Outcome(number, label, "error", str(problem)))
            continue
        except ApiError as problem:
            outcomes.append(Outcome(number, label, "error", problem.message))
            continue
        if key is not None:
            seen[key] = "Repeated earlier in this file."
        outcomes.append(Outcome(number, label, "new", "", warnings, values))
    return outcomes


def report(spec: KindSpec, outcomes: list[Outcome]) -> dict[str, Any]:
    def count(status: Status) -> int:
        return sum(1 for outcome in outcomes if outcome.status == status)

    return {
        "kind": spec.kind,
        "total": len(outcomes),
        "new_count": count("new"),
        "skipped_count": count("skipped"),
        "error_count": count("error"),
        "rows": [
            {
                "row_number": outcome.row_number,
                "label": outcome.label,
                "status": outcome.status,
                "message": outcome.message,
                "warnings": outcome.warnings,
            }
            for outcome in outcomes
        ],
    }


def commit(conn: Connection, actor: Actor, spec: KindSpec, data: bytes) -> list[Outcome]:
    """Checks the file again and adds its valid new rows, in the caller's one transaction."""
    # Taken before reading what exists, so two uploads at once cannot add the same item twice.
    lock_catalog(conn)
    outcomes = evaluate(conn, spec, data, actor.role == "super_admin")
    for outcome in outcomes:
        if outcome.status != "new" or outcome.values is None:
            continue
        values = outcome.values
        row = _insert(conn, spec.table, {"slug": new_slug(conn, spec.table, spec.slug_of(values)), **values, **spec.extra})
        write_audit(conn, actor, spec.audit_action, f"{row[spec.name_key]}: added by Excel upload")
        if values.get("employer_verified"):
            _verified_audit(conn, actor, values)
    return outcomes
