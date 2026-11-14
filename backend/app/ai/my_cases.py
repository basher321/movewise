"""The signed-in applicant's own cases for the advisor (spec B25, applicant mode).

Only what the applicant already sees on their own application pages: reference, item, status,
stage, fee, latest payment status, documents (missing and rejected with the note shown to them),
deadline, interview, completion letter and the last public history lines. Never internal notes,
private history, staff emails, commissions or anything of another applicant.
"""

import re
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import STATUS_LABELS, app_fee, dhaka_text, item_row, item_title, money_text
from app.documents import documents_part
from app.stages import stage_count, stage_name

AgentModule = Literal["study", "job", "visa", "remote"]
MAX_CASES = 10
MAX_HISTORY = 3
# Rule-based reply: a question is about the applicant's own cases when it has a status word, or a
# case word together with "my", "I" or "me" ("What is the fee?" stays a general question).
STATUS_WORDS = ("status", "stage", "progress", "my application", "my case", "missing", "interview", "deadline", "letter")
CASE_WORDS = ("application", "document", "paid", "payment", "fee", "update", "case")
_PERSONAL = re.compile(r"\b(my|i|me|mine)\b")
_MODULE_NOUN = {"study": "study", "job": "job", "visa": "visa", "remote": "remote job"}

_MY_APPS = text(
    "SELECT * FROM applications WHERE applicant_id = :applicant AND module = :module "
    "ORDER BY created_at DESC, id DESC LIMIT :limit"
)
_HISTORY = text(
    "SELECT at, text FROM app_events WHERE application_id = :id AND public ORDER BY at DESC, id DESC LIMIT :limit"
)
_LATEST_PAYMENT = text(
    "SELECT status FROM payments WHERE ref_type = 'application' AND ref_id = :id ORDER BY created_at DESC, id LIMIT 1"
)
_LETTER = text("SELECT 1 FROM case_letters WHERE application_id = :id")


def my_cases(conn: Connection, applicant: RowMapping, module: AgentModule) -> list[dict[str, Any]]:
    apps = list(
        conn.execute(_MY_APPS, {"applicant": applicant["id"], "module": module, "limit": MAX_CASES}).mappings()
    )
    docs = documents_part(conn, apps, "applicant")
    out = []
    for app in apps:
        item = item_row(conn, app)
        part = docs[app["id"]]
        current = {d["type"]: d for d in part["documents"]}
        done = ("pending", "verified", "expiring")
        missing = [t for t in part["required_types"] if current.get(t, {}).get("shown_status") not in done]
        rejected = [
            {"type": d["type"], "note": d["note"]} for d in part["documents"] if d["shown_status"] == "rejected"
        ]
        fee = None if app["fee_paid"] else app_fee(conn, app, item)
        case: dict[str, Any] = {
            "reference": app["ref"],
            "applied_for": item_title(module, item),
            "country": item["country"],
            "status": STATUS_LABELS[app["status"]],
            "stage": stage_name(module, app["stage"]),
            "stage_number": f"stage {app['stage'] + 1} of {stage_count(module)}",
            "fee_paid": bool(app["fee_paid"]),
            "fee_to_pay": money_text(fee) if fee is not None else None,
            "latest_payment_status": conn.execute(_LATEST_PAYMENT, {"id": app["id"]}).scalar_one_or_none(),
            "missing_documents": missing,
            "rejected_documents": rejected,
            "deadline": app["deadline"].isoformat() if app["deadline"] else None,
            "completion_letter_issued": conn.execute(_LETTER, {"id": app["id"]}).first() is not None,
            "latest_updates": [
                e.text for e in conn.execute(_HISTORY, {"id": app["id"], "limit": MAX_HISTORY})
            ],
        }
        if module != "study":
            case["interview"] = dhaka_text(app["interview_at"]) if app["interview_at"] else None
        out.append(case)
    return out


def is_status_question(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in STATUS_WORDS) or (any(w in q for w in CASE_WORDS) and bool(_PERSONAL.search(q)))


def no_case_text(module: AgentModule) -> str:
    return f"You have no {_MODULE_NOUN[module]} application yet."


def my_cases_answer(module: AgentModule, cases: list[dict[str, Any]]) -> str:
    """The rule-based reply about the applicant's own cases (at most 3, newest first)."""
    if not cases:
        return no_case_text(module)
    parts = []
    for c in cases[:3]:
        line = f"{c['reference']} ({c['applied_for']}, {c['country']}): {c['status']}, {c['stage']} ({c['stage_number']})."
        if c["fee_paid"]:
            line += " Fee paid."
        elif c["fee_to_pay"]:
            line += f" Fee to pay: {c['fee_to_pay']}."
        if c["missing_documents"]:
            line += f" Missing documents: {', '.join(c['missing_documents'])}."
        for r in c["rejected_documents"]:
            line += f" {r['type']} was rejected" + (f" ({r['note']})" if r["note"] else "") + ", please upload it again."
        if c.get("interview"):
            line += f" Interview: {c['interview']}."
        if c["deadline"]:
            line += f" Deadline: {c['deadline']}."
        if c["completion_letter_issued"]:
            line += " Your completion letter is ready in your profile."
        parts.append(line)
    more = f" You have {len(cases) - 3} more in your profile." if len(cases) > 3 else ""
    return " ".join(parts) + more
