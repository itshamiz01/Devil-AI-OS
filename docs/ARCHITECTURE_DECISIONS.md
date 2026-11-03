# Architecture Decision Record Index

**Rule:** Owner-locked decisions, accepted P-00 actions and proposed engineering decisions are distinct. A proposed ADR is not approval to implement.

| ADR | Decision | Status |
|---|---|---|
| [0001](decisions/ADR-0001-HYBRID-LOCAL-FIRST.md) | Hybrid AI with local default and optional cloud | Owner-locked in supplied Constitution |
| [0002](decisions/ADR-0002-CONTROLLED-AUTONOMY.md) | Controlled autonomy and deterministic authority | Owner-locked in supplied Constitution |
| [0003](decisions/ADR-0003-WINDOWS-FIRST.md) | Windows-first product direction | Owner-locked; minimum OS/version pending |
| [0004](decisions/ADR-0004-GOVERNANCE-SOURCE.md) | Use owner-supplied governance texts and preserve provenance | Accepted for P-00 by explicit owner selection |
| [0005](decisions/ADR-0005-MODULAR-LOCAL-CORE.md) | Modular local core, durable queue and SQLite-first persistence | Proposed; owner review pending |
| [0006](decisions/ADR-0006-FINANCIAL-AUTHORITY.md) | Separate financial authority, immutable records and early controls | Proposed implementation of constitutional requirements; accounting details pending |
| [0007](decisions/ADR-0007-CANDIDATE-TOOLCHAIN.md) | Compatible candidate versions rather than blindly using latest | Proposed; Windows validation pending |
| [0008](decisions/ADR-0008-DEFER-VECTOR-STORE.md) | Replaceable retrieval boundary; defer vector-server installation | Proposed; P-09 selection pending |
| [0009](decisions/ADR-0009-CONDITIONAL-P01-BACKEND.md) | Conditional backend-only P-01 while Windows/full gate remains pending | Accepted for conditional implementation |
| [0010](decisions/ADR-0010-OWNER-SESSION-AUTH.md) | Owner password hash and opaque bearer sessions | Implemented for P-01 backend |
| [0011](decisions/ADR-0011-SAFE-TASK-HANDLERS.md) | Registered safe internal task handlers only | Implemented for P-01 backend |
| [0012](decisions/ADR-0012-SECRET-STORE-DESIGN-ONLY.md) | Secret store delivered as design only; no `keyring` dependency added | Implemented as DESIGN for P-01; implementation deferred to P-05/P-07 |
| [0013](decisions/ADR-0013-EMERGENCY-STOP-FOUNDATION.md) | Durable owner-only emergency stop; in-flight work paused, not killed | Implemented for P-01 backend |
| [0014](decisions/ADR-0014-BACKUP-RESTORE-CLI-ONLY.md) | Verified SQLite online-backup snapshots; restore is CLI-only, never HTTP | Implemented for P-01 backend |
| [0015](decisions/ADR-0015-INTELLIGENCE-ENGINE-BOUNDARIES.md) | Intelligence engine reasons and recommends, never executes; cloud routing implemented but inert | Implemented for P-02; inert-cloud posture needs owner ratification |
| [0016](decisions/ADR-0016-NO-PAID-INFERENCE-FALLBACK.md) | No automatic paid inference fallback; unpermitted providers excluded at selection | Implemented for P-02 |
| [0017](decisions/ADR-0017-DETERMINISTIC-FIRST-INTELLIGENCE.md) | Deterministic-first intelligence; models are never the source of authority or evidence | Implemented for P-02; local-model integration NOT VERIFIED |

## Change protocol

Record context, problem, options, decision, reasons, consequences and status. Changes to locked architecture, authority, security, financial permissions, data ownership, providers or platform require explicit owner approval and a Constitution revision where applicable.

Open items are consolidated in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Do not change an ADR from Proposed to Accepted merely because documentation or code was generated.
