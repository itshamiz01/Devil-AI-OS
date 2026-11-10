# P-09 Implementation Plan (Stage 2, §27)

Derived from the Stage-1 audit (`P09_PRE_IMPLEMENTATION_AUDIT.md`)
and the four Stage-1 notes on the PHASE_TRACKER P-09 row.

1. **Data model** — 15 additive tables in
   `app/database/models/memory.py`: records, versions, entities,
   relationships, embeddings (local vector backing), ingestion jobs,
   contradictions, retrieval logs, learning records, handoffs,
   consolidations, owner preferences, review tasks, deletion
   receipts, exports. One migration `7b13db7e9bfa` revising the P-08
   head; cycle verified 108 → 123 → 108 → 123.
2. **Write gate (Article 0)** — a single policy module
   (`app/memory/policy.py`): every write passes secret screening
   (pattern names only, values never stored/logged), a
   governance-claim screen (agents cannot store text claiming to
   change owner rules), truth-class and category restrictions for
   agents, and scope checks. Memory has no path to permissions,
   approvals, `system_config` governance keys or limits — enforced
   structurally (the package holds no reference to the approvals
   service or the permission engine) and by test.
3. **Records** — create/update (versioned, prior snapshot preserved),
   supersede (original preserved, marked SUPERSEDED), owner-only
   verify (→ `verified_fact` with evidence), owner-only delete with
   retention blocks and receipt-after-index-verification.
4. **Ingestion (§7)** — screen → usefulness filter → exact-duplicate
   hash → deterministic classification + entity extraction → gated
   store; every decision job-logged.
5. **Retrieval (§9/§10)** — hard filters (principal, scope, status,
   business/project/agent, time) BEFORE ranking; §9.3 weighted
   scoring with per-result breakdown and reasons; freshness state;
   contradiction flags; honest `no_reliable_memory`; retrieval
   logged with the query stored as a digest only. Context builder
   with §10.2 priority and a settings item cap.
6. **Learning (§11)** — expected AND actual outcomes required;
   mechanical confidence ceiling (1 observation ≤ LOW, 2 ≤ MODERATE,
   ≥3 + owner review = VERIFIED); builders from real P-08
   experiments/decisions; P-07 financial references resolved by
   existence only.
7. **Knowledge services** — contradiction detection preserving both
   records; entity/relationship graph with traversal; consolidation
   creating a NEW summary linked to preserved sources; maintenance
   scan (working-memory TTL expiry, stale review tasks); handoffs
   with agent isolation; `P09MemoryInterface` implementing the P-04
   protocol and wired into the agent factory at startup (the three
   deferred scopes served; cross-agent requests refused).
8. **Facade + API** — `MemoryService` (settings seed/owner-only
   update, capability flip, status, §22 analytics measured from
   tables, owner preferences with explicit-beats-inferred, owner-only
   export, `memory.*` audit trail) and routes under
   `/api/v1/memory` following project conventions.
9. **Tests** — unit (§25.1 incl. the measured §22.3 retrieval
   evaluation), integration (§25.2: migration cycle, wiring, HTTP,
   real P-07/P-08 records), security (§25.3), and all 17 acceptance
   scenarios (§25.4) as real named tests.
10. **Smoke + docs + tracker/README + transfer zip**, then STOP
    (§31): no P-10 work.
