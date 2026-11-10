# P-15 DATABASE & DATA RECOVERY (§6)

## Monitoring

The evidence layer measures, on every readiness computation and
on demand in panel G:

- **Connectivity** — the P-01 monitor's database check.
- **Latency** — a timed `SELECT 1` round-trip (ms), also recorded
  in every performance sample.
- **Integrity** — SQLite `PRAGMA integrity_check`, consumed by the
  data-integrity readiness category and acting as a **critical
  gate**: a failed integrity check caps the classification at NOT
  PRODUCTION READY regardless of score. (Non-SQLite backends
  report the check as not-applicable rather than fabricating a
  result; the staging and target-local deployments are SQLite.)
- **Migration state** — the database revision vs the single
  Alembic head, so schema drift is a scored, visible condition.
- **Storage growth** — disk utilisation is in every sample; the
  stability report's memory/disk trend fields expose growth over
  the recorded window.

## Backup (§6.2)

Owned by the P-10 `BackupService` (create → SHA-256 + table
inventory → verify; retention and storage are the service's own
concerns). P-15 adds the missing operational loop around it:

- The Command Center's Data Protection panel creates a **verified**
  backup through the P-15 endpoint, which delegates to P-10 and
  returns its verification result — no parallel backup code.
- The evaluator watches posture: **no backups** (P3) and **stale
  latest backup** beyond `backup_max_age_hours` (default 168h, P3)
  become incidents; both auto-resolve when posture recovers.
- The readiness data category scores existence, verification and
  freshness separately, so an unverified or ancient backup cannot
  masquerade as protection.

## Recovery procedure (§6.3)

Unchanged from the P-14 position, and restated so it is findable:

1. Stop the application (P-01 graceful shutdown).
2. Use the P-10 guarded restore **preview** to see exactly what a
   candidate backup contains (table inventory + checksum).
3. The owner performs the restore manually — restore *execution*
   is deliberately not an application feature (P-14 DEF-A4), so a
   compromised or confused agent session cannot overwrite valid
   production data.
4. Restart; the startup recovery scans (P-01/P-05/P-12) park any
   interrupted work for review, and P-15's first evaluation
   re-checks integrity, backups and incidents against the restored
   state.

Verified in staging: backup creation + verification through the
P-15 delegation is covered by integration tests and the live
smoke (25/25), including the incident auto-resolution when the
first backup appears. A full restore *execution* rehearsal
remains an owner-machine pilot activity — reported as such, not
claimed here.

## Transaction integrity (§6.1)

Unchanged and re-verified: P-07's double-entry ledger verifies
per business through `LedgerService.verify_integrity` (consumed
read-only by P-15's financial read-model); multi-step writes stay
inside the owning services' transactions. P-15 writes only its
own four tables, each in single-row commits.
