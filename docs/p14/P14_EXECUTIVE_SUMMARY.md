# P-14 EXECUTIVE SUMMARY — Stage A: Audit (Preliminary)

**What Stage A was:** a full, evidence-first audit of the complete
AUTONOMUS system (P-01–P-13) under P-14 §23's sequencing — inventory,
architecture audit, integration matrix, data/security/financial
audits, end-to-end scenarios and failure probes as **62 new additive
tests**, and a full baseline regression. **No production code was
changed.** Repairs are Stage B, after the owner reviews this audit.

**Preliminary readiness view (NOT the §18 classification — that is
issued in Stage B):** the system is trending toward **READY FOR
CONTROLLED PILOT** — owner-supervised, on the owner's Windows
machine, with the locked spending/approval controls — and is
**not a production candidate** while Windows remains unverified
(DEF-A1) and no real LLM has ever run (DEF-A2).

## What works — verified, not claimed

- **It is one system.** All 13 module services assemble once, in
  dependency order, on the P-01 substrate (assembly probe + wiring
  evidence). One permission engine, one approval store, one event
  bus, one task queue, one financial authority, one business
  registry. Zero circular imports at file level; zero orphan
  tables; a single linear 13-migration chain with one head.
- **The safety core held under independent attack.** 23 new
  adversarial probes (approval replay/drift/self-approval, prompt
  injection, memory poisoning, cross-business leakage, symlink
  escapes, prohibited tools, credential surfaces, audit-chain
  tamper-deletion) found **no P0 and no P1 security defect**.
- **The money is right.** §10 reconciliation re-ran seven
  simulations and the eight invariants against P-07 + P-13:
  double-entry integrity, idempotency, reversal-only correction,
  projected ≠ collected, per-currency separation — all hold.
- **The lifecycle runs end to end.** §11 scenarios: distress,
  collaboration, infrastructure failure and security incident
  executed **fully** on the real module chain; opportunity→business
  and autonomous-task scenarios executed with two precisely
  recorded choreography gaps (below).
- **Regression:** backend **774 passed + 1 xfailed of 775** (713
  baseline fully preserved + 62 new audit tests), frontend **40/40**,
  strict build clean. One run was poisoned by this VM's 512 MB /tmp
  filling mid-run; the 57 affected tests were re-run clean at 57/57
  and the incident is disclosed in full in the regression report.

## What does not work — the honest list

- **One real bug (P2):** the Portfolio view's *gross* collected
  revenue silently reports 0 (P14-DEF-F1) — a wrong key read from
  P-07 metrics in P-13's finance view. Net figures and the books
  are correct; the displayed gross is not. It survived three phase
  gates because no earlier test asserted gross.
- **Module verdicts (§3):** 6 modules IMPLEMENTED AND VERIFIED
  (P-01, P-04, P-07, P-08, P-12, P-13), 5 IMPLEMENTED BUT NOT FULLY
  VERIFIED (P-02, P-03, P-06, P-10, P-11), 2 PARTIALLY IMPLEMENTED
  (P-05 — browser partial/desktop disabled/code not sandboxed;
  P-09 — ChromaDB replaced by a SQLite substitute). None broken,
  none missing.
- **Events are the weakest seam (2× P1):** `SecurityIncidentDetected`
  and `PortfolioRiskDetected` events don't exist, and the event
  envelope lacks business/workflow IDs, schema version,
  authorization context and processing status — §14-grade
  traceability cannot be reconstructed from events alone.
- **Data-layer debt (1× P1):** 320 timezone-naive datetime columns
  against an aware-UTC runtime — currently safe only where modules
  shim on read (P-12 does; others are exposed by inspection).
  Plus ≈59 entity references without foreign keys, two float money
  columns in pre-P-07 declaration tables, and free-text business
  references in four modules.
- **Two integration gaps (P2):** P-02 never consumes P-03
  opportunities, and P-02 planning never retrieves P-09 memory —
  two §11 chain steps exist only as test choreography today.
- **The two standing giants (P1):** **Windows has never run this
  system** (the locked primary platform; launchers, DPAPI, startup
  all unverified), and **no real LLM has ever run in it** (Ollama
  unverified against a real server; the cloud adapter is an inert
  stub; "hybrid AI" is currently an interface, not a capability).

## Defect register totals

**P0: 0 · P1: 5 · P2: 17 · P3: 19** — full register with root
causes and proposed minimal repairs in P14_DEFECT_REGISTER.md.
Every P-01–P-13 carried limitation was re-verified against current
code; all remain true as disclosed (PDF export and both
natural-language analysts NOT IMPLEMENTED; Stripe owner-config
only; MFA recovery codes absent; encryption at rest partial; audit
chain tamper-evident, not tamper-proof).

## What Stage B needs from the owner

1. **Review this audit** and accept/reject the proposed repairs
   (the register is ordered so the P1s and F1 can be approved as a
   first batch).
2. **Two decisions:** DEF-I5 (document the two-path permission
   model, or route P-05 through the broker) and DEF-E1 (accept the
   P-03→P-06 evaluation path, or build the P-02 assessment link).
3. **Owner-machine items no staging work can close:** the P-00
   Windows environment run, and a real local model (Ollama) pass
   against P-02.
4. Stage B then executes repairs, builds the §14 monitoring view
   (DEF-A3), re-runs the full regression, and issues the formal
   §18 readiness classification in
   P14_PRODUCTION_READINESS_REPORT.md.

**P-15 was not started.** Nothing in Stage A touched production
code, an existing test, or a migration.
