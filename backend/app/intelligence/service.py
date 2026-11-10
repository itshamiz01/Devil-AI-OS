"""Intelligence service (P-02): mission intake -> planning -> approval ->
execution -> verification -> explanation.

Hard rules enforced here:
- Execution happens ONLY through ``TaskManager.submit`` (P-01), with
  idempotency keys derived from plan+step, and permissions are
  RE-VALIDATED at execution time, not only at plan time.
- Approval binds the plan's canonical steps by hash (P-01 approvals
  pattern): any change after approval makes execution refuse.
- Operating mode (Settings.mode, owner-controlled config — the system
  never changes its own mode): simulation and emergency block execution;
  supervised and controlled require an approved plan.
- Mission text is data. Injection patterns in it are detected, recorded
  and audited; they can never create tools, change permissions, or edit
  model profiles (Article 0).
"""
from __future__ import annotations

import asyncio

from ..core.exceptions import (
    ApprovalError, InvalidStateTransitionError, NotFoundError,
    PermissionDeniedError, ValidationError,
)
from ..database.models.intelligence import Mission, Plan, PlanStep
from ..database.repositories.intelligence import (
    MissionRepository, ModelProfileRepository, PlanRepository,
)
from ..events.events import Event, EventType
from ..permissions.approvals import ApprovalService, parameters_hash
from ..permissions.models import Principal, PrincipalType
from ..tasks.models import TaskStatus
from .context import ContextManager
from .planner import BaselinePlanner, PlanRejectedError, PlanValidator, parse_proposal
from .providers import ProviderError
from .recorder import DecisionRecorder
from .router import ModelRouter
from .schemas import ValidatedStep, canonical_steps
from .tools import ToolRegistryView
from .verifier import ResultVerifier

# Substrings that mark a prompt-injection attempt inside mission text.
# Detection only ever RECORDS; planning proceeds (or fails) through the
# same governed templates/validation as any other mission.
INJECTION_PATTERNS = [
    "ignore your rules", "ignore previous instructions", "ignore all instructions",
    "disregard your instructions", "os.system", "create a tool", "create tool",
    "raise your permissions", "raise my permissions", "increase your permissions",
    "edit model profiles", "edit the model profiles", "modify model profiles",
    "grant yourself", "bypass your", "jailbreak", "unrestricted shell",
    "delete the audit", "turn off audit", "disable audit",
]

DEFAULT_PROFILES = [
    ("fast-local", ["fast", "planning"], "ollama", {"size_rank": 10}),
    ("standard-local", ["standard", "planning"], "ollama", {"size_rank": 20}),
    ("coding-local", ["coding"], "ollama", {"size_rank": 25}),
    ("reasoning-local", ["reasoning", "planning"], "ollama",
     {"size_rank": 30, "requires_headroom": True}),
]

_TERMINAL_TASK_STATES = {
    TaskStatus.COMPLETED.value, TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value, TaskStatus.PAUSED.value,
}


def detect_injection(text: str) -> list[str]:
    lower = text.lower()
    return [p for p in INJECTION_PATTERNS if p in lower]


def _canonical_from_steps(steps) -> list[dict]:
    return [
        {"tool_name": s.tool_name, "payload": s.payload, "expectation": s.expectation}
        for s in sorted(steps, key=lambda s: s.order_index)
    ]


class IntelligenceService:
    def __init__(self, session_factory, bus, permissions, tasks,
                 approvals: ApprovalService, settings, monitor=None, providers=None):
        from .providers import CloudProviderStub, OllamaProvider

        self._session_factory = session_factory
        self._bus = bus
        self._permissions = permissions
        self._tasks = tasks
        self._approvals = approvals
        self._settings = settings
        self._monitor = monitor
        self.providers = providers if providers is not None else {
            "ollama": OllamaProvider(settings.ollama_base_url, settings.ollama_timeout_seconds),
            "cloud": CloudProviderStub(settings.cloud_ai_enabled),
        }
        self.tools = ToolRegistryView(tasks.registry)
        self.recorder = DecisionRecorder(session_factory)
        self.verifier = ResultVerifier()
        self.context = ContextManager(session_factory)
        # P-14 Stage B: late-attached integration handles. P-03 (DEF-E1)
        # and P-09 (DEF-E2) are constructed AFTER P-02 in the assembly,
        # so the Application wires them in post-construction; both
        # features degrade honestly while unattached.
        self._opportunities = None
        # P-14 Stage B (DEF-A5): provider probe cache — (monotonic
        # timestamp, status dict) so health consumers do not re-probe
        # live providers on every call.
        self._probe_cache: tuple[float, dict] | None = None
        self._baseline = BaselinePlanner()
        self._validator = PlanValidator(self.tools, permissions)
        self._router = ModelRouter(session_factory, self.providers, monitor)

    # ------------------------------------------- P-14 integration wiring
    def attach_opportunities(self, opportunities) -> None:
        """Wire the P-03 OpportunityService (DEF-E1 thin path)."""
        self._opportunities = opportunities

    def attach_memory(self, memory) -> None:
        """Wire the P-09 MemoryService into context building (DEF-E2)."""
        self.context.attach_memory(memory)

    # ------------------------------------------------------------ seeding
    def seed_default_profiles(self) -> None:
        """Seed owner-editable profile rows with EMPTY model_id and
        enabled=False. No default model is invented while the owner's
        hardware is unknown (P-00 carried item)."""
        session = self._session_factory()
        try:
            repo = ModelProfileRepository(session)
            from ..database.models.intelligence import ModelProfile
            for name, classes, provider, limits in DEFAULT_PROFILES:
                if repo.get_by_name(name) is None:
                    repo.add(ModelProfile(
                        name=name, task_classes=classes, provider=provider,
                        model_id="", enabled=False, limits=limits))
        finally:
            session.close()

    # ------------------------------------------------------------- events
    async def _publish(self, event_type: EventType, payload: dict,
                       correlation_id: str | None = None, severity: str = "info") -> None:
        if self._bus is not None:
            await self._bus.publish(Event(
                event_type=event_type, source="intelligence.service",
                payload=payload, correlation_id=correlation_id, severity=severity))

    # ------------------------------------------------------------ missions
    async def create_mission(self, principal: Principal, text: str,
                             correlation_id: str | None = None) -> Mission:
        session = self._session_factory()
        try:
            mission = MissionRepository(session).add(Mission(
                text=text, creator_type=principal.type.value, creator_id=principal.id,
                status="received", mode=self._settings.mode,
                matched_template=self._baseline.match_name(text),
                correlation_id=correlation_id))
        finally:
            session.close()
        self.recorder.record(
            "mission_received", actor="system",
            reason="mission accepted into the governed planning pipeline",
            mission_id=mission.id, correlation_id=correlation_id)
        patterns = detect_injection(text)
        if patterns:
            self.recorder.record(
                "injection_detected", actor="system",
                reason=("prompt-injection patterns detected in mission text; the text is "
                        "treated as data only — no tools, permissions or model profiles "
                        "can be created or changed by mission text (Article 0)"),
                mission_id=mission.id,
                evidence={"patterns": patterns}, correlation_id=correlation_id)
        await self._publish(EventType.MISSION_RECEIVED,
                            {"mission_id": mission.id}, correlation_id)
        return mission

    def get_mission(self, mission_id: str) -> Mission:
        session = self._session_factory()
        try:
            mission = MissionRepository(session).get(mission_id)
            if mission is None:
                raise NotFoundError(f"mission {mission_id} not found")
            return mission
        finally:
            session.close()

    def list_missions(self, status: str | None = None, limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            return MissionRepository(session).list(status, limit, offset)
        finally:
            session.close()

    # ------------------------------------------------------------- planning
    async def create_plan(self, principal: Principal, mission_id: str,
                          correlation_id: str | None = None) -> Plan:
        mission = self.get_mission(mission_id)
        router_decision = await self._router.select("planning")
        self.recorder.record(
            "router_selection", actor="system",
            reason="; ".join(router_decision.reasons),
            mission_id=mission.id,
            evidence={"kind": router_decision.kind, "profile": router_decision.profile_name,
                      "provider": router_decision.provider_name,
                      "model_id": router_decision.model_id},
            correlation_id=correlation_id)

        planner_actor = "rule-engine"
        profile_name = None
        llm_failure: str | None = None

        if router_decision.kind == "llm":
            provider = self.providers[router_decision.provider_name]
            llm_actor = f"llm:{router_decision.provider_name}:{router_decision.model_id}"
            raw = None
            try:
                raw = await asyncio.wait_for(
                    provider.generate_plan_raw(
                        mission.text, self.tools.list_tools(), router_decision.model_id),
                    timeout=self._settings.llm_plan_timeout_seconds)
                proposal = parse_proposal(raw)
            except (ProviderError, asyncio.TimeoutError, PlanRejectedError) as exc:
                # Unavailable / timed out / garbage output -> recorded,
                # then the deterministic baseline planner is tried.
                llm_failure = f"{type(exc).__name__}: {exc}"
                self.recorder.record(
                    "llm_plan_unusable", actor=llm_actor,
                    reason=(f"LLM planning produced no usable proposal ({llm_failure}); "
                            "falling back to the deterministic baseline planner"),
                    mission_id=mission.id, correlation_id=correlation_id)
                proposal = None
            if raw is not None and llm_failure is None:
                try:
                    validated = self._validator.validate(proposal, principal, correlation_id)
                except PlanRejectedError as exc:
                    # Well-formed but impermissible: REJECTED outright,
                    # no fallback. The attempt itself is the record.
                    rejected = self._persist_plan(
                        mission, planner=llm_actor,
                        profile_name=router_decision.profile_name,
                        proposal=proposal, status="rejected")
                    self.recorder.record(
                        "plan_rejected", actor=llm_actor, reason=str(exc),
                        mission_id=mission.id, plan_id=rejected.id,
                        evidence={"step_tool": exc.details.get("step_tool")},
                        correlation_id=correlation_id)
                    exc.details["plan_id"] = rejected.id
                    raise
                return await self._store_valid_plan(
                    mission, planner_actor=llm_actor,
                    profile_name=router_decision.profile_name,
                    validated=validated, rationale=proposal.rationale,
                    correlation_id=correlation_id)

        # Baseline path (router chose it, or LLM output was unusable).
        matched = self._baseline.plan(mission.text)
        if matched is None:
            self.recorder.record(
                "plan_failed", actor="rule-engine",
                reason=("no baseline template matched this mission and no usable LLM "
                        "plan was available; the mission cannot be planned in P-02"),
                mission_id=mission.id, correlation_id=correlation_id)
            self._set_mission_status(mission.id, "planning_failed")
            raise ValidationError(
                "no planner could produce a plan for this mission: no baseline "
                "template matched and no LLM plan was available or usable",
                details={"mission_id": mission.id, "llm_failure": llm_failure})
        template_name, proposal = matched
        validated = self._validator.validate(proposal, principal, correlation_id)
        if llm_failure is not None:
            self.recorder.record(
                "llm_fallback_to_baseline", actor="rule-engine",
                reason=f"baseline template '{template_name}' used after LLM failure",
                mission_id=mission.id, correlation_id=correlation_id)
        return await self._store_valid_plan(
            mission, planner_actor=planner_actor, profile_name=profile_name,
            validated=validated, rationale=proposal.rationale,
            correlation_id=correlation_id)

    def _persist_plan(self, mission: Mission, planner: str, profile_name: str | None,
                      proposal, status: str) -> Plan:
        session = self._session_factory()
        try:
            repo = PlanRepository(session)
            plan = repo.add(Plan(
                mission_id=mission.id, version=repo.count_for_mission(mission.id) + 1,
                planner=planner, model_profile=profile_name, status=status,
                rationale=proposal.rationale or None))
            for index, step in enumerate(proposal.steps):
                repo.add_step(PlanStep(
                    plan_id=plan.id, order_index=index, name=step.name,
                    tool_name=step.tool_name, payload=step.payload,
                    expectation=step.expectation.model_dump(),
                    task_class=step.task_class, essential=step.essential,
                    timeout_seconds=step.timeout_seconds, status="pending"))
            return repo.get(plan.id)
        finally:
            session.close()

    async def _store_valid_plan(self, mission: Mission, planner_actor: str,
                                profile_name: str | None, validated: list[ValidatedStep],
                                rationale: str, correlation_id: str | None) -> Plan:
        from .schemas import PlanProposal, StepProposal
        proposal = PlanProposal(steps=[
            StepProposal(name=s.name, tool_name=s.tool_name, payload=s.payload,
                         expectation=s.expectation, task_class=s.task_class,
                         essential=s.essential, timeout_seconds=s.timeout_seconds)
            for s in validated
        ], rationale=rationale)
        plan = self._persist_plan(mission, planner=planner_actor,
                                  profile_name=profile_name,
                                  proposal=proposal, status="draft")
        self.recorder.record(
            "plan_created", actor=planner_actor,
            reason=(f"plan v{plan.version} created with {len(validated)} validated "
                    "step(s); every step references a registered tool and passed "
                    "payload + permission validation"),
            mission_id=mission.id, plan_id=plan.id,
            evidence={"tools": [s.tool_name for s in validated]},
            correlation_id=correlation_id)
        self._set_mission_status(mission.id, "planned")
        await self._publish(EventType.PLAN_CREATED,
                            {"mission_id": mission.id, "plan_id": plan.id,
                             "planner": planner_actor}, correlation_id)
        return plan

    def _set_mission_status(self, mission_id: str, status: str) -> None:
        session = self._session_factory()
        try:
            repo = MissionRepository(session)
            mission = repo.get(mission_id)
            if mission is not None:
                mission.status = status
                repo.save(mission)
        finally:
            session.close()

    def get_plan(self, plan_id: str) -> Plan:
        session = self._session_factory()
        try:
            plan = PlanRepository(session).get(plan_id)
            if plan is None:
                raise NotFoundError(f"plan {plan_id} not found")
            return plan
        finally:
            session.close()

    # ------------------------------------------------------------- approval
    async def approve_plan(self, principal: Principal, plan_id: str,
                           correlation_id: str | None = None) -> Plan:
        plan = self.get_plan(plan_id)
        if plan.status != "draft":
            raise InvalidStateTransitionError(
                f"only a draft plan can be approved (current status: {plan.status})",
                details={"plan_id": plan_id, "status": plan.status})
        canonical = _canonical_from_steps(plan.steps)
        parameters = {"plan_id": plan.id, "steps": canonical}
        resource = f"plan:{plan.id}"
        risk = "high" if any(self.tools.requires_approval(s.tool_name) for s in plan.steps) \
            else "low"
        approval = self._approvals.create(
            principal, action="plan.execute", resource=resource,
            risk_classification=risk,
            reason=f"approval of plan v{plan.version} for mission {plan.mission_id}",
            requested_permissions=["execute_tools"], parameters=parameters)
        decided = self._approvals.decide(approval.id, principal, True,
                                         notes="approved via the plan-approve endpoint")
        if not self._approvals.verify_binding(decided, "plan.execute", resource, parameters):
            raise ApprovalError("approval binding verification failed for plan",
                                details={"plan_id": plan_id})
        session = self._session_factory()
        try:
            repo = PlanRepository(session)
            row = repo.get(plan_id)
            row.approval_id = approval.id
            row.plan_hash = parameters_hash("plan.execute", resource, parameters)
            row.status = "approved"
            plan = repo.save(row)
        finally:
            session.close()
        self._set_mission_status(plan.mission_id, "approved")
        self.recorder.record(
            "plan_approved", actor=f"{principal.type.value}:{principal.id}",
            reason="plan approved; approval bound to the exact plan steps by hash",
            mission_id=plan.mission_id, plan_id=plan.id,
            evidence={"approval_id": approval.id, "plan_hash": plan.plan_hash},
            correlation_id=correlation_id)
        await self._publish(EventType.PLAN_APPROVED,
                            {"mission_id": plan.mission_id, "plan_id": plan.id},
                            correlation_id)
        return plan

    # ------------------------------------------------------------ execution
    async def execute_plan(self, principal: Principal, plan_id: str,
                           correlation_id: str | None = None) -> Plan:
        plan = self.get_plan(plan_id)
        mode = self._settings.mode
        if mode in ("simulation", "emergency"):
            self.recorder.record(
                "execution_blocked_mode", actor="system",
                reason=(f"operating mode is '{mode}': plan execution is blocked in "
                        "this mode (mode is owner-controlled configuration; the "
                        "system never changes its own mode)"),
                mission_id=plan.mission_id, plan_id=plan.id, correlation_id=correlation_id)
            raise InvalidStateTransitionError(
                f"plan execution is blocked in '{mode}' mode",
                details={"plan_id": plan_id, "mode": mode})
        if plan.status != "approved":
            self.recorder.record(
                "execution_blocked_unapproved", actor="system",
                reason=f"plan status is '{plan.status}', not 'approved'; execution refused",
                mission_id=plan.mission_id, plan_id=plan.id, correlation_id=correlation_id)
            raise InvalidStateTransitionError(
                "only an approved plan can be executed",
                details={"plan_id": plan_id, "status": plan.status})
        # Approval binding: the plan must be byte-identical to what was approved.
        approval = None
        if plan.approval_id:
            try:
                approval = self._approvals.get(plan.approval_id)
            except NotFoundError:
                approval = None
        canonical_now = _canonical_from_steps(plan.steps)
        binding_ok = approval is not None and self._approvals.verify_binding(
            approval, "plan.execute", f"plan:{plan.id}",
            {"plan_id": plan.id, "steps": canonical_now})
        if not binding_ok:
            self.recorder.record(
                "plan_tampered", actor="system",
                reason=("plan contents changed after approval (approval hash no "
                        "longer binds this plan); execution refused — a new "
                        "approval is required"),
                mission_id=plan.mission_id, plan_id=plan.id, correlation_id=correlation_id)
            raise ApprovalError(
                "plan changed after approval; the approval no longer binds this "
                "plan and execution is refused",
                details={"plan_id": plan_id})

        self._set_plan_status(plan.id, "executing")
        self._set_mission_status(plan.mission_id, "executing")
        self.recorder.record(
            "execution_started", actor=f"{principal.type.value}:{principal.id}",
            reason=f"executing approved plan in '{mode}' mode",
            mission_id=plan.mission_id, plan_id=plan.id, correlation_id=correlation_id)
        await self._publish(EventType.PLAN_EXECUTION_STARTED,
                            {"mission_id": plan.mission_id, "plan_id": plan.id},
                            correlation_id)

        for step in sorted(plan.steps, key=lambda s: s.order_index):
            if not await self._execute_step(principal, plan, step, correlation_id):
                return self.get_plan(plan.id)

        self._set_plan_status(plan.id, "completed")
        self._set_mission_status(plan.mission_id, "completed")
        self.recorder.record(
            "plan_completed", actor=plan.planner,
            reason="all steps executed and passed through the result verifier",
            mission_id=plan.mission_id, plan_id=plan.id, correlation_id=correlation_id)
        await self._publish(EventType.PLAN_COMPLETED,
                            {"mission_id": plan.mission_id, "plan_id": plan.id},
                            correlation_id)
        return self.get_plan(plan.id)

    async def _execute_step(self, principal: Principal, plan: Plan, step: PlanStep,
                            correlation_id: str | None) -> bool:
        """Returns False when the plan must halt (step failed / denied)."""
        # Permissions are re-validated at EXECUTION time (not plan time only).
        permission = self.tools.permission(step.tool_name)
        decision = self._permissions.check(
            principal, permission, resource=f"tool:{step.tool_name}",
            correlation_id=correlation_id)
        if not decision.allowed:
            self._update_step(step.id, status="failed")
            self.recorder.record(
                "permission_denied_at_execution", actor="system",
                reason=(f"step '{step.name}' denied at execution time: principal "
                        f"lacks '{permission}' ({decision.reason})"),
                mission_id=plan.mission_id, plan_id=plan.id, step_id=step.id,
                correlation_id=correlation_id)
            await self._fail_plan(plan, f"step {step.order_index + 1} denied at execution time",
                                  correlation_id)
            return False
        try:
            task = await self._tasks.submit(
                principal, name=step.name, handler_name=step.tool_name,
                payload=step.payload, category="intelligence",
                timeout_seconds=step.timeout_seconds, essential=step.essential,
                idempotency_key=f"plan:{plan.id}:step:{step.id}",
                correlation_id=correlation_id)
        except Exception as exc:
            self._update_step(step.id, status="failed")
            self.recorder.record(
                "step_submission_failed", actor="system",
                reason=f"step '{step.name}' could not be submitted: {exc}",
                mission_id=plan.mission_id, plan_id=plan.id, step_id=step.id,
                correlation_id=correlation_id)
            await self._fail_plan(plan, f"step {step.order_index + 1} submission failed: {exc}",
                                  correlation_id)
            return False
        self._update_step(step.id, status="submitted", task_id=task.id)
        finished = await self._wait_for_task(task.id, step.timeout_seconds + 30.0)
        step_status = "completed" if finished.status == TaskStatus.COMPLETED.value else "failed"
        self._update_step(step.id, status=step_status)
        v_status, v_detail = self.verifier.verify(step.expectation, finished)
        self._update_step(step.id, verification_status=v_status, verification_detail=v_detail)
        verified = v_status == "verified"
        self.recorder.record(
            "step_verified" if v_status != "failed" else "step_verification_failed",
            actor="verifier",
            reason=f"step '{step.name}' verification: {v_status} — {v_detail}",
            mission_id=plan.mission_id, plan_id=plan.id, step_id=step.id,
            evidence={"task_id": task.id, "task_status": finished.status,
                      "verification_status": v_status},
            correlation_id=correlation_id)
        await self._publish(
            EventType.STEP_VERIFIED if v_status != "failed" else EventType.STEP_VERIFICATION_FAILED,
            {"mission_id": plan.mission_id, "plan_id": plan.id, "step_id": step.id,
             "verification_status": v_status}, correlation_id,
            severity="info" if v_status != "failed" else "error")
        if finished.status != TaskStatus.COMPLETED.value or v_status == "failed":
            await self._fail_plan(
                plan,
                f"step {step.order_index + 1} ('{step.name}') did not pass: "
                f"task_status={finished.status}, verification={v_status} ({v_detail})",
                correlation_id)
            return False
        return True

    async def _wait_for_task(self, task_id: str, deadline_seconds: float):
        deadline = asyncio.get_event_loop().time() + deadline_seconds
        while True:
            task = self._tasks.get(task_id)
            if task.status in _TERMINAL_TASK_STATES:
                return task
            if asyncio.get_event_loop().time() >= deadline:
                return task
            await asyncio.sleep(0.05)

    async def _fail_plan(self, plan: Plan, reason: str, correlation_id: str | None) -> None:
        self._set_plan_status(plan.id, "failed")
        self._set_mission_status(plan.mission_id, "failed")
        self.recorder.record(
            "plan_failed", actor="system", reason=reason,
            mission_id=plan.mission_id, plan_id=plan.id, correlation_id=correlation_id)
        await self._publish(EventType.PLAN_FAILED,
                            {"mission_id": plan.mission_id, "plan_id": plan.id,
                             "reason": reason}, correlation_id, severity="error")

    def _set_plan_status(self, plan_id: str, status: str) -> None:
        session = self._session_factory()
        try:
            repo = PlanRepository(session)
            row = repo.get(plan_id)
            if row is not None:
                row.status = status
                repo.save(row)
        finally:
            session.close()

    def _update_step(self, step_id: str, **fields) -> None:
        session = self._session_factory()
        try:
            from sqlalchemy import select
            row = session.scalar(select(PlanStep).where(PlanStep.id == step_id))
            if row is not None:
                for key, value in fields.items():
                    setattr(row, key, value)
                session.commit()
        finally:
            session.close()

    # ------------------------------------------------------------ explanation
    def explanation(self, plan_id: str) -> dict:
        plan = self.get_plan(plan_id)
        mission = self.get_mission(plan.mission_id)
        decisions, _ = self.recorder.list(mission_id=mission.id, limit=500)
        decisions = [d for d in decisions if d.plan_id in (None, plan.id)]
        llm_used = plan.planner.startswith("llm:")
        if llm_used:
            honesty = (f"The plan was proposed by {plan.planner} and passed the "
                       "identical validation gate as deterministic plans before execution.")
        else:
            honesty = ("No LLM was used for this plan: it was produced by the "
                       "deterministic baseline planner (rule-engine) and validated "
                       "against the registered tool registry.")
        steps = []
        for s in sorted(plan.steps, key=lambda s: s.order_index):
            task_status = None
            if s.task_id:
                try:
                    task_status = self._tasks.get(s.task_id).status
                except NotFoundError:
                    task_status = None
            steps.append({
                "order": s.order_index, "name": s.name, "tool_name": s.tool_name,
                "step_status": s.status, "task_id": s.task_id, "task_status": task_status,
                "verification_status": s.verification_status,
                "verification_detail": s.verification_detail,
            })
        return {
            "plan_id": plan.id, "mission_id": mission.id, "mission_text": mission.text,
            "mission_status": mission.status, "plan_status": plan.status,
            "planner": plan.planner, "model_profile": plan.model_profile,
            "llm_used": llm_used, "honesty_statement": honesty,
            "mode_at_intake": mission.mode, "current_mode": self._settings.mode,
            "steps": steps,
            "decisions": [
                {"type": d.decision_type, "actor": d.actor, "reason": d.reason,
                 "at": d.created_at.isoformat() if d.created_at else None}
                for d in decisions
            ],
            "outcome": plan.status,
        }

    # ------------------------------------- P-14 Stage B (DEF-E1): P-03 path
    async def assess_opportunity(
        self, principal: Principal, opportunity_id: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Thin P-02 assessment over a P-03 opportunity (DEF-E1).

        P-02 consumes P-03's OWN evaluation report and score — the
        scoring logic stays in P-03 (no duplicated engine here). The
        assessment is recorded as a P-02 decision record so the
        consumption is auditable, and published as a decision event.
        Raises NotFoundError for an unknown opportunity (propagated
        from P-03) and a plain-language error when the P-03 handle
        was never attached.
        """
        if self._opportunities is None:
            raise ValidationError(
                "opportunity assessment is unavailable: the P-03 "
                "opportunity service is not wired into P-02")
        report = self._opportunities.report(opportunity_id)
        score = self._opportunities.latest_score(opportunity_id)
        summary = report.get("executive_summary") or {}
        gaps = report.get("evidence_gaps") or []
        assessment = {
            "opportunity_id": opportunity_id,
            "overall_score": summary.get("overall_score"),
            "recommendation": summary.get("recommendation"),
            "hard_rejection": bool(summary.get("hard_rejection")),
            "validation_level": summary.get("validation_level"),
            "evidence_quality": summary.get("evidence_quality"),
            "score_id": score.id if score is not None else None,
            "score_value": (float(score.weighted_score)
                            if score is not None else None),
            "evidence_gap_count": len(gaps),
            "assessed_by": f"{principal.type.value}:{principal.id}",
            "source": "p03_evaluation_report",
        }
        reason = (
            f"P-02 assessment of P-03 opportunity {opportunity_id}: "
            f"overall_score={assessment['overall_score']}, "
            f"recommendation={assessment['recommendation']}, "
            f"validation_level={assessment['validation_level']}, "
            f"evidence_gaps={assessment['evidence_gap_count']}")
        decision = self.recorder.record(
            "opportunity_assessed", assessment["assessed_by"], reason,
            evidence={"assessment": assessment},
            correlation_id=correlation_id)
        assessment["decision_record_id"] = decision.id
        await self._publish(
            EventType.DECISION_RECORDED,
            {"decision_id": decision.id, "decision_type": "opportunity_assessed",
             "opportunity_id": opportunity_id,
             "overall_score": assessment["overall_score"]},
            correlation_id=correlation_id)
        return assessment

    # --------------------------------------------------------- model profiles
    def list_profiles(self) -> list:
        session = self._session_factory()
        try:
            return ModelProfileRepository(session).list()
        finally:
            session.close()

    def upsert_profile(self, principal: Principal, name: str, data: dict,
                       correlation_id: str | None = None):
        if principal.type != PrincipalType.OWNER:
            self.recorder.record(
                "model_profile_edit_denied", actor=f"{principal.type.value}:{principal.id}",
                reason=("model profiles are governance configuration (Article 0): "
                        "only the Owner principal may edit them"),
                evidence={"profile": name}, correlation_id=correlation_id)
            raise PermissionDeniedError(
                "model profiles may only be edited by the Owner principal (Article 0)",
                details={"profile": name})
        session = self._session_factory()
        try:
            from ..database.models.intelligence import ModelProfile
            repo = ModelProfileRepository(session)
            row = repo.get_by_name(name)
            creating = row is None
            if creating:
                # repositories commit inside add(): populate every column
                # BEFORE inserting, with governance-safe defaults.
                row = ModelProfile(name=name, task_classes=[], provider="ollama",
                                   model_id="", enabled=False, limits={})
            for field in ("task_classes", "provider", "model_id", "enabled", "limits"):
                if field in data and data[field] is not None:
                    setattr(row, field, data[field])
            row = repo.add(row) if creating else repo.save(row)
        finally:
            session.close()
        self.recorder.record(
            "model_profile_updated", actor=f"owner:{principal.id}",
            reason=f"model profile '{name}' updated by the owner",
            evidence={"profile": name, "provider": row.provider, "model_id": row.model_id,
                      "enabled": row.enabled},
            correlation_id=correlation_id)
        return row

    async def models_status(self, force: bool = False) -> dict:
        """Probe providers live; the result is cached for 60s (DEF-A5).

        The cache only ever holds a REAL probe result — provider
        availability is never fabricated. ``force=True`` re-probes.
        Health consumers (dashboard, SystemMonitor) call this without
        ``force`` and therefore read the cached real probe instead of
        probing live on every status call.
        """
        import time as _time

        if (not force and self._probe_cache is not None
                and _time.monotonic() - self._probe_cache[0] < 60.0):
            return self._probe_cache[1]
        status: dict = {"mode": self._settings.mode, "providers": {}}
        for name, provider in self.providers.items():
            available, detail = await provider.probe()
            models = await provider.list_models() if available else []
            status["providers"][name] = {
                "available": available, "detail": detail, "models": models}
        profiles = self.list_profiles()
        configured = [p.name for p in profiles if p.enabled and p.model_id]
        status["configured_profiles"] = configured
        status["planner_default"] = (
            "llm (router-selected profile)" if configured else
            "deterministic baseline planner (no model profile is configured — "
            "model_id values are empty until the owner selects local models)")
        self._probe_cache = (_time.monotonic(), status)
        return status

    def cached_models_status(self) -> dict | None:
        """Most recent probe result without triggering a new probe
        (P-14 Stage B, DEF-A5): the feed SystemMonitor includes in its
        status so provider health is visible outside the dashboard's
        own call path. None = no probe has run yet in this process."""
        return self._probe_cache[1] if self._probe_cache else None

    async def close(self) -> None:
        for provider in self.providers.values():
            try:
                await provider.close()
            except Exception:
                pass
