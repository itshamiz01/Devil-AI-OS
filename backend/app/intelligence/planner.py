"""Planning engine (P-02): deterministic baseline planner + LLM adapter,
behind ONE identical validation gate.

Design rule (preparation pack §2.1): the acceptance flow must work with
NO model available, so the baseline planner is a real planner, not a
fallback stub. LLM output is untrusted data: it is parsed into
PlanProposal and then validated exactly like baseline output.

Failure semantics (documented, tested):
- Provider unavailable / timeout / unparseable garbage output
  -> recorded, then baseline planner is tried (fallback).
- A well-formed proposal that FAILS VALIDATION (unregistered tool,
  invalid payload, permission pre-check denied) -> the plan is REJECTED
  outright. There is no fallback: the model attempted something
  impermissible and that attempt is a security record.
"""
from __future__ import annotations

import re

from pydantic import ValidationError as PydanticValidationError

from ..core.exceptions import ValidationError
from ..permissions.models import Principal
from ..tasks.models import TaskExecutionError
from .schemas import PlanProposal, StepProposal, ValidatedStep
from .tools import ToolRegistryView


class PlanRejectedError(ValidationError):
    """A proposal failed the identical validation gate."""

    def __init__(self, message: str, step_tool: str | None = None):
        super().__init__(message, details={"step_tool": step_tool})


class PlanValidator:
    def __init__(self, tools: ToolRegistryView, permissions):
        self._tools = tools
        self._permissions = permissions

    def validate(self, proposal: PlanProposal, principal: Principal,
                 correlation_id: str | None = None) -> list[ValidatedStep]:
        validated: list[ValidatedStep] = []
        for index, step in enumerate(proposal.steps):
            if not self._tools.has(step.tool_name):
                raise PlanRejectedError(
                    f"step {index + 1} references unregistered tool "
                    f"'{step.tool_name}'; plans may only use registered tools",
                    step_tool=step.tool_name)
            try:
                payload = self._tools.validate_payload(step.tool_name, step.payload)
            except TaskExecutionError as exc:
                raise PlanRejectedError(
                    f"step {index + 1} payload invalid for '{step.tool_name}': {exc}",
                    step_tool=step.tool_name)
            permission = self._tools.permission(step.tool_name)
            decision = self._permissions.check(
                principal, permission, resource=f"tool:{step.tool_name}",
                correlation_id=correlation_id)
            if not decision.allowed:
                raise PlanRejectedError(
                    f"step {index + 1} ('{step.tool_name}') denied at plan time: "
                    f"principal lacks '{permission}' ({decision.reason})",
                    step_tool=step.tool_name)
            validated.append(ValidatedStep(
                name=step.name or f"step {index + 1}: {step.tool_name}",
                tool_name=step.tool_name, payload=payload,
                expectation=step.expectation.model_dump(),
                task_class=step.task_class, essential=step.essential,
                timeout_seconds=step.timeout_seconds))
        return validated


def parse_proposal(raw) -> PlanProposal:
    """Parse untrusted provider output into the typed plan schema."""
    if not isinstance(raw, dict):
        raise PlanRejectedError("provider output is not a JSON object; cannot be a plan")
    try:
        return PlanProposal(**raw)
    except PydanticValidationError as exc:
        raise PlanRejectedError(f"provider output failed plan schema validation: {exc.errors()}")


# --------------------------------------------------------------------------
# Baseline (deterministic) planner: known mission templates.
# --------------------------------------------------------------------------

def _health_template(text: str, lower: str):
    if "health" not in lower:
        return None
    return PlanProposal(steps=[
        StepProposal(
            name="snapshot system health", tool_name="core.health_snapshot",
            payload={}, task_class="fast",
            expectation={"kind": "result_fields", "require_ok": True, "fields": {}}),
        StepProposal(
            name="task system self-test (echo)", tool_name="core.echo_check",
            payload={"message": "task system self-test", "data": {"probe": "p02"}},
            expectation={"kind": "result_fields", "require_ok": True,
                         "fields": {"echo.message": "task system self-test"}}),
    ], rationale="template system_health_check: monitor snapshot + governed echo self-test")


def _wait_template(text: str, lower: str):
    if "wait" not in lower:
        return None
    ms = 250
    match = re.search(r"(\d+)\s*(ms|milliseconds|s|sec|seconds)?", lower)
    if match:
        value = int(match.group(1))
        unit = match.group(2) or "ms"
        ms = value * 1000 if unit in ("s", "sec", "seconds") else value
    ms = max(0, min(ms, 10_000))  # core.wait's own bound
    return PlanProposal(steps=[
        StepProposal(
            name=f"wait {ms} ms", tool_name="core.wait",
            payload={"milliseconds": ms},
            expectation={"kind": "result_fields", "require_ok": True,
                         "fields": {"waited_ms": ms}}),
        StepProposal(
            name="report wait completion", tool_name="core.echo_check",
            payload={"message": "wait complete", "data": {"waited_ms": ms}},
            expectation={"kind": "result_fields", "require_ok": True,
                         "fields": {"echo.message": "wait complete"}}),
    ], rationale="template wait_and_report: bounded wait, then a governed echo report")


def _echo_template(text: str, lower: str):
    stripped = text.strip()
    if lower.startswith("echo "):
        message = stripped[5:].strip()
    elif lower.startswith("echo:"):
        message = stripped[5:].strip()
    else:
        return None
    if not message:
        return None
    return PlanProposal(steps=[
        StepProposal(
            name="echo mission message", tool_name="core.echo_check",
            payload={"message": message, "data": {}},
            expectation={"kind": "result_fields", "require_ok": True,
                         "fields": {"echo.message": message}}),
    ], rationale="template echo_message: single governed echo step")


_TEMPLATES = [
    ("system_health_check", _health_template),
    ("wait_and_report", _wait_template),
    ("echo_message", _echo_template),
]


class BaselinePlanner:
    """Rule-based planner. Returns (template_name, PlanProposal) or None
    when no known template matches — an honest 'cannot plan', never an
    invented plan."""

    actor = "rule-engine"

    def match_name(self, text: str) -> str | None:
        lower = text.lower()
        for name, builder in _TEMPLATES:
            if builder(text, lower) is not None:
                return name
        return None

    def plan(self, text: str) -> tuple[str, PlanProposal] | None:
        lower = text.lower()
        for name, builder in _TEMPLATES:
            proposal = builder(text, lower)
            if proposal is not None:
                return name, proposal
        return None
