"""Launch Readiness Engine (§20): eight deterministic dimensions,
five results, hard blockers override any score.

Every finding carries its evidence reference. The review never claims
legal compliance is certified (see the disclaimer constant) and launch
judgement is anchored to the pre-declaration, not to checklist
completion: the review embeds the declaration comparison, including the
machine-checkable budget-cap test.
"""
from __future__ import annotations

from . import constants as C


def _dim(status: str, findings: list[str]) -> dict:
    return {"status": status, "findings": findings}


def evaluate(facts: dict) -> dict:
    dims: dict[str, dict] = {}
    blockers: list[dict] = []
    warnings: list[str] = []
    outstanding: list[str] = []

    def blocker(dim: str, text: str, kind: str = "internal") -> None:
        blockers.append({"dimension": dim, "blocker": text, "kind": kind})
        outstanding.append(text)

    def warn(dim: str, text: str) -> None:
        warnings.append(text)

    # A — Market readiness
    f: list[str] = []
    status = "pass"
    if facts["validation_level"] < facts["min_level"]:
        status = "blocker"
        blocker("A", f"validation level {facts['validation_level']} below "
                     f"minimum {facts['min_level']}")
    else:
        f.append(f"validation level {facts['validation_level']} meets the "
                 f"minimum {facts['min_level']} (P-03, computed)")
    if not facts["customer_defined"]:
        status = "blocker"; blocker("A", "target customer is not defined")
    if not (facts["competitor_count"] > 0 or facts["market_analysis"]):
        status = "blocker" if status != "blocker" else status
        blocker("A", "no competitor research or market analysis on file")
    if not facts["pricing_documented"]:
        status = "blocker"; blocker("A", "pricing is not documented")
    dims["A_market"] = _dim(status, f or ["market checks passed"])

    # B — Product readiness
    f, status = [], "pass"
    if not facts["product_exists"]:
        status = "blocker"; blocker("B", "no product exists (a blueprint "
                                         "is not a product, §19)")
    else:
        qr = facts.get("quality_review") or {}
        checks = qr.get("checks") or []
        failed = [c for c in checks if c.get("status") == "failed"]
        missing = [c for c in checks if c.get("status") == "not_run"]
        if failed:
            status = "blocker"
            blocker("B", "quality checks failed: " +
                    ", ".join(c["name"] for c in failed))
        if missing:
            status = "blocker"
            blocker("B", "required quality checks not run: " +
                    ", ".join(c["name"] for c in missing))
        if not failed and not missing and checks:
            f.append(f"{len(checks)} quality checks passed "
                     f"(reviewer: {qr.get('reviewed_by', 'recorded')})")
    if not facts["limitations_documented"]:
        status = "blocker"
        blocker("B", "product limitations are not documented")
    if not facts["documentation_assets"]:
        status = "blocker"
        blocker("B", "required documentation assets are missing")
    dims["B_product"] = _dim(status, f or ["product checks passed"])

    # C — Brand readiness
    f, status = [], "pass"
    if not facts["identity_exists"]:
        status = "blocker"; blocker("C", "brand identity does not exist")
    if not facts["brand_assets"]:
        status = "blocker"; blocker("C", "brand assets are not prepared")
    if not facts["product_description_asset"]:
        status = "blocker"
        blocker("C", "accurate product description asset is missing")
    if facts["rights_unresolved"]:
        status = "blocker"
        blocker("C", "asset usage-rights conflicts are unresolved")
    dims["C_brand"] = _dim(status, f or ["brand checks passed"])

    # D — Distribution readiness
    f, status = [], "pass"
    if not facts["primary_channel_selected"]:
        status = "blocker"; blocker("D", "no primary channel is selected")
    if not facts["gates_recorded"]:
        status = "blocker"
        blocker("D", "platform-gate outcomes are not recorded for all "
                     "channels")
    if facts.get("primary_gate_outcome") == "BLOCKED":
        status = "blocker"
        blocker("D", "primary channel is blocked by its platform gate",
                kind="external")
    if not facts["channel_assets_ready"]:
        status = "blocker"
        blocker("D", "required channel assets are not prepared")
    for platform in facts.get("human_action_pending") or []:
        warn("D", f"{platform}: publish step requires human action "
                  "(platform gate) — prepared package only")
        f.append(f"{platform} gate: REQUIRES_HUMAN_ACTION recorded")
    dims["D_distribution"] = _dim(status, f or ["distribution checks passed"])

    # E — Customer readiness
    f, status = [], "pass"
    if not facts["onboarding_prepared"]:
        status = "blocker"; blocker("E", "customer onboarding is not prepared")
    if not facts["support_procedures"]:
        status = "blocker"; blocker("E", "support procedures do not exist")
    if not facts["refund_documented"]:
        status = "blocker"
        blocker("E", "refund/complaint process is not documented")
    dims["E_customer"] = _dim(status, f or ["customer checks passed"])

    # F — Operational readiness
    f, status = [], "pass"
    for key, label in (("monitoring_noted", "monitoring approach"),
                       ("backup_noted", "backup approach"),
                       ("recovery_noted", "recovery procedures"),
                       ("dependencies_identified", "dependency list")):
        if not facts[key]:
            status = "blocker"; blocker("F", f"{label} is not recorded")
    if not facts["agents_assigned"]:
        status = "blocker"
        blocker("F", "no responsible agents are assigned to the business")
    dims["F_operational"] = _dim(status, f or ["operational checks passed"])

    # G — Legal and compliance readiness (never "certified")
    f, status = [], "pass"
    if not facts["legal_requirements_identified"]:
        status = "blocker"
        blocker("G", "legal/compliance requirements are not identified")
    if not facts["policies_prepared"]:
        status = "blocker"
        blocker("G", "privacy/terms templates are not prepared")
    if not facts["platform_terms_reviewed"]:
        status = "blocker"
        blocker("G", "platform terms have not been reviewed (gate records)")
    f.append("legal readiness is an internal checklist outcome only — "
             "not independently certified")
    dims["G_legal"] = _dim(status, f)

    # H — Financial readiness (inputs only; P-07 owns truth)
    f, status = [], "pass"
    if not facts["costs_documented"]:
        status = "blocker"; blocker("H", "startup/operating costs are "
                                         "not documented")
    if not facts["risks_recorded"]:
        status = "blocker"; blocker("H", "financial risks are not recorded")
    if not facts["p07_payload_ok"]:
        status = "blocker"
        blocker("H", "P-07 financial-input payload does not validate")
    decl = facts.get("declaration") or {}
    if decl.get("present") and decl.get("startup_total") is not None:
        if decl["startup_total"] > decl["budget_cap"]:
            status = "blocker"
            blocker("H", f"estimated startup total {decl['startup_total']} "
                         f"exceeds the declared budget cap "
                         f"{decl['budget_cap']} {decl.get('currency', '')} "
                         "(judged against the pre-declaration)")
        else:
            f.append(f"startup estimate {decl['startup_total']} within the "
                     f"declared budget cap {decl['budget_cap']}")
    dims["H_financial"] = _dim(status, f or ["financial-input checks passed"])

    # ---- overall result: blockers override everything ----------------
    if any(b["kind"] == "external" for b in blockers):
        overall = "BLOCKED"
    elif blockers:
        overall = "NOT_READY"
    elif facts.get("professional_review_required"):
        overall = "OWNER_REVIEW_REQUIRED"
        outstanding.append(
            "compliance screening requires professional/owner review "
            "before launch (not a certification)")
    elif warnings:
        overall = "READY_WITH_WARNINGS"
    else:
        overall = "READY"

    declaration_comparison = {
        "declaration_present": bool(decl.get("present")),
        "declaration_approved": bool(decl.get("approved")),
        "success_criteria": decl.get("success_criteria", []),
        "budget_cap": decl.get("budget_cap"),
        "currency": decl.get("currency"),
        "startup_total_estimate": decl.get("startup_total"),
        "note": ("Launch is judged against this pre-declaration. "
                 "Narrative success criteria are owner-judged at the "
                 "launch decision; the machine-checkable budget test is "
                 "applied in dimension H."),
    }
    return {
        "overall_status": overall, "dimensions": dims,
        "blockers": blockers, "warnings": warnings,
        "outstanding_requirements": outstanding,
        "declaration_comparison": declaration_comparison,
        "disclaimer": C.READINESS_DISCLAIMER,
    }
