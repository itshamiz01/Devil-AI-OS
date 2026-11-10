"""Workflow plan validation and deterministic decomposition (§5/§6).

Pure module. A workflow definition is structured data — never free
text and never code. Validation enforces the §22 pipeline's stage 2
(structured validation): known step kinds, known substrate targets,
a dependency DAG with no cycles, action classes drawn from P-10's
classified vocabulary only.

Decomposition is deterministic (named templates), exactly like
P-02's BaselinePlanner: staging has no real LLM (see the P-12 audit
§1.2), so plans come from templates or from importing a P-02 plan —
both paths pass through the identical validation below.
"""
from __future__ import annotations

import hashlib
import json

from ..core.exceptions import ValidationError
from . import constants as C

MAX_STEPS = 100

# Internal step runners implemented by the P-12 service (deterministic
# data composition over real records — no model calls).
INTERNAL_RUNNERS = ("summarize_inputs", "compose_report", "record_note")


def definition_hash(definition: dict) -> str:
    """SHA-256 over the canonical definition — binds a workflow-start
    approval to the exact plan that was approved."""
    canonical = json.dumps(definition, sort_keys=True,
                           separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_definition(definition: dict) -> list[dict]:
    """Validate a workflow definition. Returns the normalized step
    list; raises ValidationError with per-step details on failure."""
    if not isinstance(definition, dict):
        raise ValidationError("workflow definition must be an object")
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValidationError("workflow definition requires a non-empty 'steps' list")
    if len(steps) > MAX_STEPS:
        raise ValidationError(f"workflow has too many steps (max {MAX_STEPS})")

    seen: set[str] = set()
    normalized: list[dict] = []
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ValidationError(f"step #{i} must be an object")
        key = raw.get("step_key")
        if not key or not isinstance(key, str):
            raise ValidationError(f"step #{i} requires a string 'step_key'")
        if key in seen:
            raise ValidationError(f"duplicate step_key '{key}'")
        seen.add(key)
        kind = raw.get("kind", "task_handler")
        if kind not in C.TASK_KINDS:
            raise ValidationError(f"step '{key}': unknown kind '{kind}'")
        action_class = raw.get("action_class", "business.read")
        if action_class not in C.ACTION_CLASSES:
            raise ValidationError(
                f"step '{key}': action_class '{action_class}' is not in the "
                "P-10 classified vocabulary (unclassified actions fail closed)")
        substrate = raw.get("substrate") or {}
        if not isinstance(substrate, dict):
            raise ValidationError(f"step '{key}': 'substrate' must be an object")
        if kind == "task_handler":
            handler = substrate.get("handler")
            if not handler or not isinstance(handler, str) or "." not in handler:
                raise ValidationError(
                    f"step '{key}': task_handler steps require substrate.handler "
                    "(a registered P-01 handler name)")
            payload = substrate.get("payload", {})
            if not isinstance(payload, dict):
                raise ValidationError(f"step '{key}': substrate.payload must be an object")
            if "code" in payload or "script" in payload:
                raise ValidationError(
                    f"step '{key}': payloads may never carry code (P-01 rule)")
        elif kind == "execution":
            if not substrate.get("tool") or not substrate.get("action"):
                raise ValidationError(
                    f"step '{key}': execution steps require substrate.tool and "
                    "substrate.action (dispatched through P-05)")
            params = substrate.get("parameters", {})
            if not isinstance(params, dict):
                raise ValidationError(f"step '{key}': substrate.parameters must be an object")
        else:  # internal
            if substrate.get("runner") not in INTERNAL_RUNNERS:
                raise ValidationError(
                    f"step '{key}': internal steps require substrate.runner in "
                    f"{sorted(INTERNAL_RUNNERS)}")
        depends = raw.get("depends_on") or []
        if not isinstance(depends, list) or not all(isinstance(d, str) for d in depends):
            raise ValidationError(f"step '{key}': depends_on must be a list of step keys")
        if key in depends:
            raise ValidationError(f"step '{key}': a step cannot depend on itself")
        budget_ref = raw.get("budget_ref") or {}
        if not isinstance(budget_ref, dict):
            raise ValidationError(f"step '{key}': budget_ref must be an object")
        if budget_ref.get("requires_spend"):
            kind_spend = budget_ref.get("spend_kind", "operating")
            if kind_spend not in C.SPEND_KINDS:
                raise ValidationError(
                    f"step '{key}': unknown spend_kind '{kind_spend}'")
            # Amounts are NOT part of the definition: a spend step
            # declares its P-07 budget + kind; the amount is supplied
            # at execution time and decided by P-07 (no money in
            # P-12's plan data either).
        normalized.append({
            "step_key": key,
            "name": str(raw.get("name") or key),
            "objective": str(raw.get("objective") or ""),
            "description": raw.get("description"),
            "kind": kind,
            "action_class": action_class,
            "substrate": substrate,
            "depends_on": list(depends),
            "required_capabilities": list(raw.get("required_capabilities") or []),
            "priority": int(raw.get("priority", 5)),
            "estimated_effort": dict(raw.get("estimated_effort") or {}),
            "budget_ref": budget_ref,
            "permission_requirements": dict(raw.get("permission_requirements") or {}),
            "input_data": dict(raw.get("input_data") or {}),
            "expected_output": dict(raw.get("expected_output") or {}),
            "acceptance_criteria": dict(raw.get("acceptance_criteria") or {}),
            "verification_method": str(raw.get("verification_method")
                                       or "acceptance_criteria"),
            "retry_policy": dict(raw.get("retry_policy") or {}),
            "assigned_agent_id": raw.get("assigned_agent_id"),
        })

    keys = {s["step_key"] for s in normalized}
    for step in normalized:
        for dep in step["depends_on"]:
            if dep not in keys:
                raise ValidationError(
                    f"step '{step['step_key']}': unknown dependency '{dep}'")
    order = topological_order(normalized)  # raises on cycles
    if len(order) != len(normalized):
        raise ValidationError("workflow dependency graph is inconsistent")
    return normalized


def topological_order(steps: list[dict]) -> list[str]:
    """Kahn's algorithm; raises ValidationError on a cycle (§6:
    circular dependencies are rejected)."""
    indegree = {s["step_key"]: 0 for s in steps}
    children: dict[str, list[str]] = {s["step_key"]: [] for s in steps}
    for step in steps:
        for dep in step["depends_on"]:
            indegree[step["step_key"]] += 1
            children[dep].append(step["step_key"])
    queue = sorted(k for k, d in indegree.items() if d == 0)
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in sorted(children[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(steps):
        raise ValidationError(
            "workflow dependency graph contains a cycle",
            details={"steps": sorted(indegree)})
    return order


def ready_steps(steps: list[dict]) -> list[dict]:
    """Steps whose dependencies are all COMPLETED and which are
    themselves runnable (PENDING/READY), in priority order."""
    done = {s["step_key"] for s in steps if s["status"] == "COMPLETED"}
    ready = [s for s in steps
             if s["status"] in ("PENDING", "READY")
             and all(d in done for d in s["depends_on"])]
    return sorted(ready, key=lambda s: (s["priority"], s["step_key"]))


# --- deterministic decomposition templates ------------------------------------
# Each template decomposes a business objective into a governed DAG.
# Steps run on real substrates (P-01 handlers / internal runners), so
# a template workflow genuinely executes end to end in staging.

TEMPLATES: dict[str, dict] = {
    "monitoring_report": {
        "description": "Collect a system snapshot, summarise it, and file a report.",
        "steps": [
            {"step_key": "collect", "name": "Collect system snapshot",
             "objective": "Read current system state",
             "kind": "task_handler", "action_class": "read",
             "substrate": {"handler": "core.health_snapshot", "payload": {}},
             "acceptance_criteria": {"task_status": "completed"}},
            {"step_key": "summarise", "name": "Summarise findings",
             "objective": "Compose a summary from collected inputs",
             "kind": "internal", "action_class": "draft.create",
             "substrate": {"runner": "summarize_inputs"},
             "depends_on": ["collect"],
             "acceptance_criteria": {"result_has": ["summary"]}},
            {"step_key": "report", "name": "File operations report",
             "objective": "Record the report as a workflow artifact",
             "kind": "internal", "action_class": "report.generate",
             "substrate": {"runner": "compose_report"},
             "depends_on": ["summarise"],
             "acceptance_criteria": {"result_has": ["report"]}},
        ],
    },
    "content_cycle": {
        "description": "Research, draft, review and (gated) publish a content item.",
        "steps": [
            {"step_key": "research", "name": "Research topic",
             "objective": "Gather source material references",
             "kind": "task_handler", "action_class": "business.read",
             "substrate": {"handler": "core.echo_check",
                           "payload": {"message": "research-complete"}},
             "acceptance_criteria": {"task_status": "completed"}},
            {"step_key": "draft", "name": "Draft content",
             "objective": "Produce a draft from the research",
             "kind": "internal", "action_class": "draft.create",
             "substrate": {"runner": "summarize_inputs"},
             "depends_on": ["research"],
             "acceptance_criteria": {"result_has": ["summary"]}},
            {"step_key": "review", "name": "Review draft",
             "objective": "Independent review pass over the draft",
             "kind": "task_handler", "action_class": "business.read",
             "substrate": {"handler": "core.echo_check",
                           "payload": {"message": "review-complete"}},
             "depends_on": ["draft"],
             "acceptance_criteria": {"task_status": "completed"}},
            {"step_key": "publish", "name": "Publish content",
             "objective": "Publish the reviewed draft (restricted action)",
             "kind": "task_handler", "action_class": "content.publish",
             "substrate": {"handler": "core.echo_check",
                           "payload": {"message": "published"}},
             "depends_on": ["review"],
             "acceptance_criteria": {"task_status": "completed"}},
        ],
    },
    "maintenance_check": {
        "description": "Snapshot, verify and note a maintenance check.",
        "steps": [
            {"step_key": "snapshot", "name": "Snapshot system",
             "objective": "Capture current system state",
             "kind": "task_handler", "action_class": "read",
             "substrate": {"handler": "core.health_snapshot", "payload": {}},
             "acceptance_criteria": {"task_status": "completed"}},
            {"step_key": "note", "name": "Record maintenance note",
             "objective": "Write the maintenance note into the workflow record",
             "kind": "internal", "action_class": "task.update_status",
             "substrate": {"runner": "record_note"},
             "depends_on": ["snapshot"],
             "acceptance_criteria": {"result_has": ["note"]}},
        ],
    },
}


def decompose(template: str, objective: str) -> dict:
    """Deterministic decomposition of an objective via a named
    template. Returns a workflow definition dict ready for
    validate_definition. Labelled honestly: this is template-based
    planning (planner id 'operations-template-v1'), not an LLM."""
    spec = TEMPLATES.get(template)
    if spec is None:
        raise ValidationError(
            f"unknown decomposition template '{template}'",
            details={"available": sorted(TEMPLATES)})
    import copy
    steps = copy.deepcopy(spec["steps"])
    return {"planner": "operations-template-v1", "template": template,
            "objective": objective, "steps": steps}
