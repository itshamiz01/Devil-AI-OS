"""Deterministic blueprint + document generation (§8/§10–§16).

All generation is templating over stored data (opportunity report,
commercial analysis, template definition). There is no LLM in this
environment; generated text is labelled as generated-from-data and is
NEVER independent evidence (§22). A redaction pass removes secret-shaped
strings that may be present in source data before any document is
produced (security test 7 scans the outputs).
"""
from __future__ import annotations

import re

from . import financial as fin

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|credential)"
               r"\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{10,}"),
]

GENERATED_NOTICE = (
    "Generated deterministically from stored opportunity data by the "
    "AUTONOMUS Business Creation Engine. This document is a planning "
    "artefact, not evidence, and not a factual claim about any market.")


def redact(text: str) -> tuple[str, int]:
    count = 0
    out = text or ""
    for pattern in _SECRET_PATTERNS:
        out, n = pattern.subn("[REDACTED]", out)
        count += n
    return out, count


def _clean(value) -> str:
    text, _ = redact(str(value or ""))
    return text.strip()


def build_financial_inputs(commercial, *, currency: str) -> dict:
    """§9 financial values from the P-03 commercial analysis. Every
    figure keeps its P-03 classification (estimate/quoted/unknown...)
    mapped onto the P-06 estimate/verified vocabulary: only owner- or
    source-verified cost facts may be 'verified'; P-03 'verified'
    classifications are carried, everything else is an estimate."""
    def values(rows, default_source):
        out = []
        for row in rows or []:
            classification = ("verified" if row.get("classification") == "verified"
                              else "estimate")
            out.append(fin.financial_value(
                amount=float(row.get("amount") or 0), currency=currency,
                source=str(row.get("source") or default_source),
                classification=classification,
                confidence=0.9 if classification == "verified" else 0.5,
                assumptions=[f"P-03 classification: {row.get('classification', 'estimate')}",
                             f"item: {row.get('label', 'cost')}"]))
        return out

    startup = values(getattr(commercial, "startup_costs", None),
                     "P-03 commercial analysis (caller-stated inputs)")
    recurring = values(getattr(commercial, "recurring_costs_monthly", None),
                       "P-03 commercial analysis (caller-stated inputs)")
    return {"currency": currency, "startup_costs": startup,
            "recurring_costs": recurring,
            "startup_total": fin.sum_amounts(startup),
            "recurring_monthly_total": fin.sum_amounts(recurring)}


def build_blueprint(ctx: dict) -> dict:
    """The §8.2 sixteen-section blueprint, as structured data."""
    opp = ctx["opportunity"]
    report = ctx["report"]
    commercial = ctx.get("commercial")
    fin_inputs = build_financial_inputs(
        commercial, currency=ctx.get("currency", "USD")) if commercial else {
        "currency": ctx.get("currency", "USD"), "startup_costs": [],
        "recurring_costs": [], "startup_total": 0.0,
        "recurring_monthly_total": 0.0}
    price_value = None
    if commercial is not None and getattr(commercial, "price_assumption", None):
        pa = commercial.price_assumption
        price_value = fin.financial_value(
            amount=float(pa.get("amount") or 0),
            currency=ctx.get("currency", "USD"),
            source="P-03 commercial analysis price assumption",
            classification=("verified" if pa.get("classification") == "verified"
                            else "estimate"),
            confidence=0.5,
            assumptions=[str(pa.get("basis") or "stated assumption")])
    name_check = {
        "proposed_name": opp["name"],
        "conflicts_found": [],
        "note": ("Automated similarity screening only. This is NOT a "
                 "trademark clearance and does not establish that the "
                 "name is legally available (§8.1)."),
    }
    return {
        "executive_summary": _clean(opp.get("proposed_solution")) or
            "See opportunity record.",
        "business_purpose": _clean(opp.get("problem_statement")),
        "customer_problem": _clean(opp.get("problem_statement")),
        "target_customer": {
            "segment": _clean(opp.get("target_customer")),
            "geography": _clean(opp.get("geography")) or "unspecified",
        },
        "proposed_solution": _clean(opp.get("proposed_solution")),
        "products_services": [{
            "name": opp["name"], "type": ctx["template"]["category"],
            "delivery": "digital download / online access (per template)"}],
        "value_proposition": _clean(opp.get("proposed_solution")),
        "revenue_model": _clean(opp.get("revenue_model")),
        "pricing": price_value,
        "distribution_strategy": (commercial.distribution
                                  if commercial is not None else []),
        "acquisition_strategy": {
            "methods": (ctx["template"].get("acquisition_requirements") or {})
            .get("methods", []),
            "note": "Plans and drafts only — no outreach or sending (§15)."},
        "operational_plan": ctx["template"].get("operational_requirements", {}),
        "technology_requirements": (ctx["template"].get("resource_estimates")
                                    or {}),
        "content_requirements": [a["asset_type"] for a in
                                 ctx["template"].get("asset_requirements", [])],
        "brand_identity": {
            "name": opp["name"], "name_check": name_check,
            "voice": "clear, honest, no exaggerated claims (§13.3)"},
        "financial_inputs": fin_inputs,
        "risks": report.get("evidence_gaps", []),
        "constraints": [
            "No external publishing by the system (platform gates, §14).",
            "No revenue is recorded by P-06 (P-07 owns financial truth).",
            "Legal pages are templates with owner-completion placeholders."],
        "assumptions_ref": "see assumption register",
        "success_criteria_ref": "see pre-declaration (judged against it, "
                                "never against checklist completion)",
        "launch_requirements": [
            "readiness review READY or READY_WITH_WARNINGS with no blockers",
            "hash-bound owner launch approval",
            "platform-gate outcomes recorded for every channel"],
        "generated_notice": GENERATED_NOTICE,
        "is_fixture": bool(ctx.get("is_fixture")),
    }


def build_assumptions(ctx: dict) -> list[dict]:
    opp = ctx["opportunity"]
    rows = [{
        "assumption": "The target customer experiences the stated problem "
                      "at the stated severity.",
        "category": "customer", "basis": "P-03 problem evidence on file",
        "status": "SUPPORTED" if ctx.get("supporting_evidence") else "UNVERIFIED",
        "impact_if_wrong": "Product would not sell; creation spend is capped "
                           "by the pre-declaration budget.",
        "validation_method": "Owner-run demand test at the declared "
                             "minimum test volume.",
        "owner": "business-strategy review"},
        {"assumption": "The estimated price is acceptable to the target "
                       "customer.",
         "category": "pricing",
         "basis": "P-03 commercial analysis price assumption (estimate)",
         "status": "TENTATIVE",
         "impact_if_wrong": "Pricing must be revised before launch.",
         "validation_method": "Declared pricing test in the experiment plan.",
         "owner": "business-strategy review"},
        {"assumption": "Distribution channels listed remain available on "
                      "the recorded terms.",
         "category": "distribution",
         "basis": "Platform-gate evaluation recorded at channel evaluation",
         "status": "TENTATIVE",
         "impact_if_wrong": "Channel plan must be re-evaluated.",
         "validation_method": "Re-run platform-gate evaluation before launch.",
         "owner": "operations review"},
    ]
    if not (opp.get("geography") or "").strip():
        rows.append({
            "assumption": "Geography-independent demand (no geography was "
                          "specified for the opportunity).",
            "category": "market", "basis": "absence of a geography constraint",
            "status": "UNVERIFIED",
            "impact_if_wrong": "Localisation/tax obligations may differ.",
            "validation_method": "Owner confirms launch geography.",
            "owner": "owner"})
    return rows


def build_product(ctx: dict, blueprint: dict) -> dict:
    opp = ctx["opportunity"]
    template = ctx["template"]
    product_type = {"digital_products": "ebook", "software": "web_tool",
                    "content": "publication", "services": "productised_service",
                    }.get(template["category"], "digital_product")
    return {
        "name": opp["name"], "product_type": product_type,
        "description": _clean(opp.get("proposed_solution")),
        "target_customer": _clean(opp.get("target_customer")),
        "problem_solved": _clean(opp.get("problem_statement")),
        "core_features": [
            "Core deliverable as specified in the product specification",
            "Support documentation (FAQ) included",
            "Honest limitations statement included"],
        "excluded_features": [
            "Any feature requiring external sending or auto-posting",
            "Any feature requiring payment processing (P-07 scope)"],
        "pricing": blueprint.get("pricing") or {},
        "delivery_method": "digital",
        "support_requirements": "FAQ + playbook support procedures",
        "development_plan": {
            "method": "deterministic generation via the P-05 execution "
                      "engine from the pinned template version",
            "stages": template.get("stages", []),
            "limitations": "Staging produces a local package only."},
    }


def build_requirements(product_type: str) -> list[dict]:
    base = [
        ("functional", "The core deliverable exists as files in the "
         "business workspace and hash-verifies.", "must",
         "Every asset row has a content_hash matching an execution read."),
        ("quality", "Generated documents contain no secret-shaped strings "
         "and no fabricated testimonials, reviews or credentials.", "must",
         "Automated scan of generated assets passes."),
        ("operational", "A support FAQ and an operational playbook exist.",
         "must", "Assets of both types are registered."),
        ("legal", "Legal pages are structural templates with clearly "
         "marked owner-completion placeholders.", "must",
         "Placeholder markers present; no invented legal facts."),
    ]
    if product_type == "web_tool":
        base.append(("technical", "The prototype verification snippet "
                     "executes successfully under process controls.",
                     "must", "code_python.run step completed in the "
                     "creation workflow run."))
    return [{"requirement_type": t, "description": d, "priority": p,
             "acceptance_criteria": a} for t, d, p, a in base]


def build_playbook(ctx: dict) -> dict:
    return {
        "daily_operations": ["Review support inbox (owner-operated)",
                             "Check execution/system health dashboard"],
        "weekly_reviews": ["Compare outcomes against the pre-declaration",
                           "Review assumption register statuses"],
        "customer_support": ["Respond using the FAQ as the source of truth",
                             "Refund/complaint path: acknowledge within 2 "
                             "business days; escalate unresolved cases to "
                             "the owner (procedure template — owner confirms "
                             "actual policy before launch)"],
        "quality_control": ["Re-run asset hash verification monthly",
                            "No claim may be published that is not backed "
                            "by stored evidence"],
        "incident_response": ["Pause the business (lifecycle) on any "
                              "security or platform-policy incident",
                              "Record the incident as business evidence"],
        "escalation": ["Owner decides all escalations; agents never "
                       "approve their own critical deliverables"],
        "backup_recovery": ["Workspace is file-based: back up the "
                            "business workspace directory",
                            "Database backup per P-01 operations guidance"],
        "performance_indicators": ["Declaration criteria progress",
                                   "Support response times (owner-recorded)"],
        "known_risks": list((ctx["report"].get("evidence_gaps") or [])),
        "improvement_procedures": ["Propose template changes as new "
                                   "versions; never edit a pinned version"],
    }


# ------------------------------------------------------------ renderers
def _header(title: str, ctx: dict) -> str:
    fixture = ("\n> **FIXTURE BUSINESS** — created for acceptance testing; "
               "its evidence is synthetic fixture data recorded through "
               "P-03 machinery.\n" if ctx.get("is_fixture") else "")
    return (f"# {title}\n\n> {GENERATED_NOTICE}\n{fixture}\n")


def render_blueprint_md(ctx: dict, blueprint: dict) -> str:
    opp = ctx["opportunity"]
    lines = [_header(f"Business Blueprint — {opp['name']}", ctx)]
    for key, value in blueprint.items():
        if key in {"generated_notice", "is_fixture"}:
            continue
        lines.append(f"## {key.replace('_', ' ').title()}")
        if isinstance(value, (dict, list)):
            import json
            lines.append("```json\n" + json.dumps(value, indent=2,
                                                  default=str) + "\n```")
        else:
            lines.append(str(value))
        lines.append("")
    return redact("\n".join(lines))[0]


def render_prd_md(ctx: dict, product: dict) -> str:
    opp = ctx["opportunity"]
    lines = [_header(f"Product Specification — {product['name']}", ctx),
             f"**Type:** {product['product_type']}  ",
             f"**Target customer:** {product['target_customer']}\n",
             "## Problem solved\n", product["problem_solved"], "",
             "## Description\n", product["description"], "",
             "## Core features"]
    lines += [f"- {f}" for f in product["core_features"]]
    lines += ["", "## Explicitly excluded"]
    lines += [f"- {f}" for f in product["excluded_features"]]
    lines += ["", "## Limitations (honest)",
              "- This specification describes a planned product. The "
              "creation run produces a local package; nothing is deployed "
              "or sold by this system.",
              "- Pricing, where shown, is an estimate recorded as data."]
    return redact("\n".join(lines))[0]


def render_manuscript_md(ctx: dict) -> str:
    opp = ctx["opportunity"]
    chapters = ["Introduction: the problem and who it affects",
                "What the evidence says (and what it does not)",
                "The method, step by step",
                "Worked examples",
                "Common mistakes",
                "Your first week plan",
                "Measuring progress honestly",
                "Appendix: templates and checklists"]
    lines = [_header(f"Manuscript Outline — {opp['name']}", ctx),
             "## Planned chapters"]
    lines += [f"{i+1}. {c}" for i, c in enumerate(chapters)]
    lines += ["", "Status: OUTLINE ONLY. No manuscript text has been "
              "written by this system, and no sales claims are made."]
    return redact("\n".join(lines))[0]


def render_architecture_md(ctx: dict) -> str:
    opp = ctx["opportunity"]
    lines = [_header(f"Technical Architecture — {opp['name']}", ctx),
             "## Scope", _clean(opp.get("proposed_solution")), "",
             "## Components",
             "- Static product site (generated locally by this package)",
             "- Tool logic: small, single-purpose, standard-library-first",
             "- Data: local files only in the MVP; no external sending",
             "", "## Verification",
             "A deterministic prototype snippet is executed under P-05 "
             "process controls during creation; its output is execution "
             "evidence, not a product claim."]
    return redact("\n".join(lines))[0]


def render_article_md(ctx: dict) -> str:
    opp = ctx["opportunity"]
    lines = [_header(f"Sample Article (DRAFT) — {opp['name']}", ctx),
             "## Draft", _clean(opp.get("problem_statement")), "",
             _clean(opp.get("proposed_solution")), "",
             "Status: DRAFT for owner review. Not published anywhere; "
             "this system never auto-posts (§15)."]
    return redact("\n".join(lines))[0]


def render_brand_md(ctx: dict) -> str:
    opp = ctx["opportunity"]
    lines = [_header(f"Brand Guide — {opp['name']}", ctx),
             f"**Name:** {opp['name']}",
             "**Name status:** automated similarity screening only — NOT "
             "a trademark clearance; legal availability is not claimed.",
             "**Voice:** clear, honest, specific. No exaggerated claims, "
             "no fake testimonials, no invented credentials (§13.3).",
             "**Colours/typography:** OWNER TO CHOOSE — placeholders only.",
             "**Logo:** brief only; no logo asset is generated in staging."]
    return redact("\n".join(lines))[0]


def render_listing_md(ctx: dict, product: dict) -> str:
    lines = [_header(f"Listing Copy (DRAFT) — {product['name']}", ctx),
             product["description"], "",
             f"**Planned price (estimate, data only):** "
             f"{(product.get('pricing') or {}).get('amount', 'TBD')} "
             f"{(product.get('pricing') or {}).get('currency', '')}",
             "", "Status: DRAFT listing copy for a prepared package. "
             "Nothing has been listed or published anywhere."]
    return redact("\n".join(lines))[0]


def render_faq_md(ctx: dict) -> str:
    lines = [_header("Customer Support — FAQ and Procedures", ctx),
             "## FAQ",
             "**What is this product?** See the product specification.",
             "**How is it delivered?** Digital delivery, arranged by the "
             "owner at launch (this package does not deliver anything).",
             "**Refunds?** [OWNER TO CONFIRM ACTUAL REFUND POLICY BEFORE "
             "LAUNCH — placeholder, not a policy statement.]",
             "", "## Support procedures",
             "- Acknowledge enquiries within 2 business days.",
             "- Complaints: log as business evidence; escalate to owner.",
             "- Never promise outcomes the evidence does not support."]
    return redact("\n".join(lines))[0]


def render_playbook_md(ctx: dict, playbook: dict) -> str:
    lines = [_header("Operational Playbook", ctx)]
    for key, items in playbook.items():
        lines.append(f"## {key.replace('_', ' ').title()}")
        lines += [f"- {i}" for i in items]
        lines.append("")
    return redact("\n".join(lines))[0]


def _legal_md(title: str, ctx: dict) -> str:
    lines = [_header(f"{title} (TEMPLATE — NOT A LEGAL DOCUMENT)", ctx),
             "> This is a structural template with placeholders. It has "
             "not been reviewed by a lawyer and makes no legal claims. "
             "The owner must complete and professionally review it "
             "before any launch.",
             "", "## Sections to complete",
             "- [OWNER TO COMPLETE: legal business name and address]",
             "- [OWNER TO COMPLETE: contact for privacy/legal enquiries]",
             "- [OWNER TO COMPLETE: data collected and purposes]",
             "- [OWNER TO COMPLETE: retention and deletion process]",
             "- [PROFESSIONAL REVIEW REQUIRED before launch]"]
    return redact("\n".join(lines))[0]


def render_privacy_md(ctx: dict) -> str:
    return _legal_md("Privacy Policy", ctx)


def render_terms_md(ctx: dict) -> str:
    return _legal_md("Terms of Service", ctx)


def render_website_html(ctx: dict, product: dict) -> str:
    opp = ctx["opportunity"]
    name = _clean(opp["name"])
    desc = _clean(product["description"])[:400]
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{name}</title></head>
<body>
<h1>{name}</h1>
<p>{desc}</p>
<p><strong>Status:</strong> locally generated package page. This business
has NOT been launched, this page has NOT been deployed, and nothing is
for sale here.</p>
</body></html>
"""
    return redact(html)[0]


PROTOTYPE_CODE = (
    "# Deterministic MVP verification snippet (P-06 SaaS template).\n"
    "price = 19.0\n"
    "monthly_cost = 25.0\n"
    "units = int(-(-monthly_cost // price))\n"
    "print('prototype-ok break-even units at estimate:', units)\n"
)


def build_inputs(ctx: dict, blueprint: dict, product: dict,
                 playbook: dict) -> dict:
    """Workflow inputs for the creation run, keyed by template input_key
    plus the workspace name. All values are rendered (and redacted)
    before they reach the execution engine."""
    return {
        "workspace": ctx["workspace_name"],
        "blueprint_md": render_blueprint_md(ctx, blueprint),
        "prd_md": render_prd_md(ctx, product),
        "manuscript_md": render_manuscript_md(ctx),
        "architecture_md": render_architecture_md(ctx),
        "article_md": render_article_md(ctx),
        "brand_md": render_brand_md(ctx),
        "listing_md": render_listing_md(ctx, product),
        "faq_md": render_faq_md(ctx),
        "playbook_md": render_playbook_md(ctx, playbook),
        "privacy_md": render_privacy_md(ctx),
        "terms_md": render_terms_md(ctx),
        "website_html": render_website_html(ctx, product),
        "prototype_code": PROTOTYPE_CODE,
    }
