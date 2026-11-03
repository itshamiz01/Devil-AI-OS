"""P-02 §17 — persistence for the intelligence layer.

The P-02 migration creates ten tables. This module is what actually writes to
them, so that intelligence state survives a restart instead of living only in
process memory.

Design rules:

* **Upsert by natural key, never delete.** §17 forbids destroying records, so a
  re-save updates the existing row and prior plan versions stay in place. A
  superseded plan is a row with `status=SUPERSEDED`, not a gap.
* **History is append-only.** `mission_history` gains only the entries that are
  not already stored, so re-saving a mission cannot duplicate or rewrite its
  audit trail.
* **No import from `engine.py`.** The engine depends on this module; depending
  back would be circular. Loaded state is returned as `StoredMission` and the
  engine maps it onto its own record type.
* **Operational accounting stays separate from money.** `model_usage` records
  inference cost so capacity can be understood. It is not a business ledger and
  is never summed into revenue or expenses (§17).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import func, select

from ..database.connection import Database
from ..database.models import (
    EvidenceRecord,
    HypothesisRecord,
    IntelligenceDecision,
    IntelligenceExecution,
    Mission,
    MissionHistory,
    ModelUsage,
    Plan,
    PlanStep,
    RegisteredModel,
)
from .schemas import (
    ClarificationQuestion,
    Constraint,
    Decision,
    DecisionOption,
    Evidence,
    Hypothesis,
    MissionClassification,
    MissionState,
    ModelCapabilities,
    ModelRecord,
    PlanStatus,
    PlanStep as PlanStepSchema,
    Plan as PlanSchema,
    RequestCategory,
    RiskLevel,
    StepStatus,
    UncertaintyLevel,
)
from .schemas import Mission as MissionSchema

#: Columns of `missions` written from the pydantic contract. Kept explicit so a
#: schema change cannot silently persist a partial row.
_MISSION_JSON_LISTS = (
    "constraints",
    "success_criteria",
    "assumptions",
    "required_capabilities",
    "expected_deliverables",
    "missing_information",
    "available_resources",
    "dependencies",
)


@dataclass
class StoredMission:
    """A mission exactly as persisted: the contract plus its plans and history."""

    mission: MissionSchema
    plans: list[PlanSchema] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime | None = None


class IntelligenceRepository:
    """Reads and writes the P-02 intelligence tables."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Missions
    # ------------------------------------------------------------------ #

    async def save_mission(
        self,
        mission: MissionSchema,
        *,
        plans: Sequence[PlanSchema] = (),
        history: Sequence[dict[str, Any]] = (),
    ) -> None:
        """Persist a mission, its plan versions and any new history entries."""
        async with self.db.session_factory() as session:
            row = await session.get(Mission, mission.mission_id)
            values = self._mission_values(mission)
            if row is None:
                session.add(Mission(id=mission.mission_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

            for plan in plans:
                await self._save_plan(session, mission.mission_id, plan)

            await self._append_history(session, mission.mission_id, history)
            await session.commit()

    async def load_mission(self, mission_id: str) -> StoredMission | None:
        async with self.db.session_factory() as session:
            row = await session.get(Mission, mission_id)
            if row is None:
                return None
            return await self._bundle(session, row)

    async def list_missions(
        self,
        *,
        owner_principal_id: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoredMission]:
        async with self.db.session_factory() as session:
            rows = await self._select_missions(
                session, owner_principal_id=owner_principal_id, state=state,
                limit=limit, offset=offset,
            )
            return [await self._bundle(session, r) for r in rows]

    async def count_missions(
        self, *, owner_principal_id: str | None = None, state: str | None = None
    ) -> int:
        async with self.db.session_factory() as session:
            query = select(func.count()).select_from(Mission)
            query = self._filter_missions(query, owner_principal_id, state)
            return int(await session.scalar(query) or 0)

    async def recover(self, *, limit: int = 500) -> list[StoredMission]:
        """Reload persisted missions after a restart (§19.5 mission recovery).

        Ordered oldest first so that a truncated recovery keeps the earliest
        missions rather than the most recent ones.
        """
        async with self.db.session_factory() as session:
            rows = (
                await session.execute(
                    select(Mission).order_by(Mission.created_at.asc()).limit(limit)
                )
            ).scalars().all()
            return [await self._bundle(session, r) for r in rows]

    # ------------------------------------------------------------------ #
    # Decisions
    # ------------------------------------------------------------------ #

    async def save_decision(self, decision: Decision, *, authorized_by: str | None = None) -> None:
        async with self.db.session_factory() as session:
            row = await session.get(IntelligenceDecision, decision.decision_id)
            values = self._decision_values(decision, authorized_by=authorized_by)
            if row is None:
                session.add(IntelligenceDecision(id=decision.decision_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    async def list_decisions(self, *, mission_id: str | None = None, limit: int = 100) -> list[Decision]:
        async with self.db.session_factory() as session:
            query = select(IntelligenceDecision).order_by(IntelligenceDecision.created_at.desc()).limit(limit)
            if mission_id is not None:
                query = query.where(IntelligenceDecision.mission_id == mission_id)
            rows = (await session.execute(query)).scalars().all()
            return [self._to_decision(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Evidence and hypotheses
    # ------------------------------------------------------------------ #

    async def save_evidence(self, evidence: Evidence) -> None:
        async with self.db.session_factory() as session:
            row = await session.get(EvidenceRecord, evidence.evidence_id)
            values = {
                "mission_id": evidence.mission_id,
                "source": evidence.source[:256],
                "observation": evidence.observation,
                "collected_at": evidence.collected_at,
                "reliability": evidence.reliability.value,
                "verification_status": evidence.verification_status.value,
                "stance": evidence.stance.value,
                "trust_domain": evidence.trust_domain.value,
                # A reference, never the artefact itself: storing retrieved
                # content verbatim would put untrusted text in the database.
                "content_reference": (evidence.content_reference or "")[:256] or None,
            }
            if row is None:
                session.add(EvidenceRecord(id=evidence.evidence_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    async def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        async with self.db.session_factory() as session:
            row = await session.get(HypothesisRecord, hypothesis.hypothesis_id)
            values = {
                "mission_id": hypothesis.mission_id,
                "statement": hypothesis.statement,
                "supporting_evidence": list(hypothesis.supporting_evidence),
                "contradicting_evidence": list(hypothesis.contradicting_evidence),
                "confidence": float(hypothesis.confidence),
                # Always labelled: a confidence figure is never presented as a
                # measured probability (§8.3).
                "confidence_basis": hypothesis.confidence_basis,
                "validation_requirement": hypothesis.validation_requirement,
                "status": hypothesis.status.value,
            }
            if row is None:
                session.add(HypothesisRecord(id=hypothesis.hypothesis_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    # ------------------------------------------------------------------ #
    # Registered models and usage accounting
    # ------------------------------------------------------------------ #

    async def upsert_model(
        self,
        record: ModelRecord,
        *,
        healthy: bool | None = None,
        health_detail: str | None = None,
        health_checked_at: datetime | None = None,
    ) -> None:
        """Persist a registry entry. `configuration` is stored but never returned by the API."""
        async with self.db.session_factory() as session:
            row = await session.get(RegisteredModel, record.model_id)
            capabilities = record.capabilities
            values: dict[str, Any] = {
                "provider": record.provider,
                "local": record.local,
                "context_window": int(capabilities.context_window),
                "supports_structured_output": bool(capabilities.supports_structured_output),
                "supports_tool_calling": bool(capabilities.supports_tool_calling),
                "supports_reasoning": bool(capabilities.supports_reasoning),
                "min_ram_gb": float(capabilities.min_ram_gb or 0.0),
                "available": bool(record.available),
                "cost_per_1k_tokens": float(record.cost_per_1k_tokens or 0.0),
                "limitations": list(record.limitations or []),
                "configuration": dict(record.configuration or {}),
            }
            if healthy is not None:
                values["healthy"] = bool(healthy)
            if health_detail is not None:
                values["health_detail"] = health_detail[:256]
            if health_checked_at is not None:
                values["health_checked_at"] = health_checked_at
            if row is None:
                session.add(RegisteredModel(model_id=record.model_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    async def list_models(self) -> list[ModelRecord]:
        async with self.db.session_factory() as session:
            rows = (await session.execute(select(RegisteredModel))).scalars().all()
            return [self._to_model_record(r) for r in rows]

    async def record_usage(
        self,
        *,
        request_id: str,
        provider: str,
        model_id: str,
        local: bool,
        duration_ms: float,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        estimated_cost: float,
        success: bool,
        error: str | None = None,
        purpose: str = "unspecified",
        correlation_id: str | None = None,
    ) -> None:
        """One inference attempt. Insert-only: usage history is never rewritten."""
        async with self.db.session_factory() as session:
            session.add(ModelUsage(
                request_id=str(request_id)[:64],
                provider=str(provider)[:64],
                model_id=str(model_id)[:128],
                local=bool(local),
                duration_ms=float(duration_ms or 0.0),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost=float(estimated_cost or 0.0),
                success=bool(success),
                error=(error or None),
                purpose=str(purpose)[:64],
                correlation_id=(str(correlation_id)[:64] if correlation_id else None),
            ))
            await session.commit()

    async def usage_summary(self) -> dict[str, Any]:
        """Aggregate inference accounting. Operational only — not business finance."""
        async with self.db.session_factory() as session:
            total = int(await session.scalar(select(func.count()).select_from(ModelUsage)) or 0)
            succeeded = int(await session.scalar(
                select(func.count()).select_from(ModelUsage).where(ModelUsage.success.is_(True))
            ) or 0)
            cost = float(await session.scalar(select(func.sum(ModelUsage.estimated_cost))) or 0.0)
            local = int(await session.scalar(
                select(func.count()).select_from(ModelUsage).where(ModelUsage.local.is_(True))
            ) or 0)
            return {"attempts": total, "succeeded": succeeded, "failed": total - succeeded,
                    "local_attempts": local, "estimated_cost": round(cost, 6)}

    async def record_execution(
        self,
        *,
        operation: str,
        mission_id: str | None = None,
        task_id: str | None = None,
        principal_id: str | None = None,
        status: str = "ok",
        duration_ms: float = 0.0,
        model_calls: int = 0,
        error_metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        async with self.db.session_factory() as session:
            session.add(IntelligenceExecution(
                operation=str(operation)[:64],
                mission_id=mission_id,
                task_id=task_id,
                principal_id=principal_id,
                status=str(status)[:32],
                duration_ms=float(duration_ms or 0.0),
                model_calls=int(model_calls or 0),
                # Metadata about a failure, never the prompt that caused it: §17
                # forbids storing full sensitive prompts.
                error_metadata=error_metadata,
                correlation_id=(str(correlation_id)[:64] if correlation_id else None),
            ))
            await session.commit()

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #

    def _mission_values(self, mission: MissionSchema) -> dict[str, Any]:
        values: dict[str, Any] = {
            "owner_principal_id": mission.owner_principal_id,
            "title": mission.title[:200],
            "original_request": mission.original_request,
            "objective": mission.objective,
            "intended_outcome": mission.intended_outcome,
            "state": mission.state.value,
            "category": mission.category.value,
            "classification": mission.classification.value,
            "risk": mission.risk.value,
            "approval_required": bool(mission.approval_required),
            "model_interpreted": bool(mission.model_interpreted),
            "financial_limit": mission.financial_limit,
            "financial_limit_currency": mission.financial_limit_currency,
            "time_constraint": mission.time_constraint,
        }
        for name in _MISSION_JSON_LISTS:
            items = getattr(mission, name, []) or []
            values[name] = [
                i.model_dump(mode="json") if hasattr(i, "model_dump") else i for i in items
            ]
        return values

    def _to_mission(self, row: Mission) -> MissionSchema:
        return MissionSchema(
            mission_id=row.id,
            owner_principal_id=row.owner_principal_id,
            title=row.title,
            original_request=row.original_request,
            objective=row.objective,
            intended_outcome=row.intended_outcome,
            state=MissionState(row.state),
            category=RequestCategory(row.category),
            classification=MissionClassification(row.classification),
            risk=RiskLevel(row.risk),
            approval_required=bool(row.approval_required),
            model_interpreted=bool(row.model_interpreted),
            financial_limit=row.financial_limit,
            financial_limit_currency=row.financial_limit_currency,
            time_constraint=row.time_constraint,
            constraints=[Constraint(**c) for c in (row.constraints or [])],
            success_criteria=list(row.success_criteria or []),
            assumptions=list(row.assumptions or []),
            required_capabilities=list(row.required_capabilities or []),
            expected_deliverables=list(row.expected_deliverables or []),
            missing_information=[ClarificationQuestion(**q) for q in (row.missing_information or [])],
            available_resources=list(row.available_resources or []),
            dependencies=list(row.dependencies or []),
        )

    async def _save_plan(self, session: Any, mission_id: str, plan: PlanSchema) -> None:
        row = await session.get(Plan, plan.plan_id)
        values = {
            "mission_id": mission_id,
            "version": int(plan.version),
            "objective": plan.objective,
            "strategy": plan.strategy,
            "status": plan.status.value,
            "risk": plan.risk.value,
            "approval_required": bool(plan.approval_required),
            "revision_reason": plan.revision_reason,
            "supersedes_plan_id": plan.supersedes_plan_id,
            "validation_errors": list(plan.validation_errors or []),
            "estimated_resource_requirements": dict(plan.estimated_resource_requirements or {}),
            "completion_criteria": list(plan.completion_criteria or []),
            "alternative_strategies": list(plan.alternative_strategies or []),
        }
        if row is None:
            row = Plan(id=plan.plan_id, **values)
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await session.flush()

        # Steps are upserted by (plan, step_key) so re-saving a plan never
        # duplicates its steps and never erases a task_id already recorded.
        for index, step in enumerate(plan.steps):
            existing = (await session.execute(
                select(PlanStep).where(
                    PlanStep.plan_id == plan.plan_id, PlanStep.step_key == step.step_id
                )
            )).scalar_one_or_none()
            step_values = {
                "title": step.title[:300],
                "order_index": index,
                "depends_on": list(step.depends_on or []),
                "capability_id": step.capability_id,
                "status": step.status.value,
                "task_id": step.task_id,
                "expected_output": step.expected_output,
                "completion_criteria": step.completion_criteria,
                "parallel_group": step.parallel_group,
                "estimated_duration_seconds": step.estimated_duration_seconds,
                "risk": step.risk.value,
            }
            if existing is None:
                session.add(PlanStep(plan_id=plan.plan_id, step_key=step.step_id, **step_values))
            else:
                for key, value in step_values.items():
                    setattr(existing, key, value)

    async def _append_history(
        self, session: Any, mission_id: str, history: Sequence[dict[str, Any]]
    ) -> None:
        """Insert only the history entries that are not already stored."""
        entries = list(history)
        stored = int(await session.scalar(
            select(func.count()).select_from(MissionHistory).where(MissionHistory.mission_id == mission_id)
        ) or 0)
        for entry in entries[stored:]:
            session.add(MissionHistory(
                mission_id=mission_id,
                from_state=entry.get("from"),
                to_state=str(entry.get("to") or ""),
                reason=str(entry.get("reason") or ""),
                actor_id=entry.get("by"),
            ))

    async def _bundle(self, session: Any, row: Mission) -> StoredMission:
        plans = (await session.execute(
            select(Plan).where(Plan.mission_id == row.id).order_by(Plan.version.asc())
        )).scalars().all()
        bundled: list[PlanSchema] = []
        for plan_row in plans:
            step_rows = (await session.execute(
                select(PlanStep).where(PlanStep.plan_id == plan_row.id).order_by(PlanStep.order_index.asc())
            )).scalars().all()
            bundled.append(self._to_plan(plan_row, step_rows))
        history_rows = (await session.execute(
            select(MissionHistory).where(MissionHistory.mission_id == row.id)
            .order_by(MissionHistory.created_at.asc())
        )).scalars().all()
        history = [
            {
                "at": h.created_at.isoformat() if h.created_at else None,
                "from": h.from_state,
                "to": h.to_state,
                "reason": h.reason,
                "by": h.actor_id,
            }
            for h in history_rows
        ]
        return StoredMission(
            mission=self._to_mission(row), plans=bundled, history=history, created_at=row.created_at
        )

    def _to_plan(self, row: Plan, step_rows: Sequence[PlanStep]) -> PlanSchema:
        return PlanSchema(
            plan_id=row.id,
            mission_id=row.mission_id,
            version=int(row.version),
            objective=row.objective,
            strategy=row.strategy,
            status=PlanStatus(row.status),
            risk=RiskLevel(row.risk),
            approval_required=bool(row.approval_required),
            revision_reason=row.revision_reason,
            supersedes_plan_id=row.supersedes_plan_id,
            validation_errors=list(row.validation_errors or []),
            estimated_resource_requirements=dict(row.estimated_resource_requirements or {}),
            completion_criteria=list(row.completion_criteria or []),
            alternative_strategies=list(row.alternative_strategies or []),
            steps=[
                PlanStepSchema(
                    step_id=s.step_key,
                    title=s.title,
                    depends_on=list(s.depends_on or []),
                    capability_id=s.capability_id,
                    status=StepStatus(s.status),
                    task_id=s.task_id,
                    expected_output=s.expected_output,
                    completion_criteria=s.completion_criteria,
                    parallel_group=s.parallel_group,
                    estimated_duration_seconds=s.estimated_duration_seconds,
                    risk=RiskLevel(s.risk),
                )
                for s in step_rows
            ],
        )

    def _decision_values(self, decision: Decision, *, authorized_by: str | None) -> dict[str, Any]:
        return {
            "mission_id": decision.mission_id,
            "problem": decision.problem,
            "options": [o.model_dump(mode="json") for o in (decision.options or [])],
            "evidence_refs": list(decision.evidence_refs or []),
            "assumptions": list(decision.assumptions or []),
            "constraints": list(decision.constraints or []),
            "scores": dict(decision.scores or {}),
            "selected_option_id": decision.selected_option_id,
            "reasoning_summary": decision.reasoning_summary,
            "risk": decision.risk.value,
            "uncertainty": decision.uncertainty.value,
            "approval_required": bool(decision.approval_required),
            "status": decision.status.value,
            "refusal_reason": decision.refusal_reason,
            "authorized_by_principal_id": authorized_by,
        }

    def _to_decision(self, row: IntelligenceDecision) -> Decision:
        return Decision(
            decision_id=row.id,
            mission_id=row.mission_id,
            problem=row.problem,
            options=[DecisionOption(**o) for o in (row.options or [])],
            evidence_refs=list(row.evidence_refs or []),
            assumptions=list(row.assumptions or []),
            constraints=list(row.constraints or []),
            scores=dict(row.scores or {}),
            selected_option_id=row.selected_option_id,
            reasoning_summary=row.reasoning_summary,
            risk=RiskLevel(row.risk),
            uncertainty=UncertaintyLevel(row.uncertainty),
            approval_required=bool(row.approval_required),
            status=row.status,
            refusal_reason=row.refusal_reason,
        )

    def _to_model_record(self, row: RegisteredModel) -> ModelRecord:
        return ModelRecord(
            model_id=row.model_id,
            provider=row.provider,
            local=bool(row.local),
            capabilities=ModelCapabilities(
                context_window=int(row.context_window),
                supports_structured_output=bool(row.supports_structured_output),
                supports_tool_calling=bool(row.supports_tool_calling),
                supports_reasoning=bool(row.supports_reasoning),
                min_ram_gb=float(row.min_ram_gb or 0.0),
            ),
            available=bool(row.available),
            cost_per_1k_tokens=float(row.cost_per_1k_tokens or 0.0),
            limitations=list(row.limitations or []),
            # Deliberately dropped on the way out to the API layer; kept here
            # because the registry needs it to talk to a provider.
            configuration=dict(row.configuration or {}),
        )

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #

    def _filter_missions(self, query: Any, owner_principal_id: str | None, state: str | None) -> Any:
        if owner_principal_id is not None:
            query = query.where(Mission.owner_principal_id == owner_principal_id)
        if state is not None:
            query = query.where(Mission.state == state)
        return query

    async def _select_missions(
        self, session: Any, *, owner_principal_id: str | None, state: str | None,
        limit: int, offset: int,
    ) -> Sequence[Mission]:
        query = select(Mission).order_by(Mission.created_at.desc()).limit(limit).offset(offset)
        query = self._filter_missions(query, owner_principal_id, state)
        return (await session.execute(query)).scalars().all()


__all__ = ["IntelligenceRepository", "StoredMission"]
