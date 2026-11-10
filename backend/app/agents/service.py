"""AgentFactoryService — the P-04 Dynamic Agent Factory.

Implements, on top of the P-01 substrate (tasks / permissions / approvals /
audit / events / monitoring / system_config) and the P-02 shared model
router:

- agent registry operations over the EXTENDED P-01 ``agents`` table,
- the §7 deterministic creation pipeline (evaluate -> decide -> create or
  hold for hash-bound owner approval),
- §9 assignment through the P-01 task engine (never a second queue),
- §11 lifecycle, §12 health/metrics, §13 configuration versioning,
- §10/§14 resource + scaling governance, §16.5 emergency controls.

Every mutating operation writes an ``audit_events`` row; state changes
also emit bus events. All decisions are deterministic code paths over
stored records — a model may recommend elsewhere in the system, but
nothing in this service asks a model anything.
"""
from __future__ import annotations

import copy
import datetime as dt
import json

from sqlalchemy import func, select

from ..core.config import Settings
from ..core.exceptions import NotFoundError, PermissionDeniedError
from ..database.models.agents import (
    AgentAssignment, AgentConfigurationHistory, AgentCreationRequest,
    AgentHealth, AgentMetric,
)
from ..database.models.base import utcnow
from ..database.models.core import Agent, Approval, AuditEvent
from ..database.repositories.agents import (
    AgentQueryRepository, AssignmentRepository, CapabilityRepository,
    ConfigHistoryRepository, CreationRequestRepository, HealthRepository,
    MetricRepository, TemplateRepository,
)
from ..database.repositories.core import AgentRepository, AuditRepository, ConfigRepository
from ..events.events import Event, EventType
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..permissions.models import Permission, Principal, PrincipalType
from ..tasks.manager import TaskManager
from . import constants as C
from .capabilities import CapabilityService, agent_principal
from .errors import (
    AgentNotFoundError, ApprovalRequiredError, AssignmentRejectedError,
    ConfigurationVersionConflictError, InitializationFailedError,
    LifecycleTransitionInvalidError, TemplateInvalidError,
)
from .lifecycle import ACTIVE_STATES, ASSIGNABLE_STATES, validate_transition
from .memory_interface import P04MemoryInterface
from .resources import AgentResourceManager
from .scaling import ScalingPolicy
from .templates import TemplateService
from .validation import validate_output_contract, validate_template_configuration

CREATE_ACTION = "agent_factory.create_agent"


def _deep_merge(base: dict, overrides: dict) -> dict:
    """Recursively merge requirement config_overrides into a template
    configuration: nested sections (resource_budget, tool_requirements)
    are patched key-by-key, never wholesale replaced; lists and scalars
    replace. The merged result is always re-validated before use."""
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


class AgentFactoryService:
    def __init__(self, session_factory, bus, permissions: PermissionEngine,
                 tasks: TaskManager, approvals: ApprovalService,
                 settings: Settings, monitor=None, intelligence=None):
        self._session_factory = session_factory
        self._bus = bus
        self._permissions = permissions
        self._tasks = tasks
        self._approvals = approvals
        self._settings = settings
        self._monitor = monitor
        self.templates = TemplateService(session_factory)
        self.capabilities = CapabilityService(session_factory, permissions, approvals)
        self.resources = AgentResourceManager(monitor)
        if intelligence is not None:
            # The P-02 service's single ModelRouter instance is THE shared
            # inference path for every logical agent (Scenario J).
            self.resources.bind_router(intelligence._router)
        self.memory = P04MemoryInterface(session_factory)
        self.scaling = ScalingPolicy()

    # ------------------------------------------------------------ utilities
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

    async def _publish(self, event_type: EventType, payload: dict,
                       severity: str = "info") -> None:
        if self._bus is not None:
            await self._bus.publish(Event(
                event_type=event_type, source="agents.factory",
                payload=payload, severity=severity))

    def _require_manage(self, principal: Principal, action: str) -> None:
        decision = self._permissions.check(principal, Permission.MANAGE_AGENTS.value)
        if not decision.allowed:
            self._audit(principal, action, "permission", Permission.MANAGE_AGENTS.value,
                        "deny", reason=decision.reason)
            raise PermissionDeniedError(
                f"principal {principal.type.value}:{principal.id} lacks manage_agents",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED",
                         "reason": decision.reason})

    @staticmethod
    def _require_owner(principal: Principal, action: str) -> None:
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                f"{action} requires the owner principal (Article 0 governance)",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED"})

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
                         "P-04 agent factory settings (owner/governance-editable only)")
        finally:
            session.close()

    def update_settings(self, principal: Principal, updates: dict) -> dict:
        """Owner-only (Article 0): agents can never change factory limits,
        including their own ceilings."""
        if principal.type is not PrincipalType.OWNER:
            self._audit(principal, "agent_factory.settings_update", "system_config",
                        C.SETTINGS_KEY, "deny",
                        reason="factory settings are owner-governance only")
            raise PermissionDeniedError(
                "factory settings may only be changed by the owner",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED"})
        unknown = set(updates) - set(C.DEFAULT_SETTINGS)
        if unknown:
            from ..core.exceptions import ValidationError
            raise ValidationError(f"unknown factory settings: {sorted(unknown)}")
        for key, value in updates.items():
            default = C.DEFAULT_SETTINGS[key]
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    from ..core.exceptions import ValidationError
                    raise ValidationError(f"setting {key} must be a boolean")
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                from ..core.exceptions import ValidationError
                raise ValidationError(f"setting {key} must be a non-negative integer")
        current = self.settings_values()
        current.update(updates)
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY,
                json.dumps({"version": C.SETTINGS_VERSION, "values": current}),
                "P-04 agent factory settings (owner/governance-editable only)")
        finally:
            session.close()
        self._audit(principal, "agent_factory.settings_update", "system_config",
                    C.SETTINGS_KEY, "allow", details={"updated_keys": sorted(updates)})
        return self.get_settings()

    # ---------------------------------------------------------------- seeding
    def seed_capabilities(self) -> int:
        session = self._session_factory()
        try:
            repo = CapabilityRepository(session)
            existing = {c.name for c in repo.list()}
            added = 0
            for entry in C.CAPABILITY_CATALOGUE:
                if entry["name"] in existing:
                    continue
                from ..database.models.agents import AgentCapability
                repo.add(AgentCapability(
                    name=entry["name"], description=entry["description"],
                    category=entry["category"], risk_level=entry["risk_level"],
                    approval_level=entry["approval_level"],
                    action_class=entry["action_class"],
                    mapped_permission=entry["mapped_permission"],
                    supported=entry["supported"],
                    enabled=entry.get("enabled", True),
                    resource_requirements={}, expiry_rule=None))
                added += 1
            return added
        finally:
            session.close()

    def seed_templates(self) -> int:
        settings = self.settings_values()
        system = Principal(PrincipalType.SYSTEM, "system")
        session = self._session_factory()
        try:
            existing = {t.name for t in TemplateRepository(session).list(limit=500)[0]}
        finally:
            session.close()
        added = 0
        for seed in C.SEED_TEMPLATES:
            if seed["name"] in existing:
                continue
            template = self.templates.create(
                system, name=seed["name"], category=seed["category"],
                description=seed["description"],
                configuration=copy.deepcopy(seed["configuration"]), settings=settings)
            version = self.templates.get_version(template.id, 1)
            if version.validation_status == "valid":
                self.templates.publish(system, template.id, version=1)
            added += 1
        return added

    # --------------------------------------------------------------- registry
    def get_agent(self, agent_id: str) -> Agent:
        session = self._session_factory()
        try:
            agent = AgentRepository(session).get(agent_id)
            if agent is None:
                raise AgentNotFoundError(f"agent {agent_id} not found",
                                         details={"error_category": "AGENT_NOT_FOUND"})
            return agent
        finally:
            session.close()

    @staticmethod
    def agent_to_dict(agent: Agent) -> dict:
        return {
            "id": agent.id, "name": agent.name, "role": agent.role,
            "agent_type": agent.agent_type, "description": agent.description,
            "parent_agent_id": agent.parent_agent_id,
            "business_ref": agent.business_ref, "objective": agent.objective,
            "model_profile": agent.model_profile, "status": agent.status,
            "template_id": agent.template_id, "template_version": agent.template_version,
            "configuration_version": agent.configuration_version,
            "security_classification": agent.security_classification,
            "budget": agent.budget,
            "created_by": ({"type": agent.created_by_type, "id": agent.created_by_id}
                           if agent.created_by_id else None),
            "last_activity_at": agent.last_activity_at.isoformat() if agent.last_activity_at else None,
            "retired_at": agent.retired_at.isoformat() if agent.retired_at else None,
            "created_at": agent.created_at.isoformat() if agent.created_at else None,
            "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
        }

    def _transition_sync(self, agent_id: str, target: str, *, actor: Principal,
                         reason: str | None = None) -> tuple[Agent, str]:
        """Validated lifecycle transition (DB + audit). Returns the agent
        and its previous state. Event publication is the async wrapper's
        job; synchronous callers (assignment refresh) use this directly so
        state never depends on an event loop being present."""
        session = self._session_factory()
        try:
            repo = AgentRepository(session)
            agent = repo.get(agent_id)
            if agent is None:
                raise AgentNotFoundError(f"agent {agent_id} not found",
                                         details={"error_category": "AGENT_NOT_FOUND"})
            current = agent.status
            if not validate_transition(current, target):
                self._audit(actor, "agent_factory.lifecycle_transition", "agent",
                            agent_id, "deny",
                            reason=f"invalid transition {current} -> {target}")
                raise LifecycleTransitionInvalidError(
                    f"invalid agent lifecycle transition {current} -> {target}",
                    details={"error_category": "LIFECYCLE_TRANSITION_INVALID",
                             "from": current, "to": target})
            agent.status = target
            if target == "retired":
                agent.retired_at = utcnow()
            agent.last_activity_at = utcnow()
            session.add(agent)
            session.commit()
            session.refresh(agent)
            result = agent
        finally:
            session.close()
        self._audit(actor, "agent_factory.lifecycle_transition", "agent", agent_id,
                    "allow", reason=reason,
                    details={"from": current, "to": target})
        return result, current

    async def transition_agent(self, agent_id: str, target: str, *, actor: Principal,
                               reason: str | None = None) -> Agent:
        result, current = self._transition_sync(agent_id, target, actor=actor,
                                                reason=reason)
        await self._publish(EventType.AGENT_STATE_CHANGED,
                            {"agent_id": agent_id, "from": current, "to": target,
                             "reason": reason})
        return result

    async def suspend_agent(self, agent_id: str, *, principal: Principal,
                            reason: str | None = None) -> Agent:
        self._require_manage(principal, "agent_factory.suspend")
        agent = await self.transition_agent(agent_id, "suspended", actor=principal,
                                            reason=reason or "suspended by operator")
        self._audit(principal, "agent_factory.suspend", "agent", agent_id, "allow",
                    reason=reason)
        return agent

    async def resume_agent(self, agent_id: str, *, principal: Principal) -> Agent:
        self._require_manage(principal, "agent_factory.resume")
        return await self.transition_agent(agent_id, "active", actor=principal,
                                           reason="resumed by operator")

    async def retire_agent(self, agent_id: str, *, principal: Principal,
                           reason: str | None = None) -> Agent:
        """Retirement preserves EVERYTHING: identity, configuration
        history, metrics, assignments and audit rows are never deleted."""
        self._require_manage(principal, "agent_factory.retire")
        agent = self.get_agent(agent_id)
        if agent.status != "retiring":
            agent = await self.transition_agent(agent_id, "retiring", actor=principal,
                                                reason=reason or "retirement initiated")
        agent = await self.transition_agent(agent_id, "retired", actor=principal,
                                            reason=reason or "retired")
        self._audit(principal, "agent_factory.retire", "agent", agent_id, "allow",
                    reason=reason,
                    details={"history_preserved": True})
        return agent

    # ------------------------------------------------------- creation pipeline
    def _catalogue_levels(self) -> dict[str, int | None]:
        session = self._session_factory()
        try:
            return {c.name: (c.approval_level if c.enabled else 3)
                    for c in CapabilityRepository(session).list()}
        finally:
            session.close()

    def _catalogue_supported(self) -> dict[str, bool]:
        session = self._session_factory()
        try:
            return {c.name: c.supported for c in CapabilityRepository(session).list()}
        finally:
            session.close()

    def _find_reusable_agent(self, requirement: dict, settings: dict) -> Agent | None:
        role = requirement["role"]
        required = set(requirement.get("capabilities") or [])
        session = self._session_factory()
        try:
            candidates = AgentQueryRepository(session).by_role(
                role, statuses=sorted(ASSIGNABLE_STATES))
        finally:
            session.close()
        for agent in candidates:
            if agent.template_id is None:
                continue  # unmanaged P-01 registration rows are not factory agents
            business = requirement.get("business_ref")
            if business and agent.business_ref not in (None, business):
                continue
            granted = set(self.capabilities.granted_capability_names(agent.id))
            if not required.issubset(granted):
                continue
            session = self._session_factory()
            try:
                active = AssignmentRepository(session).active_for_agent(agent.id)
            finally:
                session.close()
            template_config = self._pinned_config(agent)
            budget = self.resources.effective_budget(agent, template_config, settings)
            if len(active) >= int(budget["max_concurrent_tasks"]):
                continue
            return agent
        return None

    def _pinned_config(self, agent: Agent) -> dict | None:
        if not agent.template_id or not agent.template_version:
            return None
        session = self._session_factory()
        try:
            row = TemplateRepository(session).version(agent.template_id, agent.template_version)
            return row.configuration if row else None
        finally:
            session.close()

    def _resolve_template(self, requirement: dict):
        session = self._session_factory()
        try:
            repo = TemplateRepository(session)
            template = None
            if requirement.get("template_id"):
                template = repo.get(requirement["template_id"])
            elif requirement.get("template_name"):
                template = repo.get_by_name(requirement["template_name"])
            if template is None:
                for candidate in repo.list(limit=500)[0]:
                    if candidate.published_version is None:
                        continue
                    row = repo.version(candidate.id, candidate.published_version)
                    if row and (row.configuration or {}).get("role") == requirement["role"]:
                        template = candidate
                        break
            return template
        finally:
            session.close()

    def _decide(self, requirement: dict, principal: Principal, settings: dict) -> dict:
        """The deterministic §7.3 decision. Returns a dict with decision,
        reasons and the context the materializer needs. Pure policy over
        stored records — no model is consulted."""
        reasons: list[str] = []
        role = requirement["role"]
        requested_caps = list(requirement.get("capabilities") or [])

        # Gate 0: factory stopped (mode / safe mode / creation switch).
        if self._settings.mode == "emergency" or settings["safe_mode"] \
                or not settings["creation_enabled"]:
            return {"decision": "QUEUE_FOR_LATER",
                    "reasons": ["agent creation is stopped (emergency mode, safe mode "
                                "or creation disabled); requirement queued for later"],
                    "template": None}

        levels = self._catalogue_levels()
        supported = self._catalogue_supported()

        # Gate 1: capability sanity — unknown or PROHIBITED can never proceed.
        for name in requested_caps:
            if name not in levels:
                return {"decision": "REJECT_CREATION",
                        "reasons": [f"requested capability '{name}' is not in the catalogue"],
                        "template": None}
            if levels[name] >= 3:
                return {"decision": "REJECT_CREATION",
                        "reasons": [f"requested capability '{name}' is PROHIBITED "
                                    "(approval level 3, §8.3)"],
                        "template": None}
            if not supported.get(name):
                return {"decision": "REJECT_CREATION",
                        "reasons": [f"requested capability '{name}' is catalogued but not "
                                    "backed by any module in this build; the factory "
                                    "does not simulate capabilities"],
                        "template": None}

        # Gate 2: parent constraints (child limits + delegation depth).
        parent_id = requirement.get("parent_agent_id")
        if parent_id:
            parent = self.get_agent(parent_id)
            session = self._session_factory()
            try:
                children = AgentQueryRepository(session).count_children(parent_id)
            finally:
                session.close()
            if children >= int(settings["max_child_agents_per_parent"]):
                return {"decision": "REJECT_CREATION",
                        "reasons": [f"parent agent already has {children} child agents "
                                    f"(limit {settings['max_child_agents_per_parent']})"],
                        "template": None}
            depth, cursor, seen = 0, parent, set()
            while cursor is not None and cursor.parent_agent_id and cursor.id not in seen:
                seen.add(cursor.id)
                depth += 1
                cursor = self.get_agent(cursor.parent_agent_id)
            if depth + 1 > int(settings["max_delegation_depth"]):
                return {"decision": "REJECT_CREATION",
                        "reasons": ["delegation depth limit would be exceeded"],
                        "template": None}

        # Gate 3: repeated initialization failures — never endless replacements.
        template_hint = requirement.get("template_id")
        session = self._session_factory()
        try:
            failed_inits = CreationRequestRepository(session).count_failed_initializations(
                role, template_hint)
        finally:
            session.close()
        if failed_inits >= int(settings["max_initialization_failures_per_template"]):
            return {"decision": "REJECT_CREATION",
                    "reasons": [f"{failed_inits} previous initialization failures for this "
                                "role/template reached the cap; the factory does not "
                                "create endless replacements — diagnose the template"],
                    "template": None}

        # Gate 4: reuse an existing suitable agent FIRST.
        reusable = self._find_reusable_agent(requirement, settings)
        if reusable is not None:
            decision = "ASSIGN_TO_EXISTING_AGENT" if requirement.get("task") \
                else "REUSE_EXISTING_AGENT"
            reasons.append(
                f"existing agent {reusable.id} (role {role}) is assignable, holds the "
                "required capabilities and has free capacity; creating a duplicate "
                "is unnecessary")
            return {"decision": decision, "reasons": reasons, "template": None,
                    "reused_agent": reusable}

        # Gate 5: template resolution.
        template = self._resolve_template(requirement)
        if template is None:
            if role in C.ROLE_TO_CATEGORY:
                return {"decision": "REQUEST_OWNER_APPROVAL",
                        "reasons": [f"no published template covers role '{role}'; a new "
                                    "template is proposed (Mode C) and requires owner "
                                    "approval before use"],
                        "template": None, "propose_template": True}
            return {"decision": "REJECT_CREATION",
                    "reasons": [f"no template covers role '{role}' and the role is not "
                                "in the taxonomy"], "template": None}
        if template.status == "deprecated":
            return {"decision": "REJECT_CREATION",
                    "reasons": [f"template '{template.name}' is deprecated"],
                    "template": template}
        if template.published_version is None:
            return {"decision": "REJECT_CREATION",
                    "reasons": [f"template '{template.name}' has no published version; "
                                "unpublished templates never produce agents"],
                    "template": template}
        session = self._session_factory()
        try:
            version_row = TemplateRepository(session).version(
                template.id, template.published_version)
        finally:
            session.close()
        config = version_row.configuration or {}
        if version_row.validation_status != "valid":
            return {"decision": "REJECT_CREATION",
                    "reasons": [f"template '{template.name}' v{template.published_version} "
                                "is not valid; invalid templates never produce agents"],
                    "template": template}

        effective_config = copy.deepcopy(config)
        if requirement.get("config_overrides"):
            _deep_merge(effective_config, requirement["config_overrides"])
        effective_caps = sorted(set(effective_config.get("allowed_capabilities") or [])
                                | set(requested_caps))
        for name in effective_caps:
            if levels.get(name) is None or levels.get(name, 0) >= 3:
                return {"decision": "REJECT_CREATION",
                        "reasons": [f"template capability '{name}' is unknown or prohibited"],
                        "template": template}
            if not supported.get(name):
                return {"decision": "REJECT_CREATION",
                        "reasons": [f"template capability '{name}' is not backed by any "
                                    "module in this build"],
                        "template": template}

        # Gate 6: approval determination (§8.3).
        approval_reasons: list[str] = []
        max_level = max((levels[n] for n in effective_caps), default=0)
        if max_level >= 2:
            approval_reasons.append("creation includes a Level-2 (owner approval) capability")
        budget = effective_config.get("resource_budget") or {}
        if float(budget.get("memory_budget_mb", 0)) > 1024 \
                or float(budget.get("max_task_seconds", 0)) > 1800:
            approval_reasons.append("agent is resource-intensive (Level 2, §8.3)")
        if principal.type in (PrincipalType.AGENT, PrincipalType.SERVICE):
            approval_reasons.append(
                "creation requested by a non-owner principal; agents cannot multiply "
                "the fleet on their own authority")

        # Gate 7: fleet limits -> queue, never crash.
        session = self._session_factory()
        try:
            query = AgentQueryRepository(session)
            total = query.count_all()
            active = query.count_by_status(sorted(ACTIVE_STATES))
            since = utcnow() - dt.timedelta(hours=1)
            recent = query.creations_since(since)
            per_business = None
            if requirement.get("business_ref"):
                per_business = query.count_by_business(requirement["business_ref"])
        finally:
            session.close()
        if total >= int(settings["max_total_agents"]):
            return {"decision": "QUEUE_FOR_LATER",
                    "reasons": [f"total agent limit reached ({total}/{settings['max_total_agents']})"],
                    "template": template}
        if active >= int(settings["max_active_agents"]):
            return {"decision": "QUEUE_FOR_LATER",
                    "reasons": [f"active agent limit reached ({active}/{settings['max_active_agents']})"],
                    "template": template}
        if per_business is not None and per_business >= int(settings["max_agents_per_business"]):
            return {"decision": "QUEUE_FOR_LATER",
                    "reasons": [f"per-business agent limit reached for "
                                f"'{requirement['business_ref']}'"],
                    "template": template}
        if recent >= int(settings["creation_rate_limit_per_hour"]):
            return {"decision": "QUEUE_FOR_LATER",
                    "reasons": [f"creation rate limit reached ({recent} in the last hour)"],
                    "template": template}

        # Gate 8: resource pressure -> queue nonessential creation (§10.4).
        blocked = self.resources.creation_blocked(
            essential=bool(requirement.get("essential")))
        if blocked:
            return {"decision": "QUEUE_FOR_LATER",
                    "reasons": [f"nonessential creation stopped: {blocked}"],
                    "template": template}

        if approval_reasons:
            return {"decision": "REQUEST_OWNER_APPROVAL",
                    "reasons": approval_reasons, "template": template,
                    "effective_capabilities": effective_caps,
                    "effective_config": effective_config}

        reasons.append("no existing agent can serve the requirement; a published, "
                       "valid template matches; capabilities and resources are within "
                       "policy; creation is justified")
        return {"decision": "CREATE_AGENT", "reasons": reasons, "template": template,
                "effective_capabilities": effective_caps,
                "effective_config": effective_config}

    async def evaluate_creation(self, requirement: dict, *, principal: Principal) -> dict:
        """§19 evaluate: run the decision engine and RECORD the decision.
        Creates nothing (except, in Mode C, a proposed template draft
        stays uncreated too — the proposal is recorded on the request;
        approval materializes it)."""
        settings = self.settings_values()
        outcome = self._decide(requirement, principal, settings)
        session = self._session_factory()
        try:
            request = AgentCreationRequest(
                requester_type=principal.type.value, requester_id=principal.id,
                requested_role=requirement["role"],
                requested_template_id=(outcome.get("template").id
                                       if outcome.get("template") else None),
                business_ref=requirement.get("business_ref"),
                justification=requirement.get("justification"),
                requested_capabilities=list(requirement.get("capabilities") or []),
                resource_estimate=requirement.get("resource_estimate") or {},
                requirement=requirement, decision=outcome["decision"],
                decision_reasons=outcome["reasons"],
                approval_status="not_required",
                reused_agent_id=(outcome.get("reused_agent").id
                                 if outcome.get("reused_agent") else None),
                completed_at=utcnow())
            CreationRequestRepository(session).add(request)
            result = self._request_to_dict(request)
        finally:
            session.close()
        self._audit(principal, "agent_factory.creation_decision", "agent_creation_request",
                    result["id"], "allow",
                    details={"decision": outcome["decision"]})
        await self._publish(EventType.AGENT_CREATION_DECIDED,
                            {"request_id": result["id"], "decision": outcome["decision"],
                             "role": requirement["role"]})
        return result

    async def create_agent(self, requirement: dict, *, principal: Principal) -> dict:
        """§19 create: decision + materialization. CREATE_AGENT proceeds;
        REQUEST_OWNER_APPROVAL creates the hash-bound P-01 approval and
        holds; REUSE/ASSIGN/QUEUE/REJECT are recorded outcomes, returned
        as-is (they are successes of the decision engine, not errors)."""
        self._require_manage(principal, "agent_factory.create")
        settings = self.settings_values()
        idem = requirement.get("idempotency_key")
        if idem:
            session = self._session_factory()
            try:
                existing = CreationRequestRepository(session).get_by_idempotency_key(idem)
                if existing is not None:
                    return self._request_to_dict(existing)
            finally:
                session.close()

        outcome = self._decide(requirement, principal, settings)
        decision = outcome["decision"]
        # P-14 Stage B (DEF-D4): a supplied business_ref must reference an
        # existing business — canonical IDs only.
        if requirement.get("business_ref"):
            from ..database.models.business import Business
            check_session = self._session_factory()
            try:
                if check_session.get(Business,
                                     requirement["business_ref"]) is None:
                    from ..core.exceptions import ValidationError
                    raise ValidationError(
                        f"business_ref {requirement['business_ref']} does not "
                        "reference an existing business (P-14 DEF-D4)")
            finally:
                check_session.close()
        session = self._session_factory()
        try:
            request = AgentCreationRequest(
                requester_type=principal.type.value, requester_id=principal.id,
                requested_role=requirement["role"],
                requested_template_id=(outcome.get("template").id
                                       if outcome.get("template") else None),
                business_ref=requirement.get("business_ref"),
                justification=requirement.get("justification"),
                requested_capabilities=list(requirement.get("capabilities") or []),
                resource_estimate=requirement.get("resource_estimate") or {},
                requirement=requirement, decision=decision,
                decision_reasons=outcome["reasons"],
                approval_status="not_required",
                reused_agent_id=(outcome.get("reused_agent").id
                                 if outcome.get("reused_agent") else None),
                idempotency_key=idem,
                completed_at=None if decision in ("CREATE_AGENT", "REQUEST_OWNER_APPROVAL")
                else utcnow())
            CreationRequestRepository(session).add(request)
            request_id = request.id
        finally:
            session.close()

        if decision == "REQUEST_OWNER_APPROVAL":
            approval_params = self._creation_approval_params(request_id, requirement, outcome)
            approval = self._approvals.create(
                principal, action=CREATE_ACTION, resource=request_id,
                risk_classification="high",
                reason="; ".join(outcome["reasons"]),
                requested_permissions=list(outcome.get("effective_capabilities") or []),
                parameters=approval_params)
            session = self._session_factory()
            try:
                repo = CreationRequestRepository(session)
                row = repo.get(request_id)
                row.approval_status = "pending"
                row.approval_id = approval.id
                repo.save(row)
                result = self._request_to_dict(row)
            finally:
                session.close()
            self._audit(principal, "agent_factory.creation_approval_requested",
                        "agent_creation_request", request_id, "allow",
                        details={"approval_id": approval.id})
            await self._publish(EventType.AGENT_CREATION_DECIDED,
                                {"request_id": request_id, "decision": decision})
            return result

        if decision != "CREATE_AGENT":
            self._audit(principal, "agent_factory.creation_decision",
                        "agent_creation_request", request_id, "allow",
                        details={"decision": decision})
            await self._publish(EventType.AGENT_CREATION_DECIDED,
                                {"request_id": request_id, "decision": decision})
            session = self._session_factory()
            try:
                return self._request_to_dict(CreationRequestRepository(session).get(request_id))
            finally:
                session.close()

        agent = await self._materialize(request_id, requirement, outcome, principal)
        session = self._session_factory()
        try:
            return self._request_to_dict(CreationRequestRepository(session).get(request_id))
        finally:
            session.close()

    @staticmethod
    def _creation_approval_params(request_id: str, requirement: dict, outcome: dict) -> dict:
        template = outcome.get("template")
        return {
            "request_id": request_id,
            "role": requirement["role"],
            "template_id": template.id if template else None,
            "template_version": (template.published_version if template else None),
            "capabilities": sorted(outcome.get("effective_capabilities")
                                   or requirement.get("capabilities") or []),
            "business_ref": requirement.get("business_ref"),
            "propose_template": bool(outcome.get("propose_template")),
        }

    async def _materialize(self, request_id: str, requirement: dict, outcome: dict,
                           principal: Principal,
                           approved_capabilities: set[str] | None = None) -> Agent:
        """Register the agent, run initialization checks, grant the
        policy-approved capabilities, snapshot configuration v1. On any
        initialization failure the agent lands in FAILED with the reasons
        recorded — never silently active, never endlessly replaced."""
        template = outcome.get("template")
        config = copy.deepcopy(outcome.get("effective_config") or {})
        settings = self.settings_values()
        display = C.ROLE_DISPLAY_NAMES.get(requirement["role"], requirement["role"])
        session = self._session_factory()
        try:
            agent = Agent(
                name=requirement.get("name") or f"{display} ({request_id[:8]})",
                role=requirement["role"],
                agent_type=config.get("agent_type") or C.ROLE_TO_CATEGORY.get(requirement["role"]),
                description=config.get("mission"),
                parent_agent_id=requirement.get("parent_agent_id"),
                business_ref=requirement.get("business_ref"),
                objective=requirement.get("justification") or config.get("primary_responsibility"),
                model_profile=(config.get("model_requirements") or {}).get("profile_name"),
                status="proposed",
                budget=config.get("resource_budget"),
                template_id=template.id if template else None,
                template_version=template.published_version if template else None,
                configuration_version=1,
                created_by_type=principal.type.value, created_by_id=principal.id,
                security_classification=config.get("security_classification", "internal"),
                last_activity_at=utcnow())
            AgentRepository(session).add(agent)
            agent_id = agent.id
        finally:
            session.close()

        await self.transition_agent(agent_id, "initializing", actor=principal,
                                    reason="creation pipeline: initialization")
        failures = self._initialization_checks(agent_id, config, settings)
        if failures:
            await self.transition_agent(agent_id, "failed", actor=principal,
                                        reason="initialization failed")
            session = self._session_factory()
            try:
                repo = CreationRequestRepository(session)
                row = repo.get(request_id)
                row.created_agent_id = agent_id
                row.completed_at = utcnow()
                row.decision_reasons = list(row.decision_reasons or []) + \
                    [f"initialization failed: {f}" for f in failures]
                repo.save(row)
            finally:
                session.close()
            self._audit(principal, "agent_factory.initialization_failed", "agent",
                        agent_id, "deny", reason="; ".join(failures))
            raise InitializationFailedError(
                f"agent {agent_id} failed initialization: {'; '.join(failures)}",
                details={"error_category": "INITIALIZATION_FAILED",
                         "agent_id": agent_id, "failures": failures})

        # Grants: Level-0 always; Level-1 when the capability is part of
        # the (owner-published) template — the §8.3 conditional policy;
        # anything the owner explicitly approved for THIS creation
        # (hash-bound approval) is granted with the approval as reference.
        template_caps = set(config.get("allowed_capabilities") or [])
        approved = approved_capabilities or set()
        approval_row_id = None
        session = self._session_factory()
        try:
            req_row = CreationRequestRepository(session).get(request_id)
            approval_row_id = req_row.approval_id if req_row else None
        finally:
            session.close()
        granted, skipped = [], []
        for name in outcome.get("effective_capabilities") or []:
            level = self._catalogue_levels().get(name, 0)
            if level == 0 or (level == 1 and name in template_caps) \
                    or name in approved:
                self.capabilities.grant(
                    agent_id, name, granted_by=principal,
                    approval_reference=approval_row_id if name in approved else None)
                granted.append(name)
            else:
                skipped.append(name)
        session = self._session_factory()
        try:
            ConfigHistoryRepository(session).add(AgentConfigurationHistory(
                agent_id=agent_id, configuration_version=1,
                configuration_snapshot=self._config_snapshot(
                    self.get_agent(agent_id), config),
                change_reason="initial configuration from template "
                              f"{template.name if template else '?'} "
                              f"v{template.published_version if template else '?'}",
                changed_by_type=principal.type.value, changed_by_id=principal.id,
                created_at=utcnow()))
            HealthRepository(session).add(AgentHealth(
                agent_id=agent_id, health_status="HEALTHY", last_check=utcnow(),
                details={"basis": "initialization checks passed",
                         "granted_capabilities": granted,
                         "skipped_capabilities": skipped}))
            repo = CreationRequestRepository(session)
            row = repo.get(request_id)
            row.created_agent_id = agent_id
            row.completed_at = utcnow()
            repo.save(row)
        finally:
            session.close()
        agent = await self.transition_agent(agent_id, "active", actor=principal,
                                            reason="initialization passed")
        self._audit(principal, "agent_factory.create", "agent", agent_id, "allow",
                    details={"template_id": agent.template_id,
                             "template_version": agent.template_version,
                             "granted_capabilities": granted,
                             "skipped_capabilities": skipped})
        await self._publish(EventType.AGENT_CREATED,
                            {"agent_id": agent_id, "role": agent.role,
                             "template_id": agent.template_id})
        return agent

    def _initialization_checks(self, agent_id: str, config: dict,
                               settings: dict) -> list[str]:
        failures: list[str] = []
        handlers = (config.get("tool_requirements") or {}).get("handlers") or []
        for handler in handlers:
            if not self._tasks.registry.has(handler):
                failures.append(f"required handler '{handler}' is not registered")
        profile_name = (config.get("model_requirements") or {}).get("profile_name")
        if profile_name:
            session = self._session_factory()
            try:
                from ..database.repositories.intelligence import ModelProfileRepository
                names = {p.name for p in ModelProfileRepository(session).list()}
            finally:
                session.close()
            if profile_name not in names:
                failures.append(f"model profile '{profile_name}' does not exist")
        levels = self._catalogue_levels()
        errors = validate_template_configuration(
            config, capability_levels=levels,
            model_profile_names=set(),  # profile existence checked above
            ceilings={"max_concurrent_tasks_per_agent": settings["max_concurrent_tasks_per_agent"],
                      "max_template_task_seconds": settings["max_template_task_seconds"],
                      "max_template_memory_budget_mb": settings["max_template_memory_budget_mb"]})
        # The merged runtime config re-validates EXCEPT the profile rule
        # (checked separately against live profiles, not the empty set).
        failures.extend(e for e in errors if "model_requirements.profile_name" not in e)
        return failures

    @staticmethod
    def _config_snapshot(agent: Agent, template_config: dict | None) -> dict:
        return {
            "name": agent.name, "role": agent.role, "agent_type": agent.agent_type,
            "description": agent.description, "objective": agent.objective,
            "business_ref": agent.business_ref,
            "parent_agent_id": agent.parent_agent_id,
            "template_id": agent.template_id, "template_version": agent.template_version,
            "model_profile": agent.model_profile, "budget": agent.budget,
            "security_classification": agent.security_classification,
            "template_capabilities": (template_config or {}).get("allowed_capabilities", []),
            "system_instruction": (template_config or {}).get("system_instruction"),
        }

    async def approve_creation(self, request_id: str, *, approver: Principal,
                               approve: bool, notes: str | None = None) -> dict:
        self._require_owner(approver, "agent_factory.approve_creation")
        session = self._session_factory()
        try:
            request = CreationRequestRepository(session).get(request_id)
            if request is None:
                raise NotFoundError(f"creation request {request_id} not found")
            if request.decision != "REQUEST_OWNER_APPROVAL" \
                    or request.approval_status != "pending":
                from ..core.exceptions import ApprovalError
                raise ApprovalError(
                    f"creation request is not awaiting approval (decision="
                    f"{request.decision}, approval_status={request.approval_status})")
            approval_id = request.approval_id
            requirement = request.requirement or {}
        finally:
            session.close()
        decided = self._approvals.decide(approval_id, approver, approve, notes)
        session = self._session_factory()
        try:
            repo = CreationRequestRepository(session)
            row = repo.get(request_id)
            row.approval_status = "approved" if approve else "rejected"
            if not approve:
                row.completed_at = utcnow()
                repo.save(row)
                result = self._request_to_dict(row)
            else:
                result = None
            template = None
            if row.requested_template_id:
                template = TemplateRepository(session).get(row.requested_template_id)
        finally:
            session.close()
        if not approve:
            self._audit(approver, "agent_factory.creation_approval", "agent_creation_request",
                        request_id, "deny", reason=notes)
            return result
        # Hash binding (P-01 ApprovalService): rebuild the parameters from
        # CURRENT facts and require an exact hash match with what the
        # owner approved. Any drift — a re-published template version, a
        # changed capability set — fails the binding and nothing is built.
        from ..core.exceptions import ApprovalError
        stored = decided.parameters or {}
        outcome: dict = {"template": template, "effective_capabilities": None,
                         "effective_config": None}
        config: dict = {}
        if stored.get("propose_template"):
            params = self._creation_approval_params(
                request_id, requirement,
                {"template": None, "propose_template": True,
                 "effective_capabilities": sorted(requirement.get("capabilities") or [])})
            if not ApprovalService.verify_binding(decided, CREATE_ACTION, request_id, params):
                raise ApprovalError(
                    "approval parameters no longer match this creation request "
                    "(hash binding failed); a new approval is required")
            template = await self._materialize_proposed_template(
                request_id, requirement, approver)
            outcome["template"] = template
            session = self._session_factory()
            try:
                version_row = TemplateRepository(session).version(
                    template.id, template.published_version)
                config = version_row.configuration if version_row else {}
            finally:
                session.close()
        else:
            if template is not None:
                session = self._session_factory()
                try:
                    version_row = TemplateRepository(session).version(
                        template.id, template.published_version)
                    config = version_row.configuration if version_row else {}
                finally:
                    session.close()
            caps = sorted(set(config.get("allowed_capabilities") or [])
                          | set(requirement.get("capabilities") or []))
            outcome["effective_capabilities"] = caps
            params = self._creation_approval_params(request_id, requirement, outcome)
            if not ApprovalService.verify_binding(decided, CREATE_ACTION, request_id, params):
                raise ApprovalError(
                    "approval parameters no longer match this creation request "
                    "(hash binding failed — template version or capability set "
                    "drifted); a new approval is required")
        outcome["effective_config"] = copy.deepcopy(config)
        agent = await self._materialize(
            request_id, requirement, outcome, approver,
            approved_capabilities=set(outcome.get("effective_capabilities") or []))
        self._audit(approver, "agent_factory.creation_approval", "agent_creation_request",
                    request_id, "allow", reason=notes,
                    details={"created_agent_id": agent.id})
        session = self._session_factory()
        try:
            return self._request_to_dict(CreationRequestRepository(session).get(request_id))
        finally:
            session.close()

    async def _materialize_proposed_template(self, request_id: str, requirement: dict,
                                             approver: Principal) -> AgentTemplate:
        """Mode C: the owner approved a brand-new template for a taxonomy
        role. Build a conservative internal-only configuration, validate,
        publish and return it."""
        from ..database.models.agents import AgentTemplate
        role = requirement["role"]
        config = {
            "role": role, "agent_type": C.ROLE_TO_CATEGORY[role],
            "mission": requirement.get("justification")
                       or f"Serve as the {C.ROLE_DISPLAY_NAMES[role]} for assigned work.",
            "system_instruction": "You are a specialised agent created from an owner-approved "
                                  "template proposal. Work only within granted capabilities.",
            "primary_responsibility": f"Act as {C.ROLE_DISPLAY_NAMES[role]} on assigned tasks.",
            "secondary_responsibilities": [],
            "input_schema": {"required_fields": ["objective"]},
            "output_schema": {"required_fields": ["summary"]},
            "allowed_capabilities": ["internal_reasoning", "internal_database_read",
                                     "memory_read"],
            "restricted_capabilities": [],
            "tool_requirements": {"handlers": ["core.echo_check", "core.noop"]},
            "model_requirements": {"task_class": "general", "profile_name": None},
            "memory_requirements": {"scopes": ["agent_configuration_history",
                                               "previous_task_references"]},
            "resource_budget": dict(C.DEFAULT_RESOURCE_BUDGET),
            "timeout_seconds": 120, "retry_policy": {"max_retries": 1},
            "quality_criteria": {"output_schema_valid": True},
            "evaluation_rules": {},
            "approval_requirements": {"creation": "owner_approved_proposal"},
            "security_classification": "internal",
        }
        settings = self.settings_values()
        template = self.templates.create(
            approver, name=f"{C.ROLE_DISPLAY_NAMES[role]} (proposed {request_id[:8]})",
            category=C.ROLE_TO_CATEGORY[role],
            description="Template created from an owner-approved Mode C proposal.",
            configuration=config, settings=settings)
        version = self.templates.get_version(template.id, 1)
        if version.validation_status != "valid":
            raise TemplateInvalidError(
                "proposed template failed validation and cannot be used",
                details={"error_category": "TEMPLATE_INVALID",
                         "validation_errors": version.validation_errors})
        self.templates.publish(approver, template.id, version=1)
        session = self._session_factory()
        try:
            repo = CreationRequestRepository(session)
            row = repo.get(request_id)
            row.proposed_template_id = template.id
            row.requested_template_id = template.id
            repo.save(row)
        finally:
            session.close()
        return self.templates.get(template.id)

    async def reject_creation(self, request_id: str, *, approver: Principal,
                              notes: str | None = None) -> dict:
        return await self.approve_creation(request_id, approver=approver,
                                           approve=False, notes=notes)

    def get_creation_request(self, request_id: str) -> dict:
        session = self._session_factory()
        try:
            row = CreationRequestRepository(session).get(request_id)
            if row is None:
                raise NotFoundError(f"creation request {request_id} not found")
            return self._request_to_dict(row)
        finally:
            session.close()

    def list_creation_requests(self, decision: str | None = None,
                               limit: int = 50, offset: int = 0):
        session = self._session_factory()
        try:
            rows, total = CreationRequestRepository(session).list(decision, limit, offset)
            return [self._request_to_dict(r) for r in rows], total
        finally:
            session.close()

    @staticmethod
    def _request_to_dict(row: AgentCreationRequest) -> dict:
        return {
            "id": row.id, "requester": {"type": row.requester_type, "id": row.requester_id},
            "requested_role": row.requested_role,
            "requested_template_id": row.requested_template_id,
            "business_ref": row.business_ref, "justification": row.justification,
            "requested_capabilities": row.requested_capabilities,
            "resource_estimate": row.resource_estimate,
            "decision": row.decision, "decision_reasons": row.decision_reasons,
            "approval_status": row.approval_status, "approval_id": row.approval_id,
            "created_agent_id": row.created_agent_id,
            "reused_agent_id": row.reused_agent_id,
            "proposed_template_id": row.proposed_template_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }

    # ---------------------------------------------------- capability requests
    async def request_capability(self, agent_id: str, capability_name: str, *,
                                 principal: Principal, reason: str | None = None,
                                 scope: str | None = None) -> dict:
        """§8 flow. An agent (or an operator on its behalf) may REQUEST;
        only policy (L0/L1 conditions) or the owner (L2, hash-bound
        approval) can grant. The agent NEVER holds the capability while
        approval is outstanding."""
        agent = self.get_agent(agent_id)
        if agent.status == "retired":
            raise AgentNotFoundError(
                f"agent {agent_id} is retired and cannot request capabilities",
                details={"error_category": "AGENT_NOT_FOUND"})
        cap = self.capabilities.get_capability(capability_name)
        if cap.approval_level >= 3 or not cap.enabled:
            self.capabilities.record_denial(agent_id, capability_name,
                                            reason="prohibited capability")
            self._audit(principal, "agent_factory.capability_request", "agent",
                        agent_id, "deny",
                        reason=f"capability '{capability_name}' is PROHIBITED (level 3)",
                        details={"capability": capability_name})
            from .errors import CapabilityProhibitedError
            raise CapabilityProhibitedError(
                f"capability '{capability_name}' is PROHIBITED (approval level 3): "
                "it cannot be requested, granted, or approved through the agent path",
                details={"error_category": "CAPABILITY_PROHIBITED"})
        if self.capabilities.has_capability(agent_id, capability_name):
            return {"status": "already_granted", "capability": capability_name,
                    "agent_id": agent_id}
        template_caps: set[str] = set()
        pinned = self._pinned_config(agent)
        if pinned:
            template_caps = set(pinned.get("allowed_capabilities") or [])
        if cap.approval_level == 0:
            grant = self.capabilities.grant(agent_id, capability_name,
                                            granted_by=principal, scope=scope)
            self._audit(principal, "agent_factory.capability_grant", "agent", agent_id,
                        "allow", details={"capability": capability_name, "level": 0})
            await self._publish(EventType.AGENT_PERMISSION_CHANGED,
                                {"agent_id": agent_id, "capability": capability_name,
                                 "change": "granted", "level": 0})
            return {"status": "granted", "capability": capability_name,
                    "agent_id": agent_id, "grant_id": grant.id}
        if cap.approval_level == 1 and capability_name in template_caps and cap.supported:
            grant = self.capabilities.grant(agent_id, capability_name,
                                            granted_by=principal, scope=scope)
            self._audit(principal, "agent_factory.capability_grant", "agent", agent_id,
                        "allow",
                        details={"capability": capability_name, "level": 1,
                                 "basis": "capability is part of the agent's published template"})
            await self._publish(EventType.AGENT_PERMISSION_CHANGED,
                                {"agent_id": agent_id, "capability": capability_name,
                                 "change": "granted", "level": 1})
            return {"status": "granted", "capability": capability_name,
                    "agent_id": agent_id, "grant_id": grant.id}
        # Level 2 (or Level 1 outside policy conditions): owner approval.
        approval = self.capabilities.create_grant_approval(
            requester=agent_principal(agent_id), agent_id=agent_id,
            capability_name=capability_name, scope=scope,
            reason=reason or f"capability '{capability_name}' requested for agent {agent_id}")
        self._audit(principal, "agent_factory.capability_request", "agent", agent_id,
                    "allow",
                    details={"capability": capability_name,
                             "approval_id": approval.id,
                             "supported": cap.supported,
                             "outcome": "approval_required"})
        return {"status": "approval_required", "capability": capability_name,
                "agent_id": agent_id, "approval_id": approval.id,
                "supported": cap.supported,
                "note": ("the agent does NOT hold this capability while approval "
                         "is outstanding"
                         + ("" if cap.supported else
                            "; the capability is not backed by any module in this "
                            "build and cannot be granted even if approved"))}

    async def approve_capability(self, agent_id: str, approval_id: str, *,
                                 approver: Principal, approve: bool) -> dict:
        self._require_owner(approver, "agent_factory.approve_capability")
        try:
            result = self.capabilities.apply_grant_approval(
                approver=approver, agent_id=agent_id, approval_id=approval_id,
                approve=approve)
        except Exception as exc:
            self._audit(approver, "agent_factory.capability_approval", "agent",
                        agent_id, "deny", reason=str(exc))
            raise
        self._audit(approver, "agent_factory.capability_approval", "agent", agent_id,
                    "allow" if result["status"] == "granted" else "deny",
                    details=result)
        if result["status"] == "granted":
            await self._publish(EventType.AGENT_PERMISSION_CHANGED,
                                {"agent_id": agent_id,
                                 "capability": result["capability"],
                                 "change": "granted", "via": "owner_approval"})
        return result

    async def revoke_capability(self, agent_id: str, capability_name: str, *,
                                principal: Principal) -> dict:
        self._require_manage(principal, "agent_factory.revoke_capability")
        grant = self.capabilities.revoke(agent_id, capability_name, revoked_by=principal)
        self._audit(principal, "agent_factory.capability_revoke", "agent", agent_id,
                    "allow", details={"capability": capability_name})
        await self._publish(EventType.AGENT_PERMISSION_CHANGED,
                            {"agent_id": agent_id, "capability": capability_name,
                             "change": "revoked"})
        return {"status": "revoked", "capability": capability_name,
                "agent_id": agent_id, "grant_id": grant.id}

    # ------------------------------------------------------ config versioning
    def _snapshot_for(self, agent: Agent) -> dict:
        return self._config_snapshot(agent, self._pinned_config(agent))

    async def update_agent_config(self, agent_id: str, changes: dict, *,
                                  principal: Principal, reason: str | None = None) -> dict:
        """§13 controlled update. A BUSY agent (running assignment) is
        never silently modified: the update is refused with
        CONFIGURATION_VERSION_CONFLICT so the caller can retry at a safe
        lifecycle point."""
        self._require_manage(principal, "agent_factory.config_update")
        agent = self.get_agent(agent_id)
        if agent.status == "retired":
            raise AgentNotFoundError("a retired agent's configuration is immutable history",
                                     details={"error_category": "AGENT_NOT_FOUND"})
        session = self._session_factory()
        try:
            active = AssignmentRepository(session).active_for_agent(agent_id)
            running = [a for a in active if a.status == "running"]
        finally:
            session.close()
        if running:
            raise ConfigurationVersionConflictError(
                "agent has a running assignment; configuration changes are deferred "
                "until a safe lifecycle state",
                details={"error_category": "CONFIGURATION_VERSION_CONFLICT",
                         "running_assignments": [a.id for a in running]})
        allowed_fields = {"name", "description", "objective", "business_ref",
                          "model_profile", "budget", "security_classification",
                          "template_version"}
        unknown = set(changes) - allowed_fields
        if unknown:
            from ..core.exceptions import ValidationError
            raise ValidationError(
                f"configuration fields are not directly editable: {sorted(unknown)} "
                "(capabilities change only through the grant flow; role/template "
                "changes require a new agent or template pin update)")
        if "template_version" in changes:
            if not agent.template_id:
                raise TemplateInvalidError("agent has no template to re-pin",
                                           details={"error_category": "TEMPLATE_INVALID"})
            target = self.templates.get_version(agent.template_id,
                                                int(changes["template_version"]))
            template = self.templates.get(agent.template_id)
            if template.published_version != int(changes["template_version"]) \
                    or target.validation_status != "valid":
                raise TemplateInvalidError(
                    "agents may only be pinned to the template's published, valid version",
                    details={"error_category": "TEMPLATE_INVALID"})
        # P-14 Stage B (DEF-D4): a new business_ref must reference an
        # existing business — canonical IDs only.
        if changes.get("business_ref"):
            from ..database.models.business import Business
            check_session = self._session_factory()
            try:
                if check_session.get(Business, changes["business_ref"]) is None:
                    from ..core.exceptions import ValidationError
                    raise ValidationError(
                        f"business_ref {changes['business_ref']} does not "
                        "reference an existing business (P-14 DEF-D4)")
            finally:
                check_session.close()
        session = self._session_factory()
        try:
            repo = AgentRepository(session)
            row = repo.get(agent_id)
            for field_name, value in changes.items():
                setattr(row, field_name, value)
            row.configuration_version = int(row.configuration_version or 1) + 1
            row.last_activity_at = utcnow()
            session.add(row)
            session.commit()
            session.refresh(row)
            snapshot = self._snapshot_for(row)
            ConfigHistoryRepository(session).add(AgentConfigurationHistory(
                agent_id=agent_id, configuration_version=row.configuration_version,
                configuration_snapshot=snapshot, change_reason=reason,
                changed_by_type=principal.type.value, changed_by_id=principal.id,
                created_at=utcnow()))
            result = self.agent_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "agent_factory.config_update", "agent", agent_id,
                    "allow", reason=reason,
                    details={"fields": sorted(changes),
                             "configuration_version": result["configuration_version"]})
        return result

    async def rollback_agent_config(self, agent_id: str, *, version: int,
                                    principal: Principal) -> dict:
        """Restore an earlier snapshot AS A NEW version (append-only)."""
        self._require_manage(principal, "agent_factory.config_rollback")
        agent = self.get_agent(agent_id)
        if agent.status == "retired":
            raise AgentNotFoundError("a retired agent's configuration is immutable history",
                                     details={"error_category": "AGENT_NOT_FOUND"})
        session = self._session_factory()
        try:
            history = ConfigHistoryRepository(session)
            target = history.get_version(agent_id, version)
            if target is None:
                raise NotFoundError(
                    f"agent {agent_id} has no configuration version {version}")
            snapshot = target.configuration_snapshot or {}
            repo = AgentRepository(session)
            row = repo.get(agent_id)
            for field_name in ("name", "description", "objective", "business_ref",
                               "model_profile", "budget", "security_classification",
                               "template_id", "template_version"):
                if field_name in snapshot:
                    setattr(row, field_name, snapshot[field_name])
            row.configuration_version = int(row.configuration_version or 1) + 1
            row.last_activity_at = utcnow()
            session.add(row)
            session.commit()
            session.refresh(row)
            history.add(AgentConfigurationHistory(
                agent_id=agent_id, configuration_version=row.configuration_version,
                configuration_snapshot=self._snapshot_for(row),
                change_reason=f"rollback to configuration version {version}",
                changed_by_type=principal.type.value, changed_by_id=principal.id,
                created_at=utcnow()))
            result = self.agent_to_dict(row)
        finally:
            session.close()
        self._audit(principal, "agent_factory.config_rollback", "agent", agent_id,
                    "allow", details={"restored_version": version,
                                      "new_version": result["configuration_version"]})
        return result

    def config_history(self, agent_id: str) -> list[dict]:
        self.get_agent(agent_id)
        session = self._session_factory()
        try:
            return [{"configuration_version": r.configuration_version,
                     "configuration_snapshot": r.configuration_snapshot,
                     "change_reason": r.change_reason,
                     "changed_by": r.changed_by_id,
                     "approval_reference": r.approval_reference,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in ConfigHistoryRepository(session).for_agent(agent_id)]
        finally:
            session.close()

    # ------------------------------------------------------------- assignment
    async def assign(self, agent_id: str, payload: dict, *,
                     principal: Principal) -> dict:
        """§9 assignment: validate all nine §9.2 rules, then submit a REAL
        P-01 task. Rejections are persisted (status=rejected) with the
        structured rule-by-rule reason and audited."""
        settings = self.settings_values()
        agent = self.get_agent(agent_id)
        idem = payload.get("idempotency_key")
        if idem:
            session = self._session_factory()
            try:
                existing = AssignmentRepository(session).get_by_idempotency_key(idem)
                if existing is not None:
                    return self._assignment_to_dict(existing)
            finally:
                session.close()

        failures: list[dict] = []

        def fail(rule: str, reason: str) -> None:
            failures.append({"rule": rule, "reason": reason})

        # Rule 9 (governance) first: factory/mode gates.
        if self._settings.mode == "emergency" or settings["safe_mode"] \
                or not settings["assignments_enabled"]:
            fail("governance_policy",
                 "assignments are stopped (emergency mode, safe mode or assignments disabled)")
        # Rule 1 + 4: agent active and not suspended/retired.
        if agent.status not in ASSIGNABLE_STATES:
            fail("agent_active",
                 f"agent status is '{agent.status}'; only active/idle/busy agents "
                 "may receive assignments (suspended, failed and retired agents may not)")
        # Rule 2: template valid (factory agents pin a validated version).
        template_config = self._pinned_config(agent)
        if agent.template_id is not None:
            if template_config is None:
                fail("template_valid", "pinned template version no longer exists")
            else:
                version_row = self.templates.get_version(agent.template_id,
                                                         agent.template_version)
                if version_row.validation_status != "valid":
                    fail("template_valid",
                         "pinned template version is not in 'valid' validation state")
        budget = self.resources.effective_budget(agent, template_config, settings)
        # Rule 3: required capabilities authorized (engine-checked).
        required_caps = list(payload.get("required_capabilities") or [])
        for name in required_caps:
            if not self.capabilities.has_capability(agent_id, name):
                fail("capabilities_authorized",
                     f"agent does not hold an authorized grant for capability '{name}'")
        # Rule 5: resource budget (concurrency + pressure ladder).
        session = self._session_factory()
        try:
            active = AssignmentRepository(session).active_for_agent(agent_id)
        finally:
            session.close()
        if len(active) >= int(budget["max_concurrent_tasks"]):
            fail("resource_budget",
                 f"agent already has {len(active)} active assignment(s); budget allows "
                 f"{budget['max_concurrent_tasks']}")
        if len(active) >= int(budget["max_queue_occupancy"]):
            fail("resource_budget", "agent queue occupancy budget reached")
        pressure = self.resources.pressure()
        if pressure["level"] >= 2 and pressure.get("blocking_enabled", True) \
                and int(payload.get("priority", 5)) < 5:
            fail("resource_budget",
                 "resource pressure level 2: low-priority assignments are queued "
                 "under the backpressure ladder (§10.4); resubmit when pressure clears")
        # Rule 6: responsibility — handler must be within the template's tools.
        handler_name = payload.get("handler_name") or ""
        if template_config is not None:
            allowed_handlers = (template_config.get("tool_requirements") or {}).get("handlers") or []
            if handler_name not in allowed_handlers:
                fail("responsibility",
                     f"handler '{handler_name}' is outside the agent's template "
                     f"responsibilities {allowed_handlers}")
        elif agent.template_id is not None:
            fail("responsibility", "agent template configuration is unavailable")
        # Rule 7: dependencies + delegation limits + circular delegation.
        depth = 0
        parent_assignment = None
        if payload.get("parent_assignment_id"):
            session = self._session_factory()
            try:
                parent_assignment = AssignmentRepository(session).get(
                    payload["parent_assignment_id"])
            finally:
                session.close()
            if parent_assignment is None:
                fail("dependencies", "parent assignment not found")
            else:
                depth = int(parent_assignment.delegation_depth) + 1
                if depth > int(settings["max_delegation_depth"]):
                    fail("delegation_depth",
                         f"delegation depth {depth} exceeds the limit "
                         f"{settings['max_delegation_depth']}")
                chain_agents: list[str] = []
                cursor = parent_assignment
                session = self._session_factory()
                try:
                    repo = AssignmentRepository(session)
                    while cursor is not None:
                        chain_agents.append(cursor.agent_id)
                        cursor = repo.get(cursor.parent_assignment_id) \
                            if cursor.parent_assignment_id else None
                finally:
                    session.close()
                if agent_id in chain_agents:
                    fail("delegation_circular",
                         "circular delegation: the agent already appears in this "
                         "delegation chain")
                session = self._session_factory()
                try:
                    siblings = AssignmentRepository(session).children_of(parent_assignment.id)
                finally:
                    session.close()
                if len(siblings) >= int(budget["max_child_agents"]):
                    fail("delegation_children",
                         "maximum child assignments for this parent reached")
        if payload.get("depends_on_assignment_id"):
            dep = None
            session = self._session_factory()
            try:
                dep = AssignmentRepository(session).get(payload["depends_on_assignment_id"])
            finally:
                session.close()
            if dep is None:
                fail("dependencies", "dependency assignment not found")
            else:
                dep = self.refresh_assignment(dep.id)
                if dep["status"] != "completed":
                    fail("dependencies",
                         f"dependency assignment is in state '{dep['status']}', not completed")
        # Rule 8: conflicting assignment (same objective already active).
        for other in active:
            if other.objective == payload.get("objective"):
                fail("conflicting_assignment",
                     "an identical objective is already active for this agent")

        if failures:
            session = self._session_factory()
            try:
                row = AgentAssignment(
                    agent_id=agent_id, task_id=None,
                    business_ref=payload.get("business_ref"),
                    objective=payload.get("objective") or "",
                    input_refs=payload.get("input_refs") or [],
                    required_capabilities=required_caps,
                    priority=int(payload.get("priority", 5)),
                    timeout_seconds=float(payload.get("timeout_seconds", 30.0)),
                    expected_output=payload.get("expected_output") or {},
                    quality_requirements=payload.get("quality_requirements") or {},
                    retry_limit=int(payload.get("retry_limit", 0)),
                    parent_assignment_id=payload.get("parent_assignment_id"),
                    delegation_depth=depth,
                    assigned_by_type=principal.type.value,
                    assigned_by_id=principal.id,
                    status="rejected",
                    rejection_reason="; ".join(f"{f['rule']}: {f['reason']}" for f in failures),
                    idempotency_key=idem)
                AssignmentRepository(session).add(row)
                result = self._assignment_to_dict(row)
            finally:
                session.close()
            self._audit(principal, "agent_factory.assignment", "agent", agent_id,
                        "deny", reason=result["rejection_reason"],
                        details={"failures": failures})
            raise AssignmentRejectedError(
                f"assignment rejected for agent {agent_id}",
                details={"error_category": "ASSIGNMENT_REJECTED",
                         "failures": failures, "assignment_id": result["id"]})

        timeout = min(float(payload.get("timeout_seconds") or budget["max_task_seconds"]),
                      float(budget["max_task_seconds"]))
        task = await self._tasks.submit(
            principal,
            name=(payload.get("name") or payload.get("objective") or "agent assignment")[:300],
            handler_name=handler_name,
            payload=payload.get("task_payload") or {},
            description=payload.get("objective"),
            category=payload.get("category", "agent_assignment"),
            priority=int(payload.get("priority", 5)),
            max_retries=min(int(payload.get("retry_limit", 0)), int(budget["max_retries"])),
            timeout_seconds=timeout,
            assigned_agent_id=agent_id,
            idempotency_key=f"assignment-task:{idem}" if idem else None)
        session = self._session_factory()
        try:
            row = AgentAssignment(
                agent_id=agent_id, task_id=task.id,
                business_ref=payload.get("business_ref"),
                objective=payload.get("objective") or "",
                input_refs=payload.get("input_refs") or [],
                required_capabilities=required_caps,
                priority=int(payload.get("priority", 5)),
                deadline=None, timeout_seconds=timeout,
                expected_output=payload.get("expected_output") or {},
                quality_requirements=payload.get("quality_requirements") or {},
                retry_limit=int(payload.get("retry_limit", 0)),
                parent_assignment_id=payload.get("parent_assignment_id"),
                delegation_depth=depth,
                assigned_by_type=principal.type.value,
                assigned_by_id=principal.id,
                status="assigned", idempotency_key=idem,
                started_at=utcnow())
            AssignmentRepository(session).add(row)
            result = self._assignment_to_dict(row)
            agent_row = AgentRepository(session).get(agent_id)
            agent_row.last_activity_at = utcnow()
            session.add(agent_row)
            session.commit()
        finally:
            session.close()
        self._record_metric(agent_id, "tasks_assigned", 1, "measured")
        if agent.status in ("active", "idle"):
            await self.transition_agent(agent_id, "busy", actor=principal,
                                        reason="assignment received")
        self._audit(principal, "agent_factory.assignment", "agent", agent_id, "allow",
                    details={"assignment_id": result["id"], "task_id": task.id,
                             "delegation_depth": depth})
        await self._publish(EventType.AGENT_ASSIGNED,
                            {"agent_id": agent_id, "assignment_id": result["id"],
                             "task_id": task.id})
        return result

    def refresh_assignment(self, assignment_id: str) -> dict:
        """Sync an assignment's verdict from its P-01 task. A completed
        task whose result fails the §9.4 output contract becomes
        'output_invalid' — never a success."""
        session = self._session_factory()
        try:
            repo = AssignmentRepository(session)
            row = repo.get(assignment_id)
            if row is None:
                raise NotFoundError(f"assignment {assignment_id} not found")
            if row.status in ("completed", "failed", "cancelled", "output_invalid",
                              "rejected") or row.task_id is None:
                return self._assignment_to_dict(row)
            assignment = row
            agent_id, task_id = row.agent_id, row.task_id
        finally:
            session.close()
        task = self._tasks.get(task_id)
        session = self._session_factory()
        try:
            repo = AssignmentRepository(session)
            row = repo.get(assignment_id)
            changed = False
            if task.status == "running" and row.status == "assigned":
                row.status = "running"
                changed = True
            elif task.status == "completed":
                verdict = validate_output_contract(task.result, row.expected_output)
                row.output_validation = verdict
                row.completed_at = utcnow()
                if verdict["valid"]:
                    row.status = "completed"
                    row.result_summary = str((task.result or {}).get("summary")
                                             or (task.result or {}).get("ok")
                                             or "task completed")[:500]
                else:
                    row.status = "output_invalid"
                    row.failure_reason = (
                        "output contract violated: missing required fields "
                        f"{verdict['missing_fields']}")
                changed = True
            elif task.status == "failed":
                row.status = "failed"
                row.completed_at = utcnow()
                row.failure_reason = str((task.error or {}).get("message") or "task failed")
                changed = True
            elif task.status == "cancelled":
                row.status = "cancelled"
                row.completed_at = utcnow()
                changed = True
            if changed:
                repo.save(row)
            result = self._assignment_to_dict(row)
            terminal = row.status in ("completed", "failed", "cancelled", "output_invalid")
            new_status = row.status
        finally:
            session.close()
        if terminal:
            kind = (task.error or {}).get("kind")
            if new_status == "completed":
                self._record_metric(agent_id, "tasks_completed", 1, "measured")
                durations = [e.duration_ms for e in task.executions
                             if e.duration_ms is not None]
                if durations:
                    self._record_metric(agent_id, "execution_duration_ms",
                                        durations[-1], "measured")
                self._record_metric(agent_id, "output_schema_valid", 1, "measured")
            elif new_status == "output_invalid":
                self._record_metric(agent_id, "tasks_failed", 1, "measured")
                self._record_metric(agent_id, "output_schema_valid", 0, "measured")
            else:
                self._record_metric(agent_id, "tasks_failed", 1, "measured")
                if kind == "timeout":
                    self._record_metric(agent_id, "tasks_timed_out", 1, "measured")
            # Agent returns to ACTIVE when no assignments remain in flight.
            agent = self.get_agent(agent_id)
            if agent.status == "busy":
                session = self._session_factory()
                try:
                    remaining = AssignmentRepository(session).active_for_agent(agent_id)
                finally:
                    session.close()
                if not remaining:
                    self._transition_sync(
                        agent_id, "active",
                        actor=Principal(PrincipalType.SYSTEM, "system"),
                        reason="all assignments finished")
        return result

    def list_assignments(self, agent_id: str, limit: int = 50, offset: int = 0):
        self.get_agent(agent_id)
        session = self._session_factory()
        try:
            rows, total = AssignmentRepository(session).for_agent(agent_id, limit, offset)
            ids = [r.id for r in rows]
        finally:
            session.close()
        return [self.refresh_assignment(i) for i in ids], total

    @staticmethod
    def _assignment_to_dict(row: AgentAssignment) -> dict:
        return {
            "id": row.id, "agent_id": row.agent_id, "task_id": row.task_id,
            "business_ref": row.business_ref, "objective": row.objective,
            "input_refs": row.input_refs, "required_capabilities": row.required_capabilities,
            "priority": row.priority, "timeout_seconds": row.timeout_seconds,
            "expected_output": row.expected_output,
            "quality_requirements": row.quality_requirements,
            "retry_limit": row.retry_limit,
            "parent_assignment_id": row.parent_assignment_id,
            "delegation_depth": row.delegation_depth, "status": row.status,
            "rejection_reason": row.rejection_reason,
            "result_summary": row.result_summary,
            "output_validation": row.output_validation,
            "failure_reason": row.failure_reason,
            "assigned_by": {"type": row.assigned_by_type, "id": row.assigned_by_id},
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ------------------------------------------------------------ metrics
    def _record_metric(self, agent_id: str, name: str, value: float | None,
                       measurement_type: str, details: dict | None = None) -> None:
        session = self._session_factory()
        try:
            MetricRepository(session).add(AgentMetric(
                agent_id=agent_id, metric_name=name, metric_value=value,
                measurement_type=measurement_type, recorded_at=utcnow(),
                details=details or {}))
        finally:
            session.close()

    def agent_metrics(self, agent_id: str) -> dict:
        """§12 metrics with honest measurement labelling. Aggregates are
        computed from assignment/task records (measured). Accuracy is
        NEVER reported: no evaluation dataset exists, so it is listed as
        unavailable rather than invented."""
        self.get_agent(agent_id)
        session = self._session_factory()
        try:
            assignments = AssignmentRepository(session).for_agent(agent_id, limit=1000)[0]
            metric_rows = MetricRepository(session).for_agent(agent_id, limit=200)
        finally:
            session.close()
        completed = [a for a in assignments if a.status == "completed"]
        failed = [a for a in assignments if a.status in ("failed", "output_invalid")]
        timed_out = [a for a in assignments
                     if a.status == "failed" and a.failure_reason
                     and "timed out" in a.failure_reason]
        durations = [m.metric_value for m in metric_rows
                     if m.metric_name == "execution_duration_ms"
                     and m.metric_value is not None]
        schema_checks = [m.metric_value for m in metric_rows
                         if m.metric_name == "output_schema_valid"]
        aggregates = {
            "tasks_assigned": {"value": len([a for a in assignments
                                             if a.status != "rejected"]),
                               "measurement_type": "measured"},
            "tasks_completed": {"value": len(completed), "measurement_type": "measured"},
            "tasks_failed": {"value": len(failed), "measurement_type": "measured"},
            "tasks_timed_out": {"value": len(timed_out), "measurement_type": "measured"},
            "average_execution_duration_ms": {
                "value": (round(sum(durations) / len(durations), 2) if durations else None),
                "measurement_type": "measured" if durations else "unavailable"},
            "output_schema_validity_rate": {
                "value": (round(sum(schema_checks) / len(schema_checks), 4)
                          if schema_checks else None),
                "measurement_type": "measured" if schema_checks else "unavailable",
                "basis": "share of completed tasks whose result satisfied the "
                         "assignment's §9.4 output contract"},
            "inference_requests": {
                "value": len([m for m in metric_rows
                              if m.metric_name == "inference_requests"]),
                "measurement_type": "estimated",
                "basis": "counted at the factory's shared-inference gate; agents "
                         "share one model infrastructure, so per-agent inference "
                         "load is an estimate, not a measurement"},
            "accuracy_percent": {
                "value": None, "measurement_type": "unavailable",
                "basis": "no evaluation dataset or methodology exists in this "
                         "build; accuracy is not invented (§12.2)"},
            "token_usage": {
                "value": None, "measurement_type": "unavailable",
                "basis": "no provider in this build reports token usage"},
            "per_agent_memory_mb": {
                "value": None, "measurement_type": "unavailable",
                "basis": "logical agents share the runtime; per-agent memory is "
                         "not separately measurable (budgets are estimates)"},
            "human_acceptance_rate": {
                "value": None, "measurement_type": "unavailable",
                "basis": "no human feedback channel exists before P-11"},
        }
        return {"agent_id": agent_id, "aggregates": aggregates,
                "observations": [{"metric_name": m.metric_name,
                                  "metric_value": m.metric_value,
                                  "measurement_type": m.measurement_type,
                                  "recorded_at": m.recorded_at.isoformat()
                                  if m.recorded_at else None}
                                 for m in metric_rows]}

    # --------------------------------------------------------------- health
    def compute_health(self, agent_id: str) -> dict:
        """Deterministic §12.3 health from measured records. An agent is
        not 'healthy' merely because a row exists: the verdict derives
        from completions, failures, timeouts and stalled work."""
        agent = self.get_agent(agent_id)
        session = self._session_factory()
        try:
            assignments = AssignmentRepository(session).for_agent(agent_id, limit=1000)[0]
        finally:
            session.close()
        thresholds = C.HEALTH_THRESHOLDS
        completed = [a for a in assignments if a.status == "completed"]
        failed = [a for a in assignments if a.status in ("failed", "output_invalid")]
        total = len(completed) + len(failed)
        failure_rate = (len(failed) / total) if total else 0.0
        consecutive = 0
        for a in sorted(assignments, key=lambda x: x.created_at or utcnow(),
                        reverse=True):
            if a.status in ("failed", "output_invalid"):
                consecutive += 1
            elif a.status == "completed":
                break
        unresponsive = False
        for a in assignments:
            if a.status == "running" and a.task_id:
                try:
                    task = self._tasks.get(a.task_id)
                except Exception:
                    continue
                if task.status == "running" and task.started_at is not None:
                    started = task.started_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=dt.timezone.utc)
                    limit = a.timeout_seconds * thresholds["unresponsive_timeout_multiplier"]
                    if (utcnow() - started).total_seconds() > limit:
                        unresponsive = True
        if agent.status == "failed":
            status = "FAILED"
        elif unresponsive:
            status = "UNRESPONSIVE"
        elif consecutive >= int(thresholds["consecutive_failures_failed"]):
            status = "FAILED"
        elif total >= int(thresholds["min_tasks_for_rate"]) \
                and failure_rate >= float(thresholds["failure_rate_degraded"]):
            status = "DEGRADED"
        elif total >= int(thresholds["min_tasks_for_rate"]) \
                and failure_rate >= float(thresholds["failure_rate_warning"]):
            status = "WARNING"
        else:
            status = "HEALTHY"
        details = {
            "tasks_total": total, "tasks_completed": len(completed),
            "tasks_failed": len(failed), "failure_rate": round(failure_rate, 4),
            "consecutive_failures": consecutive, "unresponsive": unresponsive,
            "lifecycle_status": agent.status,
            "basis": "measured assignment/task outcomes; thresholds in "
                     "agents.constants.HEALTH_THRESHOLDS",
            "last_successful_execution": max(
                (a.completed_at.isoformat() for a in completed if a.completed_at),
                default=None),
        }
        session = self._session_factory()
        try:
            HealthRepository(session).add(AgentHealth(
                agent_id=agent_id, health_status=status, last_check=utcnow(),
                details=details))
        finally:
            session.close()
        return {"agent_id": agent_id, "health_status": status, "details": details,
                "checked_at": utcnow().isoformat()}

    def latest_health(self, agent_id: str) -> dict:
        self.get_agent(agent_id)
        session = self._session_factory()
        try:
            row = HealthRepository(session).latest(agent_id)
        finally:
            session.close()
        if row is None:
            return self.compute_health(agent_id)
        return {"agent_id": agent_id, "health_status": row.health_status,
                "details": row.details,
                "checked_at": row.last_check.isoformat() if row.last_check else None}

    # ----------------------------------------------------------- maintenance
    async def run_maintenance(self, *, principal: Principal) -> dict:
        """§11.1 policy-driven automation, run deterministically:
        expired-grant sweep, idle suspension, failed-agent recovery
        (bounded), health checks with degraded<->active reconciliation."""
        self._require_manage(principal, "agent_factory.maintenance")
        settings = self.settings_values()
        expired = self.capabilities.sweep_expired()
        session = self._session_factory()
        try:
            agents = AgentQueryRepository(session).by_status(
                ["active", "idle", "busy", "degraded", "failed", "suspended"])
        finally:
            session.close()
        idle_suspended, recovered, health = [], [], {}
        for agent in agents:
            health[agent.id] = self.compute_health(agent.id)["health_status"]
            last = agent.last_activity_at or agent.created_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=dt.timezone.utc)
            idle_for = (utcnow() - last).total_seconds() if last else 0
            if agent.status in ("active", "idle") \
                    and idle_for >= int(settings["idle_suspend_seconds"]):
                session = self._session_factory()
                try:
                    busy = AssignmentRepository(session).active_for_agent(agent.id)
                finally:
                    session.close()
                if not busy:
                    await self.transition_agent(
                        agent.id, "suspended", actor=principal,
                        reason=f"automatic idle suspension after {int(idle_for)}s idle")
                    idle_suspended.append(agent.id)
                    continue
            if agent.status == "degraded" and health[agent.id] == "HEALTHY":
                await self.transition_agent(agent.id, "active", actor=principal,
                                            reason="health recovered to HEALTHY")
            elif agent.status == "active" and health[agent.id] == "DEGRADED":
                await self.transition_agent(agent.id, "degraded", actor=principal,
                                            reason="health degraded by measured failure rate")
            if agent.status == "failed":
                # Bounded recovery: re-initialization is allowed only while
                # the failed-init cap has not been hit for this agent's role.
                session = self._session_factory()
                try:
                    failed_inits = CreationRequestRepository(
                        session).count_failed_initializations(
                            agent.role, agent.template_id)
                finally:
                    session.close()
                if failed_inits < int(settings["max_initialization_failures_per_template"]):
                    config = self._pinned_config(agent) or {}
                    failures = self._initialization_checks(agent.id, config, settings)
                    if not failures:
                        await self.transition_agent(agent.id, "initializing",
                                                    actor=principal,
                                                    reason="automatic recovery attempt")
                        await self.transition_agent(agent.id, "active", actor=principal,
                                                    reason="recovery initialization passed")
                        recovered.append(agent.id)
        result = {"expired_grants_swept": expired,
                  "idle_suspended": idle_suspended,
                  "recovered_agents": recovered,
                  "health": health}
        self._audit(principal, "agent_factory.maintenance", "agent_factory", None,
                    "allow", details={k: v for k, v in result.items() if k != "health"})
        return result

    # ------------------------------------------------------ emergency controls
    async def emergency_stop(self, *, principal: Principal, scope: str = "all",
                             agent_id: str | None = None,
                             reason: str | None = None) -> dict:
        """§16.5 deterministic emergency controls. No LLM is consulted:
        this is straight-line backend logic over stored state."""
        self._require_owner(principal, "agent_factory.emergency_stop")
        system = Principal(PrincipalType.SYSTEM, "system")
        affected: list[str] = []
        cancelled_tasks: list[str] = []
        revoked: list[str] = []
        if scope == "agent":
            if not agent_id:
                from ..core.exceptions import ValidationError
                raise ValidationError("scope 'agent' requires agent_id")
            agent = self.get_agent(agent_id)
            if agent.status not in ("retired", "retiring"):
                if agent.status != "suspended":
                    await self.transition_agent(agent_id, "suspended", actor=principal,
                                                reason=reason or "emergency stop (single agent)")
                affected.append(agent_id)
            for name in self.capabilities.granted_capability_names(agent_id):
                self.capabilities.revoke(agent_id, name, revoked_by=principal)
                revoked.append(name)
            session = self._session_factory()
            try:
                active = AssignmentRepository(session).active_for_agent(agent_id)
            finally:
                session.close()
            for assignment in active:
                if assignment.task_id:
                    try:
                        await self._tasks.cancel(system, assignment.task_id)
                        cancelled_tasks.append(assignment.task_id)
                    except Exception:
                        pass
                    self.refresh_assignment(assignment.id)
        else:
            # Fleet-wide: stop creation + assignments (safe mode), suspend
            # every non-retired agent, cancel eligible queued/running work.
            current = self.settings_values()
            session = self._session_factory()
            try:
                ConfigRepository(session).set(
                    C.SETTINGS_KEY,
                    json.dumps({"version": C.SETTINGS_VERSION,
                                "values": {**current, "safe_mode": True,
                                           "creation_enabled": False,
                                           "assignments_enabled": False}}),
                    "P-04 agent factory settings (owner/governance-editable only)")
            finally:
                session.close()
            session = self._session_factory()
            try:
                agents = AgentQueryRepository(session).by_status(
                    ["proposed", "pending_approval", "initializing", "active",
                     "idle", "busy", "degraded", "failed"])
            finally:
                session.close()
            for agent in agents:
                if validate_transition(agent.status, "suspended"):
                    await self.transition_agent(agent.id, "suspended", actor=principal,
                                                reason=reason or "emergency stop (all agents)")
                    affected.append(agent.id)
            session = self._session_factory()
            try:
                from ..database.models.core import Task
                tasks = list(session.scalars(
                    select(Task).where(Task.assigned_agent_id.is_not(None),
                                       Task.status.in_(["queued", "paused",
                                                        "retry_pending",
                                                        "waiting_for_approval"]))).all())
            finally:
                session.close()
            for task in tasks:
                try:
                    await self._tasks.cancel(system, task.id)
                    cancelled_tasks.append(task.id)
                except Exception:
                    pass
        result = {"scope": scope, "agents_suspended": affected,
                  "tasks_cancelled": cancelled_tasks,
                  "capabilities_revoked": revoked,
                  "safe_mode": scope == "all", "reason": reason}
        self._audit(principal, "agent_factory.emergency_stop", "agent_factory",
                    agent_id, "allow", reason=reason, details=result)
        await self._publish(EventType.AGENT_EMERGENCY_STOP, result, severity="critical")
        return result

    async def resume_operations(self, *, principal: Principal) -> dict:
        """Owner lifts the emergency stop's factory gates. Suspended
        agents are NOT auto-resumed — each resume is a deliberate act."""
        self._require_owner(principal, "agent_factory.resume_operations")
        current = self.settings_values()
        session = self._session_factory()
        try:
            ConfigRepository(session).set(
                C.SETTINGS_KEY,
                json.dumps({"version": C.SETTINGS_VERSION,
                            "values": {**current, "safe_mode": False,
                                       "creation_enabled": True,
                                       "assignments_enabled": True}}),
                "P-04 agent factory settings (owner/governance-editable only)")
        finally:
            session.close()
        self._audit(principal, "agent_factory.resume_operations", "agent_factory",
                    None, "allow")
        return {"safe_mode": False, "creation_enabled": True,
                "assignments_enabled": True,
                "note": "suspended agents remain suspended until individually resumed"}

    # ------------------------------------------------------------- inference
    async def run_inference(self, agent_id: str, task_class: str, *,
                            principal: Principal) -> dict:
        """One inference selection for a logical agent through the SHARED
        P-02 router (§10/Scenario J). Requires the internal_reasoning
        capability; concurrency-gated; counted as an ESTIMATED metric."""
        agent = self.get_agent(agent_id)
        if agent.status not in ASSIGNABLE_STATES:
            from .errors import AgentNotActiveError
            raise AgentNotActiveError(
                f"agent {agent_id} is '{agent.status}' and cannot run inference",
                details={"error_category": "AGENT_NOT_ACTIVE"})
        if not self.capabilities.has_capability(agent_id, "internal_reasoning"):
            from .errors import CapabilityNotAuthorizedError
            raise CapabilityNotAuthorizedError(
                "agent does not hold the internal_reasoning capability",
                details={"error_category": "CAPABILITY_NOT_AUTHORIZED"})
        settings = self.settings_values()
        decision = await self.resources.run_shared_inference(task_class, settings=settings)
        self._record_metric(agent_id, "inference_requests", 1, "estimated",
                            {"task_class": task_class,
                             "note": "shared router; per-agent load is estimated"})
        return {"agent_id": agent_id, "task_class": task_class,
                "kind": decision.kind, "provider": decision.provider_name,
                "profile": decision.profile_name, "model_id": decision.model_id,
                "reasons": decision.reasons,
                "shared_infrastructure": True,
                "router_bindings": self.resources.router_bindings}

    # ------------------------------------------------------------ status views
    def agent_events(self, agent_id: str, limit: int = 50) -> list[dict]:
        """The agent's event view is served from the append-only audit
        trail (audit §5: no separate agent_events table)."""
        self.get_agent(agent_id)
        session = self._session_factory()
        try:
            rows = list(session.scalars(
                select(AuditEvent).where(
                    (AuditEvent.actor_id == agent_id)
                    | (AuditEvent.target_id == agent_id))
                .order_by(AuditEvent.created_at.desc()).limit(limit)).all())
            return [{"id": r.id, "action": r.action, "actor": r.actor_id,
                     "decision": r.decision, "reason": r.reason,
                     "details": r.details,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()

    def factory_status(self) -> dict:
        settings = self.settings_values()
        session = self._session_factory()
        try:
            query = AgentQueryRepository(session)
            from ..database.models.core import Agent as AgentRow
            statuses = {}
            for status_name in ("proposed", "pending_approval", "initializing",
                                "active", "idle", "busy", "degraded", "suspended",
                                "failed", "retiring", "retired", "created"):
                count = query.count_by_status([status_name])
                if count:
                    statuses[status_name] = count
            pending_factory_approvals = session.scalar(
                select(func.count()).select_from(Approval).where(
                    Approval.status == "pending",
                    Approval.action.in_([CREATE_ACTION,
                                         "agent_factory.grant_capability"]))) or 0
            total_agents = query.count_all()
        finally:
            session.close()
        pressure = self.resources.pressure()
        return {
            "total_agents": total_agents,
            "agents_by_status": statuses,
            "active_agents": statuses.get("active", 0) + statuses.get("busy", 0)
                             + statuses.get("idle", 0),
            "pending_approval_requests": int(pending_factory_approvals),
            "creation_enabled": settings["creation_enabled"],
            "assignments_enabled": settings["assignments_enabled"],
            "safe_mode": settings["safe_mode"],
            "system_mode": self._settings.mode,
            "limits": {k: settings[k] for k in (
                "max_total_agents", "max_active_agents", "max_agents_per_business",
                "max_child_agents_per_parent", "max_delegation_depth",
                "max_concurrent_inference_requests", "creation_rate_limit_per_hour")},
            "resource_pressure": pressure,
            "backpressure_actions": self.resources.backpressure_actions(pressure["level"]),
            "shared_inference": {"router_bindings": self.resources.router_bindings,
                                 "inference_active": self.resources.inference_active,
                                 "note": "one shared P-02 model router for all "
                                         "logical agents; no per-agent instances"},
        }

    def factory_resources(self) -> dict:
        pressure = self.resources.pressure()
        host = self.resources.host_resources()
        status = self.factory_status()
        return {
            "host": host,
            "pressure": pressure,
            "backpressure_actions": self.resources.backpressure_actions(pressure["level"]),
            "agents": {"total": status["total_agents"],
                       "by_status": status["agents_by_status"]},
            "queue": pressure.get("queue"),
            "inference": {"active": self.resources.inference_active,
                          "limit": self.settings_values()["max_concurrent_inference_requests"],
                          "measurement_type": "estimated",
                          "note": "inference is shared; per-agent figures are estimates"},
            "cpu_ram_measurement": "measured (host, via P-01 SystemMonitor/psutil)",
        }

    def scaling_evaluate(self) -> dict:
        settings = self.settings_values()
        session = self._session_factory()
        try:
            query = AgentQueryRepository(session)
            active = query.count_by_status(sorted(ACTIVE_STATES))
            busy = query.count_by_status(["busy"])
            idle = query.count_by_status(["idle"])
            total = query.count_all()
            durations: list[float] = []
            rows = list(session.scalars(
                select(AgentMetric).where(
                    AgentMetric.metric_name == "execution_duration_ms")).all())
            durations = [r.metric_value for r in rows if r.metric_value is not None]
        finally:
            session.close()
        queue = self.resources.pressure().get("queue") or {}
        queue_depth = int((queue.get("queued") or 0))
        snapshot = {
            "queue_depth": queue_depth,
            "pending_tasks": queue_depth,
            "active_agents": active, "busy_agents": busy, "idle_agents": idle,
            "pressure_level": self.resources.pressure()["level"],
            "specialized_demand": False,
            "at_agent_ceiling": total >= int(settings["max_total_agents"]),
            "avg_task_seconds": (round(sum(durations) / len(durations) / 1000.0, 3)
                                 if durations else None),
            "local_only": not self._settings.cloud_ai_enabled,
        }
        return self.scaling.evaluate(snapshot, settings)
