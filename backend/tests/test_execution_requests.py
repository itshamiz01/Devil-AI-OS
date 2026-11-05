"""P-05 Stage 2: the tool registry and the request manager, end to end.

The registry half proves the §7 discipline: registration declares, validation
admits, and a tool that cannot run here - or has not declared what it does -
cannot be made available by asking nicely.

The request half proves the §4 lifecycle's first seven steps against a real
database: identity from the principal, policy's ten checks, a Risk 2 request
held for an approval in the central table (bound by hash, so a substituted
request is caught), standing authorizations with their limits, idempotency,
and cancellation. Every refusal asserts the resulting row: a policy refusal
must exist at REJECTED with its reason, because that row is the audit trail;
a structural refusal must not invent one.
"""
import asyncio
import pytest
from sqlalchemy import select

from app.agents.capabilities import CapabilityService
from app.core.application import seed_core_data
from app.database.connection import Database
from app.database.models import Agent, AuditEvent, Principal, Task
from app.database.repositories import ConfigRepo
from app.execution.registry import (
    ToolNotFoundError,
    ToolRegistrationError,
    ToolTransitionError,
)
from app.execution.requests import (
    STANDING_AUTHORIZATIONS_KEY,
    ExecutionIdentityError,
    ExecutionRequestNotFoundError,
    ExecutionTransitionError,
)
from app.execution.schemas import ExecutionRequestInput, ToolRegistrationInput
from app.execution.subsystem import build_execution, initialize
from app.monitoring.system_monitor import SystemMonitor
from app.permissions.approvals import ApprovalService
from app.permissions.models import ApprovalDecisionRequest


class _Bus:
    def __init__(self):
        self.events = []

    async def publish_new(self, event_type, source, payload=None, **kwargs):
        self.events.append((event_type, payload or {}))


def _run(settings, body):
    """Boot the subsystem once and hand the body the world it needs."""

    async def go():
        db = Database(settings)
        try:
            await db.initialize()
            await seed_core_data(db, settings)
            bus = _Bus()
            approvals = ApprovalService(db, bus)
            capabilities = CapabilityService(db, settings)
            # What production's agent-subsystem startup does: without the
            # catalog rows, every capability check would answer "not in the
            # catalog" and the interesting verdicts would never be reached.
            await capabilities.reconcile_catalog()
            execution = build_execution(
                settings, db, bus,
                capabilities=capabilities,
                approvals=approvals, monitor=SystemMonitor(settings))
            await initialize(execution)
            async with db.session_factory() as session:
                owner = Principal(kind="owner", name="owner")
                session.add(owner)
                await session.flush()
                world = {"owner_id": owner.id, "bus": bus}
                await session.commit()
            return await body(db, execution, approvals, world)
        finally:
            await db.dispose()

    return asyncio.run(go())


async def _world(db, *, agent_status="ACTIVE", assigned=True):
    async with db.session_factory() as session:
        import uuid
        principal = Principal(kind="agent", name=f"agent-{uuid.uuid4().hex[:8]}")
        session.add(principal)
        await session.flush()
        agent = Agent(principal_id=principal.id, name=f"worker-{principal.id[:8]}",
                      role="research", status=agent_status)
        session.add(agent)
        await session.flush()
        owner = (await session.execute(
            select(Principal).where(Principal.kind == "owner"))).scalars().first()
        task = Task(name="job", handler="test.handler", status="QUEUED",
                    creator_id=owner.id,
                    assigned_agent_id=agent.id if assigned else None)
        session.add(task)
        await session.flush()
        await session.commit()
        return {"agent_id": agent.id, "principal_id": principal.id,
                "task_id": task.id}


async def _tool(execution, actor, **over):
    definition = {"name": "fs.work", "adapter_type": "filesystem",
                  "supported_actions": ["read", "write"], "risk_level": 0}
    definition.update(over)
    tool = await execution.registry.register(
        ToolRegistrationInput(**definition), actor=actor)
    await execution.registry.validate_tool(tool.id, actor=actor)
    return await execution.registry.get_tool(tool.id)


def _request(task_id, tool_id, **over):
    payload = {"task_id": task_id, "tool_id": tool_id, "action_name": "read",
               "requested_scope": "workspace:reports"}
    payload.update(over)
    return ExecutionRequestInput(**payload)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registration_declares_and_validation_admits(settings):
    async def body(db, execution, approvals, world):
        tool = await execution.registry.register(
            ToolRegistrationInput(name="fs.work", adapter_type="filesystem",
                                  supported_actions=["read"], risk_level=0),
            actor=world["owner_id"])
        assert tool.status == "REGISTERED"
        result = await execution.registry.validate_tool(tool.id, actor=world["owner_id"])
        assert result.available and result.status == "AVAILABLE"
        checks = {c["name"]: c["passed"] for c in result.checks}
        assert all(checks.values()) and len(checks) == 5
        return tool.id
    tool_id = _run(settings, body)
    assert tool_id


def test_a_tool_cannot_register_twice_or_with_an_unknown_adapter(settings):
    async def body(db, execution, approvals, world):
        definition = ToolRegistrationInput(name="fs.work", adapter_type="filesystem")
        await execution.registry.register(definition, actor=world["owner_id"])
        with pytest.raises(ToolRegistrationError):
            await execution.registry.register(definition, actor=world["owner_id"])
        with pytest.raises(ToolRegistrationError):
            await execution.registry.register(
                ToolRegistrationInput(name="x", adapter_type="telepathy"),
                actor=world["owner_id"])
    _run(settings, body)


def test_validation_refuses_what_cannot_run_or_has_not_declared_itself(settings):
    async def body(db, execution, approvals, world):
        # A browser tool cannot be validated available in this environment.
        browser = await execution.registry.register(
            ToolRegistrationInput(name="web", adapter_type="browser",
                                  supported_actions=["navigate"], risk_level=2,
                                  required_approval_level=2),
            actor=world["owner_id"])
        result = await execution.registry.validate_tool(browser.id, actor=world["owner_id"])
        assert not result.available and result.status == "DISABLED"
        failed = [c["name"] for c in result.checks if not c["passed"]]
        assert failed == ["adapter_supported"]

        # A code tool that has not declared its isolation cannot be available:
        # §30 rule 22 forbids claiming unverified sandbox security.
        code = await execution.registry.register(
            ToolRegistrationInput(name="code.run", adapter_type="code",
                                  supported_actions=["run"], risk_level=1),
            actor=world["owner_id"])
        result = await execution.registry.validate_tool(code.id, actor=world["owner_id"])
        failed = [c["name"] for c in result.checks if not c["passed"]]
        assert failed == ["isolation_declared"]

        code = await execution.registry.register(
            ToolRegistrationInput(
                name="code.run", version="1.0.1", adapter_type="code",
                supported_actions=["run"], risk_level=1,
                isolation_strength="subprocess-with-timeout (weak)"),
            actor=world["owner_id"])
        result = await execution.registry.validate_tool(code.id, actor=world["owner_id"])
        assert result.available

        # A Risk 3 tool can never be routed, so it can never be available.
        dangerous = await execution.registry.register(
            ToolRegistrationInput(name="bad", adapter_type="filesystem",
                                  supported_actions=["anything"], risk_level=3),
            actor=world["owner_id"])
        result = await execution.registry.validate_tool(dangerous.id, actor=world["owner_id"])
        assert not result.available
        assert "risk_permitted" in [c["name"] for c in result.checks if not c["passed"]]

        # An available tool cannot be re-validated from AVAILABLE, and a
        # disabled one can always be disabled again only through transitions.
        available = await _tool(execution, world["owner_id"], name="fs.ok")
        with pytest.raises(ToolTransitionError):
            await execution.registry.validate_tool(available.id, actor=world["owner_id"])
        view = await execution.registry.disable_tool(available.id, reason="suspect",
                                                     actor=world["owner_id"])
        assert view.status == "DISABLED" and view.disabled_reason == "suspect"
        with pytest.raises(ToolNotFoundError):
            await execution.registry.get_tool("no-such-tool")
    _run(settings, body)


def test_builtin_tools_are_registered_disabled_with_reasons(settings):
    async def body(db, execution, approvals, world):
        tools, total = await execution.registry.list_tools()
        by_name = {t["name"]: t for t in tools}
        assert by_name["browser.session"]["status"] == "DISABLED"
        assert by_name["desktop.window"]["status"] == "DISABLED"
        assert "no browser" in by_name["browser.session"]["disabled_reason"]
        # Discovery never carries a configuration reference (§7).
        assert "configuration_reference" not in by_name["browser.session"]
        # Reconciling again changes nothing.
        again = await execution.registry.reconcile_builtin_tools()
        assert again["created"] == [] and len(again["existing"]) == 2
    _run(settings, body)


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
def test_a_risk_0_request_is_admitted_and_queued(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"])
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        assert result.status == "QUEUED"
        assert all(c.passed for c in result.evaluation.checks)
        view = await execution.requests.get(result.request_id)
        assert view.status == "QUEUED" and view.risk_level == 0
        async with db.session_factory() as session:
            audits = (await session.execute(select(AuditEvent).where(
                AuditEvent.event_type == "execution.request_queued"))).scalars().all()
        assert len(audits) == 1 and audits[0].principal_id == w["principal_id"]
        assert ("ExecutionRequested", {"status": "QUEUED", "retried": False}) in world["bus"].events
    _run(settings, body)


def test_identity_comes_from_the_principal_never_the_payload(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"])
        # The owner principal holds every permission but is not an agent:
        # submission is refused, because there is no agent to attribute it to.
        with pytest.raises(ExecutionIdentityError):
            await execution.requests.submit(world["owner_id"],
                                            _request(w["task_id"], tool.id))
        with pytest.raises(ToolNotFoundError):
            await execution.requests.submit(w["principal_id"],
                                            _request(w["task_id"], "no-such-tool"))
        with pytest.raises(ExecutionRequestNotFoundError):
            await execution.requests.get("no-such-request")
    _run(settings, body)


def test_a_policy_refusal_leaves_a_rejected_row_with_its_reason(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db, assigned=False)
        tool = await _tool(execution, world["owner_id"])
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        assert result.status == "REJECTED"
        view = await execution.requests.get(result.request_id)
        assert view.status == "REJECTED"
        assert "not assigned" in view.refusal_reason
        failed = [c.name for c in result.evaluation.checks if not c.passed]
        assert failed == ["assigned_task"]
    _run(settings, body)


def test_a_disabled_catalog_capability_refuses_until_its_adapter_exists(settings):
    """The P-04 catalog holds filesystem.read disabled pending P-05 adapters,
    so the capability check refuses honestly rather than admitting work
    nobody can perform yet."""
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"],
                           capability_requirements=["filesystem.read"])
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        assert result.status == "REJECTED"
        assert "filesystem.read" in result.evaluation.reason
        assert "disabled" in result.evaluation.reason
    _run(settings, body)


def test_a_prohibited_action_is_risk_3_on_the_row_and_refused(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"],
                           supported_actions=["audit.delete"], risk_level=0)
        result = await execution.requests.submit(
            w["principal_id"],
            _request(w["task_id"], tool.id, action_name="audit.delete"))
        assert result.status == "REJECTED" and result.evaluation.risk == 3
        view = await execution.requests.get(result.request_id)
        assert view.risk_level == 3  # the classification is recorded, not trusted
    _run(settings, body)


def test_risk_2_waits_for_a_bound_approval_and_retry_admits_it(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"], risk_level=2,
                           required_approval_level=2)
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        assert result.status == "AWAITING_APPROVAL"
        view = await execution.requests.get(result.request_id)
        assert view.approval_reference

        # Retrying before the owner decides changes nothing.
        result = await execution.requests.retry(result.request_id, w["principal_id"])
        assert result.status == "AWAITING_APPROVAL"

        # The owner decides in the central queue; retry then admits.
        await approvals.decide(world["owner_id"], view.approval_reference,
                               ApprovalDecisionRequest(decision="approved"))
        result = await execution.requests.retry(result.request_id, w["principal_id"])
        assert result.status == "QUEUED"
    _run(settings, body)


def test_a_rejected_approval_rejects_the_request_on_retry(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"], risk_level=2,
                           required_approval_level=2)
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        view = await execution.requests.get(result.request_id)
        await approvals.decide(world["owner_id"], view.approval_reference,
                               ApprovalDecisionRequest(decision="rejected"))
        result = await execution.requests.retry(result.request_id, w["principal_id"])
        assert result.status == "REJECTED"
    _run(settings, body)


def test_a_substituted_request_fails_the_approval_binding(settings):
    """The approval binds tool, action, parameters and scope by hash. Changing
    the parameters afterwards must be caught, not honoured."""
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"], risk_level=2,
                           required_approval_level=2)
        result = await execution.requests.submit(
            w["principal_id"], _request(w["task_id"], tool.id,
                                        action_parameters={"target": "a"}))
        view = await execution.requests.get(result.request_id)
        await approvals.decide(world["owner_id"], view.approval_reference,
                               ApprovalDecisionRequest(decision="approved"))
        async with db.session_factory() as session:
            from app.database.repositories import ExecutionRequestRepo
            row = await ExecutionRequestRepo(session).get(result.request_id)
            await ExecutionRequestRepo(session).update(
                row, request_payload={"target": "somewhere-else"})
            await session.commit()
        result = await execution.requests.retry(result.request_id, w["principal_id"])
        assert result.status == "REJECTED"
        assert "does not match" in result.evaluation.reason
    _run(settings, body)


def test_a_standing_authorization_carries_risk_2_until_its_limit(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"], risk_level=2,
                           required_approval_level=2)
        async with db.session_factory() as session:
            await ConfigRepo(session).set(STANDING_AUTHORIZATIONS_KEY, {
                "authorizations": [{
                    "id": "sa-1", "agent_id": w["agent_id"], "tool_id": tool.id,
                    "action_name": "read", "scope": "workspace:reports",
                    "max_uses": 1, "revoked": False,
                    "expires_at": "2999-01-01T00:00:00+00:00"}]})
            await session.commit()
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        assert result.status == "QUEUED"
        assert result.evaluation.standing_authorization_id == "sa-1"

        # The limit is one: the next request waits for the owner again.
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        assert result.status == "AWAITING_APPROVAL"
    _run(settings, body)


def test_idempotency_returns_the_original_request(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        tool = await _tool(execution, world["owner_id"])
        first = await execution.requests.submit(
            w["principal_id"], _request(w["task_id"], tool.id, idempotency_key="k-9"))
        again = await execution.requests.submit(
            w["principal_id"], _request(w["task_id"], tool.id, idempotency_key="k-9"))
        assert again.request_id == first.request_id and again.status == "QUEUED"
        # Another agent may not replay somebody else's key.
        other = await _world(db)
        with pytest.raises(ExecutionIdentityError):
            await execution.requests.submit(
                other["principal_id"],
                _request(other["task_id"], tool.id, idempotency_key="k-9"))
    _run(settings, body)


def test_cancellation_is_the_submitting_agents_and_terminal_states_refuse(settings):
    async def body(db, execution, approvals, world):
        w = await _world(db)
        other = await _world(db)
        tool = await _tool(execution, world["owner_id"])
        result = await execution.requests.submit(w["principal_id"],
                                                 _request(w["task_id"], tool.id))
        with pytest.raises(ExecutionIdentityError):
            await execution.requests.cancel(result.request_id, other["principal_id"])
        view = await execution.requests.cancel(result.request_id, w["principal_id"],
                                               reason="no longer needed")
        assert view.status == "CANCELLED"
        with pytest.raises(ExecutionTransitionError):
            await execution.requests.cancel(result.request_id, w["principal_id"])
        with pytest.raises(ExecutionTransitionError):
            await execution.requests.retry(result.request_id, w["principal_id"])
    _run(settings, body)
