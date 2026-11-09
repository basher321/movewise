"""B23: Excel upload of universities, vacancies and visa programmes."""

import io
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import excel_import
from app.excel_import import KINDS
from app.licence import today_dhaka
from auth_helpers import audit_count, license_modules, sign_in_admin_on

UNI = {
    "University name*": "North Example University",
    "Country*": "Canada",
    "Levels*": "Bachelor, Master",
    "Fields*": "Business, Computer Science",
    "Tuition per year USD*": 15000,
    "Minimum GPA*": 3.2,
    "Minimum IELTS*": 6.5,
}
JOB = {
    "Job title*": "Test Welder",
    "Employer*": "Example Works",
    "Country*": "Qatar",
    "Occupation*": "Construction",
    "Minimum experience years*": 2,
    "Minimum education*": "SSC / HSC",
    "Minimum English*": "Basic",
    "Salary USD per month*": 900,
}
VISA = {
    "Programme name*": "Test Visitor Visa",
    "Country*": "Canada",
    "Visa type*": "Visit visa",
    "Eligibility*": "Valid passport; Enough funds",
    "Required documents*": "Passport\nBank statement",
}
BODY = {"university": UNI, "vacancy": JOB, "visa": VISA}


def workbook(rows: list[dict[str, Any]], headers: list[str] | None = None) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    names = headers if headers is not None else list(dict.fromkeys(k for row in rows for k in row))
    sheet.append(names)
    for row in rows:
        sheet.append([row.get(name) for name in names])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def send(client: TestClient, kind: str, step: str, data: bytes, name: str = "list.xlsx") -> Any:
    return client.post(f"/api/admin/import/{kind}/{step}", files={"file": (name, data, excel_import.XLSX_MIME)})


def count(conn: Connection, table: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


@pytest.fixture
def sa(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> TestClient:
    license_modules(conn, "study", "job", "visa")
    act_as("super_admin")
    return client


@pytest.mark.parametrize("kind", ["university", "vacancy", "visa"])
def test_template_has_the_columns_and_no_sample_rows(sa: TestClient, kind: str) -> None:
    response = sa.get(f"/api/admin/import/{kind}/template")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == excel_import.XLSX_MIME
    assert "attachment" in response.headers["content-disposition"]
    book = load_workbook(io.BytesIO(response.content))
    sheet = book.worksheets[0]
    assert [c.value for c in sheet[1]] == [c.title for c in KINDS[kind].columns]
    assert all(cell.value is None for row in sheet.iter_rows(min_row=2) for cell in row)
    assert book.sheetnames[1] == "Instructions"


@pytest.mark.parametrize(
    ("kind", "table", "action"),
    [
        ("university", "universities", "catalog.university_saved"),
        ("vacancy", "vacancies", "catalog.vacancy_saved"),
        ("visa", "visa_programs", "catalog.visa_program_saved"),
    ],
)
def test_preview_saves_nothing_and_commit_adds_rows(sa: TestClient, conn: Connection, kind: str, table: str, action: str) -> None:
    before = count(conn, table)
    audits = audit_count(conn, action)
    data = workbook([BODY[kind]])

    preview = send(sa, kind, "preview", data)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert (body["kind"], body["total"], body["new_count"], body["skipped_count"], body["error_count"]) == (kind, 1, 1, 0, 0)
    assert body["rows"][0]["row_number"] == 2 and body["rows"][0]["status"] == "new"
    assert count(conn, table) == before and audit_count(conn, action) == audits

    done = send(sa, kind, "commit", data)
    assert done.status_code == 200, done.text
    assert done.json()["new_count"] == 1
    assert count(conn, table) == before + 1
    assert audit_count(conn, action) == audits + 1


def test_cells_reach_the_right_columns(sa: TestClient, conn: Connection) -> None:
    row = {**UNI, "Self Apply fee taka": 1500.5, "Hide from website": "Yes", "Deadline": datetime(2027, 3, 1)}
    assert send(sa, "university", "commit", workbook([row])).json()["new_count"] == 1
    saved = conn.execute(text("SELECT * FROM universities WHERE name = :n"), {"n": UNI["University name*"]}).mappings().one()
    assert list(saved["levels"]) == ["Bachelor", "Master"] and list(saved["fields"]) == ["Business", "Computer Science"]
    assert saved["tuition_usd"] == 15000 and float(saved["min_gpa"]) == 3.2 and float(saved["min_ielts"]) == 6.5
    assert saved["self_apply_fee_poisha"] == 150050 and saved["published"] is False
    assert saved["deadline_text"] == "1 March 2027"

    assert send(sa, "visa", "commit", workbook([VISA])).json()["new_count"] == 1
    visa = conn.execute(text("SELECT * FROM visa_programs WHERE title = :t"), {"t": VISA["Programme name*"]}).mappings().one()
    assert visa["visa_type"] == "visit" and visa["published"] is True
    assert list(visa["eligibility"]) == ["Valid passport", "Enough funds"]
    assert list(visa["required_documents"]) == ["Passport", "Bank statement"]

    until = today_dhaka() + timedelta(days=30)
    job = {**JOB, "Minimum education*": "Diploma", "Minimum English*": "Fluent", "Seats": 4, "Apply by": until.isoformat(), "Employer verified": "Yes"}
    verified = audit_count(conn, "Employer verified")
    assert send(sa, "vacancy", "commit", workbook([job])).json()["new_count"] == 1
    vacancy = conn.execute(text("SELECT * FROM vacancies WHERE title = :t"), {"t": JOB["Job title*"]}).mappings().one()
    assert (vacancy["min_education"], vacancy["min_english"], vacancy["seats"], vacancy["apply_by"]) == (2, 2, 4, until)
    assert vacancy["employer_verified"] is True and vacancy["remote"] is False
    assert audit_count(conn, "Employer verified") == verified + 1


def test_columns_are_found_by_name_in_any_order(sa: TestClient, conn: Connection) -> None:
    data = workbook([UNI], headers=list(reversed(list(UNI))) + ["Our own notes"])
    assert send(sa, "university", "preview", data).json()["new_count"] == 1


def test_existing_items_are_skipped_and_never_changed(sa: TestClient, conn: Connection) -> None:
    assert send(sa, "university", "commit", workbook([{**UNI, "City": "Toronto"}])).json()["new_count"] == 1
    total = count(conn, "universities")
    audits = audit_count(conn, "catalog.university_saved")
    same = {**UNI, "University name*": "  north   EXAMPLE university ", "Country*": "canada", "City": "Other"}
    body = send(sa, "university", "commit", workbook([same])).json()
    assert (body["new_count"], body["skipped_count"]) == (0, 1)
    assert body["rows"][0]["message"] == "Already in the system, left unchanged."
    assert count(conn, "universities") == total and audit_count(conn, "catalog.university_saved") == audits
    city = conn.execute(text("SELECT city FROM universities WHERE name = :n"), {"n": UNI["University name*"]}).scalar_one()
    assert city == "Toronto"


def test_a_row_repeated_in_the_file_is_added_once(sa: TestClient, conn: Connection) -> None:
    before = count(conn, "visa_programs")
    other_type = {**VISA, "Visa type*": "Work visa"}
    body = send(sa, "visa", "commit", workbook([VISA, VISA, other_type])).json()
    assert (body["new_count"], body["skipped_count"]) == (2, 1)
    assert body["rows"][1]["message"] == "Repeated earlier in this file."
    assert count(conn, "visa_programs") == before + 2


def test_a_remote_job_does_not_count_as_the_same_vacancy(sa: TestClient, conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO vacancies (slug, title, employer, country, occupation, min_experience, min_education, "
            "min_english, salary_usd, remote) VALUES ('remote-test-welder', :t, :e, :c, 'Construction', 0, 0, 0, 900, true)"
        ),
        {"t": JOB["Job title*"], "e": JOB["Employer*"], "c": JOB["Country*"]},
    )
    assert send(sa, "vacancy", "preview", workbook([JOB])).json()["new_count"] == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"Country*": None}, "Please fill in: Country."),
        ({"Tuition per year USD*": "a lot"}, "Tuition per year USD must be a whole number."),
        ({"Tuition per year USD*": 2.5}, "Tuition per year USD must be a whole number."),
        ({"Minimum GPA*": 5}, "Minimum GPA must be from 0 to 4."),
        ({"Minimum IELTS*": 6.3}, "Minimum IELTS must be from 0 to 9 in steps of 0.5."),
        ({"Application link": "http://example.test"}, "The application link must start with https://."),
        ({"Admissions email": "nobody"}, "Please enter a valid admissions email."),
        ({"Hide from website": "maybe"}, "Hide from website must be Yes or No."),
        ({"Self Apply fee taka": 10.555}, "Self Apply fee taka must be an amount in taka above 0."),
    ],
)
def test_bad_rows_are_reported_and_good_rows_still_added(
    sa: TestClient, conn: Connection, change: dict[str, Any], message: str
) -> None:
    before = count(conn, "universities")
    bad = {**UNI, "University name*": "Bad Example University", **change}
    good = {**UNI, "University name*": "Good Example University"}
    headers = list(dict.fromkeys(list(UNI) + list(change)))
    body = send(sa, "university", "commit", workbook([bad, good], headers=headers)).json()
    assert (body["new_count"], body["error_count"]) == (1, 1)
    assert body["rows"][0]["status"] == "error" and body["rows"][0]["message"] == message
    assert count(conn, "universities") == before + 1


def test_vacancy_rules_match_the_form(sa: TestClient, conn: Connection) -> None:
    past = (today_dhaka() - timedelta(days=1)).isoformat()
    rows = [
        {**JOB, "Job title*": "A", "Apply by": past},
        {**JOB, "Job title*": "B", "Minimum education*": "Astronaut"},
        {**JOB, "Job title*": "C", "Seats": 99_999_999_999},
    ]
    body = send(sa, "vacancy", "preview", workbook(rows)).json()
    assert [r["status"] for r in body["rows"]] == ["error", "error", "error"]
    assert body["rows"][0]["message"] == "Apply by must not be in the past for an open vacancy."
    assert body["rows"][1]["message"].startswith("Minimum education must be one of:")
    assert body["rows"][2]["message"] == "Seats is too large."


def test_empty_rows_are_ignored(sa: TestClient) -> None:
    body = send(sa, "university", "preview", workbook([{}, UNI, {}], headers=list(UNI))).json()
    assert body["total"] == 1 and body["rows"][0]["row_number"] == 3


def test_file_level_errors(sa: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def message(data: bytes) -> str:
        response = send(sa, "university", "preview", data)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "VALIDATION"
        return str(response.json()["message"])

    assert message(b"just some text") == "Only .xlsx Excel files."
    assert message(b"") == "The file must be from 1 byte to 5 MB."
    assert message(b"PK\x03\x04" + b"0" * (5 * 1024 * 1024)) == "The file must be from 1 byte to 5 MB."
    assert message(b"PK\x03\x04 not really a workbook") == "This file could not be read."
    assert message(workbook([], headers=list(UNI))) == "This file has no rows to import."
    assert message(workbook([UNI] * 1001)) == "At most 1000 rows in one file."
    assert message(workbook([{"Name": "x"}])) == "This does not look like the right template. Missing column: University name."
    assert send(sa, "university", "preview", b"x" * 100, name="x.txt").status_code == 422

    missing = sa.post("/api/admin/import/university/preview", data={"note": "no file"})
    assert missing.status_code == 422 and missing.json()["message"] == "Please choose a file."

    monkeypatch.setattr(excel_import, "MAX_EXPANDED_BYTES", 10)
    assert message(workbook([UNI])) == "This file could not be read."


def test_body_limit_is_six_mb_on_the_upload_paths_only(sa: TestClient) -> None:
    big = send(sa, "university", "preview", b"x" * (6 * 1024 * 1024 + 1))
    assert big.status_code == 422 and big.json()["message"] == "The file must be 5 MB or smaller."
    other = sa.post("/api/admin/import/university/template", files={"file": ("a", b"x" * (3 * 1024 * 1024 + 1))})
    assert other.status_code == 422 and other.json()["message"] == "Request body is larger than 3 MB."


def test_unknown_kind_is_not_found(sa: TestClient) -> None:
    assert sa.get("/api/admin/import/course/template").status_code == 404
    response = send(sa, "remote", "preview", workbook([UNI]))
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"


def test_not_signed_in(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    assert client.get("/api/admin/import/university/template").json()["code"] == "UNAUTHENTICATED"
    assert send(client, "university", "commit", workbook([UNI])).status_code == 401


def test_unlicensed_module_is_refused_first(sa: TestClient, conn: Connection) -> None:
    license_modules(conn, "job")
    for response in (sa.get("/api/admin/import/university/template"), send(sa, "university", "commit", b"not checked yet")):
        assert response.status_code == 403 and response.json()["code"] == "MODULE_NOT_LICENSED"


def test_finance_is_refused(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    sign_in_admin_on(client, conn, "finance", [])
    response = send(client, "university", "preview", workbook([UNI]))
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"


def test_admin_only_in_assigned_sections(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job", "visa")
    sign_in_admin_on(client, conn, "admin", ["job"])
    assert send(client, "university", "preview", workbook([UNI])).json()["code"] == "FORBIDDEN"
    assert client.get("/api/admin/import/visa/template").status_code == 403
    assert client.get("/api/admin/import/vacancy/template").status_code == 200
    assert send(client, "vacancy", "commit", workbook([JOB])).json()["new_count"] == 1


def test_admin_cannot_set_the_super_admin_columns(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job")
    sign_in_admin_on(client, conn, "admin", ["study", "job"])
    job = send(client, "vacancy", "commit", workbook([{**JOB, "Employer verified": "Yes"}])).json()
    assert job["new_count"] == 1
    assert job["rows"][0]["warnings"] == ["Employer verified was ignored: only the super admin can set it."]
    verified = conn.execute(text("SELECT employer_verified FROM vacancies WHERE title = :t"), {"t": JOB["Job title*"]}).scalar_one()
    assert verified is False

    uni = send(client, "university", "commit", workbook([{**UNI, "Self Apply fee taka": 1500}])).json()
    assert uni["rows"][0]["warnings"] == ["Self Apply fee taka was ignored: only the super admin can set it."]
    fee = conn.execute(text("SELECT self_apply_fee_poisha FROM universities WHERE name = :n"), {"n": UNI["University name*"]}).scalar_one()
    assert fee is None

    no_effect = send(client, "vacancy", "preview", workbook([{**JOB, "Job title*": "Other", "Employer verified": "No"}])).json()
    assert no_effect["rows"][0]["warnings"] == []


def test_slugs_stay_unique_for_rows_with_the_same_name(sa: TestClient, conn: Connection) -> None:
    rows = [UNI, {**UNI, "Country*": "Australia"}]
    assert send(sa, "university", "commit", workbook(rows)).json()["new_count"] == 2
    slugs = [r[0] for r in conn.execute(text("SELECT slug FROM universities WHERE name = :n"), {"n": UNI["University name*"]})]
    assert len(set(slugs)) == 2
