"""P-10 security vocabulary: settings, modes, risk levels,
classification levels and the seeded threat register.

Settings live in ``system_config`` under ``security.settings`` and
are writable ONLY through the versioned, owner-only policy path on
the facade (Article 0). Mandatory protections (deny-by-default,
approval binding, secret non-storage) are code, not settings — no
setting below can switch them off, and rollback cannot either
(§23.4).
"""
from __future__ import annotations

SETTINGS_KEY = "security.settings"

# ------------------------------------------------------------- modes (§20)
MODE_NORMAL = "normal"
MODE_SAFE = "safe_mode"
MODE_EMERGENCY = "emergency_stop"
MODES = {MODE_NORMAL, MODE_SAFE, MODE_EMERGENCY}

# ------------------------------------------------- risk levels (§8.1)
RISK_READ_ONLY = 0        # read-only within scope: automatic
RISK_REVERSIBLE = 1       # reversible low-risk: automatic within grants
RISK_SIGNIFICANT = 2      # significant/external: capability or approval
RISK_CRITICAL = 3         # critical/irreversible: owner-decided approval

# Action → risk classification (§8.1). Anything not listed here is
# UNKNOWN and classifies at RISK_CRITICAL (fail closed, §2 rule 14):
# an unclassified action never slips through as low-risk.
ACTION_RISK: dict[str, int] = {
    # Level 0 — read-only
    "read": RISK_READ_ONLY,
    "research.read": RISK_READ_ONLY,
    "filesystem.read": RISK_READ_ONLY,
    "filesystem.list": RISK_READ_ONLY,
    "business.read": RISK_READ_ONLY,
    "financial.view": RISK_READ_ONLY,
    "memory.retrieve": RISK_READ_ONLY,
    "browser.read": RISK_READ_ONLY,
    "network.fetch": RISK_READ_ONLY,
    # Level 1 — reversible, local
    "draft.create": RISK_REVERSIBLE,
    "report.generate": RISK_REVERSIBLE,
    "filesystem.write": RISK_REVERSIBLE,
    "task.update_status": RISK_REVERSIBLE,
    # Level 2 — significant / externally visible
    "content.publish": RISK_SIGNIFICANT,
    "message.send_external": RISK_SIGNIFICANT,
    "filesystem.delete": RISK_SIGNIFICANT,
    "command.execute": RISK_SIGNIFICANT,
    "software.install": RISK_SIGNIFICANT,
    "browser.publish": RISK_SIGNIFICANT,
    "browser.purchase": RISK_SIGNIFICANT,
    "account.modify_external": RISK_SIGNIFICANT,
    # Level 3 — critical / irreversible
    "financial.transfer": RISK_CRITICAL,
    "financial.approve": RISK_CRITICAL,
    "security.policy_change": RISK_CRITICAL,
    "security.disable_control": RISK_CRITICAL,
    "secret.access": RISK_CRITICAL,
    "secret.reveal": RISK_CRITICAL,
    "data.delete_permanent": RISK_CRITICAL,
    "wallet.modify": RISK_CRITICAL,
}

# Permissions that are owner authority itself. They can never be
# delegated through the capability system to an agent (§7.3/§15.3:
# an agent must never delegate — or receive by delegation —
# owner-only privileges), and a non-owner can never issue them.
OWNER_ONLY_PERMISSIONS = {
    "approve_actions",
    "modify_system_config",
    "access_sensitive_data",
}

# ------------------------------------------- data classification (§4.2)
CLASSIFICATION_LEVELS = {
    1: "public",
    2: "internal",
    3: "confidential",
    4: "restricted",
    5: "critical",
}

# Logical protected roots (§10.3). A filesystem-guard target whose
# first path segment names one of these roots is a protected
# location: owner-only unless a classification record says otherwise.
# These are logical policy roots (the guard evaluates workspace-
# relative paths), not host paths — staging never touches the real
# host filesystem through them.
DEFAULT_PROTECTED_ROOTS = [
    "security-config", "credentials", "browser-profiles",
    "backups", "keys", "vault",
]

DEFAULT_SETTINGS: dict = {
    # Current security mode (§20). Changed only via the emergency
    # service (owner-only, versioned, event-recorded).
    "mode": MODE_NORMAL,
    # Financial emergency suspension (§16.6), independent of mode.
    "financial_suspension": False,
    # Capability tokens (§7.2).
    "capability_default_ttl_minutes": 60,
    "capability_max_ttl_minutes": 1440,
    # Login throttling (§5.2).
    "login_max_failures": 10,
    "login_window_minutes": 15,
    # Alerting (§19.5): denied checks per actor inside the window.
    "alert_denial_threshold": 5,
    "alert_window_minutes": 60,
    # Command guard (§11): executable basenames an execution agent
    # may run through the guard. Everything else is denied or (for
    # denylisted patterns) blocked outright.
    "command_allowlist": [
        "python", "python3", "git", "ls", "dir", "echo", "cat",
        "type", "pytest",
    ],
    # Filesystem guard (§10.3).
    "protected_roots": list(DEFAULT_PROTECTED_ROOTS),
    # Egress (§13.1): empty allowlist = no allowlist restriction
    # (SSRF range checks still always apply); denylist always wins.
    "egress_allowlist": [],
    "egress_denylist": [],
    "allow_http_egress": False,
    # Downloads (§12.5).
    "max_download_bytes": 50 * 1024 * 1024,
}

# Extensions that are executable content: downloads carrying them
# are refused by default (§12.5 — reject unexpected executables).
EXECUTABLE_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".ps1", ".sh", ".com", ".scr",
    ".dll", ".jar", ".vbs", ".js", ".wsf",
}

# ------------------------------------------------- threat register (§4.3)
# Seeded verbatim into security_threat_register at startup when
# empty. verification_test names the P-10 test that proves the
# control; statuses are the honest staging state.
THREAT_REGISTER_SEED: list[dict] = [
    {"code": "T-01", "title": "Agent reads protected credential file",
     "description": "A research or execution agent attempts to read files in a protected root (credentials, keys, vault).",
     "entry_point": "Filesystem guard / broker authorization",
     "affected_assets": ["Owner credentials", "API keys", "Encryption keys"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "Protected-root policy in the filesystem guard; broker denies non-owner access; secrets stored only as broker references.",
     "detection_controls": "Denied guard evaluations are audit events; repeated denials raise alerts.",
     "recovery_procedure": "Rotate the affected credential via the secret registry lifecycle; review the agent's restrictions.",
     "verification_test": "test_scenario_01_unauthorized_file_access",
     "status": "mitigated"},
    {"code": "T-02", "title": "Cross-business data leakage",
     "description": "An agent scoped to one business reads another business's confidential records.",
     "entry_point": "Broker authorization with business_ref",
     "affected_assets": ["Business information", "Customer data"],
     "likelihood": "medium", "impact": "high", "risk_level": "high",
     "preventive_controls": "Broker business-scope gate resolves the agent's registered business_ref (P-01) and denies mismatches regardless of model reasoning.",
     "detection_controls": "Broker decision ledger + audit events for every denial.",
     "recovery_procedure": "Restrict the agent (security_agent_restrictions); audit its prior accesses.",
     "verification_test": "test_scenario_02_cross_business_data_leakage",
     "status": "mitigated"},
    {"code": "T-03", "title": "Prompt injection from web content",
     "description": "A website instructs an agent to reveal credentials or ignore security policy.",
     "entry_point": "Browser/research content ingestion",
     "affected_assets": ["System policies", "Owner credentials"],
     "likelihood": "high", "impact": "high", "risk_level": "high",
     "preventive_controls": "Content-trust hierarchy: external content is data, never instructions; deterministic injection screening; no code path from content to policy.",
     "detection_controls": "Screening findings recorded as security events (pattern names only).",
     "recovery_procedure": "None required when controls hold; incident record if an agent acted on injected content.",
     "verification_test": "test_scenario_03_prompt_injection",
     "status": "mitigated"},
    {"code": "T-04", "title": "Fake owner approval",
     "description": "An agent claims the owner approved a payment; no approval record exists.",
     "entry_point": "Financial guard",
     "affected_assets": ["Financial records", "Wallets"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "Financial guard accepts only a real P-01 approval record verified by hash binding; claims in content are not approvals.",
     "detection_controls": "Denied guard evaluations audited with reason 'no valid approval record'.",
     "recovery_procedure": "No funds move; review the requesting agent.",
     "verification_test": "test_scenario_04_fake_approval",
     "status": "mitigated"},
    {"code": "T-05", "title": "Approved transaction parameters modified",
     "description": "Amount or recipient is changed after the owner approved a transaction.",
     "entry_point": "Financial guard execution-time verification",
     "affected_assets": ["Financial records"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "SHA-256 approval binding over exact parameters; drift invalidates the approval and requires a new one.",
     "detection_controls": "Binding failures audited (financial guard + P-07 spend drift precedent).",
     "recovery_procedure": "Request a fresh approval for the changed parameters.",
     "verification_test": "test_scenario_05_modified_approval",
     "status": "mitigated"},
    {"code": "T-06", "title": "Agent privilege escalation via agent creation",
     "description": "An agent creates another agent and tries to give it owner privileges.",
     "entry_point": "Capability issuance / delegation",
     "affected_assets": ["System policies", "Agent instructions"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "Owner-only permissions can never be issued as capabilities to agents; non-owners cannot issue beyond their own grants nor to themselves; P-04 creation remains gated.",
     "detection_controls": "Refused issuance is audited; escalation attempts raise alerts.",
     "recovery_procedure": "Restrict or suspend the escalating agent.",
     "verification_test": "test_scenario_06_agent_privilege_escalation",
     "status": "mitigated"},
    {"code": "T-07", "title": "Destructive command execution",
     "description": "An execution agent attempts an unauthorized destructive shell command.",
     "entry_point": "Command guard",
     "affected_assets": ["Local files", "Operating system"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "Deterministic command guard: allowlisted executables, denylisted destructive patterns, structured argv only, workspace-contained working directories. The guard evaluates; execution stays in P-05 under its own policy.",
     "detection_controls": "Blocked commands audited with the matched pattern name.",
     "recovery_procedure": "Quarantine-based deletion in P-05 limits loss; restore from verified backup.",
     "verification_test": "test_scenario_07_dangerous_command",
     "status": "mitigated"},
    {"code": "T-08", "title": "Secret leakage into prompts, reports or logs",
     "description": "An agent includes an API key in a prompt, report or output.",
     "entry_point": "Outbound content screening",
     "affected_assets": ["API keys", "Credentials"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "Agents hold references, never values (P-05 broker); outbound screening reuses P-09's deterministic secret patterns and blocks matches; audit/events store pattern names only.",
     "detection_controls": "Blocked screening attempts recorded as value-free security events.",
     "recovery_procedure": "Rotate the exposed secret immediately via the registry; the value must be treated as compromised.",
     "verification_test": "test_scenario_08_secret_leakage",
     "status": "mitigated"},
    {"code": "T-09", "title": "SSRF to internal services",
     "description": "A browser or research agent requests loopback, private-network or cloud-metadata addresses.",
     "entry_point": "Network egress validator",
     "affected_assets": ["Local services", "Cloud metadata credentials"],
     "likelihood": "high", "impact": "high", "risk_level": "high",
     "preventive_controls": "Deterministic SSRF validator: resolved-IP range checks (loopback/private/link-local/reserved/metadata), scheme policy, redirect-chain re-validation, DNS-rebinding resistant (resolution is checked, not just the hostname).",
     "detection_controls": "Blocked egress audited with the matched range/reason.",
     "recovery_procedure": "None when controls hold; incident record on repeated attempts.",
     "verification_test": "test_scenario_09_ssrf_attack",
     "status": "mitigated"},
    {"code": "T-10", "title": "Forged or replayed payment webhook",
     "description": "An external webhook claims a payment succeeded without valid verification.",
     "entry_point": "P-07 payment webhook processing",
     "affected_assets": ["Financial records"],
     "likelihood": "medium", "impact": "high", "risk_level": "high",
     "preventive_controls": "P-07 verifies HMAC signatures, timestamp windows and idempotency before any confirmation; P-10 adds no second path.",
     "detection_controls": "P-07 records forged events as unverified; reconciliation surfaces them.",
     "recovery_procedure": "No revenue is confirmed from unverified events; investigate the source.",
     "verification_test": "test_scenario_10_forged_payment_event",
     "status": "mitigated"},
    {"code": "T-11", "title": "Runaway autonomous operation",
     "description": "Autonomous tasks continue while the owner wants everything stopped.",
     "entry_point": "Emergency stop / safe mode",
     "affected_assets": ["All system assets"],
     "likelihood": "low", "impact": "critical", "risk_level": "high",
     "preventive_controls": "Owner-controlled security modes enforced at the broker, capability, secret and financial-guard layers; owner access is never blocked by the stop.",
     "detection_controls": "Mode transitions are append-only emergency events + audit entries.",
     "recovery_procedure": "Owner resumes explicitly after verification (§20.4).",
     "verification_test": "test_scenario_11_emergency_stop",
     "status": "mitigated"},
    {"code": "T-12", "title": "Security service failure opens a hole",
     "description": "The authorization path errors and actions proceed by default.",
     "entry_point": "Broker / permission engine",
     "affected_assets": ["All system assets"],
     "likelihood": "low", "impact": "critical", "risk_level": "high",
     "preventive_controls": "Fail-closed everywhere: engine denies when permission data is unavailable (P-01); broker converts any internal error into a denial.",
     "detection_controls": "Fail-closed denials carry the reason 'security service unavailable; failing closed'.",
     "recovery_procedure": "Restore the security store; denials during the outage are the correct outcome.",
     "verification_test": "test_scenario_12_security_service_failure",
     "status": "mitigated"},
    {"code": "T-13", "title": "Audit record tampering",
     "description": "An agent or attacker modifies or deletes audit records to hide activity.",
     "entry_point": "Audit trail",
     "affected_assets": ["Logs", "Audit records"],
     "likelihood": "low", "impact": "high", "risk_level": "high",
     "preventive_controls": "No update/delete API exists for audit events; hash-chain seals make later tampering detectable. Honest limit: the chain is tamper-evident, not tamper-proof against raw database write access.",
     "detection_controls": "Chain verification reports the first mismatching or missing entry.",
     "recovery_procedure": "Restore from a verified backup; treat the tamper window as an incident.",
     "verification_test": "test_scenario_18_audit_integrity",
     "status": "partially_mitigated"},
    {"code": "T-14", "title": "Memory poisoning becomes governance",
     "description": "Stored memory content claims new owner instructions or grants permissions (Article 0).",
     "entry_point": "P-09 memory → any governance surface",
     "affected_assets": ["System policies", "Spending limits", "Approvals"],
     "likelihood": "medium", "impact": "critical", "risk_level": "critical",
     "preventive_controls": "P-09's write gate refuses agent governance claims; P-10 policy/broker/financial guard read nothing from memory — there is no code path from memory content to a governance decision.",
     "detection_controls": "P-09 records refused poisoning attempts; P-10 policy versions show only owner actors.",
     "recovery_procedure": "Delete the poisoned memory through P-09's governed deletion; no governance state needs repair because none changed.",
     "verification_test": "test_article0_memory_poisoning_cannot_amend_governance",
     "status": "mitigated"},
]
