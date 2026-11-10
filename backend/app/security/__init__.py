"""P-10 Security and Governance Engine.

A security LAYER over P-01–P-09, never a parallel system: identity,
sessions, permissions, approvals and the audit trail remain P-01's;
execution enforcement remains P-05's; financial truth remains
P-07's; memory governance remains P-09's. This package adds the
cross-cutting controls those phases scoped out: a permission broker
with task-scoped capabilities, hardened approval decisions, secret
metadata + brokered use, filesystem/command/network guards, AI
content-trust screening, a financial authorization guard, security
modes with emergency stop, an audit hash chain, deterministic
monitoring/alerts, and backup verification.

Article 0 boundary: nothing in this package lets an agent amend
governance. Policy writes are owner-only and versioned; approvals
are consumed through P-01's hash-bound verification only (this
package never calls ``ApprovalService.decide`` — a structural test
enforces that); no LLM participates in any decision here.
"""
