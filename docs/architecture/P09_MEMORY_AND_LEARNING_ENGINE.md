# P-09 Memory and Continuous Learning Engine — Architecture

## Position in the system

P-09 gives AUTONOMUS a governed long-term memory: what the owner,
businesses, agents and the system itself have learned, with
provenance, truth classification, access scopes and an audit trail.
It sits **below** authority: memory informs decisions made by P-02 /
P-06 / P-08 and approved under P-01; it never makes or changes them.

```
        owner / agents / services
                 │  (P-01 principals, /api/v1/memory)
        ┌────────▼─────────┐
        │  MemoryService   │  settings · status · analytics ·
        │  (facade)        │  preferences · export · audit
        └──┬───┬───┬───┬───┘
   records │   │   │   │ learning        knowledge
  ingestion┘   │   └retrieval            (graph, contradictions,
               │   (hybrid search,       consolidation, handoffs,
               │    context builder)     maintenance, P-04 iface)
        ┌──────▼───────────────┐
        │ policy.py — the one  │  secret screen · governance screen ·
        │ write gate           │  truth/category/scope rules (Art. 0)
        └──────┬───────────────┘
        ┌──────▼───────────────┐      references only (never copies)
        │ 15 memory_* tables   ├────► P-07 ledger ids · P-08 experiment/
        │ + SQLite vectors     │      decision ids · P-06 business ids
        └──────────────────────┘
```

## Layers, truth and lifecycle

Seven layers (§6.2): working, episodic, semantic, procedural,
business, preference, strategic. Eighteen categories (§6.1). Eight
truth classes (§3.1) from `verified_fact` down to `speculation`;
confidence is stored in basis points and reported on the §3.3
ladder. Records move ACTIVE → SUPERSEDED / ARCHIVED / EXPIRED /
DELETED; updates snapshot the prior state into `memory_versions`;
supersede creates a successor and preserves the original.

## Retrieval

Hybrid: keyword (task relevance) + local vector similarity +
confidence, source reliability, importance, recency and relationship
components, weighted per §9.3 from owner-governed settings. Access
filtering happens **before** ranking — an invisible record cannot
influence results, counts or the vector index. Every result carries
its score breakdown, a plain-language reason, its freshness state and
any open contradictions. When nothing trustworthy matches, the engine
returns `no_reliable_memory` rather than padding results.

## Learning

A learning record requires an expected outcome, an actual outcome and
supporting observations. Confidence is mechanical: one observation
can never exceed LOW; VERIFIED requires at least three observations
**and** an owner review. Learning from P-08 experiments/decisions
reads the real rows; financial context is a resolved P-07 reference
(table + id existence), never figures.

## Degraded operation

- No LLM: nothing changes — there is no LLM in the loop.
- No vector store (or vectors disabled in settings): keyword/exact
  retrieval continues, status reports `degraded.semantic = true`,
  authoritative records are untouched.
