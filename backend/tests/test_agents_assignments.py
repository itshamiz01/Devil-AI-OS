"""P-04 Stage 6: the nine assignment rules, the ledger, and the output contract.

These tests are about the two things an assignment module can quietly get wrong.

The first is a rule that passes when it should not. Every refusal test here
asserts *which* rule refused, because a refusal from the wrong rule and a refusal
from the right one look identical in a status code. Where a rule depends on state
that had to be mutated to set up, the mutation is asserted afterwards: a test whose
setup silently did nothing passes for the wrong reason.

The second is a completion that is accepted on the agent's word. The contract tests
therefore include the case that matters — an agent reporting success with a result
that does not satisfy the contract — and assert the assignment ends `failed` with
the violations listed.

Helpers are imported from the Stage-5 module rather than copied, so there is one
definition of "an agent created through the factory" in the suite.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.assignments import AssignmentService, validate_output_contract
from app.agents.schemas import ASSIGNMENT_RULES, ASSIGNMENT_STATUSES
from app.database.connection import Database
from app.database.models import Agent, AgentAssignment, AgentTemplateVersion, Task

from tests.test_agents_capabilities import (  # noqa: F401 - shared helpers
    _agent,
    _ask,
    _db,
    _grant,
    _held,
    _published,
    _set_agent_field,
)


# --------------------------------------------------------------------------- #
# Fixtures and helpers
# --------------------------------------------------------------------------- #
def _task(settings, *, status: str = "QUEUED", payload: dict | None = None,
          name: str = "screen the list") -> str:
    """A real task row. Inserted rather than submitted so its status and payload
    are the ones the rule under test needs, not the ones a scheduler produced."""
    async def go(session):
        from app.database.models import Principal
        principal = (await session.execute(select(Principal).limit(1))).scalars().first()
        row = Task(name=name, description="created by the assignment tests",
                   category="research", handler="opportunities.screen", priority=5,
                   status=status, creator_id=principal.id if principal else None,
                   payload=dict(payload or {}))
        session.add(row)
        await session.flush()
        return row.id
    return _db(settings, go)


def _assignment_row(settings, assignment_id: str) -> tuple:
    """(id, agent, task, status, depth, required, contract, failure_reason)."""
    async def go(session):
        row = await session.get(AgentAssignment, assignment_id)
        return (row.id, row.agent_id, row.task_id, row.status, row.delegation_depth,
                list(row.required_capabilities or []),
                dict(row.expected_output_schema or {}), row.failure_reason)
    return _db(settings, go)


def _rows(settings) -> list:
    async def go(session):
        from app.database.models import AgentAssignment
        return [(r.id, r.agent_id, r.task_id, r.status, r.delegation_depth,
                 list(r.required_capabilities or []), dict(r.expected_output_schema or {}),
                 r.failure_reason)
                for r in (await session.execute(select(AgentAssignment))).scalars().all()]
    return _db(settings, go)


def _creation_reason(settings, request_id: str) -> str:
    """The decision_reason the creation ledger holds for one request."""
    async def go(session):
        from app.database.models import AgentCreationRequest
        row = await session.get(AgentCreationRequest, request_id)
        return row.decision_reason or ""
    return _db(settings, go)


def _budget(settings, agent_id: str) -> int:
    """The concurrency ceiling the agent was actually built with, read from the
    stored template version rather than assumed."""
    async def go(session):
        agent = await session.get(Agent, agent_id)
        version = (await session.execute(
            select(AgentTemplateVersion).where(
                AgentTemplateVersion.template_id == agent.template_id,
                AgentTemplateVersion.version == agent.template_version))).scalars().first()
        from app.agents.schemas import TemplateConfiguration
        cfg = TemplateConfiguration.model_validate(version.configuration_json or {})
        return int(cfg.resource_budget.max_concurrent_tasks)
    return _db(settings, go)


def _assign(client, agent_id, task_id, **extra):
    return client.post(f"/api/v1/agents/{agent_id}/assign",
                       json=dict({"task_id": task_id}, **extra))


def _capable(client: TestClient, capabilities: tuple[str, ...] = ("research.read",),
             name: str = "researcher") -> str:
    """An agent that actually holds the capabilities its template allows.

    Creating through the factory is not enough: a created agent holds zero grants
    (L-73), so an assignment requiring anything would be refused at rule 7 for a
    reason that has nothing to do with the rule under test.
    """
    agent_id = _agent(client, capabilities=capabilities, name=name)
    for key in capabilities:
        assert _grant(client, agent_id, key).status_code == 201, key
    assert {key for key in capabilities} == {g["capability_key"] for g in _held(client, agent_id)}
    return agent_id


def _refused(response) -> dict:
    """The structured evaluation a refusal carries, or a failure that says why not."""
    assert response.status_code == 409, (response.status_code, response.text)
    error = response.json()["error"]
    assert error["code"] == "assignment_refused", error
    evaluation = error["details"]["evaluation"]
    assert evaluation["assigned"] is False
    return evaluation


def _refusing_rule(evaluation: dict) -> str:
    failed = [c["name"] for c in evaluation["checks"] if c["passed"] is False]
    assert len(failed) == 1, evaluation["checks"]
    return failed[0]


# --------------------------------------------------------------------------- #
# The contract validator on its own
# --------------------------------------------------------------------------- #
def test_the_validator_checks_types_required_and_nesting():
    schema = {"type": "object", "required": ["summary", "score"],
              "properties": {"summary": {"type": "string"},
                             "score": {"type": "integer"},
                             "sources": {"type": "array",
                                         "items": {"type": "string"}}}}
    assert validate_output_contract(
        {"summary": "three candidates", "score": 7, "sources": ["a", "b"]}, schema) == []
    violations = validate_output_contract({"summary": 3, "sources": ["a", 2]}, schema)
    assert any("required key 'score' is missing" in v for v in violations), violations
    assert any("$.summary: expected string, got int" in v for v in violations), violations
    assert any("$.sources[1]" in v for v in violations), violations


def test_the_validator_fails_closed_on_a_keyword_it_does_not_implement():
    """An unchecked result recorded as verified is worse than a refusal."""
    violations = validate_output_contract(42, {"type": "mystery"})
    assert violations and "does not implement" in violations[0]


def test_the_validator_refuses_unexpected_keys_when_the_contract_says_to():
    schema = {"type": "object", "properties": {"a": {"type": "string"}},
              "additionalProperties": False}
    assert validate_output_contract({"a": "x"}, schema) == []
    assert any("unexpected key 'b'" in v
               for v in validate_output_contract({"a": "x", "b": 1}, schema))


def test_an_empty_contract_accepts_anything_and_says_so():
    assert validate_output_contract({"anything": 1}, {}) == []


def test_a_boolean_is_not_an_integer():
    """Python treats True as 1; an output contract should not."""
    assert validate_output_contract(True, {"type": "integer"}) != []


# --------------------------------------------------------------------------- #
# A successful assignment
# --------------------------------------------------------------------------- #
def test_assigning_records_a_ledger_row(client: TestClient, settings):
    agent_id = _capable(client, capabilities=("research.read",))
    task_id = _task(settings)
    response = _assign(client, agent_id, task_id,
                       required_capabilities=["research.read"],
                       expected_output_schema={"type": "object", "required": ["summary"]},
                       priority=3, reason="it is the only researcher")
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["assigned"] is True
    assert data["assignment_id"]
    assert data["delegation_depth"] == 0
    assert data["required_capabilities"] == ["research.read"]
    # Every rule ran and passed, and the response says so rather than only that it
    # succeeded.
    assert [c["name"] for c in data["checks"]] == list(ASSIGNMENT_RULES)
    assert all(c["passed"] for c in data["checks"])

    row = _rows(settings)
    assert len(row) == 1
    _id, agent, task, status, depth, required, schema, failure = row[0]
    assert (agent, task, status, depth) == (agent_id, task_id, "assigned", 0)
    assert required == ["research.read"]
    assert schema == {"type": "object", "required": ["summary"]}
    assert failure is None


def test_the_status_endpoint_reports_every_rule_and_every_status(client: TestClient, settings):
    _agent(client)
    body = client.get("/api/v1/assignments/status").json()["data"]
    assert body["rules"] == list(ASSIGNMENT_RULES)
    assert body["statuses"] == list(ASSIGNMENT_STATUSES)
    assert set(body["assignments_by_status"]) == set(ASSIGNMENT_STATUSES)
    assert body["capability_authority_available"] is True
    # Stated rather than left to be inferred from a healthy-looking count.
    assert body["progress_observed"] is False


# --------------------------------------------------------------------------- #
# The rules, one at a time
# --------------------------------------------------------------------------- #
def test_rule_1_refuses_a_task_that_does_not_exist(client: TestClient, settings):
    agent_id = _agent(client)
    evaluation = _refused(_assign(client, agent_id, "no-such-task"))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[0]
    assert "does not exist" in evaluation["reason"]
    assert _rows(settings) == [], "a refusal must not create a row"


def test_rule_1_refuses_a_task_that_has_already_finished(client: TestClient, settings):
    agent_id = _agent(client)
    task_id = _task(settings, status="COMPLETED")
    evaluation = _refused(_assign(client, agent_id, task_id))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[0]
    assert "COMPLETED" in evaluation["reason"]


def test_rule_2_refuses_work_somebody_already_holds(client: TestClient, settings):
    agent_id = _agent(client)
    other = _agent(client, name="second")
    task_id = _task(settings)
    assert _assign(client, agent_id, task_id).status_code == 201
    evaluation = _refused(_assign(client, other, task_id))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[1]
    assert agent_id in evaluation["reason"]
    # Still exactly one row: the second request added nothing.
    assert len(_rows(settings)) == 1


def test_rule_2_allows_reassignment_once_the_first_is_cancelled(client: TestClient, settings):
    """Governance allows reassignment only after the previous hold is released, so
    releasing it has to be enough — otherwise work could never move."""
    first = _agent(client, name="first")
    second = _agent(client, name="second")
    task_id = _task(settings)
    assignment_id = _assign(client, first, task_id).json()["data"]["assignment_id"]
    assert client.post(f"/api/v1/assignments/{assignment_id}/cancel",
                       json={"reason": "the first agent is not the right one"}
                       ).status_code == 200
    assert _assignment_row(settings, assignment_id)[3] == "cancelled"
    response = _assign(client, second, task_id)
    assert response.status_code == 201, response.text
    # One row per task: the Stage-2 UNIQUE means a reassignment supersedes the
    # finished row rather than adding to it, and the previous holder survives in
    # the failure reason.
    rows = _rows(settings)
    assert len(rows) == 1, rows
    assert rows[0][1] == second, rows[0]
    assert rows[0][3] == "assigned"
    assert first in rows[0][7] and "superseded" in rows[0][7], rows[0][7]


def test_rule_4_refuses_an_agent_that_cannot_accept_work(client: TestClient, settings):
    agent_id = _agent(client)
    task_id = _task(settings)
    _set_agent_field(settings, agent_id, status="SUSPENDED")
    # Assert the setup landed: without this, a refusal from any rule looks the same.
    async def read(session):
        return (await session.get(Agent, agent_id)).status
    assert _db(settings, read) == "SUSPENDED"
    evaluation = _refused(_assign(client, agent_id, task_id))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[3]
    assert "SUSPENDED" in evaluation["reason"]


def test_rule_6_refuses_work_that_crosses_a_business_boundary(client: TestClient, settings):
    agent_id = _agent(client)
    scoped = _agent(client, name="scoped")
    _set_agent_field(settings, scoped, business_id="business-1")
    task_id = _task(settings, payload={"business_id": "business-2"})

    evaluation = _refused(_assign(client, scoped, task_id))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[5]
    assert "business-2" in evaluation["reason"] and "business-1" in evaluation["reason"]

    # An agent belonging to no business cannot show it is inside one either.
    evaluation = _refused(_assign(client, agent_id, task_id))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[5]
    assert "belongs to none" in evaluation["reason"]


def test_rule_6_passes_when_both_sides_are_inside_the_same_business(client: TestClient, settings):
    agent_id = _agent(client)
    _set_agent_field(settings, agent_id, business_id="business-1")
    task_id = _task(settings, payload={"business_id": "business-1"})
    assert _assign(client, agent_id, task_id).status_code == 201


def test_rule_6_says_so_when_the_task_declares_no_business(client: TestClient, settings):
    """Honesty about what could not be checked: tasks carry no business column, so
    a task whose payload declares nothing gives the rule nothing to compare."""
    agent_id = _agent(client)
    task_id = _task(settings)
    data = _assign(client, agent_id, task_id).json()["data"]
    detail = next(c["detail"] for c in data["checks"] if c["name"] == ASSIGNMENT_RULES[5])
    assert "could not be checked" in detail, detail


def test_rule_7_refuses_a_capability_the_agent_does_not_hold(client: TestClient, settings):
    agent_id = _agent(client, capabilities=("research.read",))
    task_id = _task(settings)
    evaluation = _refused(_assign(client, agent_id, task_id,
                                  required_capabilities=["tasks.read"]))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[6]
    assert "tasks.read" in evaluation["reason"]


def test_rule_7_passes_once_the_capability_is_granted(client: TestClient, settings):
    """This is the call that gives `CapabilityService.check()` its first caller:
    until Stage 6 nothing asked the boundary Stage 5 built a question.

    The template allows `tasks.read` so that rule 8 has nothing to say and the
    refusal that disappears here can only be rule 7's.
    """
    agent_id = _agent(client, capabilities=("research.read", "tasks.read"))
    task_id = _task(settings)
    assert _grant(client, agent_id, "tasks.read").status_code == 201
    assert "tasks.read" in [g["capability_key"] for g in _held(client, agent_id)]
    response = _assign(client, agent_id, task_id, required_capabilities=["tasks.read"])
    assert response.status_code == 201, response.text


def test_rule_8_refuses_an_assignment_that_would_widen_the_agent(client: TestClient, settings):
    """Granted but not authorized by the template: the two questions are different,
    and only rule 8 asks the second one."""
    agent_id = _agent(client, capabilities=("research.read",))
    task_id = _task(settings)
    assert _grant(client, agent_id, "tasks.read").status_code == 201
    # Rule 7 now passes, so a refusal here can only come from rule 8.
    evaluation = _refused(_assign(client, agent_id, task_id,
                                  required_capabilities=["tasks.read"]))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[7]
    assert "template" in evaluation["reason"]


def test_rule_9_refuses_work_beyond_the_agent_s_own_budget(client: TestClient, settings):
    agent_id = _agent(client)
    budget = _budget(settings, agent_id)
    for index in range(budget):
        response = _assign(client, agent_id, _task(settings, name=f"task-{index}"))
        assert response.status_code == 201, (index, response.text)
    evaluation = _refused(_assign(client, agent_id, _task(settings, name="one-too-many")))
    assert _refusing_rule(evaluation) == ASSIGNMENT_RULES[8]
    assert str(budget) in evaluation["reason"]


def test_rule_9_ignores_work_that_is_finished(client: TestClient, settings):
    """Counting history would mean an agent's past limited its future."""
    agent_id = _agent(client)
    budget = _budget(settings, agent_id)
    if budget < 2:
        pytest.skip(f"a budget of {budget} cannot show that finished work stops counting")
    ids = [_assign(client, agent_id, _task(settings, name=f"t{i}")).json()["data"]["assignment_id"]
           for i in range(budget)]
    for assignment_id in ids[:-1]:
        client.post(f"/api/v1/assignments/{assignment_id}/complete",
                    json={"succeeded": True, "result": {}})
    assert _assign(client, agent_id, _task(settings, name="after")).status_code == 201


def test_rule_3_refuses_while_the_emergency_stop_is_active(client: TestClient, settings):
    """Driven at the service level with a stub stop.

    The rules are the subject here. Reaching the same refusal through HTTP would
    also be testing the emergency endpoint, and a failure would not say which of the
    two was wrong.
    """
    agent_id = _agent(client)
    task_id = _task(settings)

    class Stopped:
        async def is_active(self) -> bool:
            return True

    async def run():
        db = Database(settings)
        try:
            service = AssignmentService(db, settings, emergency=Stopped())
            return await service.assign(agent_id, task_id)
        finally:
            await db.dispose()

    outcome = asyncio.run(run())
    assert outcome.assigned is False
    assert [c.name for c in outcome.checks if not c.passed] == [ASSIGNMENT_RULES[2]]
    assert "emergency stop" in outcome.reason
    assert _rows(settings) == [], "a refusal writes no row"


# --------------------------------------------------------------------------- #
# Completion: the contract is the verification
# --------------------------------------------------------------------------- #
def test_completion_accepts_a_result_that_satisfies_the_contract(client: TestClient, settings):
    agent_id = _agent(client)
    assignment_id = _assign(
        client, agent_id, _task(settings),
        expected_output_schema={"type": "object", "required": ["summary"],
                                "properties": {"summary": {"type": "string"}}}
    ).json()["data"]["assignment_id"]
    response = client.post(f"/api/v1/assignments/{assignment_id}/complete",
                           json={"succeeded": True, "result": {"summary": "done"}})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["accepted"] is True and data["status"] == "completed"
    assert data["contract_violations"] == []
    row = _assignment_row(settings, assignment_id)
    assert row[3] == "completed" and row[7] is None


def test_completion_fails_a_reported_success_that_breaks_the_contract(client: TestClient, settings):
    """The case the whole endpoint exists for: the agent said it worked."""
    agent_id = _agent(client)
    assignment_id = _assign(
        client, agent_id, _task(settings),
        expected_output_schema={"type": "object", "required": ["summary", "score"],
                                "properties": {"score": {"type": "integer"}}}
    ).json()["data"]["assignment_id"]
    response = client.post(f"/api/v1/assignments/{assignment_id}/complete",
                           json={"succeeded": True, "result": {"summary": "done",
                                                               "score": "high"}})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["accepted"] is False
    assert data["status"] == "failed", data
    assert any("$.score: expected integer" in v for v in data["contract_violations"]), data
    row = _assignment_row(settings, assignment_id)
    assert row[3] == "failed"
    assert "output contract" in row[7]


def test_completion_records_a_reported_failure_as_a_failure(client: TestClient, settings):
    agent_id = _agent(client)
    assignment_id = _assign(client, agent_id, _task(settings)).json()["data"]["assignment_id"]
    data = client.post(f"/api/v1/assignments/{assignment_id}/complete",
                       json={"succeeded": False, "reason": "the source refused"}
                       ).json()["data"]
    assert data["status"] == "failed" and data["accepted"] is False
    assert _assignment_row(settings, assignment_id)[7] == "the source refused"


def test_an_undeclared_contract_is_recorded_unjudged_and_says_so(client: TestClient, settings):
    """Not a silent pass: the reason states that nothing was checked."""
    agent_id = _agent(client)
    assignment_id = _assign(client, agent_id, _task(settings)).json()["data"]["assignment_id"]
    data = client.post(f"/api/v1/assignments/{assignment_id}/complete",
                       json={"succeeded": True, "result": {"anything": 1}}).json()["data"]
    assert data["accepted"] is True and data["status"] == "completed"
    assert "unjudged" in data["reason"], data


# --------------------------------------------------------------------------- #
# Lifecycle and reads
# --------------------------------------------------------------------------- #
def test_start_then_complete_moves_through_the_vocabulary(client: TestClient, settings):
    agent_id = _agent(client)
    assignment_id = _assign(client, agent_id, _task(settings)).json()["data"]["assignment_id"]
    assert client.post(f"/api/v1/assignments/{assignment_id}/start").status_code == 200
    assert _assignment_row(settings, assignment_id)[3] == "in_progress"
    assert client.post(f"/api/v1/assignments/{assignment_id}/complete",
                       json={"succeeded": True, "result": {}}).status_code == 200
    assert _assignment_row(settings, assignment_id)[3] == "completed"


def test_transitions_are_forward_only(client: TestClient, settings):
    agent_id = _agent(client)
    assignment_id = _assign(client, agent_id, _task(settings)).json()["data"]["assignment_id"]
    assert client.post(f"/api/v1/assignments/{assignment_id}/cancel",
                       json={"reason": "withdrawn"}).status_code == 200
    for method, payload in (("complete", {"succeeded": True, "result": {}}),
                            ("start", None), ("cancel", {"reason": "again"})):
        response = client.post(f"/api/v1/assignments/{assignment_id}/{method}",
                               json=payload or {})
        assert response.status_code == 409, (method, response.text)
        assert response.json()["error"]["code"] == "assignment_transition_invalid"


def test_starting_before_an_assignment_exists_is_a_404(client: TestClient, settings):
    _agent(client)
    response = client.post("/api/v1/assignments/not-real/start", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "assignment_not_found"


def test_the_ledger_reads_back_with_the_task_state_beside_it(client: TestClient, settings):
    agent_id = _agent(client)
    task_id = _task(settings)
    _assign(client, agent_id, task_id)
    body = client.get("/api/v1/assignments").json()
    assert body["meta"]["total"] == 1
    row = body["data"][0]
    assert row["task_id"] == task_id and row["agent_id"] == agent_id
    assert row["task_status"] == "QUEUED", "the task's own state is resolved at read time"

    per_agent = client.get(f"/api/v1/agents/{agent_id}/assignments").json()
    assert per_agent["meta"]["total"] == 1
    single = client.get(f"/api/v1/assignments/{row['id']}").json()["data"]
    assert single["id"] == row["id"]


def test_the_ledger_filters_by_status(client: TestClient, settings):
    agent_id = _agent(client)
    kept = _assign(client, agent_id, _task(settings, name="kept")).json()["data"]["assignment_id"]
    _assign(client, agent_id, _task(settings, name="closed"))
    closed = _rows(settings)[-1][0]
    client.post(f"/api/v1/assignments/{closed}/cancel", json={"reason": "no longer needed"})
    assert client.get("/api/v1/assignments", params={"status": "cancelled"}
                      ).json()["meta"]["total"] == 1
    assert client.get("/api/v1/assignments", params={"status": "assigned"}
                      ).json()["meta"]["total"] == 1
    assert kept


# --------------------------------------------------------------------------- #
# ASSIGN_EXISTING: declared at Stage 4, emitted from Stage 6
# --------------------------------------------------------------------------- #
def test_the_factory_emits_assign_existing_when_the_request_names_a_task(client: TestClient, settings):
    template = _published(client, name="researcher", allowed_capabilities=["research.read"])
    first = _ask(client, template_id=template["id"], requested_capabilities=["research.read"])
    assert first["decision"] == "CREATE_AGENT", first
    # A created agent holds no grants (L-73), so the work would be refused at rule 7
    # for a reason unrelated to the decision under test.
    assert _grant(client, first["agent_id"], "research.read").status_code == 201

    task_id = _task(settings)
    second = _ask(client, template_id=template["id"],
                  requested_capabilities=["research.read"], task_id=task_id)
    assert second["decision"] == "ASSIGN_EXISTING", second
    assert second["agent_id"] == first["agent_id"]

    # The decision is not just a label: the nine rules ran and the work was handed over.
    rows = _rows(settings)
    assert len(rows) == 1, rows
    assert rows[0][2] == task_id and rows[0][1] == first["agent_id"]


def test_the_factory_still_emits_reuse_existing_when_no_work_is_named(client: TestClient, settings):
    """The regression this guards: naming work is what separates the two decisions,
    so not naming it must leave the Stage-4 answer untouched."""
    template = _published(client, name="researcher", allowed_capabilities=["research.read"])
    assert _ask(client, template_id=template["id"],
                requested_capabilities=["research.read"])["decision"] == "CREATE_AGENT"
    second = _ask(client, template_id=template["id"],
                  requested_capabilities=["research.read"])
    assert second["decision"] == "REUSE_EXISTING", second
    assert _rows(settings) == [], "reusing an identity assigns no work"


def test_assign_existing_records_a_refusal_instead_of_assigning(client: TestClient, settings):
    """The factory deciding that an agent *should* take work is not evidence that it
    *may*: the rules still run, and their answer is recorded on the request."""
    template = _published(client, name="researcher", allowed_capabilities=["research.read"])
    first = _ask(client, template_id=template["id"], requested_capabilities=["research.read"])
    assert first["decision"] == "CREATE_AGENT"
    task_id = _task(settings, payload={"business_id": "somewhere-else"})
    second = _ask(client, template_id=template["id"],
                  requested_capabilities=["research.read"], task_id=task_id)
    assert second["decision"] == "ASSIGN_EXISTING", second
    # The response carries the factory's reason; what the assignment did is recorded
    # on the creation request, which is where a later reader will look.
    assert _rows(settings) == [], "a refused assignment must not create a row"
    reason = _creation_reason(settings, second["request_id"])
    assert "not assigned" in reason and "business" in reason, reason
