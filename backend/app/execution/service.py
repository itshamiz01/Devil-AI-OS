"""ExecutionService — the Universal Digital Execution Engine (§§4–6, 18).

Owns the request lifecycle: submit (validate → policy → QUEUED /
AWAITING_APPROVAL / REJECTED), execute (re-validate → adapter →
verification → terminal outcome), cancel, emergency stop, recovery,
metrics, and the startup health report. Approvals are the P-01
hash-bound ApprovalService — there is no second approval system (§17);
capability checks are the live P-04 grants; audit is P-01 audit_events.

Four separate facts (§6): ``requested_action`` (what was asked),
``approved_action`` (what an approval/standing authorization covered),
``executed_action`` (what the adapter actually ran), ``verified_outcome``
(what verification established). COMPLETED requires verification against
the expected outcome — a tool returning without error is not completion.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from ..agents.capabilities import CapabilityService
from ..core.exceptions import PermissionDeniedError, ValidationError
from ..database.models.base import utcnow
from ..database.models.core import AuditEvent
from ..database.models.execution import (
    BrowserSession, ExecutionEvidence, ExecutionRequest, ExecutionRun,
    StandingAuthorization,
)
from ..database.repositories.agents import CapabilityRepository
from ..database.repositories.core import AgentRepository, AuditRepository, ConfigRepository
from ..database.repositories.execution import (
    BrowserSessionRepository, ExecutionEvidenceRepository,
    ExecutionRequestRepository, ExecutionRunRepository,
    StandingAuthorizationRepository, WorkflowRunRepository,
)
from ..events.bus import EventBus
from ..events.events import Event, EventType
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..permissions.models import Principal, PrincipalType
from . import constants as C
from .adapters.api import ApiAdapter
from .adapters.browser import BrowserAdapter
from .adapters.code import CodeExecutionAdapter, screen_code
from .adapters.desktop import DesktopAdapter
from .adapters.documents import DocumentsAdapter
from .adapters.filesystem import FilesystemAdapter, sha256_file
from .credentials import CredentialBroker, EnvCredentialBroker
from .errors import (
    ApprovalRequiredError, ExecutionNotFoundError, ExecutionStateError,
)
from .policy import ExecutionPolicy, PolicyContext
from .registry import ToolRegistry
from .schemas import ExecutionRequestIn, StandingAuthorizationIn, reject_secret_values
from .workflows import WorkflowEngine
from .workspaces import WorkspaceManager

APPROVAL_ACTION = "execution.execute"
RESOURCE_CLASS_CEILINGS = {
    "filesystem": "max_concurrent_runs",
    "subprocess": "max_concurrent_subprocesses",
    "api": "max_api_concurrency",
    "browser": "max_concurrent_runs",
    "desktop": "max_concurrent_runs",
}
SECURITY_EVENT_CATEGORIES = {"PATH_TRAVERSAL", "SECRET_VALUE_REJECTED", "CREDENTIAL_UNRESOLVED"}


class _BrowserSessionStore:
    """Store protocol for the browser adapter over BrowserSessionRepository."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(self, *, agent_id: str, start_url: str, allowed_domains: list[str]):
        session = self._session_factory()
        try:
            row = BrowserSession(agent_id=agent_id, browser_type=BrowserAdapter.backend,
                                 allowed_domains=allowed_domains, status="active",
                                 current_url=start_url or None, last_activity=utcnow())
            BrowserSessionRepository(session).add(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    def get(self, session_id: str):
        session = self._session_factory()
        try:
            row = BrowserSessionRepository(session).get(session_id)
            if row is not None:
                session.expunge(row)
            return row
        finally:
            session.close()

    def update(self, session_id: str, **fields):
        session = self._session_factory()
        try:
            repo = BrowserSessionRepository(session)
            row = repo.get(session_id)
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            repo.save(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    def count_open(self, agent_id: str) -> int:
        session = self._session_factory()
        try:
            rows = BrowserSessionRepository(session).list(
                agent_id=agent_id, status=None, limit=500, offset=0)[0]
            return len([r for r in rows if r.status in ("active", "requires_human", "paused")])
        finally:
            session.close()


class ExecutionService:
    def __init__(self, session_factory, *, settings, permissions: PermissionEngine,
                 approvals: ApprovalService, capabilities: CapabilityService,
                 bus: EventBus, broker: CredentialBroker | None = None,
                 api_transport=None, browser_transport=None,
                 workspace_root: Path | None = None):
        self._session_factory = session_factory
        self._core_settings = settings
        self._permissions = permissions
        self._approvals = approvals
        self._capabilities = capabilities
        self._bus = bus
        root = workspace_root or (Path(settings.data_dir) / "execution_workspaces")
        self.workspaces = WorkspaceManager(session_factory, root)
        self.registry = ToolRegistry(session_factory)
        self.policy = ExecutionPolicy(session_factory, permissions, capabilities,
                                      self.workspaces)
        store = _BrowserSessionStore(session_factory)
        self._session_store = store
        if api_transport is None:
            from .adapters.api import HttpTransport
            api_transport = HttpTransport(
                proxy_url=getattr(settings, "research_proxy_url", None))
        if browser_transport is None:
            from .adapters.api import HttpTransport
            browser_transport = HttpTransport(
                proxy_url=getattr(settings, "research_proxy_url", None))
        self.adapters = {
            "filesystem": FilesystemAdapter(self.workspaces),
            "documents": DocumentsAdapter(self.workspaces),
            "code": CodeExecutionAdapter(self.workspaces),
            "api": ApiAdapter(transport=api_transport, broker=broker or EnvCredentialBroker()),
            "browser": BrowserAdapter(store, self.workspaces, transport=browser_transport),
            "desktop": DesktopAdapter(),
        }
        self.workflows = WorkflowEngine(session_factory, self)
        self._semaphores: dict[int, dict[str, asyncio.Semaphore]] = {}
        # P-14 Stage B (DEF-I6): P-09 outcome-ingestion callable,
        # late-attached by the Application assembly (P-09 is built
        # after P-05). Signature: ingest(principal, candidate) -> dict.
        # ``None`` → outcome feeding is off; execution is unaffected.
        self.outcome_ingestor = None
        # P-14 Stage B (DEF-I5): P-10 PermissionBroker handle,
        # late-attached by the Application assembly (P-10 is built
        # after P-05). ``None`` → submission is governed by the P-05
        # policy alone (direct-construction contexts); when attached,
        # every policy-passing submission is ALSO authorized through
        # the broker — see _broker_gate.
        self.permission_broker = None

    def _feed_outcome(self, principal: Principal, candidate: dict) -> None:
        """Feed a completed execution outcome into P-09 ingestion.

        Best-effort by design: ingestion outcomes never change the
        execution result, and a feeding failure is logged, never
        raised into the execution path.
        """
        if self.outcome_ingestor is None:
            return
        try:
            self.outcome_ingestor(principal, candidate)
        except Exception as exc:  # feeding must not break execution
            import logging
            logging.getLogger("autonomus.execution").warning(
                "outcome feed to P-09 failed: %s", exc)

    # --------------------------------------------------------------- settings
    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = ConfigRepository(session).get(C.SETTINGS_KEY)
            if row is not None and row.value:
                data = json.loads(row.value)
                values = {**C.DEFAULT_SETTINGS, **(data.get("values") or {})}
                return {"version": data.get("version", C.SETTINGS_VERSION), "values": values}
        finally:
            session.close()
        return {"version": C.SETTINGS_VERSION, "values": dict(C.DEFAULT_SETTINGS)}

    def settings_values(self) -> dict:
        return self.get_settings()["values"]

    def seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = ConfigRepository(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY,
                         json.dumps({"version": C.SETTINGS_VERSION,
                                     "values": dict(C.DEFAULT_SETTINGS)}),
                         "P-05 execution settings (owner-governance-editable only)")
        finally:
            session.close()

    def update_settings(self, principal: Principal, updates: dict) -> dict:
        if principal.type is not PrincipalType.OWNER:
            self._audit(principal, "execution.settings_update", "system_config",
                        C.SETTINGS_KEY, "deny",
                        reason="execution settings are owner-governance only")
            raise PermissionDeniedError(
                "execution settings may only be changed by the owner",
                details={"error_category": "EXECUTION_NOT_AUTHORIZED"})
        unknown = set(updates) - set(C.DEFAULT_SETTINGS)
        if unknown:
            raise ValidationError(f"unknown execution settings: {sorted(unknown)}")
        for key, value in updates.items():
            default = C.DEFAULT_SETTINGS[key]
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise ValidationError(f"setting {key} must be a boolean")
            elif isinstance(default, list):
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ValidationError(f"setting {key} must be a list of strings")
            elif not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValidationError(f"setting {key} must be a non-negative number")
        current = self.settings_values()
        current.update(updates)
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY,
                json.dumps({"version": C.SETTINGS_VERSION, "values": current}),
                "P-05 execution settings (owner-governance-editable only)")
        finally:
            session.close()
        self._audit(principal, "execution.settings_update", "system_config",
                    C.SETTINGS_KEY, "allow", details={"updated_keys": sorted(updates)})
        return self.get_settings()

    # ---------------------------------------------------------------- seeding
    def seed(self) -> dict:
        """Idempotent startup seeding: settings, tools + truthful health,
        workspaces, and the P-05 capability-support flip (grants still
        flow only through the P-04 factory)."""
        self.seed_settings()
        self.registry.seed_tools()
        self.workspaces.seed_workspaces()
        health = {}
        for tool in self.registry.list_tools(limit=100)[0]:
            adapter = self.adapters.get(tool.adapter_type)
            if adapter is None:
                continue
            report = adapter.health()
            status = report["status"]
            if tool.name == "desktop":
                status = "disabled"  # never resurrectable here (§30)
            self.registry.apply_health(
                tool.name, status=status,
                health_status=report["health_status"], details=report["details"])
            health[tool.name] = report
        flipped = self._flip_capability_support()
        return {"tools_health": health, "capabilities_flipped": flipped}

    def _flip_capability_support(self) -> list[str]:
        session = self._session_factory()
        try:
            repo = CapabilityRepository(session)
            flipped = []
            for name, description in C.P05_SUPPORTED_CAPABILITIES.items():
                row = repo.get_by_name(name)
                if row is not None and not row.supported:
                    row.supported = True
                    row.description = description
                    repo.save(row)
                    flipped.append(name)
            return flipped
        finally:
            session.close()

    def startup_health_report(self) -> dict:
        """§27: per-adapter truth for THIS environment, stated plainly."""
        tools = []
        for tool in self.registry.list_tools(limit=100)[0]:
            adapter = self.adapters.get(tool.adapter_type)
            health = adapter.health() if adapter else {"status": "missing_dependency",
                                                       "details": {}}
            tools.append({"tool": tool.name, "adapter": tool.adapter_type,
                          "registry_status": tool.status,
                          "health_status": tool.health_status,
                          "adapter_report": health})
        settings = self.settings_values()
        return {
            "engine": "P-05 Universal Digital Execution Engine",
            "mode": self._core_settings.mode,
            "emergency_stop": bool(settings.get("emergency_stop")),
            "workspace_root": str(self.workspaces.root),
            "code_isolation": "process_controls_only — NOT a strong sandbox (§10.2)",
            "browser_backend": "fetch (SSRF-guarded); live browser engine unavailable "
                               "in this environment; interactive actions disabled",
            "desktop_adapter": "disabled — Windows UI Automation cannot run or be "
                               "tested in this Linux staging environment",
            "tools": tools,
        }

  # ------------------------------------------------------------------ audit
    def _audit(self, actor: Principal, action: str, target_type: str | None,
               target_id: str | None, decision: str | None,
               reason: str | None = None, details: dict | None = None) -> None:
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=actor.type.value, actor_id=actor.id, action=action,
                target_type=target_type, target_id=target_id, decision=decision,
                reason=reason, details=details or {}, created_at=utcnow()))
        finally:
            session.close()

    def _publish(self, event_type: EventType, payload: dict,
                 severity: str = "info") -> None:
        self._bus.publish_sync_safe(Event(event_type=event_type, source="execution",
                                          payload=payload, severity=severity))

    # ------------------------------------------------------- DEF-I5 broker
    def _broker_gate(self, principal: Principal, tool, payload,
                     parameters: dict, approval_satisfied: bool) -> tuple[str, dict | None]:
        """P-14 Stage B (DEF-I5): authorize a policy-passing submission
        through the P-10 PermissionBroker, when the assembly attached
        one. Returns (verdict, broker_result):

        - ``"allow"`` — proceed with the P-05 policy outcome.
        - ``"reject"`` — the broker's hard gates (security mode,
          agent restriction overlay, business scope, permission
          engine) deny the submission outright. These are the
          broker-only gates DEF-I5 found missing outside P-12, and
          they are enforced here.

        The broker's risk gates (capability / owner approval) are
        consulted and the decision is recorded in the broker's
        decision ledger, but they do not hold or deny the submission:
        P-05 has its own per-action §8 risk table with hash-bound
        owner approvals and standing authorizations, and that
        machinery remains the risk authority for tool execution.
        The broker's ACTION_RISK table classifies P-12 action
        classes and defaults every unlisted P-05 tool action to
        CRITICAL (fail closed) — enforcing it here would park every
        governed workflow step behind an owner approval and deadlock
        creation runs (observed in the Stage B completion run:
        ``filesystem.mkdir`` demanded a Level-3 approval). The wiring
        never weakens an existing gate: broker hard gates can only
        add denials, and no P-05 check is bypassed.
        """
        if self.permission_broker is None:
            return "allow", None
        try:
            result = self.permission_broker.authorize(
                principal, permission="execute_tools",
                action=f"{tool.name}.{payload.action}",
                resource=f"tool:{tool.name}",
                business_ref=payload.business_ref,
                task_id=payload.task_id,
                parameters={"tool": tool.name, "action": payload.action,
                            "parameters": parameters},
                approval_id=payload.approval_id if approval_satisfied else None)
        except Exception as exc:  # broker contract is never-raise; fail closed if it ever does
            result = {"allowed": False, "risk_level": None,
                      "reason": (f"permission broker error "
                                 f"({type(exc).__name__}); failing closed (deny)"),
                      "gates": [{"gate": "internal", "passed": False,
                                 "reason": "exception during broker authorization"}],
                      "decision_id": None}
        if result.get("allowed"):
            return "allow", result
        failed = {g.get("gate") for g in result.get("gates", [])
                  if not g.get("passed")}
        if failed & {"mode", "restriction", "business_scope",
                     "permission_engine", "internal"}:
            return "reject", result
        # Risk gates only: recorded in the broker ledger; P-05's own
        # risk/approval machinery governs (see docstring).
        return "allow", result

    # ----------------------------------------------------------------- submit
    def submit(self, principal: Principal, payload: ExecutionRequestIn) -> ExecutionRequest:
        settings = self.settings_values()
        # Idempotency (§16.2): the same key returns the original request.
        if payload.idempotency_key:
            existing = self._find_by_idempotency_key(payload.idempotency_key)
            if existing is not None:
                return existing
        # §19: raw secret values never enter an execution table.
        reject_secret_values(payload.parameters)
        session = self._session_factory()
        try:
            agent = AgentRepository(session).get(payload.agent_id)
            if agent is None:
                from ..agents.errors import AgentNotFoundError
                raise AgentNotFoundError(f"agent '{payload.agent_id}' not found")
            agent_role = agent.role
            session.expunge(agent)
        finally:
            session.close()
        # The engine manages workspace lifecycle: an agent's own
        # workspace materializes on first use (idempotent).
        self.workspaces.ensure_agent_workspace(payload.agent_id)
        tool = self.registry.get_tool(payload.tool)
        action_spec = ToolRegistry.action_spec(tool, payload.action)
        parameters = dict(payload.parameters)
        self._enrich_browser_scope(parameters, tool, payload.action)
        code_screen = None
        if tool.adapter_type == "code" and payload.action == "run":
            code_screen = screen_code(str(parameters.get("code") or ""))
        requested_scope = payload.requested_scope or self._derive_scope(
            tool, payload.action, parameters)
        timeout = min(float(payload.timeout_seconds or settings["default_timeout_seconds"]),
                      float(settings["max_timeout_seconds"]))

        approval_satisfied = False
        approval_note = None
        if payload.approval_id:
            approval_satisfied, approval_note = self._verify_offered_approval(
                payload.approval_id, payload)

        ctx = PolicyContext(
            principal=principal, agent=agent, tool=tool, action_spec=action_spec,
            parameters=parameters, requested_scope=requested_scope,
            business_ref=payload.business_ref, task_id=payload.task_id,
            mode=self._core_settings.mode, settings=settings,
            approval_satisfied=approval_satisfied, code_screen=code_screen)
        decision = self.policy.evaluate(ctx)

        # P-14 Stage B (DEF-I5): route policy-passing submissions
        # through the P-10 PermissionBroker (no-op when unattached).
        broker_verdict, broker_result = "allow", None
        if not decision.prohibited and (decision.allowed
                                        or decision.requires_approval):
            broker_verdict, broker_result = self._broker_gate(
                principal, tool, payload, parameters, approval_satisfied)

        request = ExecutionRequest(
            agent_id=payload.agent_id, task_id=payload.task_id,
            business_ref=payload.business_ref, tool_id=tool.id, tool_name=tool.name,
            adapter_type=tool.adapter_type, action_name=payload.action,
            parameters=parameters, input_refs=payload.input_refs,
            required_capabilities=list(action_spec.get("required_capabilities") or []),
            requested_scope=requested_scope, risk_level=decision.risk_level,
            priority=payload.priority, timeout_seconds=timeout,
            retry_policy=payload.retry_policy, expected_outcome=payload.expected_outcome,
            approval_id=payload.approval_id,
            standing_authorization_id=decision.standing_authorization_id,
            idempotency_key=payload.idempotency_key,
            requested_action={"tool": tool.name, "action": payload.action,
                              "parameters": parameters},
            submitted_by_type=principal.type.value, submitted_by_id=principal.id)
        if approval_satisfied or decision.standing_authorization_id:
            request.approved_action = {"tool": tool.name, "action": payload.action,
                                       "parameters": parameters,
                                       "via": "approval" if approval_satisfied
                                       else "standing_authorization"}

        if broker_verdict == "reject":
            # P-14 Stage B (DEF-I5): the broker's hard gates deny this
            # submission even though the P-05 policy passed it.
            request.status = "REJECTED"
            request.error_category = "POLICY_REJECTED"
            request.result_summary = broker_result.get("reason")
            self._save_new(request)
            self._audit(principal, "execution.submit", "execution_request", request.id,
                        "deny", reason=broker_result.get("reason"),
                        details={"checks": decision.checks,
                                 "risk_level": decision.risk_level,
                                 "approval_note": approval_note,
                                 "broker_decision_id": broker_result.get("decision_id"),
                                 "broker_gates": broker_result.get("gates")})
            self._publish(EventType.EXECUTION_REJECTED,
                          {"request_id": request.id,
                           "reason": broker_result.get("reason"),
                           "agent_id": request.agent_id,
                           "task_id": request.task_id},
                          severity="warning")
            return request

        if decision.prohibited or not decision.allowed and not decision.requires_approval:
            request.status = "REJECTED"
            request.error_category = ("RISK_PROHIBITED" if decision.prohibited
                                      else "POLICY_REJECTED")
            request.result_summary = decision.reason
            self._save_new(request)
            self._audit(principal, "execution.submit", "execution_request", request.id,
                        "deny", reason=decision.reason,
                        details={"checks": decision.checks, "risk_level": decision.risk_level,
                                 "approval_note": approval_note})
            if code_screen and code_screen.get("hard"):
                self._publish(EventType.SANDBOX_VIOLATION,
                              {"request_id": request.id, "agent_id": payload.agent_id,
                               "constructs": code_screen["hard"]}, severity="warning")
            # P-14 Stage B (DEF-I11): EXECUTION_* payloads carry the
            # agent_id and originating task id for the traceability chain.
            self._publish(EventType.EXECUTION_REJECTED,
                          {"request_id": request.id, "reason": decision.reason,
                           "agent_id": request.agent_id,
                           "task_id": request.task_id},
                          severity="warning")
            return request

        if decision.requires_approval:
            request.status = "AWAITING_APPROVAL"
            self._save_new(request)
            approval = self._create_execution_approval(principal, request, settings)
            session = self._session_factory()
            try:
                repo = ExecutionRequestRepository(session)
                row = repo.get(request.id)
                row.approval_id = approval.id
                repo.save(row)
                session.expunge(row)
                request = row
            finally:
                session.close()
            self._audit(principal, "execution.submit", "execution_request", request.id,
                        "allow", reason="held for owner approval",
                        details={"approval_id": approval.id, "risk_level": decision.risk_level,
                                 "checks": decision.checks,
                                 "broker_decision_id": (broker_result or {}).get("decision_id")})
            self._publish(EventType.EXECUTION_AWAITING_APPROVAL,
                          {"request_id": request.id, "approval_id": approval.id,
                           "risk_level": decision.risk_level,
                           "agent_id": request.agent_id,
                           "task_id": request.task_id})
            return request

        request.status = "QUEUED"
        self._save_new(request)
        self._audit(principal, "execution.submit", "execution_request", request.id, "allow",
                    details={"checks": decision.checks, "risk_level": decision.risk_level,
                             "standing_authorization_id": decision.standing_authorization_id,
                             "broker_decision_id": (broker_result or {}).get("decision_id")})
        self._publish(EventType.EXECUTION_SUBMITTED,
                      {"request_id": request.id, "tool": tool.name,
                       "action": payload.action, "risk_level": decision.risk_level,
                       "agent_id": request.agent_id, "task_id": request.task_id})
        return request

    def _save_new(self, request: ExecutionRequest) -> ExecutionRequest:
        session = self._session_factory()
        try:
            ExecutionRequestRepository(session).add(request)
            session.expunge(request)
            return request
        finally:
            session.close()

    def _find_by_idempotency_key(self, key: str) -> ExecutionRequest | None:
        session = self._session_factory()
        try:
            row = ExecutionRequestRepository(session).get_by_idempotency_key(key)
            if row is not None:
                session.expunge(row)
            return row
        finally:
            session.close()

    def get_request(self, request_id: str) -> ExecutionRequest:
        session = self._session_factory()
        try:
            row = ExecutionRequestRepository(session).get(request_id)
            if row is None:
                raise ExecutionNotFoundError(f"execution request '{request_id}' not found")
            session.expunge(row)
            return row
        finally:
            session.close()

    def link_workflow(self, request_id: str, workflow_run_id: str, step_id: str) -> None:
        session = self._session_factory()
        try:
            repo = ExecutionRequestRepository(session)
            row = repo.get(request_id)
            if row is not None:
                row.workflow_run_id = workflow_run_id
                row.workflow_step_id = step_id
                repo.save(row)
        finally:
            session.close()

    # -------------------------------------------------------------- approvals
    @staticmethod
    def _approval_binding(payload_agent: str, tool: str, action: str,
                          parameters: dict) -> tuple[str, dict]:
        resource = f"execution:{payload_agent}:{tool}:{action}"
        binding = {"agent_id": payload_agent, "tool": tool, "action": action,
                   "parameters": parameters}
        return resource, binding

    def _verify_offered_approval(self, approval_id: str,
                                 payload: ExecutionRequestIn) -> tuple[bool, str | None]:
        try:
            approval = self._approvals.get(approval_id)
        except Exception as exc:
            return False, f"approval '{approval_id}' could not be loaded: {exc}"
        if approval.status != "approved":
            return False, f"approval status is '{approval.status}'"
        resource, binding = self._approval_binding(
            payload.agent_id, payload.tool, payload.action, dict(payload.parameters))
        if not ApprovalService.verify_binding(approval, APPROVAL_ACTION, resource, binding):
            return False, "approval does not bind to this exact action and parameters (drift)"
        return True, None

    def _create_execution_approval(self, principal: Principal,
                                   request: ExecutionRequest, settings: dict):
        resource, binding = self._approval_binding(
            request.agent_id, request.tool_name, request.action_name, request.parameters)
        return self._approvals.create(
            principal, action=APPROVAL_ACTION, resource=resource,
            risk_classification=f"risk_{request.risk_level}",
            reason=f"P-05 execution: {request.tool_name}.{request.action_name} "
                   f"for agent {request.agent_id} (request {request.id})",
            requested_permissions=list(request.required_capabilities or []),
            parameters=binding,
            expires_at=utcnow() + timedelta(
                minutes=int(settings.get("approval_expiry_minutes", 30))))

    def request_approval(self, principal: Principal, request_id: str) -> ExecutionRequest:
        """Create a fresh approval for a request held at AWAITING_APPROVAL
        (e.g. after the previous approval expired)."""
        request = self.get_request(request_id)
        if request.status != "AWAITING_APPROVAL":
            raise ExecutionStateError(
                f"request is {request.status}; approvals can only be (re)created "
                "for AWAITING_APPROVAL requests")
        approval = self._create_execution_approval(principal, request, self.settings_values())
        session = self._session_factory()
        try:
            repo = ExecutionRequestRepository(session)
            row = repo.get(request_id)
            row.approval_id = approval.id
            repo.save(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    # ---------------------------------------------------------------- execute
    async def submit_and_execute(self, principal: Principal,
                                 payload: ExecutionRequestIn) -> ExecutionRequest:
        request = self.submit(principal, payload)
        if request.status == "QUEUED":
            request = await self.execute(principal, request.id)
        return request

    def _semaphore(self, resource_class: str, settings: dict) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        key = id(loop)
        bucket = self._semaphores.setdefault(key, {})
        if resource_class not in bucket:
            ceiling_key = RESOURCE_CLASS_CEILINGS.get(resource_class, "max_concurrent_runs")
            bucket[resource_class] = asyncio.Semaphore(max(1, int(settings[ceiling_key])))
        return bucket[resource_class]

    async def execute(self, principal: Principal, request_id: str) -> ExecutionRequest:
        request = self.get_request(request_id)
        if request.status == "AWAITING_APPROVAL":
            gate = self._approval_gate(request)
            if gate == "denied":
                return self._finalize_simple(request_id, "REJECTED",
                                             "APPROVAL_DENIED", "the owner denied this approval")
            if gate != "approved":
                raise ApprovalRequiredError(
                    "this request is awaiting an approved, unexpired, hash-bound "
                    "owner approval before it can execute",
                    details={"request_id": request_id, "approval_id": request.approval_id})
            request = self._mark_queued(request_id, approved_via="approval")
        if request.status in ("FAILED", "TIMED_OUT"):
            tool = self.registry.get_tool(request.tool_name)
            spec = ToolRegistry.action_spec(tool, request.action_name)
            attempts = self._run_count(request_id)
            allowed_attempts = int((request.retry_policy or {}).get(
                "max_attempts", 3 if spec.get("idempotent") else 1))
            if not spec.get("idempotent") or attempts >= allowed_attempts:
                raise ExecutionStateError(
                    f"request is {request.status} and cannot be retried "
                    f"(idempotent={bool(spec.get('idempotent'))}, attempts={attempts})")
            request = self._mark_queued(request_id)
        if request.status != "QUEUED":
            raise ExecutionStateError(
                f"request is {request.status}; only QUEUED requests can execute")

        settings = self.settings_values()
        # Re-run policy at execution time: grants, mode and emergency stop
        # may have changed while the request waited (§8.1).
        gate = self._recheck_policy(principal, request, settings)
        if gate is not None:
            return gate

        tool = self.registry.get_tool(request.tool_name)
        resource_class = (tool.resource_requirements or {}).get("resource_class", "filesystem")
        semaphore = self._semaphore(resource_class, settings)
        if semaphore.locked():
            session = self._session_factory()
            try:
                repo = ExecutionRequestRepository(session)
                row = repo.get(request_id)
                row.result_summary = ("resource ceiling reached for "
                                      f"'{resource_class}'; request remains QUEUED")
                repo.save(row)
                session.expunge(row)
                return row
            finally:
                session.close()
        async with semaphore:
            return await self._execute_under_lock(principal, request, settings, tool)

    def _approval_gate(self, request: ExecutionRequest) -> str:
        if not request.approval_id:
            return "pending"
        try:
            approval = self._approvals.get(request.approval_id)
        except Exception:
            return "pending"
        if approval.status == "rejected":
            return "denied"
        if approval.status != "approved":
            return "pending"
        resource, binding = self._approval_binding(
            request.agent_id, request.tool_name, request.action_name, request.parameters)
        if not ApprovalService.verify_binding(approval, APPROVAL_ACTION, resource, binding):
            return "pending"  # drift: the approval no longer covers this payload
        return "approved"

    def _mark_queued(self, request_id: str, approved_via: str | None = None) -> ExecutionRequest:
        session = self._session_factory()
        try:
            repo = ExecutionRequestRepository(session)
            row = repo.get(request_id)
            row.status = "QUEUED"
            if approved_via is not None and not row.approved_action:
                row.approved_action = {"tool": row.tool_name, "action": row.action_name,
                                       "parameters": row.parameters, "via": approved_via}
            repo.save(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    def _finalize_simple(self, request_id: str, status: str, category: str,
                         summary: str) -> ExecutionRequest:
        session = self._session_factory()
        try:
            repo = ExecutionRequestRepository(session)
            row = repo.get(request_id)
            row.status = status
            row.error_category = category
            row.result_summary = summary
            row.completed_at = utcnow()
            repo.save(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    def _recheck_policy(self, principal: Principal, request: ExecutionRequest,
                        settings: dict) -> ExecutionRequest | None:
        session = self._session_factory()
        try:
            agent = AgentRepository(session).get(request.agent_id)
            session.expunge(agent)
        finally:
            session.close()
        tool = self.registry.get_tool(request.tool_name)
        spec = ToolRegistry.action_spec(tool, request.action_name)
        parameters = dict(request.parameters)
        self._enrich_browser_scope(parameters, tool, request.action_name)
        code_screen = (screen_code(str(parameters.get("code") or ""))
                       if tool.adapter_type == "code" and request.action_name == "run"
                       else None)
        approval_satisfied = bool(request.approved_action) and (
            request.standing_authorization_id is not None or request.approval_id is not None)
        ctx = PolicyContext(
            principal=principal, agent=agent, tool=tool, action_spec=spec,
            parameters=parameters, requested_scope=request.requested_scope,
            business_ref=request.business_ref, task_id=request.task_id,
            mode=self._core_settings.mode, settings=settings,
            approval_satisfied=approval_satisfied, code_screen=code_screen)
        decision = self.policy.evaluate(ctx)
        if decision.prohibited or (not decision.allowed and not decision.requires_approval):
            return self._finalize_simple(request.id, "REJECTED", "POLICY_REJECTED",
                                         f"execution-time policy re-check: {decision.reason}")
        if decision.requires_approval:
            session = self._session_factory()
            try:
                repo = ExecutionRequestRepository(session)
                row = repo.get(request.id)
                row.status = "AWAITING_APPROVAL"
                repo.save(row)
                session.expunge(row)
                return row
            finally:
                session.close()
        return None

    async def _execute_under_lock(self, principal: Principal, request: ExecutionRequest,
                                  settings: dict, tool) -> ExecutionRequest:
        from .adapters.base import AdapterContext
        session = self._session_factory()
        try:
            repo = ExecutionRequestRepository(session)
            row = repo.get(request.id)
            row.status = "RUNNING"
            row.started_at = utcnow()
            repo.save(row)
            run = ExecutionRun(request_id=request.id, worker_id="execution-engine",
                               attempt_number=self._run_count(request.id) + 1,
                               status="RUNNING")
            ExecutionRunRepository(session).add(run)
            run_id = run.id
        finally:
            session.close()

        adapter = self.adapters[request.adapter_type]
        parameters = dict(request.parameters)
        if request.adapter_type == "code":
            parameters["_timeout_seconds"] = request.timeout_seconds
        adapter_settings = dict(settings)
        if request.adapter_type == "api":
            adapter_settings["_allowed_hosts"] = list(settings.get("api_allowlist") or [])
        context = AdapterContext(agent_id=request.agent_id, request_id=request.id,
                                 mode=self._core_settings.mode, settings=adapter_settings)
        started = time.monotonic()
        timed_out = False
        try:
            result = await asyncio.wait_for(
                adapter.execute(request.action_name, parameters, context),
                timeout=request.timeout_seconds + 30)
        except asyncio.TimeoutError:
            timed_out = True
            if request.adapter_type == "code":
                await self.adapters["code"].terminate(request.id)
            from .adapters.base import AdapterResult
            result = AdapterResult(False, error_category="EXECUTION_TIMEOUT",
                                   summary="execution exceeded its time budget")
        duration_ms = (time.monotonic() - started) * 1000.0

        outcome, verification_status, verified = self._verify(request, result)
        if timed_out:
            outcome = "TIMED_OUT"
        session = self._session_factory()
        try:
            run_repo = ExecutionRunRepository(session)
            run = run_repo.get(run_id)
            run.status = outcome
            run.completed_at = utcnow()
            run.duration_ms = duration_ms
            run.exit_code = result.exit_code
            run.result = {"output": result.output, "warnings": result.warnings}
            run.result_summary = result.summary
            run.error_category = result.error_category
            run.resource_usage = result.resource_usage or {}
            run_repo.save(run)
            evidence_repo = ExecutionEvidenceRepository(session)
            for item in result.evidence:
                evidence_repo.add(ExecutionEvidence(
                    run_id=run_id, request_id=request.id,
                    evidence_type=item.get("type", "record"),
                    reference=item.get("reference"), content_hash=item.get("content_hash"),
                    verification_status=verification_status,
                    details=item.get("details") or {}))
            repo = ExecutionRequestRepository(session)
            row = repo.get(request.id)
            if row.status == "CANCELLED":  # cancelled while running: honour it
                session.expunge(row)
                return row
            row.status = outcome
            row.completed_at = utcnow()
            row.result_summary = result.summary
            row.error_category = result.error_category
            row.verification_status = verification_status
            row.verified_outcome = verified
            row.executed_action = {"tool": request.tool_name, "action": request.action_name,
                                   "parameters": request.parameters, "run_id": run_id,
                                   "adapter": request.adapter_type}
            repo.save(row)
            session.expunge(row)
            request = row
        finally:
            session.close()

        if request.standing_authorization_id:
            self._consume_standing_authorization(request.standing_authorization_id)
        self._audit(principal, "execution.execute", "execution_request", request.id,
                    "allow" if outcome in ("COMPLETED", "COMPLETED_WITH_WARNINGS") else "deny",
                    reason=result.summary,
                    details={"outcome": outcome, "run_id": run_id,
                             "verification_status": verification_status,
                             "error_category": result.error_category})
        if result.error_category in SECURITY_EVENT_CATEGORIES:
            self._publish(EventType.SANDBOX_VIOLATION,
                          {"request_id": request.id, "agent_id": request.agent_id,
                           "category": result.error_category,
                           "tool": request.tool_name, "action": request.action_name},
                          severity="warning")
        if outcome in ("COMPLETED", "COMPLETED_WITH_WARNINGS"):
            self._publish(EventType.EXECUTION_COMPLETED,
                          {"request_id": request.id, "outcome": outcome,
                           "agent_id": request.agent_id,
                           "task_id": request.task_id})
            # P-14 Stage B (DEF-I6): completed executions feed P-09
            # outcome memory. The outcome is reported by the task
            # owner principal (the agent that ran it).
            self._feed_outcome(
                Principal(PrincipalType.AGENT, request.agent_id), {
                    "title": (f"Execution {request.id} completed: "
                              f"{request.tool_name}.{request.action_name}"),
                    "content": (
                        f"Execution request {request.id} completed with "
                        f"outcome {outcome}. Tool {request.tool_name} "
                        f"action {request.action_name} was executed by "
                        f"agent {request.agent_id} for task "
                        f"{request.task_id}. Result summary: "
                        f"{result.summary or 'no summary recorded'}."),
                    "source_type": "execution",
                    "source_ref": request.id,
                    "business_id": request.business_ref,
                    "layer": "episodic",
                    "category": "execution_outcome",
                    "truth_class": "observed",
                })
        elif outcome == "FAILED" and result.error_category == "VERIFICATION_FAILED":
            self._publish(EventType.EXECUTION_VERIFICATION_FAILED,
                          {"request_id": request.id,
                           "agent_id": request.agent_id,
                           "task_id": request.task_id}, severity="warning")
        elif outcome in ("FAILED", "TIMED_OUT"):
            self._publish(EventType.EXECUTION_FAILED,
                          {"request_id": request.id, "outcome": outcome,
                           "error_category": result.error_category,
                           "agent_id": request.agent_id,
                           "task_id": request.task_id}, severity="warning")
        return request

    # ------------------------------------------------------------ verification
    def _verify(self, request: ExecutionRequest, result) -> tuple[str, str, dict]:
        """§6.1: COMPLETED requires validation against the expected
        outcome. Returns (outcome, verification_status, verified_outcome)."""
        verified: dict = {"checks": []}
        if result.error_category == "REQUIRES_HUMAN_AUTHENTICATION":
            return "REQUIRES_HUMAN_ACTION", "unverified", {
                "checks": [{"check": "human_authentication", "passed": False,
                            "reason": result.summary}]}
        if result.error_category == "EXECUTION_TIMEOUT":
            return "TIMED_OUT", "unverified", verified
        if not result.success:
            return "FAILED", "failed", verified
        expected = request.expected_outcome or {}
        failures = []
        if "exit_code" in expected:
            actual = result.exit_code if result.exit_code is not None \
                else result.output.get("exit_code")
            ok = actual == expected["exit_code"]
            verified["checks"].append({"check": "exit_code", "passed": ok,
                                       "expected": expected["exit_code"], "actual": actual})
            if not ok:
                failures.append("exit_code")
        if "output_contains" in expected:
            haystack = json.dumps(result.output, default=str)
            ok = str(expected["output_contains"]) in haystack
            verified["checks"].append({"check": "output_contains", "passed": ok})
            if not ok:
                failures.append("output_contains")
        if "status" in expected:
            actual = result.output.get("status")
            ok = actual == expected["status"]
            verified["checks"].append({"check": "status", "passed": ok,
                                       "expected": expected["status"], "actual": actual})
            if not ok:
                failures.append("status")
        if "file" in expected:
            file_check = self._verify_file(expected["file"])
            verified["checks"].append(file_check)
            if not file_check["passed"]:
                failures.append("file")
        if failures:
            result.error_category = "VERIFICATION_FAILED"
            result.summary = (result.summary + " — verification failed: "
                              + ", ".join(failures)).strip(" —")
            return "FAILED", "failed", verified
        if verified["checks"]:
            return "COMPLETED", "verified", verified
        if result.evidence:
            verified["checks"].append({"check": "evidence_recorded", "passed": True,
                                       "count": len(result.evidence)})
            return "COMPLETED", "verified", verified
        if result.output:
            verified["checks"].append({"check": "structured_output", "passed": True})
            return "COMPLETED", "verified", verified
        return "COMPLETED_WITH_WARNINGS", "unverified", verified

    def _verify_file(self, spec: dict) -> dict:
        try:
            workspace = self.workspaces.get_workspace(str(spec.get("workspace") or ""))
            target = Path(workspace.root_path) / str(spec.get("path") or "")
            if not target.is_file():
                return {"check": "file", "passed": False, "reason": "file does not exist"}
            digest = sha256_file(target)
            check = {"check": "file", "passed": True, "sha256": digest,
                     "reference": f"{workspace.name}:{spec.get('path')}"}
            if spec.get("sha256") and spec["sha256"] != digest:
                check["passed"] = False
                check["reason"] = "sha256 mismatch"
            if spec.get("content_contains") and spec["content_contains"] not in \
                    target.read_text(encoding="utf-8", errors="replace"):
                check["passed"] = False
                check["reason"] = "expected content not present"
            return check
        except Exception as exc:
            return {"check": "file", "passed": False, "reason": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------ cancel
    def cancel(self, principal: Principal, request_id: str) -> ExecutionRequest:
        request = self.get_request(request_id)
        if request.status in C.TERMINAL_OUTCOMES:
            raise ExecutionStateError(f"request is already terminal ({request.status})")
        session = self._session_factory()
        try:
            repo = ExecutionRequestRepository(session)
            row = repo.get(request_id)
            row.status = "CANCELLED"
            row.completed_at = utcnow()
            row.result_summary = "cancelled by " + principal.type.value
            repo.save(row)
            session.expunge(row)
            request = row
        finally:
            session.close()
        self._audit(principal, "execution.cancel", "execution_request", request_id, "allow",
                    details={"note": "a RUNNING code process is terminated via cancel_async"})
        self._publish(EventType.EXECUTION_CANCELLED,
                      {"request_id": request_id, "agent_id": request.agent_id,
                       "task_id": request.task_id})
        return request

    async def cancel_async(self, principal: Principal, request_id: str) -> ExecutionRequest:
        request = self.get_request(request_id)
        if request.status == "RUNNING" and request.adapter_type == "code":
            await self.adapters["code"].terminate(request_id)
        return self.cancel(principal, request_id)

    # ------------------------------------------------------- standing auth (§17)
    def create_standing_authorization(self, principal: Principal,
                                      payload: StandingAuthorizationIn) -> StandingAuthorization:
        if principal.type is not PrincipalType.OWNER:
            self._audit(principal, "execution.standing_authorization.create",
                        "execution_standing_authorizations", None, "deny",
                        reason="standing authorizations are owner-configured only (§17)")
            raise PermissionDeniedError(
                "standing authorizations may only be created by the owner",
                details={"error_category": "EXECUTION_NOT_AUTHORIZED"})
        if payload.action_name in ("delete_permanent",):
            raise ValidationError(
                "standing authorizations can never cover delete_permanent (§17)")
        session = self._session_factory()
        try:
            row = StandingAuthorization(
                tool_name=payload.tool_name, action_name=payload.action_name,
                scope_pattern=payload.scope_pattern, agent_id=payload.agent_id,
                role=payload.role, limits=payload.limits, max_uses=payload.max_uses,
                uses=0, expires_at=utcnow() + timedelta(minutes=payload.expires_in_minutes),
                status="active", created_by_type=principal.type.value,
                created_by_id=principal.id)
            StandingAuthorizationRepository(session).add(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    def revoke_standing_authorization(self, principal: Principal,
                                      auth_id: str) -> StandingAuthorization:
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "standing authorizations may only be revoked by the owner",
                details={"error_category": "EXECUTION_NOT_AUTHORIZED"})
        session = self._session_factory()
        try:
            repo = StandingAuthorizationRepository(session)
            row = repo.get(auth_id)
            if row is None:
                raise ExecutionNotFoundError(f"standing authorization '{auth_id}' not found")
            row.status = "revoked"
            row.revoked_at = utcnow()
            repo.save(row)
            session.expunge(row)
            return row
        finally:
            session.close()

    def list_standing_authorizations(self, status: str | None = None,
                                     limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = StandingAuthorizationRepository(session).list(
                status=status, limit=limit, offset=offset)
            for row in rows:
                session.expunge(row)
            return rows, total
        finally:
            session.close()

    def _consume_standing_authorization(self, auth_id: str) -> None:
        session = self._session_factory()
        try:
            repo = StandingAuthorizationRepository(session)
            row = repo.get(auth_id)
            if row is None:
                return
            row.uses = int(row.uses or 0) + 1
            if row.uses >= row.max_uses:
                row.status = "exhausted"
            repo.save(row)
        finally:
            session.close()

    # ------------------------------------------------------------ emergency (§23.7)
    async def emergency_stop(self, principal: Principal) -> dict:
        if principal.type is not PrincipalType.OWNER:
            self._audit(principal, "execution.emergency_stop", "execution", None, "deny",
                        reason="emergency stop is owner-only")
            raise PermissionDeniedError(
                "the execution emergency stop is owner-only",
                details={"error_category": "EXECUTION_NOT_AUTHORIZED"})
        self.update_settings(principal, {"emergency_stop": True})
        terminated = 0
        code_adapter = self.adapters["code"]
        for request_id in list(code_adapter.active_processes):
            if await code_adapter.terminate(request_id):
                terminated += 1
        session = self._session_factory()
        try:
            repo = BrowserSessionRepository(session)
            paused = 0
            for row in repo.active_sessions():
                row.status = "paused"
                repo.save(row)
                paused += 1
            queued = ExecutionRequestRepository(session).count_by_status("QUEUED")
        finally:
            session.close()
        report = {"emergency_stop": True, "processes_terminated": terminated,
                  "browser_sessions_paused": paused, "queued_requests_blocked": queued,
                  "note": "new execution is refused by policy check 1 while the stop is active"}
        self._audit(principal, "execution.emergency_stop", "execution", None, "allow",
                    details=report)
        self._publish(EventType.EXECUTION_EMERGENCY_STOP, report, severity="warning")
        return report

    def emergency_resume(self, principal: Principal) -> dict:
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "resuming execution after an emergency stop is owner-only",
                details={"error_category": "EXECUTION_NOT_AUTHORIZED"})
        self.update_settings(principal, {"emergency_stop": False})
        session = self._session_factory()
        try:
            repo = BrowserSessionRepository(session)
            resumed = 0
            for row in repo.list(status="paused", limit=500, offset=0)[0]:
                row.status = "active"
                repo.save(row)
                resumed += 1
        finally:
            session.close()
        report = {"emergency_stop": False, "browser_sessions_resumed": resumed}
        self._audit(principal, "execution.emergency_resume", "execution", None, "allow",
                    details=report)
        self._publish(EventType.EXECUTION_EMERGENCY_RESUMED, report)
        return report

    # --------------------------------------------------------------- recovery
    def recover_interrupted(self) -> dict:
        """Startup recovery (§16.4/§21): runs left RUNNING become
        INTERRUPTED; workflow runs settle per idempotency — never a blind
        repeat of a non-idempotent step."""
        session = self._session_factory()
        try:
            run_repo = ExecutionRunRepository(session)
            request_repo = ExecutionRequestRepository(session)
            interrupted = []
            for run in run_repo.in_statuses(["RUNNING"]):
                run.status = "INTERRUPTED"
                run.completed_at = utcnow()
                run_repo.save(run)
                request = request_repo.get(run.request_id)
                if request is not None and request.status == "RUNNING":
                    request.status = "INTERRUPTED"
                    request.result_summary = "interrupted by a restart; outcome not assumed"
                    request_repo.save(request)
                    interrupted.append(request.id)
        finally:
            session.close()

        def _idempotent(tool_name: str, action_name: str) -> bool:
            try:
                tool = self.registry.get_tool(tool_name)
                return bool(ToolRegistry.action_spec(tool, action_name).get("idempotent"))
            except Exception:
                return False

        workflow_report = self.workflows.recover_interrupted(_idempotent)
        return {"interrupted_requests": interrupted, "workflows": workflow_report}

    # ---------------------------------------------------------------- metrics
    def metrics(self) -> dict:
        session = self._session_factory()
        try:
            request_repo = ExecutionRequestRepository(session)
            by_status = {status: request_repo.count_by_status(status)
                         for status in C.OUTCOMES}
            runs = ExecutionRunRepository(session).in_statuses(
                ["COMPLETED", "FAILED", "TIMED_OUT", "INTERRUPTED", "RUNNING"])
            durations = [r.duration_ms for r in runs if r.duration_ms is not None]
            sessions_active = BrowserSessionRepository(session).count_active()
            standing = len(StandingAuthorizationRepository(session).active())
            workflows = {status: 0 for status in C.WORKFLOW_STATES}
            for row in WorkflowRunRepository(session).list(limit=500, offset=0)[0]:
                workflows[row.status] = workflows.get(row.status, 0) + 1
        finally:
            session.close()
        settings = self.settings_values()
        return {
            "measurement": "measured from execution tables",
            "requests_by_status": by_status,
            "runs_total": len(runs),
            "average_run_duration_ms": (round(sum(durations) / len(durations), 2)
                                        if durations else None),
            "browser_sessions_active": sessions_active,
            "standing_authorizations_active": standing,
            "workflow_runs_by_status": workflows,
            "active_code_processes": len(self.adapters["code"].active_processes),
            "ceilings": {k: settings[k] for k in (
                "max_concurrent_runs", "max_concurrent_subprocesses",
                "max_browser_sessions", "max_api_concurrency", "max_workflow_concurrency")},
            "emergency_stop": bool(settings.get("emergency_stop")),
        }

    def audit_for_request(self, request_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows = list(session.scalars(
                select(AuditEvent).where(
                    AuditEvent.target_type == "execution_request",
                    AuditEvent.target_id == request_id)
                .order_by(AuditEvent.created_at.asc())).all())
            return [{"id": r.id, "actor_type": r.actor_type, "actor_id": r.actor_id,
                     "action": r.action, "decision": r.decision, "reason": r.reason,
                     "details": r.details,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()

    def evidence_for_request(self, request_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows = ExecutionEvidenceRepository(session).for_request(request_id)
            return [{"id": r.id, "run_id": r.run_id, "type": r.evidence_type,
                     "reference": r.reference, "content_hash": r.content_hash,
                     "verification_status": r.verification_status, "details": r.details,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()

    def list_requests(self, *, agent_id=None, status=None, limit=50, offset=0):
        session = self._session_factory()
        try:
            rows, total = ExecutionRequestRepository(session).list(
                agent_id=agent_id, status=status, limit=limit, offset=offset)
            for row in rows:
                session.expunge(row)
            return rows, total
        finally:
            session.close()

    def _run_count(self, request_id: str) -> int:
        session = self._session_factory()
        try:
            return ExecutionRunRepository(session).count_for_request(request_id)
        finally:
            session.close()

    # ---------------------------------------------------------------- helpers
    def _enrich_browser_scope(self, parameters: dict, tool, action: str) -> None:
        if tool.adapter_type != "browser":
            return
        session_id = parameters.get("session_id")
        if session_id:
            row = self._session_store.get(str(session_id))
            if row is not None:
                parameters["_session_allowed_domains"] = list(row.allowed_domains or [])
        if action == "open_session":
            allowlist = list(self.settings_values().get("browser_allowlist") or [])
            if allowlist:
                from .policy import host_matches
                for domain in parameters.get("allowed_domains") or []:
                    if not host_matches(str(domain), allowlist):
                        raise ValidationError(
                            f"session domain '{domain}' is outside the owner-governed "
                            "browser allowlist")

    @staticmethod
    def _derive_scope(tool, action: str, parameters: dict) -> str:
        adapter = tool.adapter_type
        if adapter in ("filesystem", "documents"):
            workspace = parameters.get("workspace") or parameters.get("dest_workspace") or ""
            path = parameters.get("path") or parameters.get("dest_path") or ""
            return f"{tool.name}:{action}:{workspace}:{path}"
        if adapter == "api":
            from urllib.parse import urlparse
            host = (urlparse(str(parameters.get("url") or "")).hostname or "")
            return f"{tool.name}:{action}:{host}"
        if adapter == "browser":
            domains = parameters.get("allowed_domains") or []
            return f"{tool.name}:{action}:{','.join(domains)}"
        return f"{tool.name}:{action}"


def request_to_dict(request: ExecutionRequest) -> dict:
    return {
        "id": request.id, "agent_id": request.agent_id, "task_id": request.task_id,
        "business_ref": request.business_ref, "tool": request.tool_name,
        "adapter_type": request.adapter_type, "action": request.action_name,
        "parameters": request.parameters, "input_refs": request.input_refs,
        "required_capabilities": request.required_capabilities,
        "requested_scope": request.requested_scope, "risk_level": request.risk_level,
        "priority": request.priority, "timeout_seconds": request.timeout_seconds,
        "retry_policy": request.retry_policy, "expected_outcome": request.expected_outcome,
        "approval_id": request.approval_id,
        "standing_authorization_id": request.standing_authorization_id,
        "idempotency_key": request.idempotency_key, "status": request.status,
        "requested_action": request.requested_action,
        "approved_action": request.approved_action,
        "executed_action": request.executed_action,
        "verified_outcome": request.verified_outcome,
        "verification_status": request.verification_status,
        "result_summary": request.result_summary, "error_category": request.error_category,
        "submitted_by": {"type": request.submitted_by_type, "id": request.submitted_by_id},
        "workflow_run_id": request.workflow_run_id, "workflow_step_id": request.workflow_step_id,
        "started_at": request.started_at.isoformat() if request.started_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "updated_at": request.updated_at.isoformat() if request.updated_at else None,
    }
