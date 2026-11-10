"""Typed plan schemas (P-02 §2: a plan is data, never code).

Both the deterministic baseline planner and any LLM planner adapter emit
exactly these models, and both pass through the identical validator. Model
output is untrusted: anything that does not parse into these schemas is
rejected before it can influence execution.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExpectationSpec(BaseModel):
    """Machine-checkable expectation for a step's handler result.

    kind="result_fields": the verifier checks ``require_ok`` and the
    (possibly dotted) ``fields`` against the task result.
    kind="none": no machine-checkable expectation — the verifier must
    honestly report the step as UNVERIFIED, never as verified.
    """

    kind: str = Field(default="result_fields", pattern="^(result_fields|none)$")
    require_ok: bool = True
    fields: dict = Field(default_factory=dict)


class StepProposal(BaseModel):
    name: str = Field(default="", max_length=300)
    tool_name: str = Field(min_length=1, max_length=200)
    payload: dict = Field(default_factory=dict)
    expectation: ExpectationSpec = Field(default_factory=ExpectationSpec)
    task_class: str = Field(default="standard", max_length=100)
    essential: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)


class PlanProposal(BaseModel):
    steps: list[StepProposal] = Field(min_length=1, max_length=50)
    rationale: str = Field(default="", max_length=4000)


class ValidatedStep(BaseModel):
    """A step after identical validation: tool exists in the registry,
    payload validated/normalised by the handler's own pydantic model,
    permission pre-check passed."""

    name: str
    tool_name: str
    payload: dict
    expectation: dict
    task_class: str = "standard"
    essential: bool = False
    timeout_seconds: float = 30.0


def canonical_steps(steps: list[ValidatedStep]) -> list[dict]:
    """Canonical form used for plan hashing / approval binding."""
    return [
        {"tool_name": s.tool_name, "payload": s.payload, "expectation": s.expectation}
        for s in steps
    ]
