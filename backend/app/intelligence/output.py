"""Structured output validation (P-02 §13).

Model output enters the system here and nowhere else. §13 is unambiguous: *never
trust model-generated JSON without schema validation*. If validation fails, one
bounded repair attempt is allowed; if that fails too, the result is a controlled
failure rather than a partially-parsed object that downstream modules would treat
as trustworthy.

The repair attempt is bounded to exactly one because an unbounded repair loop is
a way to burn inference budget while appearing to make progress.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .router import ModelRouter, RouteRequirements
from .schemas import ClarificationQuestion, GenerationRequest

T = TypeVar("T", bound=BaseModel)

#: One repair attempt, never more (§13).
MAX_REPAIR_ATTEMPTS = 1

_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


class StructuredOutputError(RuntimeError):
    """Model output could not be validated against its schema."""

    def __init__(self, detail: str, *, raw: str | None = None, errors: list[str] | None = None) -> None:
        self.detail = detail
        self.raw = raw
        self.errors = list(errors or [])
        super().__init__(detail)


class InterpretationPayload(BaseModel):
    """The shape a model must return for mission interpretation.

    Mirrors `prompts.interpretation_request_schema()`. `extra="forbid"` matters:
    a model that invents additional fields (a `budget` it decided on, an
    `authorized` flag) must fail validation rather than have those fields
    silently carried into a Mission.
    """

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=500)
    intended_outcome: str | None = Field(default=None, max_length=500)
    expected_deliverables: list[str] = Field(default_factory=list, max_length=10)
    required_capabilities: list[str] = Field(default_factory=list, max_length=10)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    missing_information: list[ClarificationQuestion] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


#: Fields a model may never supply, because they carry authority. Even though
#: `extra="forbid"` already rejects them, this list makes the boundary explicit
#: and lets the error message say *why* the output was refused.
AUTHORITY_FIELDS = frozenset({
    "budget", "financial_limit", "authorized", "authorization", "approved",
    "permission", "permissions", "autonomy_level", "risk_override",
    "success_criteria", "credentials", "secret", "secrets",
})


def extract_json(text: str) -> Any:
    """Pull the first JSON object or array out of model output.

    Handles the three shapes models actually produce: bare JSON, fenced JSON, and
    JSON embedded in prose. Extraction is deliberately narrow — it takes the
    first balanced candidate and lets validation decide whether it is right.
    """
    if not text or not text.strip():
        raise StructuredOutputError("model returned empty output")

    fenced = _FENCED_JSON.search(text)
    candidates: list[str] = []
    if fenced:
        candidates.append(fenced.group(1))

    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        candidates.append(stripped)

    # Fall back to the outermost braces in prose-wrapped output.
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start:end + 1])
    start, end = stripped.find("["), stripped.rfind("]")
    if start != -1 and end > start:
        candidates.append(stripped[start:end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise StructuredOutputError("no parseable JSON found in model output", raw=text[:500])


def check_authority_fields(data: Any) -> list[str]:
    """Report any authority-bearing field a model tried to supply.

    This is the concrete defence behind §16: a model cannot grant itself an
    approval, a budget or a permission by including one in its JSON.
    """
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in AUTHORITY_FIELDS:
                    found.append(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return sorted(set(found))


class StructuredOutputParser:
    """Validates model output, with exactly one bounded repair attempt."""

    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router
        self.repair_attempts = 0
        self.rejected: list[str] = []

    def parse(self, text: str, model_type: type[T]) -> T:
        """Validate already-obtained text. No repair (that needs the router)."""
        data = extract_json(text)
        violations = check_authority_fields(data)
        if violations:
            self.rejected.append(f"authority fields: {violations}")
            raise StructuredOutputError(
                f"model output attempted to supply authority-bearing field(s) "
                f"{violations}; a model may not set budgets, approvals or permissions",
                raw=text[:500],
                errors=violations,
            )
        try:
            return model_type.model_validate(data)
        except ValidationError as exc:
            errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            self.rejected.append("; ".join(errors))
            raise StructuredOutputError(
                f"model output failed schema validation: {'; '.join(errors)}",
                raw=text[:500],
                errors=errors,
            ) from exc

    async def parse_with_repair(
        self,
        text: str,
        model_type: type[T],
        *,
        request: GenerationRequest,
        requirements: RouteRequirements | None = None,
    ) -> T:
        """Parse, and on failure make one bounded repair attempt (§13).

        The repair prompt contains only the validation errors and the original
        schema — never the raw output echoed back at length, which would waste
        context budget on a host with very little of it.
        """
        try:
            return self.parse(text, model_type)
        except StructuredOutputError as first:
            if self.router is None or self.repair_attempts >= MAX_REPAIR_ATTEMPTS:
                raise
            self.repair_attempts += 1

        repair_prompt = (
            "Your previous response could not be validated. Return ONLY a JSON "
            "object matching the required schema, with no prose and no code fence.\n\n"
            f"Validation errors:\n{chr(10).join('- ' + e for e in first.errors) or '- ' + first.detail}\n\n"
            f"Required schema:\n{json.dumps(model_type.model_json_schema(), indent=2)[:2000]}"
        )
        repair_request = request.model_copy(update={
            "prompt": repair_prompt,
            "purpose": "output_repair",
            # A repair must not be allowed to run hotter than the original:
            # determinism is the point.
            "temperature": 0.0,
        })
        result = await self.router.generate(repair_request, requirements)
        # A repair attempt is itself validated, and its own failure is terminal:
        # there is no second repair.
        return self.parse(result.text, model_type)


__all__ = [
    "AUTHORITY_FIELDS",
    "InterpretationPayload",
    "MAX_REPAIR_ATTEMPTS",
    "StructuredOutputError",
    "StructuredOutputParser",
    "check_authority_fields",
    "extract_json",
]
