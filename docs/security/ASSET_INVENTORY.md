# Asset Inventory (P-10)

The assets P-10 protects, where they live, and their default
classification (levels: 1 public, 2 internal, 3 confidential,
4 restricted, 5 critical):

| Asset | Location | Class | Notes |
|-------|----------|-------|-------|
| Owner credentials (password hash) | P-01 `users` | 5 | scrypt hash; never returned by any API |
| Session tokens | P-01 `app_sessions` | 5 | SHA-256 hashed at rest; raw token shown once |
| Secret values (API keys etc.) | owner environment / Windows vault | 5 | NEVER stored by AUTONOMUS; metadata only (P-10 registry) |
| Approval records + hashes | P-01 `approval_requests` | 4 | SHA-256 parameter binding |
| Audit trail | P-01 `audit_events` | 4 | append-only; P-10 hash chain over it |
| Financial journal & balances | P-07 tables | 4 | double-entry; P-10 holds no copy |
| Business records | P-06 tables | 3 | scoped by `business_ref` |
| Memory records | P-09 tables | 3 | data, never authority; screened for secrets |
| Security policy (versioned) | `system_config` + `security_policy_versions` | 4 | owner-writable only |
| Capability tokens | `security_capabilities` | 4 | metadata (permission, holder, expiry); no secret value |
| Backups | data dir `backups/` | 4 | SHA-256 manifest + integrity verification |
| Agent identities | P-01 `agents` | 3 | business-scoped via `business_ref` |
| Threat register | `security_threat_register` | 2 | seeded; owner-maintained |
| Source code & docs | repository | 2 | governance docs are owner-governed (Article 0) |

Inventory method: derived from the schema (137 tables after the
P-10 migration) and the phase implementation reports. New asset
classes require an owner-approved inventory update; classifications
can be raised per-path via `security_data_classifications`.
