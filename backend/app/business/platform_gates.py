"""Platform gates (§14): design, not an afterthought.

Every external publish/listing step passes a gate check first: can an
agent sign in at all? What are the platform's AI-content rules? Is the
action reversible? The gate outcome is recorded as business evidence and
channel data. In staging **no gate ever returns "publish now"**: the
best outcome is a prepared package; KDP — where Amazon blocks AI-agent
sign-in (verified 2026-11-08 against the real KDP) — can only ever
return REQUIRES_HUMAN_ACTION.
"""
from __future__ import annotations

# Gate outcome vocabulary.
GATE_PASS_PREPARED_ONLY = "PASS_PREPARED_ONLY"
GATE_REQUIRES_HUMAN = "REQUIRES_HUMAN_ACTION"
GATE_BLOCKED = "BLOCKED"

PLATFORM_GATES: dict[str, dict] = {
    "amazon_kdp": {
        "platform": "Amazon KDP",
        "agent_signin_possible": False,
        "agent_signin_note": (
            "Verified 2026-11-08: Amazon returns 'Access restricted' to "
            "AI-agent sign-in on kdp.amazon.com (Conditions of Use). The "
            "owner publishes personally in their own browser."),
        "ai_content_rules": (
            "AI-generated content must be disclosed at upload; the "
            "prepared package includes the disclosure note."),
        "reversible": True,
        "outcome": GATE_REQUIRES_HUMAN,
        "publish_step_result": "prepared_package_only",
    },
    "gumroad": {
        "platform": "Gumroad",
        "agent_signin_possible": False,
        "agent_signin_note": (
            "No verified agent sign-in path exists in staging (browser "
            "interactive actions are ADAPTER_UNAVAILABLE; no API "
            "credentials are configured). Listing is prepared locally."),
        "ai_content_rules": "Seller is responsible for content rights; "
                            "original-work assets only.",
        "reversible": True,
        "outcome": GATE_REQUIRES_HUMAN,
        "publish_step_result": "prepared_package_only",
    },
    "own_website": {
        "platform": "Own website / direct download",
        "agent_signin_possible": True,
        "agent_signin_note": (
            "No third-party account is involved. Staging has no "
            "deployment adapter, so the site package is generated and "
            "verified locally only — never deployed by P-06."),
        "ai_content_rules": "Owner's own disclosures apply.",
        "reversible": True,
        "outcome": GATE_PASS_PREPARED_ONLY,
        "publish_step_result": "local_package_prepared",
    },
    "youtube": {
        "platform": "YouTube",
        "agent_signin_possible": False,
        "agent_signin_note": (
            "Upload requires the owner's channel credentials and Google "
            "OAuth (ClipOS pilot finding); no agent upload path exists."),
        "ai_content_rules": "Altered/synthetic content disclosure applies.",
        "reversible": True,
        "outcome": GATE_REQUIRES_HUMAN,
        "publish_step_result": "prepared_package_only",
    },
    "substack": {
        "platform": "Substack",
        "agent_signin_possible": False,
        "agent_signin_note": "No verified agent sign-in path in staging.",
        "ai_content_rules": "Publisher is responsible for content.",
        "reversible": True,
        "outcome": GATE_REQUIRES_HUMAN,
        "publish_step_result": "prepared_package_only",
    },
}


def evaluate_gate(platform_key: str) -> dict:
    """Deterministic gate evaluation for one platform key."""
    spec = PLATFORM_GATES.get(platform_key)
    if spec is None:
        return {
            "platform_key": platform_key, "platform": platform_key,
            "outcome": GATE_BLOCKED,
            "agent_signin_possible": False,
            "agent_signin_note": "Unknown platform: no gate evaluation "
                                 "exists, so the gate fails closed.",
            "ai_content_rules": "unknown", "reversible": False,
            "publish_step_result": "refused",
        }
    return {"platform_key": platform_key, **spec}
