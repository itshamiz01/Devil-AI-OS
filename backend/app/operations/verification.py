"""Independent step verification (§6/§22 stage 7).

Verification is a separate evaluation from execution: the executor's
claim is checked against the step's declared acceptance criteria and
the substrate's own terminal state. The vocabulary is P-02's —
``verified`` / ``failed`` / ``unverified`` — and ``unverified`` is
never promoted to success anywhere in P-12 (a workflow whose
verification is unverified cannot reach COMPLETED).
"""
from __future__ import annotations


def evaluate(criteria: dict, *, substrate_status: str | None,
             result: dict | None) -> dict:
    """Evaluate acceptance criteria against an execution outcome.

    Criteria keys:
    * ``task_status``: expected substrate terminal status
      (e.g. "completed" for P-01 tasks, "verified"/"completed" for
      P-05 executions).
    * ``result_has``: list of keys that must be present in result.
    * ``result_equals``: {key: expected} exact matches in result.
    With no criteria, the substrate's success state alone decides:
    an explicitly successful substrate verifies; anything else is
    unverified (never silently passed).
    """
    checks: list[dict] = []
    result = result or {}
    failed = False

    expected_status = (criteria or {}).get("task_status")
    if expected_status:
        ok = substrate_status == expected_status
        checks.append({"check": "substrate_status",
                       "expected": expected_status,
                       "actual": substrate_status, "ok": ok})
        failed = failed or not ok
    for key in (criteria or {}).get("result_has") or []:
        ok = key in result and result.get(key) not in (None, "")
        checks.append({"check": "result_has", "key": key, "ok": ok})
        failed = failed or not ok
    for key, expected in ((criteria or {}).get("result_equals") or {}).items():
        ok = result.get(key) == expected
        checks.append({"check": "result_equals", "key": key,
                       "expected": expected, "actual": result.get(key),
                       "ok": ok})
        failed = failed or not ok

    if failed:
        return {"status": "failed", "checks": checks,
                "reason": "one or more acceptance criteria failed"}
    if checks:
        return {"status": "verified", "checks": checks,
                "reason": "all acceptance criteria satisfied"}
    if substrate_status in ("completed", "verified"):
        return {"status": "verified",
                "checks": [{"check": "substrate_status",
                            "actual": substrate_status, "ok": True}],
                "reason": "substrate reported success; no explicit criteria"}
    return {"status": "unverified", "checks": checks,
            "reason": "no acceptance criteria and no substrate success "
                      "signal — not counted as success"}
