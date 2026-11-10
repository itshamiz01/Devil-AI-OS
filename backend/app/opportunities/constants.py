"""Controlled vocabularies for P-03 (prompt §6–§16).

These are vocabularies and deterministic rule tables — not facts about any
market. Candidate "startup class" figures in seed_data are internal rough
classes used ONLY for budget screening and are always labelled estimates.
"""
from __future__ import annotations

# §6 business categories. complexity is the engine's own operational
# complexity prior (1=simple .. 5=complex), used by the simplicity score.
CATEGORIES: dict[str, dict] = {
    "digital_products": {
        "label": "Digital products", "complexity": 2, "physical": False,
        "examples": ["e-books", "templates", "digital planners", "design assets", "spreadsheet tools"],
    },
    "software_services": {
        "label": "Software and technology services", "complexity": 4, "physical": False,
        "examples": ["micro-SaaS", "productivity tools", "workflow automation", "dashboards"],
    },
    "content": {
        "label": "Content businesses", "complexity": 3, "physical": False,
        "examples": ["newsletters", "specialized blogs", "research publications", "niche content libraries"],
    },
    "freelance_services": {
        "label": "Freelance and productized services", "complexity": 2, "physical": False,
        "examples": ["website development", "data analysis", "content production", "technical documentation"],
    },
    "online_education": {
        "label": "Online education", "complexity": 3, "physical": False,
        "examples": ["skill courses", "downloadable learning resources", "paid communities"],
    },
    "ecommerce_digital": {
        "label": "E-commerce and digital distribution", "complexity": 3, "physical": False,
        "examples": ["print-on-demand", "digital asset marketplaces", "licensed digital products"],
    },
    "b2b_services": {
        "label": "Business-to-business opportunities", "complexity": 4, "physical": False,
        "examples": ["industry automation", "data reporting services", "workflow tools"],
    },
}

DISCOVERY_METHODS = [
    "problem_driven", "demand_driven", "competitor_gap", "trend",
    "capability_fit", "budget_driven", "manual",
]

# §9.1 evidence categories
EVIDENCE_CATEGORIES = [
    "demand", "problem", "purchasing_intent", "competitor", "pricing",
    "market_size", "cost", "distribution", "operational", "legal", "platform_policy",
]

# §9.2 evidence classifications (best -> worst trust)
EVIDENCE_CLASSIFICATIONS = [
    "VERIFIED", "CORROBORATED", "SUPPORTING", "TENTATIVE",
    "UNVERIFIED", "CONTRADICTED", "OUTDATED",
]

# Relative strength used by the evidence-quality computation (§16.3).
CLASSIFICATION_STRENGTH = {
    "VERIFIED": 1.0, "CORROBORATED": 0.8, "SUPPORTING": 0.55,
    "TENTATIVE": 0.3, "UNVERIFIED": 0.1, "CONTRADICTED": 0.0, "OUTDATED": 0.0,
}

# §8.3 source reliability classes
SOURCE_RELIABILITY = [
    "primary_official", "government_regulatory", "direct_marketplace",
    "industry_publication", "public_customer_feedback", "community_discussion",
    "secondary_analysis", "owner_provided", "unverified_claim",
]

# §12 revenue models
REVENUE_MODELS = [
    "one_time_sales", "subscription", "usage_based", "service_fees",
    "project_contracts", "licensing", "memberships", "advertising",
    "affiliate_disclosed", "marketplace_sales", "freemium",
]

# §13.1 cost figure classifications
COST_CLASSIFICATIONS = ["verified", "quoted", "historical", "estimate", "unknown"]

# Capabilities the current AUTONOMUS build can truthfully claim (§7.5):
# research + content (ClipOS/KDP assets), software (the owner's stack).
SYSTEM_CAPABILITIES = [
    "research", "content_production", "software_development",
    "data_analysis", "design", "automation", "customer_support",
]

# The exact phrase the system must use instead of inventing data (§19).
INSUFFICIENT_EVIDENCE = "Insufficient verified evidence"

# Core evidence categories a well-researched opportunity is expected to
# have at least some coverage of (used by evidence-quality coverage).
CORE_EVIDENCE_CATEGORIES = ["demand", "problem", "pricing", "cost", "distribution", "competitor"]
