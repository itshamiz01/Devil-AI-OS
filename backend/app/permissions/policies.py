from __future__ import annotations

PERMISSIONS: list[tuple[str, str, str]] = [
    ("system.read", "system", "Read system data"),
    ("system.write", "system", "Write system data"),
    ("tasks.submit", "tasks", "Submit tasks"),
    ("tasks.read", "tasks", "Read tasks"),
    ("tasks.cancel", "tasks", "Cancel tasks"),
    ("tasks.retry", "tasks", "Retry failed tasks"),
    ("tasks.pause", "tasks", "Pause and resume eligible tasks"),
    ("tools.execute", "tools", "Execute approved tools"),
    ("business.read", "business", "Read business data"),
    ("business.write", "business", "Modify business data"),
    ("sensitive.read", "sensitive", "Access sensitive data"),
    ("financial.request", "financial", "Request financial operations"),
    ("approvals.request", "approvals", "Request approvals"),
    ("approvals.decide", "approvals", "Approve or reject sensitive actions"),
    ("config.modify", "configuration", "Modify system configuration"),
    # Owner-only. OWNER_PERMISSIONS is derived from this list, so the owner
    # receives it automatically; SYSTEM_PERMISSIONS is enumerated explicitly and
    # does not include it, so the system principal can never halt or un-halt the
    # application on its own authority.
    ("system.emergency", "system", "Activate or clear the global emergency stop"),
    ("agents.manage", "agents", "Manage agents"),
    ("agents.read", "agents", "Read agent metadata"),
    ("events.read", "events", "Read system events"),
    ("audit.read", "audit", "Read audit events"),
    # ---- P-02 Master Intelligence Engine ----
    # OWNER_PERMISSIONS is derived from this list, so the owner receives all four
    # automatically (and the startup reconciliation added in P-01 grants them to
    # an owner whose database predates this change). SYSTEM_PERMISSIONS is
    # enumerated explicitly and includes none of them, so the application can
    # never reason about, replan or re-authorize itself on its own authority.
    ("intelligence.use", "intelligence", "Submit requests to the intelligence engine"),
    ("intelligence.read", "intelligence", "Read missions, plans and intelligence status"),
    ("intelligence.manage", "intelligence", "Approve, pause, cancel or replan a mission"),
    ("intelligence.autonomy", "intelligence", "Change the autonomy level (owner only)"),
    # ---- P-03 Opportunity Discovery Engine ----
    # OWNER_PERMISSIONS is derived from this list, so the owner receives all four
    # automatically; SYSTEM_PERMISSIONS is enumerated explicitly and includes none
    # of them, so the system can never authorize its own research or change which
    # hosts it may reach.
    #
    # There is deliberately NO permission for spending money. §26 prohibits the
    # engine from purchasing domains, subscriptions, datasets or advertising, and
    # from creating any financial obligation, at every autonomy level. A permission
    # code would imply the capability exists and merely needs granting, which is not
    # the case: the GovernanceGate refuses those actions outright.
    ("opportunities.read", "opportunities", "Read opportunities, evidence, scores and reports"),
    ("opportunities.research", "opportunities", "Run discovery and research for an opportunity"),
    ("opportunities.manage", "opportunities", "Open, screen, advance, score or reject an opportunity"),
    ("opportunities.sources", "opportunities", "Register or authorize a research source (owner only)"),
]

OWNER_PERMISSIONS = [code for code, _, _ in PERMISSIONS]
SYSTEM_PERMISSIONS = ["system.read", "tasks.read", "events.read"]
