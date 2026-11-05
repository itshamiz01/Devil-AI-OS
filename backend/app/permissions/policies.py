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
    # ---- P-04 Dynamic Agent Factory ----
    # Added add-only, one stage at a time, so a code exists exactly when the code
    # that enforces it does. `agents.read` and `agents.manage` already existed
    # before P-04 (see the withdrawn audit finding §9.1 and L-60): they are not
    # re-added here.
    #
    # OWNER_PERMISSIONS is derived from this list, so the owner receives both
    # automatically, and the P-01 startup reconciliation grants them to an owner
    # whose database predates the change. SYSTEM_PERMISSIONS is enumerated
    # explicitly and includes neither, so the application can never define,
    # validate or publish the template that governs its own agents.
    #
    # Stage 3 adds the template codes only. The factory, capability, permission,
    # retirement and metrics codes arrive with the stages that enforce them, so
    # the catalog never advertises an authority nothing implements.
    ("agents.templates.read", "agents", "Read agent templates and their versions"),
    ("agents.templates.write", "agents", "Create, revise, validate, publish, deprecate, restore or clone agent templates"),
    # ---- P-04 Dynamic Agent Factory, Stage 4 ----
    # Two codes, and both are enforced by a route in this stage. No
    # `agents.factory.approve` is added: a gated creation is decided through the
    # central approval endpoints under the existing `approvals.decide`, so the
    # owner uses one approval surface for every gated action in the system
    # instead of a second one that only agents know about. Splitting read from
    # admin means an agent can be given the ability to *ask* what a creation
    # would decide without the ability to make one happen.
    ("agents.factory.read", "agents", "Evaluate creation requests and read the creation ledger"),
    ("agents.factory.admin", "agents", "Create agents, drain the creation queue"),
    # ---- P-04 Dynamic Agent Factory, Stage 5 ----
    # Reading the catalog is separated from granting against it for the same
    # reason as the factory split: an agent may need to know what a capability
    # costs without being able to hold one. Neither code is in
    # SYSTEM_PERMISSIONS, so the application cannot widen its own authority.
    ("agents.capabilities.read", "agents", "Read the capability catalog and agent capability grants"),
    ("agents.permissions.grant", "agents", "Grant and revoke agent capabilities"),
]

OWNER_PERMISSIONS = [code for code, _, _ in PERMISSIONS]
SYSTEM_PERMISSIONS = ["system.read", "tasks.read", "events.read"]
