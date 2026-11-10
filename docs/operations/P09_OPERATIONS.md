# P-09 Operations

- **Settings** live in `system_config` under `memory.settings`
  (owner-governed; agents receive 403 on update). Keys: retrieval
  weights (§9.3), `working_ttl_hours` (24), `context_item_limit`
  (12), freshness windows per category, `vector_enabled`.
- **Maintenance**: `POST /api/v1/memory/maintenance/scan` expires
  working memory past its TTL (to ARCHIVED, never deleted), flags
  stale high-value knowledge and long-unverified learnings, and opens
  `memory_review_tasks` for the owner. Safe to run repeatedly.
- **Review queue**: `GET /api/v1/memory/maintenance/review-tasks`
  (owner). Resolve contradictions at
  `POST /api/v1/memory/contradictions/{id}/resolve` — resolution
  records the decision; it never edits either record away.
- **Deletion**: `DELETE /api/v1/memory/{id}` (owner). Permanent and
  legal-hold records are refused (`BLOCKED_RETENTION`). A receipt is
  COMPLETED only after the embedding row is removed and re-checked;
  receipts are listed in `memory_deletion_receipts`.
- **Export**: `POST /api/v1/memory/owner/export` (owner) returns all
  owner-visible records and writes a `memory_exports` row; the export
  action itself is audited.
- **Health**: `GET /api/v1/memory/status` reports counts, the vector
  store's real state (adapter, indexed count, degraded flags) and
  pending review tasks. If it reports `degraded.semantic`, keyword
  retrieval still works; check `vector_enabled` and the embeddings
  table.
- **Backups**: memory tables are ordinary application tables — the
  standard database backup covers them. Deletion receipts and audit
  events should be retained with the backup set.
