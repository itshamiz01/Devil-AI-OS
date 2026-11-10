# P-16 — Economic Memory (§17)

**Module:** `app/economy/service.py` (`_feed_memory`) ·
**Tables:** `economic_decisions`

## What is remembered

Only **verified outcomes** are fed to P-09 memory
(`memory.ingestion.ingest`, `source_type: "agent_output"`, tagged
with the business and the verification status):

- experiment outcomes, after P-08 has evaluated the experiment
  and P-16 has synced the verdict;
- strategic decisions with their recorded outcomes (owner records
  the outcome against the decision; the pair is what is fed).

Proposals, scores and projections are never fed as fact. The feed
is best-effort: a memory failure never blocks or falsifies the
economic record itself, and the economic record (P-16's tables)
remains the auditable source.

## Decision records (§16)

`economic_decisions` stores owner decisions with their rationale,
the alternatives considered, the evidence relied on, and — later —
the recorded outcome and lessons. Outcome recording validates
against the decision's own declared success criteria fields; a
decision without recorded criteria cannot be given a verdict.
This is the §16 discipline: decisions are reviewable because the
reasoning was written down *before* the outcome was known.

## Pattern learning

Cross-experiment patterns (§11 doc) are computed from evaluated
proposals at read time — repeated failure/success per market tag.
Nothing is "learned" into a model in staging (no real LLM,
DEF-A2); patterns are arithmetic over recorded outcomes, and the
API presents them as such.
