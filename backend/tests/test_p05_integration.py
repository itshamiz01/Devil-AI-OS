"""P-05 integration tests: migration cycle, end-to-end adapter flows,
acceptance scenarios A–E + workflow behaviour, approval lifecycle,
standing authorizations, mode gates — over the real substrate."""
from __future__ import annotations

import pytest

from app.execution.adapters.api import MockTransport, TransportResponse
from app.execution.schemas import (
    ExecutionRequestIn, StandingAuthorizationIn, WorkflowDefinitionIn,
    WorkflowRunIn,
)
from app.permissions.models import Principal, PrincipalType
from tests.conftest import OWNER
from tests.p05_support import (
    app_rw, client_rw, create_agent_http, engine, grant, grant_http,
    make_agent, owner_headers,
)

AGENT = Principal(PrincipalType.AGENT, "placeholder")


# ------------------------------------------------------------------ migration
def test_p05_migration_cycle(tmp_path):
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    db = tmp_path / "cycle.db"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "app" / "database" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")

    command.upgrade(cfg, "a694abea811f")
    con = sqlite3.connect(db)
    before = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    execution_tables = {t for t in tables if t.startswith("execution_")}
    assert len(execution_tables) == 10, execution_tables
    # P-06 disclosure: "head" has since advanced to the additive P-06
    # migration (a8d7e0c717b4 revises 6ffcc7e899fa). The version pin is
    # updated to the new head; the execution-table assertions and the
    # exact downgrade comparison below are unchanged in kind.
    # P-07 disclosure: head advanced again by the additive P-07
    # migration (c3b5cdba2559 revises a8d7e0c717b4); same update,
    # same strictness.
    # P-08 disclosure: head advanced again by the additive P-08 migration (99902c03a197 revises c3b5cdba2559); same update, same strictness.
    # P-09 disclosure: head advanced again by the additive P-09 migration (7b13db7e9bfa revises 99902c03a197); same update, same strictness.
    # P-10 disclosure: head advanced again by the additive P-10 migration (e37d00443d20 revises 7b13db7e9bfa); same update, same strictness.
    # P-11 disclosure: head advanced again by the additive P-11 migration (193731df4c37 revises e37d00443d20); same update, same strictness.
    # P-12 disclosure: head advanced again by the additive P-12 migration (3a77efe78faa revises 193731df4c37); same update, same strictness.
    # P-13 disclosure: head advanced again by the additive P-13 migration (d02b4208d228 revises 3a77efe78faa); same update, same strictness.
    # P-14 disclosure: head advanced again by the additive P-14 Stage B migration (4d41d6a6a605 revises d02b4208d228); same update, same strictness.
    # P-16 disclosure: head advanced again by the additive P-16 migration (ccd744b29e54 revises d12e4d6cf5ef); same update, same strictness.
        # P-17 disclosure: head advanced again by the additive P-17 migration (afe062122eb5 revises ccd744b29e54); same update, same strictness.
        # P-18 disclosure: head advanced again by the additive P-18 migration (218ddd92a0aa revises afe062122eb5); same update, same strictness.
    # Expansion F01 disclosure: head advanced again by the
    # additive Expansion Feature 1 migration (85b7a9805207
    # revises 218ddd92a0aa); same update, same strictness.
    # Expansion F02 disclosure: head advanced again by the additive
    # Expansion Feature 2 migration (3f7a1c9e52b4 revises
    # 85b7a9805207); same update, same strictness.
    # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
    # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] \
        == "af39baad9c40"
    con.close()

    command.downgrade(cfg, "a694abea811f")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {t for t in tables if t.startswith("execution_")}
    assert tables == before
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    # Head is now the additive P-06 migration (see disclosure above).
    # P-07 disclosure: head advanced again by the additive P-07
    # migration (c3b5cdba2559 revises a8d7e0c717b4); same update,
    # same strictness.
    # P-08 disclosure: head advanced again by the additive P-08 migration (99902c03a197 revises c3b5cdba2559); same update, same strictness.
    # P-09 disclosure: head advanced again by the additive P-09 migration (7b13db7e9bfa revises 99902c03a197); same update, same strictness.
    # P-10 disclosure: head advanced again by the additive P-10 migration (e37d00443d20 revises 7b13db7e9bfa); same update, same strictness.
    # P-11 disclosure: head advanced again by the additive P-11 migration (193731df4c37 revises e37d00443d20); same update, same strictness.
    # P-12 disclosure: head advanced again by the additive P-12 migration (3a77efe78faa revises 193731df4c37); same update, same strictness.
    # P-13 disclosure: head advanced again by the additive P-13 migration (d02b4208d228 revises 3a77efe78faa); same update, same strictness.
    # P-14 disclosure: head advanced again by the additive P-14 Stage B migration (4d41d6a6a605 revises d02b4208d228); same update, same strictness.
    # P-16 disclosure: head advanced again by the additive P-16 migration (ccd744b29e54 revises d12e4d6cf5ef); same update, same strictness.
        # P-17 disclosure: head advanced again by the additive P-17 migration (afe062122eb5 revises ccd744b29e54); same update, same strictness.
        # P-18 disclosure: head advanced again by the additive P-18 migration (218ddd92a0aa revises afe062122eb5); same update, same strictness.
    # Expansion F01 disclosure: head advanced again by the
    # additive Expansion Feature 1 migration (85b7a9805207
    # revises 218ddd92a0aa); same update, same strictness.
    # Expansion F02 disclosure: head advanced again by the additive
    # Expansion Feature 2 migration (3f7a1c9e52b4 revises
    # 85b7a9805207); same update, same strictness.
    # Expansion F03 disclosure: head/count advanced by the additive Expansion Feature 3 migration (c41f7a9d03e6 revises 3f7a1c9e52b4; +4 voice tables); same update, same strictness.
    # Expansion F06 disclosure: head/count advanced by the additive Expansion Feature 6 migration (af39baad9c40 revises c41f7a9d03e6; +3 knowledge tables); same update, same strictness.
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] \
        == "af39baad9c40"
    con.close()


# ------------------------------------------------------- Scenario A (service)
async def test_scenario_a_research_agent_report_verified(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    await grant(app_rw, agent_id, "file_write")
    service = engine(app_rw)
    workspace = f"agent:{agent_id}"
    request = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="documents", action="create_text",
        parameters={"workspace": workspace, "path": "reports/weekly.md",
                    "content": "# Weekly Research Report\n\nFindings verified."},
        expected_outcome={"file": {"workspace": workspace, "path": "reports/weekly.md",
                                   "content_contains": "Weekly Research Report"}}))
    assert request.status == "COMPLETED"
    assert request.verification_status == "verified"
    # Four separate facts (§6).
    assert request.requested_action["action"] == "create_text"
    assert request.executed_action["run_id"]
    assert request.verified_outcome["checks"][0]["passed"] is True
    evidence = service.evidence_for_request(request.id)
    assert evidence and evidence[0]["content_hash"] == \
        request.verified_outcome["checks"][0]["sha256"]
    # The file is really in the agent's own workspace.
    read_back = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": workspace, "path": "reports/weekly.md"}))
    assert read_back.status == "COMPLETED"
    runs = service.list_requests(agent_id=agent_id)[0]
    assert len(runs) == 2


async def test_scenario_a_over_http(client_rw, owner_headers):
    agent_id = create_agent_http(client_rw, owner_headers)
    grant_http(client_rw, owner_headers, agent_id, "file_read")
    grant_http(client_rw, owner_headers, agent_id, "file_write")
    resp = client_rw.post("/api/v1/execution/documents/create_text",
                          headers=owner_headers, json={
                              "agent_id": agent_id,
                              "parameters": {"workspace": f"agent:{agent_id}",
                                             "path": "report.md",
                                             "content": "# Report\n\nHTTP-created."},
                              "expected_outcome": {
                                  "file": {"workspace": f"agent:{agent_id}",
                                           "path": "report.md",
                                           "content_contains": "HTTP-created"}}})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["verification_status"] == "verified"
    resp = client_rw.get(f"/api/v1/execution/requests/{data['id']}/evidence",
                         headers=owner_headers)
    assert resp.json()["data"], "evidence recorded"
    resp = client_rw.get("/api/v1/execution/health-report", headers=owner_headers)
    report = resp.json()["data"]
    assert report["desktop_adapter"].startswith("disabled")
    assert "process_controls_only" in report["code_isolation"]


# ------------------------------------------------------------ Scenario B (code)
async def test_scenario_b_approved_python_execution(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "sandboxed_code_execution")
    service = engine(app_rw)
    request = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="code_python", action="run",
        parameters={"code": "print('total', sum(range(10)))",
                    "inputs": {"note.txt": "hello"}},
        expected_outcome={"output_contains": "total 45", "exit_code": 0}))
    assert request.status == "COMPLETED"
    run_output = request.executed_action
    assert run_output["adapter"] == "code"
    evidence = service.evidence_for_request(request.id)
    assert evidence and evidence[0]["type"] == "code_execution"
    assert evidence[0]["details"]["isolation"] == "process_controls_only"
    # Cleanup: no run directory remains under the temporary workspace.
    temp_root = service.workspaces.temporary_root() / "code_runs"
    leftovers = list(temp_root.iterdir()) if temp_root.exists() else []
    assert leftovers == []


async def test_code_environment_is_scrubbed(app_rw, monkeypatch):
    """Adapter-level proof (the policy screen separately forbids agents
    from reading os.environ at all — §25.3 #6): the child process
    environment is built from an allowlist, so a secret present in the
    SERVER environment never reaches executed code."""
    monkeypatch.setenv("AUTONOMUS_ADMIN_PASSWORD", "should-never-leak")
    service = engine(app_rw)
    from app.execution.adapters.base import AdapterContext
    adapter = service.adapters["code"]
    result = await adapter.execute(
        "run", {"code": "import os, json\n"
                        "print(json.dumps(sorted(os.environ.keys())))"},
        AdapterContext(agent_id="env-probe", request_id="env-probe-1",
                       mode="controlled", settings=service.settings_values()))
    assert result.success, result.summary
    keys = result.output["stdout"]
    assert "should-never-leak" not in str(result.output)
    assert "AUTONOMUS_ADMIN_PASSWORD" not in keys
    assert "AUTONOMUS_EXECUTION" in keys


# --------------------------------------------------------- Scenario C (browser)
def _page_transport():
    html = (b"<html><head><title>Example Domain</title></head><body>"
            b"<h1>Example Domain</h1><p>Price: $42</p>"
            b"<a href='/more'>More</a></body></html>")
    return MockTransport({
        "https://example.com/": TransportResponse(
            url="https://example.com/", status=200, body=html),
        "https://example.com/more": TransportResponse(
            url="https://example.com/more", status=200,
            body=b"<html><head><title>More</title></head><body>details</body></html>"),
    })


async def test_scenario_c_browser_readonly_research(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "browser_interaction")
    transport = _page_transport()
    service = engine(app_rw, browser_transport=transport)
    opened = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="open_session",
        parameters={"allowed_domains": ["example.com"],
                    "start_url": "https://example.com/"}))
    assert opened.status == "COMPLETED"
    session_id = opened.executed_action and None  # output checked via runs below
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import (
            BrowserSessionRepository, ExecutionRunRepository)
        sessions = BrowserSessionRepository(session).list(agent_id=agent_id)[0]
        assert len(sessions) == 1
        session_id = sessions[0].id
        run = ExecutionRunRepository(session).for_request(opened.id)[0]
        assert run.result["output"]["session_id"] == session_id
    finally:
        session.close()
    navigated = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="navigate",
        parameters={"session_id": session_id, "url": "https://example.com/"}))
    assert navigated.status == "COMPLETED"
    evidence = service.evidence_for_request(navigated.id)
    assert any(e["type"] == "browser_page" for e in evidence)
    # No external write occurred: every request in the system is a browser
    # read-path action for this agent.
    rows, _ = service.list_requests(agent_id=agent_id)
    assert {r.tool_name for r in rows} == {"browser"}


# -------------------------------------------------- Scenario D (approval hold)
async def test_scenario_d_sensitive_action_held_until_approval(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "browser_interaction")
    service = engine(app_rw, browser_transport=_page_transport())
    request = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="interact",
        parameters={"session_id": "any", "interaction": "submit_form"}))
    assert request.status == "AWAITING_APPROVAL"
    assert request.approval_id
    # Nothing executed before approval: no runs exist.
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import ExecutionRunRepository
        assert ExecutionRunRepository(session).count_for_request(request.id) == 0
    finally:
        session.close()
    # The owner can inspect the exact intended action via the approval.
    approval = app_rw.approvals.get(request.approval_id)
    assert approval.parameters["tool"] == "browser"
    assert approval.parameters["action"] == "interact"
    # After approval the request executes — and fails TRUTHFULLY here:
    # no live browser engine exists in this environment (audit §7).
    app_rw.approvals.decide(request.approval_id, OWNER, True)
    executed = await service.execute(OWNER, request.id)
    assert executed.status == "FAILED"
    assert executed.error_category == "ADAPTER_UNAVAILABLE"


# ----------------------------------------------------- Scenario E (auth wall)
async def test_scenario_e_auth_challenge_requires_human(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "browser_interaction")
    login_html = (b"<html><body><form><input type='password' name='pw'>"
                  b"</form>Sign in</body></html>")
    transport = MockTransport({
        "https://example.com/login": TransportResponse(
            url="https://example.com/login", status=200, body=login_html)})
    service = engine(app_rw, browser_transport=transport)
    opened = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="open_session",
        parameters={"allowed_domains": ["example.com"]}))
    assert opened.status == "COMPLETED"
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import BrowserSessionRepository
        session_id = BrowserSessionRepository(session).list(agent_id=agent_id)[0][0].id
    finally:
        session.close()
    navigated = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="navigate",
        parameters={"session_id": session_id, "url": "https://example.com/login"}))
    assert navigated.status == "REQUIRES_HUMAN_ACTION"
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import BrowserSessionRepository
        row = BrowserSessionRepository(session).get(session_id)
        assert row.status == "requires_human"
    finally:
        session.close()


# ------------------------------------------------------- standing authorization
async def test_standing_authorization_covers_risk2_and_is_consumed(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "api_write")
    transport = MockTransport({
        ("POST", "https://api.example.com/items"): TransportResponse(
            url="https://api.example.com/items", status=201, body=b'{"id": 1}')})
    service = engine(app_rw, api_transport=transport)
    service.update_settings(OWNER, {"api_allowlist": ["api.example.com"]})
    auth = service.create_standing_authorization(OWNER, StandingAuthorizationIn(
        tool_name="api_http", action_name="post",
        scope_pattern="api_http:post:api.example.com", agent_id=agent_id,
        max_uses=1, expires_in_minutes=60))
    request = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="api_http", action="post",
        parameters={"url": "https://api.example.com/items", "body": "{}"}))
    assert request.status == "COMPLETED"
    assert request.standing_authorization_id == auth.id
    assert request.approved_action["via"] == "standing_authorization"
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import StandingAuthorizationRepository
        row = StandingAuthorizationRepository(session).get(auth.id)
        assert row.uses == 1 and row.status == "exhausted"
    finally:
        session.close()
    # Exhausted: the next identical request needs a fresh approval.
    second = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="api_http", action="post",
        parameters={"url": "https://api.example.com/items", "body": "{}"}))
    assert second.status == "AWAITING_APPROVAL"


async def test_api_credential_reference_resolved_by_broker_only(app_rw):
    from app.execution.credentials import DictCredentialBroker
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "api_read")
    transport = MockTransport({
        ("GET", "https://api.example.com/me"): TransportResponse(
            url="https://api.example.com/me", status=200, body=b'{"ok": true}')})
    service = engine(app_rw, api_transport=transport,
                     broker=DictCredentialBroker({"API_TOKEN": "s3cr3t-value"}))
    service.update_settings(OWNER, {"api_allowlist": ["api.example.com"]})
    request = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="api_http", action="get",
        parameters={"url": "https://api.example.com/me",
                    "credential_ref": "env:API_TOKEN"}))
    assert request.status == "COMPLETED"
    # The broker value reached the transport header — and ONLY there.
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer s3cr3t-value"
    assert "s3cr3t-value" not in str(request.parameters)
    assert "s3cr3t-value" not in str(request.result_summary)
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import ExecutionRunRepository
        run = ExecutionRunRepository(session).for_request(request.id)[0]
        assert "s3cr3t-value" not in str(run.result)
    finally:
        session.close()


# ------------------------------------------------------------------- workflows
async def _workflow_agent(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    await grant(app_rw, agent_id, "file_write")
    return agent_id


async def test_workflow_two_steps_complete_with_checkpoint(app_rw):
    agent_id = await _workflow_agent(app_rw)
    service = engine(app_rw)
    definition = service.workflows.create_definition(OWNER, WorkflowDefinitionIn(
        name="write-then-read", version=1, definition={"steps": [
            {"id": "write", "tool": "documents", "action": "create_text",
             "parameters": {"workspace": f"agent:{agent_id}", "path": "note.txt",
                            "content": "checkpointed"}},
            {"id": "read", "tool": "filesystem", "action": "read",
             "parameters": {"workspace": f"agent:{agent_id}", "path": "note.txt"},
             "expected_outcome": {"output_contains": "checkpointed"}},
        ]}))
    run = await service.workflows.start_run(
        OWNER, definition.id, WorkflowRunIn(agent_id=agent_id))
    assert run.status == "COMPLETED"
    assert run.checkpoint["completed_steps"] == ["write", "read"]
    assert set(run.checkpoint["step_outputs"]) == {"write", "read"}


async def test_workflow_compensation_on_failure(app_rw):
    agent_id = await _workflow_agent(app_rw)
    service = engine(app_rw)
    definition = service.workflows.create_definition(OWNER, WorkflowDefinitionIn(
        name="compensating", version=1, definition={"steps": [
            {"id": "create", "tool": "documents", "action": "create_text",
             "parameters": {"workspace": f"agent:{agent_id}", "path": "temp.txt",
                            "content": "to be compensated"},
             "compensation": {"tool": "filesystem", "action": "delete",
                              "parameters": {"workspace": f"agent:{agent_id}",
                                             "path": "temp.txt"}}},
            {"id": "boom", "tool": "filesystem", "action": "read",
             "parameters": {"workspace": f"agent:{agent_id}", "path": "missing.txt"}},
        ]}))
    run = await service.workflows.start_run(
        OWNER, definition.id, WorkflowRunIn(agent_id=agent_id))
    assert run.status == "FAILED"
    assert run.checkpoint["compensated_steps"] == ["create"]
    # The created file was quarantined by compensation (not hard-deleted).
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import WorkflowStepRunRepository
        steps = {s.step_id: s for s in
                 WorkflowStepRunRepository(session).for_run(run.id)}
        assert steps["create"].status == "compensated"
        assert steps["boom"].status == "failed"
    finally:
        session.close()
    quarantine = service.workspaces.quarantine_workspace()
    from pathlib import Path
    assert list(Path(quarantine.root_path).iterdir()), "compensation quarantined the file"


async def test_workflow_step_approval_blocks_then_resumes(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "api_write")
    transport = MockTransport({
        ("POST", "https://api.example.com/items"): TransportResponse(
            url="https://api.example.com/items", status=201, body=b'{"id": 7}')})
    service = engine(app_rw, api_transport=transport)
    service.update_settings(OWNER, {"api_allowlist": ["api.example.com"]})
    definition = service.workflows.create_definition(OWNER, WorkflowDefinitionIn(
        name="api-workflow", version=1, definition={"steps": [
            {"id": "post", "tool": "api_http", "action": "post",
             "parameters": {"url": "https://api.example.com/items", "body": "{}"}},
        ]}))
    run = await service.workflows.start_run(
        OWNER, definition.id, WorkflowRunIn(agent_id=agent_id))
    assert run.status == "AWAITING_APPROVAL"
    assert transport.calls == []
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import WorkflowStepRunRepository
        step = WorkflowStepRunRepository(session).for_run(run.id)[0]
        request = service.get_request(step.execution_request_id)
    finally:
        session.close()
    app_rw.approvals.decide(request.approval_id, OWNER, True)
    run = await service.workflows.resume(OWNER, run.id)
    assert run.status == "COMPLETED"
    assert len(transport.calls) == 1


# ------------------------------------------------- Scenario J (emergency stop)
async def test_scenario_j_emergency_stop_and_resume(app_rw):
    agent_id = await _workflow_agent(app_rw)
    await grant(app_rw, agent_id, "browser_interaction")
    from app.execution.adapters.api import MockTransport
    service = engine(app_rw, browser_transport=MockTransport({}))
    opened = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="browser", action="open_session",
        parameters={"allowed_domains": ["example.com"]}))
    assert opened.status == "COMPLETED"

    report = await service.emergency_stop(OWNER)
    assert report["emergency_stop"] is True
    assert report["browser_sessions_paused"] >= 1
    # New work is blocked while the stop is active (policy check 1).
    blocked = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="list",
        parameters={"workspace": "shared", "path": ""}))
    assert blocked.status == "REJECTED"
    assert "emergency stop" in blocked.result_summary
    # The browser session was paused, not silently dropped.
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import BrowserSessionRepository
        rows = BrowserSessionRepository(session).list(agent_id=agent_id)[0]
        assert rows[0].status == "paused"
    finally:
        session.close()
    # Audit records for the stop are intact.
    audit = service.audit_for_request(blocked.id)
    assert audit  # the blocked submission itself was audited
    # Resume restores normal operation.
    resumed = service.emergency_resume(OWNER)
    assert resumed["emergency_stop"] is False
    after = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="list",
        parameters={"workspace": "shared", "path": ""}))
    assert after.status == "COMPLETED"


# ------------------------------------------------------------------ mode gates
async def test_simulation_mode_refuses_writes_but_allows_reads(application):
    """The default P-01 test application runs in simulation mode."""
    agent_id = await make_agent(application)
    await grant(application, agent_id, "file_read")
    await grant(application, agent_id, "file_write")
    service = engine(application)
    write = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="documents", action="create_text",
        parameters={"workspace": f"agent:{agent_id}", "path": "x.txt", "content": "no"}))
    assert write.status == "REJECTED"
    assert "simulation" in write.result_summary
    read = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="list",
        parameters={"workspace": "shared", "path": ""}))
    assert read.status == "COMPLETED"


# ----------------------------------------------------------- documents and CSV
async def test_csv_create_transform_summarize(app_rw):
    agent_id = await _workflow_agent(app_rw)
    service = engine(app_rw)
    workspace = f"agent:{agent_id}"
    created = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="documents", action="create_csv",
        parameters={"workspace": workspace, "path": "data.csv",
                    "headers": ["name", "city", "score"],
                    "rows": [{"name": "a", "city": "Lahore", "score": "10"},
                             {"name": "b", "city": "Karachi", "score": "20"},
                             {"name": "c", "city": "Lahore", "score": "30"}]}))
    assert created.status == "COMPLETED"
    transformed = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="documents", action="transform_csv",
        parameters={"workspace": workspace, "source_path": "data.csv",
                    "dest_path": "lahore.csv", "columns": ["name", "score"],
                    "filters": {"city": "Lahore"}},
        expected_outcome={"file": {"workspace": workspace, "path": "lahore.csv",
                                   "content_contains": "a,10"}}))
    assert transformed.status == "COMPLETED"
    summary = await service.submit_and_execute(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="documents", action="summarize_csv",
        parameters={"workspace": workspace, "path": "data.csv"},
        expected_outcome={"output_contains": "row_count"}))
    assert summary.status == "COMPLETED"


# ------------------------------------------------------ filesystem full cycle
async def test_filesystem_write_append_copy_delete_quarantine_cycle(app_rw):
    agent_id = await _workflow_agent(app_rw)
    service = engine(app_rw)
    workspace = f"agent:{agent_id}"

    async def run(action, **params):
        return await service.submit_and_execute(OWNER, ExecutionRequestIn(
            agent_id=agent_id, tool="filesystem", action=action, parameters=params))

    assert (await run("create", workspace=workspace, path="a.txt",
                      content="one")).status == "COMPLETED"
    assert (await run("append", workspace=workspace, path="a.txt",
                      content=" two")).status == "COMPLETED"
    copied = await run("copy", source_workspace=workspace, source_path="a.txt",
                       dest_workspace=workspace, dest_path="b.txt")
    assert copied.status == "COMPLETED"
    deleted = await run("delete", workspace=workspace, path="b.txt")
    assert deleted.status == "COMPLETED"
    # Quarantined, not gone: permanent deletion is the separate Risk-2 act.
    listing = await run("list", workspace="quarantine", path="")
    assert listing.status == "COMPLETED"
    permanent = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="delete_permanent",
        parameters={"workspace": "quarantine",
                    "path": deleted.executed_action and _quarantine_name(app_rw, service, deleted)}))
    assert permanent.status == "AWAITING_APPROVAL"
    app_rw.approvals.decide(permanent.approval_id, OWNER, True)
    permanent = await service.execute(OWNER, permanent.id)
    assert permanent.status == "COMPLETED"


def _quarantine_name(app_rw, service, deleted_request) -> str:
    session = app_rw.session_factory()
    try:
        from app.database.repositories.execution import ExecutionRunRepository
        run = ExecutionRunRepository(session).for_request(deleted_request.id)[0]
        return run.result["output"]["quarantined_as"]
    finally:
        session.close()
