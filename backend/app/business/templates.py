"""Business template registry data + validation (§7).

A template is versioned DATA: steps, input schema, allowed tools,
budget caps, platform gates. A template whose workflow steps cannot be
expressed with registered P-05 tools/actions is rejected at validation —
there is no workaround path (prep-pack decision 1, prompt §33 rule 20).
Businesses pin a template version; a later version never silently
changes an existing business.
"""
from __future__ import annotations

import json
import re

from ..core.exceptions import ValidationError
from . import constants as C

REQUIRED_SECTIONS = {
    "category", "description", "required_information", "required_agents",
    "required_capabilities", "stages", "asset_requirements",
    "distribution_requirements", "acquisition_requirements",
    "operational_requirements", "approval_gates", "resource_estimates",
    "readiness_criteria", "platform_gates", "workflow",
}

_PLACEHOLDER = re.compile(r"^\{\{input\.([a-zA-Z0-9_]+)\}\}$")


def _step(step_id: str, tool: str, action: str, parameters: dict) -> dict:
    return {"id": step_id, "tool": tool, "action": action,
            "parameters": parameters, "on_failure": "stop"}


def _mkdir_steps() -> list[dict]:
    return [_step(f"mkdir_{d}", "filesystem", "mkdir",
                  {"workspace": "{{input.workspace}}", "path": d})
            for d in C.WORKSPACE_SUBDIRS]


def _doc(step_id: str, path: str, input_key: str) -> dict:
    return _step(step_id, "documents", "create_text",
                 {"workspace": "{{input.workspace}}", "path": path,
                  "content": "{{input." + input_key + "}}"})


def _file(step_id: str, path: str, input_key: str) -> dict:
    return _step(step_id, "filesystem", "create",
                 {"workspace": "{{input.workspace}}", "path": path,
                  "content": "{{input." + input_key + "}}"})


EBOOK_TEMPLATE: dict = {
    "category": "digital_products",
    "description": "Digital product business: an ebook sold via prepared "
                   "distribution packages (KDP gate: human publishes).",
    "required_information": ["target_customer", "problem_statement",
                             "proposed_solution", "price_estimate"],
    "required_agents": [
        {"role": "business_strategy_agent", "purpose": "blueprint and model review"},
        {"role": "content_writing_agent", "purpose": "product and asset creation"},
        {"role": "quality_assurance_agent", "purpose": "independent quality review"},
    ],
    "required_capabilities": ["file_read", "file_write"],
    "stages": ["blueprint", "product_spec", "assets", "distribution_prep",
               "readiness"],
    "asset_requirements": [
        {"asset_type": "business_blueprint", "path": "blueprint/blueprint.md", "input_key": "blueprint_md"},
        {"asset_type": "product_specification", "path": "product/product_spec.md", "input_key": "prd_md"},
        {"asset_type": "manuscript_outline", "path": "product/manuscript_outline.md", "input_key": "manuscript_md"},
        {"asset_type": "brand_guide", "path": "brand/brand_guide.md", "input_key": "brand_md"},
        {"asset_type": "product_description", "path": "marketing/listing_copy.md", "input_key": "listing_md"},
        {"asset_type": "support_documentation", "path": "customer_support/faq.md", "input_key": "faq_md"},
        {"asset_type": "operational_playbook", "path": "operations/playbook.md", "input_key": "playbook_md"},
        {"asset_type": "legal_template", "path": "legal/privacy_policy.md", "input_key": "privacy_md"},
        {"asset_type": "legal_template", "path": "legal/terms.md", "input_key": "terms_md"},
        {"asset_type": "website_source", "path": "website/index.html", "input_key": "website_html"},
    ],
    "distribution_requirements": {
        "channels": [
            {"platform_key": "own_website", "channel_type": "direct",
             "purpose": "Primary: direct download from the business website package"},
            {"platform_key": "amazon_kdp", "channel_type": "marketplace",
             "purpose": "Secondary: Kindle edition — owner publishes the prepared package"},
        ]},
    "acquisition_requirements": {
        "methods": ["content drafts", "listing copy drafts"],
        "note": "Drafts only. No outreach, no sending, no auto-posting (§15)."},
    "operational_requirements": {
        "support": "FAQ + support procedures in the playbook",
        "monitoring": "execution metrics + weekly review (playbook)"},
    "approval_gates": ["business.create", "business.blueprint",
                       "business.launch"],
    "resource_estimates": {"creation": "deterministic local generation; "
                                       "no paid services"},
    "readiness_criteria": {"dimensions": ["A", "B", "C", "D", "E", "F", "G", "H"]},
    "platform_gates": ["own_website", "amazon_kdp"],
    "budget_caps": {"max_files": 40, "external_spend": 0},
    "workflow": {"steps": _mkdir_steps() + [
        _doc("write_blueprint", "blueprint/blueprint.md", "blueprint_md"),
        _doc("write_product_spec", "product/product_spec.md", "prd_md"),
        _doc("write_manuscript", "product/manuscript_outline.md", "manuscript_md"),
        _doc("write_brand", "brand/brand_guide.md", "brand_md"),
        _doc("write_listing", "marketing/listing_copy.md", "listing_md"),
        _doc("write_faq", "customer_support/faq.md", "faq_md"),
        _doc("write_playbook", "operations/playbook.md", "playbook_md"),
        _doc("write_privacy", "legal/privacy_policy.md", "privacy_md"),
        _doc("write_terms", "legal/terms.md", "terms_md"),
        _file("write_website", "website/index.html", "website_html"),
    ]},
}

SAAS_TEMPLATE: dict = {
    "category": "software",
    "description": "Micro-SaaS / digital tool: specification-first build "
                   "with a verified prototype execution step.",
    "required_information": ["target_customer", "problem_statement",
                             "proposed_solution", "price_estimate"],
    "required_agents": [
        {"role": "business_strategy_agent", "purpose": "scope and model review"},
        {"role": "content_writing_agent", "purpose": "specification and site copy"},
        {"role": "quality_assurance_agent", "purpose": "independent quality review"},
    ],
    "required_capabilities": ["file_read", "file_write",
                              "sandboxed_code_execution"],
    "stages": ["blueprint", "product_spec", "prototype_verification",
               "assets", "readiness"],
    "asset_requirements": [
        {"asset_type": "business_blueprint", "path": "blueprint/blueprint.md", "input_key": "blueprint_md"},
        {"asset_type": "product_specification", "path": "product/product_spec.md", "input_key": "prd_md"},
        {"asset_type": "technical_architecture", "path": "product/architecture.md", "input_key": "architecture_md"},
        {"asset_type": "brand_guide", "path": "brand/brand_guide.md", "input_key": "brand_md"},
        {"asset_type": "product_description", "path": "marketing/listing_copy.md", "input_key": "listing_md"},
        {"asset_type": "support_documentation", "path": "customer_support/faq.md", "input_key": "faq_md"},
        {"asset_type": "operational_playbook", "path": "operations/playbook.md", "input_key": "playbook_md"},
        {"asset_type": "legal_template", "path": "legal/privacy_policy.md", "input_key": "privacy_md"},
        {"asset_type": "legal_template", "path": "legal/terms.md", "input_key": "terms_md"},
        {"asset_type": "website_source", "path": "website/index.html", "input_key": "website_html"},
    ],
    "distribution_requirements": {
        "channels": [
            {"platform_key": "own_website", "channel_type": "direct",
             "purpose": "Primary: product site package (local only in staging)"},
            {"platform_key": "gumroad", "channel_type": "marketplace",
             "purpose": "Secondary: prepared listing package — human lists it"},
        ]},
    "acquisition_requirements": {
        "methods": ["landing copy drafts"],
        "note": "Drafts only. No outreach, no sending, no auto-posting (§15)."},
    "operational_requirements": {
        "support": "FAQ + support procedures in the playbook",
        "monitoring": "execution metrics + weekly review (playbook)"},
    "approval_gates": ["business.create", "business.blueprint",
                       "business.launch"],
    "resource_estimates": {"creation": "deterministic local generation; "
                                       "prototype runs under process controls"},
    "readiness_criteria": {"dimensions": ["A", "B", "C", "D", "E", "F", "G", "H"]},
    "platform_gates": ["own_website", "gumroad"],
    "budget_caps": {"max_files": 40, "external_spend": 0},
    "workflow": {"steps": _mkdir_steps() + [
        _doc("write_blueprint", "blueprint/blueprint.md", "blueprint_md"),
        _doc("write_product_spec", "product/product_spec.md", "prd_md"),
        _doc("write_architecture", "product/architecture.md", "architecture_md"),
        _step("verify_prototype", "code_python", "run",
              {"code": "{{input.prototype_code}}"}),
        _doc("write_brand", "brand/brand_guide.md", "brand_md"),
        _doc("write_listing", "marketing/listing_copy.md", "listing_md"),
        _doc("write_faq", "customer_support/faq.md", "faq_md"),
        _doc("write_playbook", "operations/playbook.md", "playbook_md"),
        _doc("write_privacy", "legal/privacy_policy.md", "privacy_md"),
        _doc("write_terms", "legal/terms.md", "terms_md"),
        _file("write_website", "website/index.html", "website_html"),
    ]},
}

CONTENT_TEMPLATE: dict = {
    "category": "content",
    "description": "Content / publication business: editorial system, "
                   "brand, sample content — publishing stays human-gated.",
    "required_information": ["target_customer", "problem_statement",
                             "proposed_solution"],
    "required_agents": [
        {"role": "business_strategy_agent", "purpose": "publication strategy review"},
        {"role": "content_writing_agent", "purpose": "editorial assets"},
        {"role": "quality_assurance_agent", "purpose": "independent quality review"},
    ],
    "required_capabilities": ["file_read", "file_write"],
    "stages": ["blueprint", "editorial_plan", "assets", "readiness"],
    "asset_requirements": [
        {"asset_type": "business_blueprint", "path": "blueprint/blueprint.md", "input_key": "blueprint_md"},
        {"asset_type": "product_specification", "path": "product/editorial_plan.md", "input_key": "prd_md"},
        {"asset_type": "sample_content", "path": "product/sample_article.md", "input_key": "article_md"},
        {"asset_type": "brand_guide", "path": "brand/brand_guide.md", "input_key": "brand_md"},
        {"asset_type": "product_description", "path": "marketing/listing_copy.md", "input_key": "listing_md"},
        {"asset_type": "support_documentation", "path": "customer_support/faq.md", "input_key": "faq_md"},
        {"asset_type": "operational_playbook", "path": "operations/playbook.md", "input_key": "playbook_md"},
        {"asset_type": "legal_template", "path": "legal/privacy_policy.md", "input_key": "privacy_md"},
        {"asset_type": "legal_template", "path": "legal/terms.md", "input_key": "terms_md"},
        {"asset_type": "website_source", "path": "website/index.html", "input_key": "website_html"},
    ],
    "distribution_requirements": {
        "channels": [
            {"platform_key": "own_website", "channel_type": "direct",
             "purpose": "Primary: publication site package (local only)"},
            {"platform_key": "substack", "channel_type": "platform",
             "purpose": "Secondary: prepared package — human publishes; "
                        "no auto-posting exists"},
        ]},
    "acquisition_requirements": {
        "methods": ["content drafts"],
        "note": "Drafts only. No outreach, no sending, no auto-posting (§15)."},
    "operational_requirements": {
        "support": "Reader support procedures in the playbook",
        "monitoring": "editorial calendar review (playbook)"},
    "approval_gates": ["business.create", "business.blueprint",
                       "business.launch"],
    "resource_estimates": {"creation": "deterministic local generation"},
    "readiness_criteria": {"dimensions": ["A", "B", "C", "D", "E", "F", "G", "H"]},
    "platform_gates": ["own_website", "substack"],
    "budget_caps": {"max_files": 40, "external_spend": 0},
    "workflow": {"steps": _mkdir_steps() + [
        _doc("write_blueprint", "blueprint/blueprint.md", "blueprint_md"),
        _doc("write_editorial_plan", "product/editorial_plan.md", "prd_md"),
        _doc("write_sample_article", "product/sample_article.md", "article_md"),
        _doc("write_brand", "brand/brand_guide.md", "brand_md"),
        _doc("write_listing", "marketing/listing_copy.md", "listing_md"),
        _doc("write_faq", "customer_support/faq.md", "faq_md"),
        _doc("write_playbook", "operations/playbook.md", "playbook_md"),
        _doc("write_privacy", "legal/privacy_policy.md", "privacy_md"),
        _doc("write_terms", "legal/terms.md", "terms_md"),
        _file("write_website", "website/index.html", "website_html"),
    ]},
}

SERVICE_TEMPLATE: dict = {
    "category": "services",
    "description": "Productised service: offer specification and delivery "
                   "playbook. Registered and validated; NOT exercised "
                   "end-to-end in staging (prepared-only).",
    "required_information": ["target_customer", "problem_statement",
                             "proposed_solution", "price_estimate"],
    "required_agents": [
        {"role": "business_strategy_agent", "purpose": "offer design review"},
        {"role": "content_writing_agent", "purpose": "offer assets"},
        {"role": "quality_assurance_agent", "purpose": "independent quality review"},
    ],
    "required_capabilities": ["file_read", "file_write"],
    "stages": ["blueprint", "offer_spec", "assets", "readiness"],
    "asset_requirements": [
        {"asset_type": "business_blueprint", "path": "blueprint/blueprint.md", "input_key": "blueprint_md"},
        {"asset_type": "product_specification", "path": "product/offer_spec.md", "input_key": "prd_md"},
        {"asset_type": "brand_guide", "path": "brand/brand_guide.md", "input_key": "brand_md"},
        {"asset_type": "product_description", "path": "marketing/listing_copy.md", "input_key": "listing_md"},
        {"asset_type": "support_documentation", "path": "customer_support/faq.md", "input_key": "faq_md"},
        {"asset_type": "operational_playbook", "path": "operations/playbook.md", "input_key": "playbook_md"},
        {"asset_type": "legal_template", "path": "legal/privacy_policy.md", "input_key": "privacy_md"},
        {"asset_type": "legal_template", "path": "legal/terms.md", "input_key": "terms_md"},
        {"asset_type": "website_source", "path": "website/index.html", "input_key": "website_html"},
    ],
    "distribution_requirements": {
        "channels": [
            {"platform_key": "own_website", "channel_type": "direct",
             "purpose": "Primary: offer page package (local only)"},
        ]},
    "acquisition_requirements": {
        "methods": ["offer copy drafts"],
        "note": "Drafts only. No outreach, no sending, no auto-posting (§15)."},
    "operational_requirements": {
        "support": "Client support procedures in the playbook",
        "monitoring": "delivery review (playbook)"},
    "approval_gates": ["business.create", "business.blueprint",
                       "business.launch"],
    "resource_estimates": {"creation": "deterministic local generation"},
    "readiness_criteria": {"dimensions": ["A", "B", "C", "D", "E", "F", "G", "H"]},
    "platform_gates": ["own_website"],
    "budget_caps": {"max_files": 40, "external_spend": 0},
    "workflow": {"steps": _mkdir_steps() + [
        _doc("write_blueprint", "blueprint/blueprint.md", "blueprint_md"),
        _doc("write_offer_spec", "product/offer_spec.md", "prd_md"),
        _doc("write_brand", "brand/brand_guide.md", "brand_md"),
        _doc("write_listing", "marketing/listing_copy.md", "listing_md"),
        _doc("write_faq", "customer_support/faq.md", "faq_md"),
        _doc("write_playbook", "operations/playbook.md", "playbook_md"),
        _doc("write_privacy", "legal/privacy_policy.md", "privacy_md"),
        _doc("write_terms", "legal/terms.md", "terms_md"),
        _file("write_website", "website/index.html", "website_html"),
    ]},
}

SEED_TEMPLATES: list[tuple[str, dict]] = [
    ("ebook_digital_product", EBOOK_TEMPLATE),
    ("saas_micro_tool", SAAS_TEMPLATE),
    ("content_publication", CONTENT_TEMPLATE),
    ("productized_service", SERVICE_TEMPLATE),
]

# Which templates have been exercised end-to-end (honesty labelling).
EXERCISED_TEMPLATES = {"ebook_digital_product", "saas_micro_tool",
                       "content_publication"}


def _scan_forbidden(node, path: str, errors: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in C.FORBIDDEN_STEP_KEYS:
                errors.append(
                    f"{path}: forbidden key {key!r} — money movement and "
                    "external sending are out of scope for P-06 (§9/§15)")
            _scan_forbidden(value, f"{path}.{key}", errors)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _scan_forbidden(value, f"{path}[{i}]", errors)
    elif isinstance(node, str):
        lowered = node.lower()
        for marker in ("external_communication", "os.system", "subprocess",
                       "__import__"):
            if marker in lowered:
                errors.append(f"{path}: forbidden construct {marker!r}")


def validate_template_definition(definition: dict, registry) -> list[str]:
    """Validate a template definition against the live P-05 tool
    registry. Returns a list of errors (empty = valid). ``registry`` is a
    ToolRegistry (anything with get_tool/action_spec)."""
    errors: list[str] = []
    if not isinstance(definition, dict):
        return ["template definition must be an object"]
    missing = REQUIRED_SECTIONS - set(definition)
    if missing:
        errors.append(f"missing required sections: {sorted(missing)}")
    caps = definition.get("required_capabilities") or []
    if "external_communication" in caps:
        errors.append("external_communication is ungrantable and may not "
                      "be required by a template (§15)")
    workflow = definition.get("workflow") or {}
    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("workflow.steps must be a non-empty list")
        steps = []
    if len(steps) > 50:
        errors.append("workflow exceeds the WorkflowEngine 50-step limit")
    seen_ids: set[str] = set()
    input_keys: set[str] = set()
    for i, step in enumerate(steps):
        where = f"workflow.steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{where}: step must be an object")
            continue
        sid = step.get("id")
        if not sid or sid in seen_ids:
            errors.append(f"{where}: step id missing or duplicated")
        seen_ids.add(str(sid))
        tool_name, action = step.get("tool"), step.get("action")
        if tool_name in C.FORBIDDEN_TEMPLATE_TOOLS:
            errors.append(f"{where}: tool {tool_name!r} is disabled and "
                          "may not appear in a template")
            continue
        if (tool_name, action) in C.FORBIDDEN_TEMPLATE_ACTIONS:
            errors.append(f"{where}: {tool_name}.{action} is unavailable "
                          "interactively and may not appear in a template")
            continue
        tool = registry.get_tool(str(tool_name)) if tool_name else None
        if tool is None:
            errors.append(f"{where}: unknown tool {tool_name!r}")
            continue
        if getattr(tool, "status", None) == "disabled":
            errors.append(f"{where}: tool {tool_name!r} is disabled in "
                          "this environment")
            continue
        if registry.action_spec(tool, str(action)) is None:
            errors.append(f"{where}: tool {tool_name!r} has no action {action!r}")
        _scan_forbidden(step.get("parameters") or {}, f"{where}.parameters",
                        errors)
        for value in (step.get("parameters") or {}).values():
            if isinstance(value, str):
                m = _PLACEHOLDER.match(value)
                if m:
                    input_keys.add(m.group(1))
    # Asset requirements must correspond to workflow inputs.
    for req in definition.get("asset_requirements") or []:
        key = req.get("input_key")
        if key and key not in input_keys:
            errors.append(
                f"asset_requirements: input_key {key!r} is not produced "
                "by any workflow step")
    blob = json.dumps(definition, default=str)
    if "collected_revenue" in blob or "verified_revenue" in blob:
        errors.append("template may not reference collected/verified "
                      "revenue (§9 — P-07 owns financial truth)")
    return errors
