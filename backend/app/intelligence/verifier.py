"""Result verifier (P-02): a component SEPARATE from execution.

Compares a finished P-01 task's result with the step's declared
expectation and returns one of three honest outcomes:

- ``verified``   — the task completed and every declared check passed.
- ``failed``     — the task did not complete, or a declared check was
                   contradicted by the actual result (field present but
                   wrong, or ``ok`` not true when required).
- ``unverified`` — the task completed but the expectation cannot be
                   machine-confirmed (no checkable expectation declared,
                   or an expected field is absent from the result). This
                   is a first-class outcome: unverified is NEVER reported
                   as verified.
"""
from __future__ import annotations

from .schemas import ExpectationSpec


def _lookup(result: dict, dotted_key: str):
    current = result
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


class ResultVerifier:
    def verify(self, expectation: dict | None, task) -> tuple[str, str]:
        """task is a P-01 Task row (status/result attributes)."""
        if task is None:
            return "failed", "task record missing at verification time"
        if task.status != "completed":
            detail = ""
            if getattr(task, "error", None):
                detail = f"; error={task.error}"
            return "failed", f"task ended in state '{task.status}', not 'completed'{detail}"
        result = task.result or {}
        try:
            spec = ExpectationSpec(**(expectation or {}))
        except Exception as exc:
            return "unverified", f"declared expectation is not parseable: {exc}"
        if spec.kind == "none":
            return "unverified", "no machine-checkable expectation was declared for this step"
        if spec.require_ok and result.get("ok") is not True:
            return "failed", f"expected result.ok to be true, got {result.get('ok')!r}"
        missing: list[str] = []
        for key, expected in spec.fields.items():
            found, value = _lookup(result, key)
            if not found:
                missing.append(key)
            elif value != expected:
                return "failed", f"field '{key}': expected {expected!r}, got {value!r}"
        if missing:
            return ("unverified",
                    f"cannot confirm: field(s) absent from the task result: {missing}")
        return "verified", "task result matches the declared expectation"
