"""B25: Remote Jobs partial match in the agent, and the advisors' applicant mode (b25-2 to b25-7).

The rule-based reply is used unless a test turns on a (fake) AI provider; no real provider is called.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import license_modules, verified_applicant
from conftest import new_client
from test_ai_advisor import FakeProviders, ai_block, ask, fake, save_ai  # noqa: F401 (fake is a fixture)
from test_catalog import university_body
from test_remote_jobs import remote_body, remote_input

ALL = ("course", "study", "job", "visa", "remote")


@pytest.fixture
def world(
    api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]
) -> dict[str, Any]:
    """A super admin (on `client`), a university, a remote role and two study applicants with one case each."""
    license_modules(conn, *ALL)
    act_as("super_admin")
    uni = client.post("/api/admin/universities", json=university_body(name="Maple Ridge University", country="Canada")).json()
    job = client.post("/api/admin/remote-jobs", json=remote_body()).json()
    people = {}
    for who in ("alice", "bob"):
        c = new_client(api)
        verified_applicant(c, conn, "study", f"{who}@example.test")
        app = c.post("/api/me/study/applications", json={"item_slug": uni["slug"], "answers": {}}).json()
        people[who] = {"client": c, "app": app}
    body = settings_body(phone="+880 1700-000000", email="hello@agency.example", name="Test Agency")
    return {"uni": uni, "job": job, "people": people, "body": body}


# b25-2
def test_remote_agent_finds_a_role_with_another_skill(client: TestClient, world: dict[str, Any]) -> None:
    reply = ask(client, "remote", "Which job fits me?", remote_input(occupation="Graphic design")).json()["answer"]
    assert "Frontend Developer" in reply


# b25-3
def test_visitor_gets_no_applicant_data(api: FastAPI, world: dict[str, Any]) -> None:
    visitor = new_client(api)
    reply = ask(visitor, "study", "What is my status?").json()["answer"]
    for p in world["people"].values():
        assert p["app"]["ref"] not in reply


# b25-4
def test_applicant_gets_only_their_own_case(world: dict[str, Any]) -> None:
    alice, bob = world["people"]["alice"], world["people"]["bob"]
    reply = ask(alice["client"], "study", "What is my status?").json()["answer"]
    assert alice["app"]["ref"] in reply
    assert "Application started" in reply and "stage 1 of" in reply
    assert bob["app"]["ref"] not in reply


# b25-5
def test_session_of_another_module_is_general_mode(api: FastAPI, conn: Connection, world: dict[str, Any]) -> None:
    other = new_client(api)
    verified_applicant(other, conn, "remote", "remote.person@example.test")
    other.post("/api/me/remote/applications", json={"item_slug": world["job"]["slug"], "answers": {}})
    reply = ask(other, "study", "What is my status?").json()["answer"]
    assert "APP-" not in reply and "no study application" not in reply


def test_signed_in_without_a_case(api: FastAPI, conn: Connection, world: dict[str, Any]) -> None:
    newcomer = new_client(api)
    verified_applicant(newcomer, conn, "study", "new.person@example.test")
    assert ask(newcomer, "study", "What is my application status?").json()["answer"].startswith(
        "You have no study application yet."
    )


# b25-6 and b25-7
def test_prompt_my_cases_is_private_and_has_the_case_fee(
    client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeProviders  # noqa: F811
) -> None:
    alice, bob = world["people"]["alice"], world["people"]["bob"]
    app_id = alice["app"]["id"]
    client.post(f"/api/admin/applications/{app_id}/notes", json={"note": "Staff-only remark XYZ"})
    assert client.put(f"/api/admin/applications/{app_id}/fee", json={"fee_poisha": 123400}).status_code == 200
    save_ai(client, world["body"], ai_block(("claude",)))

    fake.reply["claude"] = "Your case is in progress."
    ask(alice["client"], "study", "What is my status?")
    content = fake.bodies()[-1]["messages"][0]["content"]
    facts = json.loads(content.split("FACTS (JSON):\n", 1)[1].split("\n\nVISITOR FORM INPUTS", 1)[0])
    assert facts["asker_is_signed_in_applicant"] is True
    assert [c["reference"] for c in facts["my_cases"]] == [alice["app"]["ref"]]
    assert facts["my_cases"][0]["fee_to_pay"] == "৳1,234"
    assert "Staff-only remark XYZ" not in content and "Case updated" not in content
    assert bob["app"]["ref"] not in content
    assert "signed-in applicant" in fake.bodies()[-1]["system"]

    # A visitor's prompt has no my_cases and the sign-in rule.
    ask(client, "study", "What is my status?")
    body = fake.bodies()[-1]
    assert "my_cases" not in body["messages"][0]["content"]
    assert "need to sign in" in body["system"]
    # Nothing was written for applicants by asking (no audit for questions).
    assert conn.execute(text("SELECT count(*) FROM ai_questions")).scalar_one() >= 2


def test_rule_based_reply_states_case_fee(client: TestClient, world: dict[str, Any]) -> None:
    alice = world["people"]["alice"]
    client.put(f"/api/admin/applications/{alice['app']['id']}/fee", json={"fee_poisha": 123400})
    reply = ask(alice["client"], "study", "How much fee do I need to pay?").json()["answer"]
    assert "Fee to pay: ৳1,234" in reply
