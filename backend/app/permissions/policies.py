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
    ("agents.manage", "agents", "Manage agents"),
    ("agents.read", "agents", "Read agent metadata"),
    ("events.read", "events", "Read system events"),
    ("audit.read", "audit", "Read audit events"),
]

OWNER_PERMISSIONS = [code for code, _, _ in PERMISSIONS]
SYSTEM_PERMISSIONS = ["system.read", "tasks.read", "events.read"]
