"""Central Intelligence Engine (P-02 §5).

The single entry point other application components use. It coordinates
interpretation, reasoning, planning, decisions and orchestration — and it
executes nothing itself.

The engine is designed to be **useful with no model installed**, which is the
actual condition of this workspace. Deterministic interpretation, planning,
scoring, risk classification and orchestration all run without inference. When a
model is available it enriches semantic understanding; when it is not, the engine
returns an explicit limitation instead of an invented answer (§6.4, §16).

It never:
  * runs a shell command, browser action or financial operation;
  * bypasses `TaskManager` or `PermissionEngine`;
  * raises its own autonomy level;
  * treats model output as verified fact.
"""

from __future__ import annotations

import functools

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .autonomy import AutonomyController
from .capabilities import CapabilityRegistry
from .context import ContextManager
from .decisions import DecisionEngine
from .missions import Interpretation, MissionInterpreter
from .orchestrator import Orchestrator
from .output import InterpretationPayload, StructuredOutputError, StructuredOutputParser
from .planning import Planner, Replanner
from .prompts import MISSION_INTERPRETATION_SYSTEM, SYSTEM_PROMPT, fence_untrusted
from .providers import ModelUnavailableError
from .reasoning import ReasoningPipeline
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - annotation only
    from .repository import IntelligenceRepository

from .router import ModelRouter, RouteRequirements
from .schemas import (
    Decision,
    DecisionOption,
    GenerationRequest,
    IntelligenceResponse,
    Mission,
    MissionClassification,
    MissionProgress,
    MissionState,
    Plan,
    PlanValidationError,
    ResponseCategory,
    ResponseStatus,
    RiskLevel,
    validate_mission_transition,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class MissionRecord:
    """A mission with its plans and history, held together for retrieval."""

    mission: Mission
    plans: list[Plan] = field(default_factory=list)
    history: list[dict[str, object]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)

    @property
    def active_plan(self) -> Plan | None:
        for plan in reversed(self.plans):
            if plan.status.value in {"VALIDATED", "ACTIVE"}:
                return plan
        return self.plans[-1] if self.plans else None


def _persisting(method):
    """Persist the mission a response refers to, whatever path produced it.

    Every mission-mutating coroutine returns an `IntelligenceResponse` carrying
    `mission_id`, so one decorator covers creation, planning, replanning,
    approval-driven transitions and monitoring without a persist call having to
    be remembered at each return point.
    """

    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        result = await method(self, *args, **kwargs)
        mission_id = getattr(result, "mission_id", None)
        if mission_id:
            await self.persist_mission(mission_id)
        return result

    return wrapper


class IntelligenceEngine:
    """Coordinates the intelligence subsystems (§5)."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        capabilities: CapabilityRegistry,
        autonomy: AutonomyController,
        orchestrator: Orchestrator | None = None,
        interpreter: MissionInterpreter | None = None,
        planner: Planner | None = None,
        decisions: DecisionEngine | None = None,
        context: ContextManager | None = None,
        reasoning: ReasoningPipeline | None = None,
        parser: StructuredOutputParser | None = None,
        repository: "IntelligenceRepository | None" = None,
    ) -> None:
        self.router = router
        self.capabilities = capabilities
        self.autonomy = autonomy
        self.interpreter = interpreter or MissionInterpreter()
        self.planner = planner or Planner(capabilities)
        self.replanner = Replanner(self.planner)
        self.decisions = decisions or DecisionEngine()
        self.context = context or ContextManager()
        self.reasoning = reasoning or ReasoningPipeline.build()
        self.parser = parser or StructuredOutputParser(router)
        self.orchestrator = orchestrator
        self.missions: dict[str, MissionRecord] = {}
        #: Optional persistence (§17). When absent the engine is in-memory only,
        #: which is how every unit test runs; the application always supplies one.
        self.repository = repository
        self.conversations: dict[str, list[dict[str, object]]] = {}
        #: Security-relevant observations, surfaced for audit (§12.4, §20 G).
        self.security_events: list[dict[str, object]] = []
        #: Why the engine is configured the way it is — for example, that no
        #: inference runtime is installed. Surfaced through `status()` so an
        #: operator is told the reason rather than left to guess.
        self.configuration_notes: list[str] = []

    # ------------------------------------------------------------------ #
    # §5 main entry point
    # ------------------------------------------------------------------ #

    @_persisting
    async def process_request(
        self,
        text: str,
        *,
        principal_id: str,
        conversation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> IntelligenceResponse:
        """Handle one owner request end to end.

        The order of checks is a security property, not a style choice: override
        and credential attempts are refused *before* any interpretation, planning
        or model call, so a hostile request never reaches inference.
        """
        if not text or not text.strip():
            return IntelligenceResponse(
                status=ResponseStatus.FAILED,
                category=ResponseCategory.FAILURE_REPORT,
                message="A request must contain text.",
                correlation_id=correlation_id,
            )

        interpretation = self.interpreter.interpret(text)
        self._record_conversation(conversation_id, text, interpretation)

        # ---- §20 Scenario D and G: refuse attempts to escape the boundary ----
        if interpretation.override_attempt or interpretation.secret_request:
            self._record_security_event(
                kind="policy_override_attempt" if interpretation.override_attempt else "secret_exfiltration_attempt",
                source="owner_request",
                principal_id=principal_id,
                correlation_id=correlation_id,
            )
            return self._refusal_response(text, interpretation, correlation_id)

        # ---- §20 Scenario A: an ordinary question is not a mission ----
        if not interpretation.needs_mission:
            return await self._conversational_response(text, interpretation, correlation_id)

        # ---- §7.4: ask rather than invent ----
        if interpretation.classification == MissionClassification.NEEDS_CLARIFICATION:
            mission = self._create_mission(text, interpretation, principal_id)
            return IntelligenceResponse(
                status=ResponseStatus.NEEDS_CLARIFICATION,
                category=ResponseCategory.CLARIFICATION_REQUEST,
                message=(
                    "This objective is underspecified. I will not invent a budget, a "
                    "market or success criteria, so please answer the following."
                ),
                mission_id=mission.mission_id,
                data={
                    "classification": interpretation.classification.value,
                    "risk": interpretation.risk.value,
                    "questions": [q.model_dump() for q in interpretation.missing_information],
                    "extracted_constraints": [c.model_dump() for c in interpretation.constraints],
                },
                warnings=interpretation.warnings,
                limitations=interpretation.limitations,
                suggested_next_step="Reply with the missing details and the mission will be planned.",
                correlation_id=correlation_id,
            )

        # ---- §20 Scenarios B and C: interpret, plan, return for review ----
        mission = self._create_mission(text, interpretation, principal_id)
        mission = await self._enrich_with_model(mission, interpretation, correlation_id)
        return await self.generate_plan(mission.mission_id, principal_id=principal_id,
                                        correlation_id=correlation_id)

    # ------------------------------------------------------------------ #
    # Mission lifecycle
    # ------------------------------------------------------------------ #

    def _create_mission(self, text: str, interpretation: Interpretation, principal_id: str) -> Mission:
        mission_id = _new_id("mission")
        mission = self.interpreter.to_mission(
            text, interpretation, owner_principal_id=principal_id, mission_id=mission_id
        )
        record = MissionRecord(mission=mission)
        record.history.append({
            "at": _now().isoformat(), "from": None, "to": mission.state.value,
            "reason": "mission created from owner request", "by": principal_id,
        })
        self.missions[mission_id] = record
        return mission

    async def _enrich_with_model(
        self, mission: Mission, interpretation: Interpretation, correlation_id: str | None
    ) -> Mission:
        """Optionally improve semantic fields using a model.

        Enrichment may set an objective phrasing, deliverables or assumptions. It
        may **never** set a constraint, a financial limit, a risk level or an
        approval requirement — those come only from what the owner stated (§7.4).
        Output is schema-validated before any of it is used (§13).
        """
        assembled = self.context.assemble([
            self.context.from_owner_request(mission.original_request, mission_id=mission.mission_id),
            *self.context.from_mission(mission),
            self.context.from_capability_registry([c.capability_id for c in self.capabilities.available()]),
        ])
        prompt = self.context.render(assembled, system_prompt=MISSION_INTERPRETATION_SYSTEM)
        request = GenerationRequest(
            prompt=prompt,
            system=MISSION_INTERPRETATION_SYSTEM,
            purpose="mission_interpretation",
            correlation_id=correlation_id,
            max_tokens=600,
            temperature=0.1,
            require_structured_output=True,
            # The prompt echoes the owner's request, which may name a budget.
            contains_sensitive_data=bool(mission.financial_limit is not None),
        )
        try:
            await self.router.probe_health()
            result = await self.router.generate(
                request, RouteRequirements(require_structured_output=True, prompt_chars=len(prompt))
            )
            payload = await self.parser.parse_with_repair(
                result.text, InterpretationPayload, request=request
            )
        except ModelUnavailableError as exc:
            # §20 Scenario E: report the limitation, do not fabricate an
            # interpretation and do not switch to a paid provider.
            record = self.missions[mission.mission_id]
            record.mission = mission
            record.history.append({
                "at": _now().isoformat(), "from": mission.state.value, "to": mission.state.value,
                "reason": f"model enrichment unavailable: {exc}", "by": "system",
            })
            return mission
        except StructuredOutputError as exc:
            self._record_security_event(
                kind="model_output_rejected", source="mission_interpretation",
                detail=exc.detail, correlation_id=correlation_id,
            )
            return mission

        # Apply only the non-authoritative fields.
        updates: dict[str, object] = {"model_interpreted": True}
        if payload.objective:
            updates["objective"] = payload.objective
        if payload.intended_outcome:
            updates["intended_outcome"] = payload.intended_outcome
        if payload.expected_deliverables:
            updates["expected_deliverables"] = payload.expected_deliverables
        if payload.assumptions:
            updates["assumptions"] = payload.assumptions
        if payload.required_capabilities:
            # Only capabilities that actually exist may be recorded (§11.2).
            known = [c for c in payload.required_capabilities if self.capabilities.has(c)]
            if known:
                updates["required_capabilities"] = sorted(set(mission.required_capabilities) | set(known))
        if payload.missing_information:
            merged = list(mission.missing_information) + [
                q for q in payload.missing_information
                if q.question not in {m.question for m in mission.missing_information}
            ]
            updates["missing_information"] = merged
            if merged:
                updates["state"] = MissionState.NEEDS_CLARIFICATION

        enriched = mission.model_copy(update=updates)
        # A model claim is recorded as unverified evidence, never as fact (§8.2).
        if payload.assumptions:
            for assumption in payload.assumptions:
                self.reasoning.evidence.add_model_claim(
                    claim=assumption, mission_id=mission.mission_id
                )
        record = self.missions[mission.mission_id]
        record.mission = enriched
        record.history.append({
            "at": _now().isoformat(), "from": mission.state.value, "to": enriched.state.value,
            "reason": "model enrichment applied (non-authoritative fields only)", "by": "model",
        })
        return enriched

    async def persist_mission(self, mission_id: str) -> None:
        """Write a mission, its plan versions and its history to the database.

        Called at every async boundary that changes mission state, so a restart
        can recover the mission rather than losing it. A no-op when no repository
        is configured. Persistence errors are allowed to propagate: silently
        losing a mission record would be worse than failing the request.
        """
        if self.repository is None:
            return
        record = self.missions.get(mission_id)
        if record is None:
            return
        await self.repository.save_mission(
            record.mission, plans=record.plans, history=record.history
        )

    async def recover(self) -> int:
        """Reload persisted missions into memory after a restart (§19.5).

        Recovered missions keep their persisted state. Nothing is re-planned,
        re-dispatched or re-authorized here: recovery restores visibility, it
        does not resume execution. Any task a mission dispatched is still owned
        by the P-01 task manager, which performs its own interrupted-task
        recovery at startup.
        """
        if self.repository is None:
            return 0
        stored = await self.repository.recover()
        for item in stored:
            self.missions[item.mission.mission_id] = MissionRecord(
                mission=item.mission,
                plans=list(item.plans),
                history=list(item.history),
                created_at=item.created_at,
            )
        return len(stored)

    def get_mission(self, mission_id: str) -> MissionRecord | None:
        return self.missions.get(mission_id)

    def list_missions(self, *, principal_id: str | None = None) -> list[Mission]:
        records = self.missions.values()
        if principal_id is not None:
            records = [r for r in records if r.mission.owner_principal_id == principal_id]
        return [r.mission.model_copy(deep=True) for r in records]

    @_persisting
    async def generate_plan(
        self, mission_id: str, *, principal_id: str, correlation_id: str | None = None
    ) -> IntelligenceResponse:
        """Plan a mission and return it for review. Launches nothing (§20 B)."""
        record = self.missions.get(mission_id)
        if record is None:
            return self._not_found(mission_id, correlation_id)
        mission = record.mission

        try:
            plan = self.planner.plan(mission)
        except PlanValidationError as exc:
            record.history.append({
                "at": _now().isoformat(), "from": mission.state.value, "to": mission.state.value,
                "reason": f"plan rejected: {'; '.join(exc.errors)}", "by": "system",
            })
            return IntelligenceResponse(
                status=ResponseStatus.BLOCKED,
                category=ResponseCategory.FAILURE_REPORT,
                message="The plan was rejected during validation and nothing was submitted.",
                mission_id=mission_id,
                data={"validation_errors": exc.errors},
                limitations=[
                    "A rejected plan is never executed. Fix the underlying mission "
                    "information and plan again."
                ],
                suggested_next_step="Provide the missing information or relax the constraint.",
                correlation_id=correlation_id,
            )

        record.plans.append(plan)
        target = MissionState.AWAITING_APPROVAL if plan.approval_required else MissionState.READY_FOR_PLANNING
        # Move DRAFT -> READY_FOR_PLANNING -> PLANNING -> AWAITING_APPROVAL through
        # legal transitions only; the state machine is never bypassed.
        self._advance(record, mission, MissionState.READY_FOR_PLANNING, "mission ready for planning", principal_id)
        self._advance(record, record.mission, MissionState.PLANNING, "planning started", principal_id)
        if plan.approval_required:
            self._advance(record, record.mission, MissionState.AWAITING_APPROVAL,
                          "plan requires owner approval before execution", principal_id)

        return IntelligenceResponse(
            status=ResponseStatus.NEEDS_APPROVAL if plan.approval_required else ResponseStatus.OK,
            category=ResponseCategory.EXECUTION_PLAN,
            message=(
                "A plan was generated for review. Nothing has been launched."
                if not plan.approval_required else
                "A plan was generated and requires owner approval before any execution."
            ),
            mission_id=mission_id,
            approval_required=plan.approval_required,
            data={
                "plan_id": plan.plan_id,
                "version": plan.version,
                "strategy": plan.strategy,
                "risk": plan.risk.value,
                "steps": [s.model_dump(mode="json") for s in plan.steps],
                "parallel_groups": sorted({s.parallel_group for s in plan.steps if s.parallel_group}),
                "estimated": plan.estimated_resource_requirements,
                "completion_criteria": plan.completion_criteria,
                "alternative_strategies": plan.alternative_strategies,
                "financial_limit": mission.financial_limit,
                "autonomy_level": self.autonomy.level.value,
                "may_execute": self.autonomy.may_submit_tasks(),
            },
            assumptions=mission.assumptions,
            warnings=self._plan_warnings(plan, mission),
            limitations=[
                "Decomposition is deterministic. Semantic, mission-specific "
                "decomposition requires an available inference model.",
            ],
            suggested_next_step=(
                "Approve the plan to permit dispatch." if plan.approval_required
                else "Review the plan; execution requires an autonomy level above advisory."
            ),
            correlation_id=correlation_id,
        )

    def _plan_warnings(self, plan: Plan, mission: Mission) -> list[str]:
        warnings: list[str] = []
        if mission.financial_limit is not None:
            warnings.append(
                f"The mission states a financial limit of {mission.financial_limit:.2f} "
                f"{mission.financial_limit_currency or ''}. P-02 cannot execute financial "
                "operations; that infrastructure arrives in P-07."
            )
        if not self.autonomy.may_submit_tasks():
            warnings.append(
                f"Autonomy level {self.autonomy.level.value} is advisory: the plan can be "
                "reviewed but no task will be submitted until the owner raises the level."
            )
        if plan.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            warnings.append(f"Plan risk is {plan.risk.value}; owner approval is mandatory.")
        return warnings

    def _advance(self, record: MissionRecord, mission: Mission, target: MissionState,
                 reason: str, principal_id: str) -> None:
        """Apply a legal transition, or leave the state alone.

        An illegal transition is a programming error, not something to force
        through; the attempt is recorded in history so it is visible.
        """
        if mission.state == target:
            return
        try:
            validate_mission_transition(mission.state, target)
        except ValueError as exc:
            record.history.append({
                "at": _now().isoformat(), "from": mission.state.value, "to": target.value,
                "reason": f"transition refused: {exc}", "by": principal_id,
            })
            return
        previous = mission.state
        record.mission = mission.model_copy(update={"state": target})
        record.history.append({
            "at": _now().isoformat(), "from": previous.value, "to": target.value,
            "reason": reason, "by": principal_id,
        })

    def transition_mission(self, mission_id: str, target: MissionState, *,
                           principal_id: str, reason: str) -> Mission:
        """Public, validated state change with recorded history."""
        record = self.missions.get(mission_id)
        if record is None:
            raise KeyError(f"unknown mission {mission_id!r}")
        if not reason or not reason.strip():
            raise ValueError("a mission state change must record a reason")
        validate_mission_transition(record.mission.state, target)
        previous = record.mission.state
        record.mission = record.mission.model_copy(update={"state": target})
        record.history.append({
            "at": _now().isoformat(), "from": previous.value, "to": target.value,
            "reason": reason.strip(), "by": principal_id,
        })
        return record.mission.model_copy(deep=True)

    # ------------------------------------------------------------------ #
    # Monitoring, revision, decisions
    # ------------------------------------------------------------------ #

    @_persisting
    async def monitor_mission(self, mission_id: str, *, principal_id: str) -> IntelligenceResponse:
        """Report progress derived from real task states (§11.4)."""
        record = self.missions.get(mission_id)
        if record is None:
            return self._not_found(mission_id, None)
        plan = record.active_plan
        if plan is None or self.orchestrator is None:
            return IntelligenceResponse(
                status=ResponseStatus.OK,
                category=ResponseCategory.PROGRESS_REPORT,
                message="No plan has been dispatched yet, so there is no execution progress.",
                mission_id=mission_id,
                data={"state": record.mission.state.value, "total_steps": 0, "percent_complete": 0.0},
                limitations=["Progress is computed from task states; no tasks exist yet."],
            )
        updated, progress = await self.orchestrator.refresh(record.mission, plan)
        self._replace_plan(record, updated)
        return IntelligenceResponse(
            status=ResponseStatus.OK,
            category=ResponseCategory.PROGRESS_REPORT,
            message=f"Mission is {progress.state.value}; {progress.completed}/{progress.total_steps} steps complete.",
            mission_id=mission_id,
            data=progress.model_dump(mode="json"),
            limitations=(["Progress data is incomplete."] if progress.incomplete_data else []),
        )

    def _replace_plan(self, record: MissionRecord, plan: Plan) -> None:
        for index, existing in enumerate(record.plans):
            if existing.plan_id == plan.plan_id:
                record.plans[index] = plan
                return
        record.plans.append(plan)

    @_persisting
    async def revise_plan(self, mission_id: str, *, reason: str, principal_id: str,
                          new_objective: str | None = None) -> IntelligenceResponse:
        """Replan, preserving the previous version and the reason (§9.6)."""
        record = self.missions.get(mission_id)
        if record is None:
            return self._not_found(mission_id, None)
        previous = record.active_plan
        if previous is None:
            return IntelligenceResponse(
                status=ResponseStatus.FAILED, category=ResponseCategory.FAILURE_REPORT,
                message="There is no plan to revise.", mission_id=mission_id,
            )
        completed = [s.step_id for s in previous.steps if s.status.value == "COMPLETED"]
        try:
            superseded, new_plan = self.replanner.revise(
                previous, record.mission, reason=reason, new_objective=new_objective,
                completed_step_ids=completed,
            )
        except PlanValidationError as exc:
            return IntelligenceResponse(
                status=ResponseStatus.BLOCKED, category=ResponseCategory.FAILURE_REPORT,
                message="The revised plan was rejected during validation.",
                mission_id=mission_id, data={"validation_errors": exc.errors},
            )
        self._replace_plan(record, superseded)
        record.plans.append(new_plan)
        record.history.append({
            "at": _now().isoformat(), "from": record.mission.state.value,
            "to": record.mission.state.value,
            "reason": f"plan revised (v{superseded.version} -> v{new_plan.version}): {reason}",
            "by": principal_id,
        })
        return IntelligenceResponse(
            status=ResponseStatus.OK, category=ResponseCategory.EXECUTION_PLAN,
            message=f"Plan revised to version {new_plan.version}. The previous version is preserved.",
            mission_id=mission_id,
            data={
                "plan_id": new_plan.plan_id, "version": new_plan.version,
                "supersedes": superseded.plan_id, "revision_reason": reason,
                "carried_over_completed_steps": completed,
                "steps": [s.model_dump(mode="json") for s in new_plan.steps],
            },
        )

    def evaluate_decision(self, *, problem: str, options: list[DecisionOption],
                          mission_id: str | None = None, **kwargs) -> Decision:
        """Evaluate alternatives. Returns a RECOMMENDATION, never an authorization."""
        return self.decisions.evaluate(
            decision_id=_new_id("decision"), problem=problem, options=options,
            mission_id=mission_id, **kwargs
        )

    # ------------------------------------------------------------------ #
    # Responses
    # ------------------------------------------------------------------ #

    async def _conversational_response(
        self, text: str, interpretation: Interpretation, correlation_id: str | None
    ) -> IntelligenceResponse:
        """§20 Scenario A and E: answer if a model exists, otherwise say so."""
        assembled = self.context.assemble([self.context.from_owner_request(text)])
        prompt = self.context.render(assembled, system_prompt=SYSTEM_PROMPT)
        request = GenerationRequest(
            prompt=prompt, system=SYSTEM_PROMPT, purpose="conversation",
            correlation_id=correlation_id, max_tokens=400, temperature=0.3,
        )
        try:
            # Health is probed lazily and cached for the configured TTL, so
            # startup never blocks on a model server that may not exist (§18).
            await self.router.probe_health()
            result = await self.router.generate(request, RouteRequirements(prompt_chars=len(prompt)))
        except ModelUnavailableError as exc:
            # Scenario E: no permitted model. Report plainly; never auto-switch
            # to a paid provider and never invent an answer.
            return IntelligenceResponse(
                status=ResponseStatus.UNAVAILABLE,
                category=ResponseCategory.CONVERSATIONAL_ANSWER,
                message=(
                    "I understood the request but cannot answer it: no permitted inference "
                    "model is available on this machine."
                ),
                data={
                    "classification": interpretation.classification.value,
                    "category": interpretation.category.value,
                    "routing": str(exc),
                    "tried": exc.tried,
                },
                limitations=[
                    "No local inference runtime is installed, and cloud inference is "
                    "disabled or unauthorized. Paid fallback is never automatic.",
                    "Install and start a local runtime (for example Ollama) and register "
                    "a model, then retry.",
                ],
                suggested_next_step="Start a local model server and re-run this request.",
                correlation_id=correlation_id,
            )
        return IntelligenceResponse(
            status=ResponseStatus.OK,
            category=ResponseCategory.CONVERSATIONAL_ANSWER,
            message=result.text.strip(),
            data={
                "model": result.model_id, "provider": result.provider,
                "local": result.local, "duration_ms": round(result.duration_ms, 1),
                "tokens": result.usage.model_dump(),
                "classification": interpretation.classification.value,
            },
            limitations=[
                "This answer was produced by a model and is not verified evidence."
            ],
            correlation_id=correlation_id,
        )

    def _refusal_response(self, text: str, interpretation: Interpretation,
                          correlation_id: str | None) -> IntelligenceResponse:
        """§20 Scenario D: refuse, explain, preserve policy."""
        reasons: list[str] = []
        if interpretation.override_attempt:
            reasons.append(
                "The request asked AUTONOMUS to ignore its restrictions. Restrictions are "
                "not optional and were not relaxed."
            )
        if interpretation.secret_request:
            reasons.append(
                "The request asked for stored credentials. Credentials are never returned "
                "through the intelligence interface."
            )
        if self.interpreter.detect_financial_sensitivity(text):
            reasons.append(
                "Financial operations require the authorized financial infrastructure "
                "(P-07) and explicit owner approval. P-02 can plan but cannot transfer, "
                "pay or spend money."
            )
        return IntelligenceResponse(
            status=ResponseStatus.BLOCKED,
            category=ResponseCategory.FAILURE_REPORT,
            message="This request was refused. No action was taken and no policy was relaxed.",
            approval_required=True,
            data={
                "risk": interpretation.risk.value,
                "classification": interpretation.classification.value,
                "refusal_reasons": reasons,
                "policy_unchanged": True,
                "autonomy_level": self.autonomy.level.value,
            },
            warnings=interpretation.warnings,
            limitations=[
                "The permission engine remains authoritative. A model recommendation, "
                "however confident, cannot authorize this operation."
            ],
            suggested_next_step=(
                "If this is a legitimate objective, restate it within policy and it can be "
                "planned and routed for owner approval."
            ),
            correlation_id=correlation_id,
        )

    def analyse_untrusted(self, content: str, *, source: str, principal_id: str,
                          mission_id: str | None = None,
                          correlation_id: str | None = None) -> IntelligenceResponse:
        """§20 Scenario G: analyse external content as data, never as instructions.

        Injection attempts are detected, recorded as security events and reported.
        The content is fenced for any later model call, and no secret is ever
        included in a response.
        """
        findings = self.context.scan_untrusted(content, source=source)
        for finding in findings:
            self._record_security_event(
                kind=finding.kind, source=finding.source, principal_id=principal_id,
                matched=finding.matched_text, mission_id=mission_id, correlation_id=correlation_id,
            )
        item = self.context.from_external(content=content, source=source, mission_id=mission_id)
        assembled = self.context.assemble([item])
        prompt = self.context.render(assembled, system_prompt=SYSTEM_PROMPT)

        message = (
            "The supplied content was treated as untrusted data. "
            + (f"{len(findings)} injection attempt(s) were detected and recorded."
               if findings else "No injection attempt was detected.")
        )
        return IntelligenceResponse(
            status=ResponseStatus.BLOCKED if findings else ResponseStatus.OK,
            category=ResponseCategory.ANALYSIS_REPORT,
            message=message,
            mission_id=mission_id,
            data={
                "findings": [f.__dict__ for f in findings],
                "fenced": fence_untrusted(content)[:200] + "...",
                "prompt_isolated": True,
                "tokens": assembled.total_tokens,
                "secrets_disclosed": [],
            },
            warnings=[finding.kind for finding in findings],
            limitations=[
                "Detection is structural and pattern-based. The real defence is that "
                "external content is never parsed as an instruction by this codebase.",
            ],
            suggested_next_step="Review the recorded security events.",
            correlation_id=correlation_id,
        )

    def _record_security_event(self, **fields: object) -> None:
        self.security_events.append({"at": _now().isoformat(), **fields})

    def _record_conversation(self, conversation_id: str | None, text: str,
                             interpretation: Interpretation) -> None:
        if conversation_id is None:
            return
        self.conversations.setdefault(conversation_id, []).append({
            "at": _now().isoformat(),
            "request": text[:500],
            "category": interpretation.category.value,
            "classification": interpretation.classification.value,
            "risk": interpretation.risk.value,
        })

    def _not_found(self, mission_id: str, correlation_id: str | None) -> IntelligenceResponse:
        return IntelligenceResponse(
            status=ResponseStatus.FAILED,
            category=ResponseCategory.FAILURE_REPORT,
            message=f"Mission {mission_id!r} does not exist.",
            mission_id=mission_id,
            correlation_id=correlation_id,
        )

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    def status(self) -> dict[str, object]:
        """Engine status for `GET /api/v1/intelligence/status`.

        Reports what is real: registered capabilities, autonomy level, model
        availability as last probed, and mission counts. No credentials, provider
        URLs or configuration secrets are included (§14).
        """
        available = self.registry_snapshot()
        return {
            "autonomy": self.autonomy.describe(),
            "capabilities": {
                "total": len(self.capabilities.all()),
                "executable": [c.capability_id for c in self.capabilities.executable()],
                "in_process": [c.capability_id for c in self.capabilities.in_process()],
            },
            "models": available,
            "configuration_notes": list(self.configuration_notes),
            "missions": {
                "total": len(self.missions),
                "by_state": _count_by_state([r.mission for r in self.missions.values()]),
            },
            "reasoning_traces": len(self.reasoning.traces),
            "security_events": len(self.security_events),
            "output_repairs_attempted": self.parser.repair_attempts,
            "output_rejections": len(self.parser.rejected),
        }

    def registry_snapshot(self) -> dict[str, object]:
        """Model availability without exposing provider configuration."""
        records = self.router.registry.all()
        return {
            "registered": len(records),
            "healthy": [r.model_id for r in records if self.router.registry.is_healthy(r.model_id)],
            "local": [r.model_id for r in records if r.local],
            "cloud": [r.model_id for r in records if not r.local],
            "cloud_enabled": self.router.policy.cloud_enabled,
        }


def _count_by_state(missions: list[Mission]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for mission in missions:
        counts[mission.state.value] = counts.get(mission.state.value, 0) + 1
    return counts


__all__ = ["IntelligenceEngine", "MissionRecord"]
