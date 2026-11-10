"""P-09 constants: layers, categories, truth classes, statuses,
confidence ladder, access scopes, scoring weights and defaults.

House discipline: every value the engine decides with is named here
or in owner-governed ``memory.settings`` — nothing is a magic number
buried in a service.
"""
from __future__ import annotations

SETTINGS_KEY = "memory.settings"

LAYERS = ("working", "episodic", "semantic", "procedural",
          "preference", "organizational")

# §6.1 categories
CATEGORIES = (
    "OWNER_INSTRUCTION", "USER_PREFERENCE", "PROJECT_CONTEXT",
    "BUSINESS_CONTEXT", "TECHNICAL_KNOWLEDGE", "BUSINESS_KNOWLEDGE",
    "CUSTOMER_INSIGHT", "MARKET_EVIDENCE", "FINANCIAL_INSIGHT",
    "DECISION_HISTORY", "EXPERIMENT_OUTCOME", "TASK_HISTORY",
    "AGENT_EXPERIENCE", "PROCEDURE", "SYSTEM_CONFIGURATION",
    "LESSON_LEARNED", "SECURITY_EVENT", "COMPLIANCE_RECORD",
)

# §3.1 truth classes — a stored statement is not automatically true.
TRUTH_CLASSES = (
    "verified_fact", "corroborated", "user_provided",
    "agent_conclusion", "assumption", "hypothesis", "prediction",
    "historical_observation",
)

# §6.3 lifecycle statuses
STATUSES = ("ACTIVE", "UNVERIFIED", "NEEDS_REVIEW", "CONTRADICTED",
            "OUTDATED", "SUPERSEDED", "ARCHIVED", "DELETED")

# §14.4 access scopes, most restrictive first
ACCESS_SCOPES = ("OWNER_ONLY", "PRIVATE_AGENT", "TASK_ONLY",
                 "PROJECT_SHARED", "BUSINESS_SHARED", "ORGANIZATION_SHARED")

SENSITIVITIES = ("normal", "internal", "restricted")
RETENTION_POLICIES = ("standard", "permanent", "time_sensitive", "working")

# §11.4 learning confidence ladder → basis points
CONFIDENCE_BPS = {"VERY_LOW": 1000, "LOW": 3000, "MODERATE": 5500,
                  "HIGH": 8000, "VERIFIED": 10000}
CONFIDENCE_ORDER = ["VERY_LOW", "LOW", "MODERATE", "HIGH", "VERIFIED"]

# A learning record may be VERIFIED only with at least this many
# independent observations AND an owner review (§11.4). One
# observation — or an LLM's say-so — never suffices.
VERIFIED_MIN_OBSERVATIONS = 3

# §9.3 hybrid retrieval weights (defaults; owner-governed via settings)
DEFAULT_WEIGHTS = {
    "task_relevance": 0.25, "semantic_similarity": 0.20,
    "evidence_confidence": 0.15, "source_reliability": 0.10,
    "importance": 0.10, "recency": 0.10, "relationship_relevance": 0.10,
}

# Source reliability for scoring: owner statements and verified
# system records outrank agent conclusions and external documents.
SOURCE_RELIABILITY_BPS = {
    "owner_instruction": 10000, "owner_correction": 10000,
    "system_record": 9000, "user_input": 8500, "task_result": 7500,
    "experiment_outcome": 7500, "decision_record": 7500,
    "financial_reference": 7000, "document": 5000,
    "agent_output": 4000, "conversation": 4000, "external_document": 2500,
}

DEFAULT_SETTINGS = {
    # Working memory (§5.1) is short-lived by default and is never
    # promoted to permanent knowledge automatically.
    "working_ttl_hours": 24,
    # Records without fresh evidence older than this are flagged for
    # revalidation when their category is time-sensitive (§13.4).
    "market_freshness_days": 90,
    "procedure_revalidation_days": 180,
    # §10.3 context budget: maximum memories per assembled package.
    "context_max_items": 12,
    "retrieval_default_limit": 10,
    # The local SQLite vector adapter is enabled by default; if it is
    # disabled or fails, retrieval degrades to keyword/exact and says
    # so (Scenario 11) rather than failing.
    "vector_enabled": True,
    "embedding_model": "local-hash-v1",
}

# Capability flip (§P-04 reconciliation): P-09 genuinely backs the
# P-04 catalogue's memory_write entry, exactly as P-05 flipped the
# capabilities it backs. The catalogue constant itself is NOT edited;
# the flip happens at P-09 seed time and is reported.
P09_SUPPORTED_CAPABILITIES = {
    "memory_write": (
        "Persistent memory writes through the P-09 memory engine: "
        "classified, provenance-carrying, access-scoped records via "
        "the governed ingestion pipeline. Owner instructions and "
        "governance can never be written through memory (Article 0)."),
}

# Governance-bearing categories an agent may never originate: owner
# instructions belong to the owner; system configuration records in
# memory are data about configuration, never configuration itself.
AGENT_FORBIDDEN_CATEGORIES = ("OWNER_INSTRUCTION",)
AGENT_FORBIDDEN_SCOPES = ("OWNER_ONLY",)
# Truth classes an agent may not assert on its own output.
AGENT_FORBIDDEN_TRUTH_CLASSES = ("verified_fact",)
