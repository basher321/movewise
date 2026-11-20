"""B28 phases 3-6: AI CV Agent - reading, merging, gaps, writing, review, export, cover letter.

No test calls a real AI provider: providers.TRANSPORT is a fake transport that answers by the
prompt it receives (extractor, passport, writer, section, reviewer, cover letter).
"""

import io
import json
from pathlib import Path
from typing import Any

import docx
import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.ai import providers
from app.cv.countries import all_country_rules, rules_for
from app.cv.layout import build
from app.cv.render_pdf import cv_pdf
from app.cv.schema import CvData, Personal
from app.secrets_store import save_secret
from auth_helpers import audit_count, license_modules, verified_applicant

CV_TEXT = (
    "Rahim Uddin\nrahim.uddin@example.test | +8801711111111 | Dhaka, Bangladesh\n"
    "Electrician, ABC Builders Ltd, Dhaka, 01/2019 - present: installed wiring for 12 buildings; repaired panels.\n"
    "Diploma in Electrical Engineering, Dhaka Polytechnic Institute, 2018, CGPA 3.45\n" + "Experience details. " * 20
)


def pdf_with_text(body: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), body, fontsize=9)
    return document.tobytes()


EXTRACTED = {
    "personal": {"full_name": "Rahim Uddin", "email": "rahim.uddin@example.test", "phone": "+8801711111111",
                 "city": "Dhaka", "country": "Bangladesh", "nationality": "Bangladeshi"},
    "personal_unsure": [],
    "experience": [{"job_title": "Electrician", "employer": "ABC Builders Ltd", "location": "Dhaka", "start_date": "2019-01",
                    "current": True, "bullets": ["Installed wiring for 12 buildings", "Repaired panels"], "confidence": "high"}],
    "education": [{"degree": "Diploma", "field": "Electrical Engineering", "institution": "Dhaka Polytechnic Institute",
                   "end_date": "2018", "grade": "CGPA 3.45", "confidence": "high"}],
    "skills": {"technical": ["Wiring", "Panel repair", "Safety"], "soft": ["Teamwork", "Reliability"]},
    "languages": [{"language": "Bengali", "level": "Native", "confidence": "high"},
                  {"language": "English", "level": "Intermediate (B1)", "test_score": "IELTS 5.5", "confidence": "high"}],
}
LETTER_EXTRACTED = {
    "personal": {"full_name": "Rahim Uddin"},
    "experience": [{"job_title": "Electrician", "employer": "ABC Builders Ltd.", "start_date": "2019-03", "current": True,
                    "bullets": ["Maintained site power"], "confidence": "medium"}],
}


class FakeAi:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.invalid_first = False
        self.writer: dict[str, Any] | None = None

    def answer(self, system: str, user: str) -> Any:
        if "passport page ONLY" in system:
            return {"full_name": "Rahim Uddin", "nationality": "Bangladeshi", "passport_number": "BX1234567"}
        if "You read ONE document" in system:
            return LETTER_EXTRACTED if "letter" in user else EXTRACTED
        if "You proofread" in system:
            return {"issues": [{"section": "Summary", "text": "recieved", "suggestion": "received"}]}
        if "cover letter" in system:
            return {"greeting": "Dear Hiring Manager,", "paragraphs": [
                "I am an electrician applying for work in Germany.", "I raised productivity by 45%. I installed wiring for 12 buildings.",
                "This letter guarantees you a skilled worker."], "closing": "Yours faithfully,"}
        if "improving ONE part" in system:
            return {"professional_summary": "Safety-focused electrician.", "experience": []}
        ids = [x["id"] for x in json.loads(user.split("CV DATA:\n", 1)[1].split("\n\nJOB ADVERT", 1)[0])["experience"]]
        return self.writer or {
            "professional_summary": "Electrician with hands-on wiring experience since 2019. Cut costs by 30%. Guaranteed visa approval.",
            "experience": [{"id": i, "bullets": ["Installed electrical wiring for 12 residential buildings", "Boosted output by 50%",
                                                 "Repaired and tested distribution panels"]} for i in ids],
            "skills_technical": ["Safety", "Wiring", "Python"], "skills_soft": ["Reliability"],
            "ask_for": ["How many electricians did you supervise?"],
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        system = body["system"]
        content = body["messages"][0]["content"]
        user = content if isinstance(content, str) else next(b["text"] for b in content if b["type"] == "text")
        if self.invalid_first and len(self.requests) == 1:
            reply = "Sure! Here is the data: {not json"
        else:
            reply = json.dumps(self.answer(system, user))
        return httpx.Response(200, json={"content": [{"type": "text", "text": reply}], "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 100, "output_tokens": 50}})


@pytest.fixture
def ai(monkeypatch: pytest.MonkeyPatch, conn: Connection) -> FakeAi:
    fake = FakeAi()
    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(fake.handler))
    conn.execute(text(
        "UPDATE settings SET ai = '{\"order\": [\"claude\",\"openai\",\"gemini\",\"groq\"], \"providers\": "
        "{\"claude\": {\"enabled\": true, \"model\": \"claude-opus-5-5\"}}}'::jsonb WHERE singleton = 'settings'"))
    save_secret(conn, "ai.claude_key", "test-claude-key")
    return fake


@pytest.fixture
def me(client: TestClient, conn: Connection, temp_storage: Path, ai: FakeAi) -> TestClient:
    license_modules(conn, "course", "study", "job", "visa", "remote")
    verified_applicant(client, conn, "job", "cv-agent@example.test")
    return client


def base(pid: str) -> str:
    return f"/api/me/job/cv/projects/{pid}"


def start(client: TestClient, country: str = "Germany", cv_type: str = "overseas", **extra: Any) -> str:
    pid = client.post("/api/me/job/cv/projects", json={"cv_type": cv_type, "cover_letter": True}).json()["id"]
    client.patch(base(pid), json={"country": country, "category": "construction", "step": 4, **extra})
    client.post(base(pid) + "/consent", json={"agree": True})
    return pid


def upload(client: TestClient, pid: str, data: bytes, name: str, kind: str = "cv") -> dict[str, Any]:
    r = client.post(base(pid) + "/files", data={"doc_kind": kind}, files={"file": (name, data, "application/pdf")})
    assert r.status_code == 200, r.text
    return next(f for f in r.json()["files"] if f["file_name"] == name)


def read_all(client: TestClient, pid: str) -> dict[str, Any]:
    for f in client.get(base(pid)).json()["files"]:
        assert client.post(base(pid) + f"/files/{f['id']}/extract").status_code == 200
    return dict(client.post(base(pid) + "/merge").json())


def ready_to_write(client: TestClient, pid: str) -> dict[str, Any]:
    upload(client, pid, pdf_with_text(CV_TEXT), "cv.pdf")
    state = read_all(client, pid)
    return state


def test_full_journey(me: TestClient, conn: Connection, ai: FakeAi) -> None:
    pid = start(me)
    upload(me, pid, pdf_with_text(CV_TEXT), "cv.pdf")
    upload(me, pid, pdf_with_text("Experience letter. " * 30), "letter.pdf", "experience")
    state = read_all(me, pid)
    data = state["data"]
    assert data["personal"]["full_name"] == "Rahim Uddin" and len(data["experience"]) == 1
    job = data["experience"][0]
    assert job["confirm"] is True and "2019-01" in job["note"] and "2019-03" in job["note"]
    assert job["source_file"] == "cv.pdf"
    assert any("Electrician" in c for c in state["confirm"])
    # The person confirms the job (keeps 2019-01).
    job["confirm"], job["note"] = False, ""
    state = me.put(base(pid) + "/data", json={"cv": data}).json()
    assert state["confirm"] == [] and [f for f in state["missing"] if f["required"]] == []

    generated = me.post(base(pid) + "/generate")
    assert generated.status_code == 200, generated.text
    state = generated.json()
    written = state["data"]
    # Grounding: invented numbers and promises dropped, real numbers kept, unknown skills dropped.
    assert "30%" not in written["professional_summary"] and "Guaranteed" not in written["professional_summary"]
    assert "since 2019" in written["professional_summary"]
    bullets = written["experience"][0]["bullets"]
    assert "Installed electrical wiring for 12 residential buildings" in bullets and not any("50%" in b for b in bullets)
    assert written["skills"]["technical"][:2] == ["Safety", "Wiring"] and "Python" not in written["skills"]["technical"]
    assert state["ask_for"] == ["How many electricians did you supervise?"] and state["written"] is True
    assert state["template"] == "europass"  # recommended for an overseas CV to Germany

    preview = me.get(base(pid) + "/preview?page=1")
    assert preview.status_code == 200 and preview.content.startswith(b"\x89PNG") and preview.headers["x-pages"] == "1"
    for t in ("modern", "academic"):
        assert me.get(base(pid) + f"/preview?page=1&template={t}&dpi=40").status_code == 200

    shorter = me.post(base(pid) + "/section", json={"section": "summary", "action": "shorter"}).json()
    assert shorter["data"]["professional_summary"] == "Safety-focused electrician."
    removed = me.post(base(pid) + "/section", json={"section": "training", "action": "remove"}).json()
    assert "training" in removed["data"]["hidden_sections"]
    undone = me.post(base(pid) + "/undo").json()
    assert "training" not in undone["data"]["hidden_sections"]
    assert me.post(base(pid) + "/section", json={"section": "education", "action": "stronger"}).status_code == 409

    review = me.post(base(pid) + "/review", json={"spelling": True}).json()
    assert review["blocking"] == 0 and any("received" in i["message"] for i in review["issues"])
    assert me.get(base(pid) + "/export?format=pdf").status_code == 409
    approved = me.post(base(pid) + "/approve")
    assert approved.status_code == 200 and approved.json()["project"]["status"] == "approved"

    pdf = me.get(base(pid) + "/export?format=pdf")
    assert pdf.status_code == 200 and 'filename="Rahim_Uddin_CV_Germany.pdf"' in pdf.headers["content-disposition"]
    with pymupdf.open(stream=pdf.content, filetype="pdf") as d:
        assert d.page_count <= 2 and "Rahim Uddin" in d[0].get_text() and "Dhaka Polytechnic Institute" in d[0].get_text()
    word = me.get(base(pid) + "/export?format=docx")
    assert word.status_code == 200 and "Rahim_Uddin_CV_Germany.docx" in word.headers["content-disposition"]
    paragraphs = [p.text for p in docx.Document(io.BytesIO(word.content)).paragraphs]
    assert "Rahim Uddin" in paragraphs and any("ABC Builders Ltd" in p for p in paragraphs)

    letter = me.post(base(pid) + "/letter").json()["letter"]["body"]
    assert letter.startswith("Dear Hiring Manager,") and "45%" not in letter and "guarantees" not in letter
    assert "12 buildings" in letter and letter.rstrip().endswith("Rahim Uddin")
    assert me.get(base(pid) + "/export?format=pdf&doc=letter").status_code == 200
    edited = me.put(base(pid) + "/letter", json={"body": "Dear Sir,\n\nShort letter."}).json()["letter"]
    assert edited["version"] == 2
    assert audit_count(conn, "cv.approved") == 1
    calls = conn.execute(text("SELECT service, status, input_tokens FROM cv_ai_calls")).all()
    assert {c.service for c in calls} >= {"extractor", "writer", "reviewer", "cover_letter"}
    assert all(c.status == "ok" and c.input_tokens == 100 for c in calls)


def test_editing_after_approval_makes_a_draft(me: TestClient) -> None:
    pid = start(me)
    ready_to_write(me, pid)
    me.post(base(pid) + "/generate")
    me.post(base(pid) + "/approve")
    data = me.get(base(pid) + "/state").json()["data"]
    data["professional_summary"] = "Electrician."
    assert me.put(base(pid) + "/data", json={"cv": data}).json()["project"]["status"] == "draft"


def test_no_documents_questions_build_the_cv(me: TestClient) -> None:
    pid = start(me, country="UK", cv_type="new")
    state = me.get(base(pid) + "/state").json()
    keys = {f["key"] for f in state["missing"]}
    assert {"personal.full_name", "education.new.degree", "experience.new.job_title", "languages.english.level"} <= keys
    assert me.post(base(pid) + "/generate").status_code == 409
    answers = {
        "personal.full_name": "Karim Ahmed", "personal.email": "karim@example.test", "personal.phone": "+8801811111111",
        "personal.city": "Sylhet", "personal.country": "Bangladesh",
        "education.new.degree": "Bachelor's degree", "education.new.field": "Accounting",
        "education.new.institution": "Sylhet University", "education.new.end_date": "2020-06",
        "experience.new.job_title": "Accounts Assistant", "experience.new.employer": "XYZ Traders",
        "experience.new.start_date": "2021-01", "experience.new.current": True,
        "experience.new.bullets": ["Kept daily ledgers", "Prepared invoices"],
        "skills.technical": ["Bookkeeping", "Excel", "Tally"], "skills.soft": ["Teamwork", "Accuracy"],
        "languages.english.level": "Advanced (C1)", "languages.mother.language": "Bengali",
    }
    state = me.post(base(pid) + "/answers", json={"answers": answers}).json()
    assert [f for f in state["missing"] if f["required"]] == []
    job = state["data"]["experience"][0]
    assert job["current"] is True and job["source_file"] == "your answer" and job["bullets"] == ["Kept daily ledgers", "Prepared invoices"]
    assert me.post(base(pid) + "/answers", json={"answers": {"personal.email": "not-an-email"}}).status_code == 422
    assert me.post(base(pid) + "/generate").status_code == 200


def test_passport_only_when_ticked_and_number_dropped(me: TestClient, conn: Connection, ai: FakeAi) -> None:
    pid = start(me)
    passport = upload(me, pid, b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "passport.png", "passport")
    unticked = me.post(base(pid) + f"/files/{passport['id']}/extract").json()
    assert unticked["extraction_status"] == "unsupported" and ai.requests == []
    pid2 = start(me, doc_kinds=["passport"])
    from PIL import Image as Pil
    buffer = io.BytesIO()
    Pil.new("RGB", (40, 30), "white").save(buffer, "PNG")
    passport = upload(me, pid2, buffer.getvalue(), "passport.png", "passport")
    me.post(base(pid2) + f"/files/{passport['id']}/extract")
    state = me.post(base(pid2) + "/merge").json()
    assert state["data"]["personal"]["full_name"] == "Rahim Uddin"
    assert "BX1234567" not in json.dumps(state) and "BX1234567" not in json.dumps(
        conn.execute(text("SELECT extracted FROM cv_files WHERE id = :i"), {"i": passport["id"]}).scalar_one())
    image_block = ai.requests[-1]["messages"][0]["content"][0]
    assert image_block["type"] == "image" and image_block["source"]["media_type"] == "image/jpeg"


def test_invalid_json_is_retried_once(me: TestClient, conn: Connection, ai: FakeAi) -> None:
    ai.invalid_first = True
    pid = start(me)
    f = upload(me, pid, pdf_with_text(CV_TEXT), "cv.pdf")
    assert me.post(base(pid) + f"/files/{f['id']}/extract").json()["extraction_status"] == "done"
    statuses = [r.status for r in conn.execute(text("SELECT status FROM cv_ai_calls ORDER BY created_at, status DESC"))]
    assert sorted(statuses) == ["invalid_json", "ok"]


def test_daily_ai_limit(me: TestClient, conn: Connection) -> None:
    conn.execute(text("UPDATE settings SET cv_ai_per_day = 1 WHERE singleton = 'settings'"))
    pid = start(me)
    f = upload(me, pid, pdf_with_text(CV_TEXT), "cv.pdf")
    g = upload(me, pid, pdf_with_text(CV_TEXT + " again"), "cv2.pdf")
    assert me.post(base(pid) + f"/files/{f['id']}/extract").status_code == 200
    blocked = me.post(base(pid) + f"/files/{g['id']}/extract")
    assert blocked.status_code == 429 and blocked.json()["code"] == "TOO_MANY_TRIES"


def test_review_blocks_what_must_be_fixed(me: TestClient) -> None:
    pid = start(me, country="USA", cv_type="professional")
    ready_to_write(me, pid)
    me.post(base(pid) + "/generate")
    data = me.get(base(pid) + "/state").json()["data"]
    data["personal"]["show"] = ["nationality"]
    data["experience"][0]["end_date"], data["experience"][0]["current"], data["experience"][0]["start_date"] = "2018-01", False, "2019-01"
    data["experience"][0]["bullets"].append("Responsible for passport BX1234567 checks")
    data["education"][0]["confirm"] = True
    me.put(base(pid) + "/data", json={"cv": data})
    review = me.post(base(pid) + "/review", json={}).json()
    messages = " ".join(i["message"] for i in review["issues"] if i["severity"] == "blocking")
    assert "Nationality should not be on a CV for USA" in messages
    assert "end date is before the start date" in messages and "passport number" in messages and "Please confirm" in messages
    assert any("action verb" in i["message"] for i in review["issues"] if i["severity"] == "warning")
    assert me.post(base(pid) + "/approve").status_code == 409


def test_usa_cv_never_has_sensitive_fields() -> None:
    data = CvData(personal=Personal(full_name="A B", nationality="Bangladeshi", date_of_birth="1990-01", marital_status="Single",
                                    show=["nationality", "date_of_birth", "marital_status"]))
    layout = build(data, rules_for("USA"), "modern")
    assert layout.details == ""
    pdf, _ = cv_pdf(layout, "CV")
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        page_text = d[0].get_text()
    assert "Bangladeshi" not in page_text and "1990" not in page_text and "Single" not in page_text
    assert "Nationality: Bangladeshi" in build(data, rules_for("Germany"), "modern").details


def test_country_rules_are_complete() -> None:
    rules = all_country_rules()
    assert len(rules) == 18
    assert rules_for("USA").document_name == "Resume" and rules_for("USA").spelling == "en-US"
    assert rules_for("UK").spelling == "en-GB" and rules_for("Bangladesh").country == "Other"
    assert rules_for("Germany", "europass").country == "Europass"
    assert all(r.photo == "never" for r in rules if r.country in ("USA", "Canada", "UK"))


def test_page_length_is_enforced(me: TestClient, ai: FakeAi) -> None:
    pid = start(me, page_length=1)
    ready_to_write(me, pid)
    state = me.get(base(pid) + "/state").json()
    data = state["data"]
    data["experience"] = [dict(data["experience"][0], id=f"job{n}", employer=f"Employer {n}", start_date=f"{2000 + n}-01",
                               end_date=f"{2001 + n}-01", current=False,
                               bullets=[f"Installed wiring and checked safety on site number {n} carefully"] * 6)
                          for n in range(14)]
    me.put(base(pid) + "/data", json={"cv": data})
    ai.writer = {"professional_summary": "Electrician.", "experience": [], "skills_technical": [], "skills_soft": [], "ask_for": []}
    state = me.post(base(pid) + "/generate").json()
    pages = me.get(base(pid) + "/pages").json()["pages"]
    review = me.post(base(pid) + "/review", json={}).json()
    if pages > 1:
        assert any("pages but you chose 1" in i["message"] for i in review["issues"])
    else:
        assert len(state["data"]["experience"]) <= 14


def test_cv_limits_in_settings(client: TestClient, act_as: Any, settings_body: Any) -> None:
    act_as("super_admin")
    shown = client.get("/api/settings").json()
    assert shown["cv"] == {"file_days": 30, "ai_per_day": 40}
    assert "cv" not in client.get("/api/settings/public").json()
    saved = client.put("/api/settings", json=settings_body(cv={"file_days": 14, "ai_per_day": 25}))
    assert saved.status_code == 200, saved.text
    assert saved.json()["cv"] == {"file_days": 14, "ai_per_day": 25}
    assert client.put("/api/settings", json=settings_body(cv={"file_days": 0, "ai_per_day": 25})).status_code == 422
    assert client.put("/api/settings", json=settings_body()).json()["cv"] == {"file_days": 14, "ai_per_day": 25}


def test_unread_documents_become_questions_and_blank_ones_are_left_out(me: TestClient, ai: FakeAi) -> None:
    pid = start(me, country="UK", cv_type="new", doc_kinds=["training", "licence", "language", "passport"])
    old_word = upload(me, pid, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "licence.doc", "licence")
    assert me.post(base(pid) + f"/files/{old_word['id']}/extract").json()["extraction_status"] == "unsupported"
    state = me.post(base(pid) + "/merge").json()
    asked = {f["key"]: f for f in state["missing"]}
    for key in ("training.new.name", "certifications.new.name", "languages.english.test_score", "personal.nationality"):
        assert key in asked and asked[key]["required"] is False and asked[key]["note"], key
    assert "training certificate was not read" in asked["training.new.name"]["note"]
    essentials = {
        "personal.full_name": "Nadia Islam", "personal.email": "nadia@example.test", "personal.phone": "+8801911111111",
        "personal.city": "Dhaka", "personal.country": "Bangladesh",
        "education.new.degree": "Diploma", "education.new.institution": "Dhaka Nursing College",
        "education.new.end_date": "2019-06", "experience.new.job_title": "Nurse", "experience.new.employer": "City Hospital",
        "experience.new.location": "Dhaka", "experience.new.start_date": "2020-01",
        "skills.technical": ["Patient care", "First aid / BLS", "Infection control"],
        "languages.english.level": "Advanced (C1)", "languages.mother.language": "Bengali",
        "training.new.name": "Basic Life Support", "training.new.provider": "Red Crescent", "training.new.date": "2022-03",
    }
    skip = ["certifications.new.name", "certifications.new.issuer", "certifications.new.date",
            "languages.english.test_score", "personal.nationality", "training.new.name"]
    state = me.post(base(pid) + "/answers", json={"answers": essentials, "skip": skip}).json()
    keys = {f["key"] for f in state["missing"]}
    assert not keys & {"certifications.new.name", "languages.english.test_score", "personal.nationality", "training.new.name"}
    assert [t["name"] for t in state["data"]["training"]] == ["Basic Life Support"]
    assert state["data"]["certifications"] == [] and state["data"]["personal"]["nationality"] == ""
    assert "training.new.name" not in state["data"]["skipped_questions"]  # it was answered, so not skipped
    assert me.post(base(pid) + "/generate").status_code == 200
    text = me.get(base(pid) + "/preview?page=1").status_code
    assert text == 200
    from app.cv.layout import build as build_layout
    from app.cv.schema import CvData as Data
    sections = {s.key for s in build_layout(Data.model_validate(me.get(base(pid) + "/state").json()["data"]), rules_for("UK"), "modern").sections}
    assert "training" in sections and "certifications" not in sections


def test_busy_provider_is_asked_again(me: TestClient, conn: Connection, ai: FakeAi, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.cv import ai_client

    waits: list[float] = []
    monkeypatch.setattr(ai_client, "SLEEP", waits.append)
    real = ai.handler
    calls = {"n": 0}

    def busy_twice(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": "rate limit"})
        return real(request)

    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(busy_twice))
    pid = start(me)
    f = upload(me, pid, pdf_with_text(CV_TEXT), "cv.pdf")
    assert me.post(base(pid) + f"/files/{f['id']}/extract").json()["extraction_status"] == "done"
    assert waits == [3.0, 3.0]


def test_accuracy_rules() -> None:
    from app.cv.schema import Experience, clean
    from app.cv.writer import JobBullets, _apply_bullets, allowed_numbers, grounded, years_of_experience

    facts = CvData(experience=[
        Experience(id="a", employer="Square", start_date="2019-05", current=True, bullets=["Care for patients on 12-hour shifts"]),
        Experience(id="b", employer="DMC", start_date="2018-01", end_date="2018-12", bullets=["Assisted senior nurses"]),
        Experience(id="c", employer="Shop", start_date="2017-01", end_date="2017-06", bullets=[]),
    ])
    allowed = allowed_numbers(facts)
    years = years_of_experience(facts)
    assert years >= 9 and str(years) in allowed
    assert not grounded("Over four years of nursing", allowed) and grounded(f"{years} years of nursing", allowed)
    assert grounded("One of the senior nurses", allowed)
    data = facts.model_copy(deep=True)
    _apply_bullets(data, facts, [
        JobBullets(id="a", bullets=["Provided patient care on 12-hour shifts", "Led triage"]),
        JobBullets(id="b", bullets=["Assisted senior nurses", "Handled documentation", "Did triage"]),
        JobBullets(id="c", bullets=["Managed the store"]),
    ], allowed, 6)
    assert [len(x.bullets) for x in data.experience] == [1, 1, 0]
    assert clean("high\u2011quality\u00a0care") == "high-quality care"


def test_capital_names_and_language_line(me: TestClient, ai: FakeAi) -> None:
    EXTRACTED["personal"]["full_name"] = "NADIA ISLAM"
    try:
        pid = start(me)
        state = ready_to_write(me, pid)
    finally:
        EXTRACTED["personal"]["full_name"] = "Rahim Uddin"
    assert state["data"]["personal"]["full_name"] == "Nadia Islam"
    from app.cv.schema import Language
    data = CvData(languages=[Language(language="English", level="IELTS Academic 7.0", test_score="7.0")])
    line = next(s for s in build(data, rules_for("UK"), "modern").sections if s.key == "languages").lines[0]
    assert line == "English – IELTS Academic 7.0"


def test_slow_provider_is_asked_once_more(me: TestClient, ai: FakeAi, monkeypatch: pytest.MonkeyPatch) -> None:
    real = ai.handler
    calls = {"n": 0}

    def slow_once(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return real(request)

    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(slow_once))
    pid = start(me)
    f = upload(me, pid, pdf_with_text(CV_TEXT), "cv.pdf")
    assert me.post(base(pid) + f"/files/{f['id']}/extract").json()["extraction_status"] == "done"
    assert calls["n"] == 2


def test_file_name_leaves_out_titles_and_nicknames() -> None:
    from app.routers.cv_agent import file_name

    def named(n: str) -> str:
        return file_name(CvData(personal=Personal(full_name=n)), "Australia", "cv", "pdf")

    assert named("Md. Rafiul Karim (Rafi)") == "Rafiul_Karim_CV_Australia.pdf"
    assert named("Mst. Nadia Islam") == "Nadia_Islam_CV_Australia.pdf"
    assert named("Karim Hossain") == "Karim_Hossain_CV_Australia.pdf"


def test_unanswered_questions_are_skipped_and_the_cv_still_goes_forward(me: TestClient) -> None:
    pid = start(me, country="UK", cv_type="new")
    missing = [f["key"] for f in me.get(base(pid) + "/state").json()["missing"]]
    state = me.post(base(pid) + "/answers", json={"answers": {"skills.technical": ["Welding", "Cutting", "Safety"]},
                                                 "skip": missing}).json()
    assert state["missing"] == []
    assert me.post(base(pid) + "/generate").status_code == 200
    review = me.post(base(pid) + "/review", json={}).json()
    assert any("full name is missing" in i["message"] for i in review["issues"] if i["severity"] == "blocking")
    assert me.post(base(pid) + "/approve").status_code == 409
    # Nothing at all to write about: the agent says what to add.
    empty = start(me, country="UK", cv_type="new")
    skip_all = [f["key"] for f in me.get(base(empty) + "/state").json()["missing"]]
    me.post(base(empty) + "/answers", json={"answers": {}, "skip": skip_all})
    assert me.post(base(empty) + "/generate").json()["message"].startswith("Please add at least your education")
