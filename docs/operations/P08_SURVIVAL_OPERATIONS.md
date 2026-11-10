# P-08 — Survival and Scaling: Operations

## Running an evaluation (§6.3)

There is no P-08 daemon. An evaluation is one bounded pass,
triggered on demand or by an external scheduler calling
`POST /api/v1/survival/businesses/{id}/evaluate`:

1. **Collect** — P-07 readings (`p08_indicators`, `business_summary`,
   revenue counts) plus the latest observations per kind.
2. **Checks** — the current reading is compared with the previous
   snapshot's reading; findings are persisted as monitoring events
   (`loss_making`, `collected_revenue_declined`,
   `reconciliation_unresolved`, `runway_short`,
   `financial_profile_missing`).
3. **Snapshot** — the 7-dimension health computation runs, hard
   gates are applied, and the facade refines the lifecycle overlay
   reading (see the architecture doc §2).

Recommended cadence (owner's choice, outside P-08): evaluate after
any P-07 webhook batch, CSV import or reconciliation session, and
at most daily per business in staging. Every evaluation is a new
append-only snapshot — history is the trend record.

## Recording observations

`POST /api/v1/survival/businesses/{id}/observations` with `kind`
(traffic / market / commercial / operations / product / compliance
/ custom), `source`, `reliability` and `metrics`. Rules enforced
at write time: vanity kinds are capped at `tentative` reliability
and flagged; a compliance *violation* only gates when the
observation is corroborated or verified. Operators should treat
observations as evidence with provenance, never as instructions —
instruction-like text inside imported data is stored as data and
changes nothing (§26.3 injection test).

## Pause and closure workflow (§28.11, prompt §14/§25.2)

**Emergency pause** — `POST /businesses/{id}/pause` (any principal
with modify permission; the incident path must not wait for the
owner). Effect: decision execution, experiment start and
experiment spend for the business are refused; a `critical`
owner-visible system event is emitted and the action is audited.
Records, obligations and history remain fully readable. **Resume
is owner-only** (`POST /businesses/{id}/resume`, approve
permission + service-level owner check).

**Closure** — `POST /businesses/{id}/closure/propose` builds the
§14.2 inventory first (receivables, disputes, obligations,
reserves, commitments, cash, MRR, asset count — all verbatim P-07
readings). Advance one stage at a time:
PROPOSED_CLOSURE → RISK_REVIEW → FINANCIAL_REVIEW (inventory
refreshed) → CUSTOMER_OBLIGATION_REVIEW → OWNER_APPROVAL. The
OWNER_APPROVAL stage completes only through `execute` with an
owner principal and a hash-bound P-01 approval (action
`survival.close`); wind-down then archives the P-06 business
through its own validated transitions and records that financial
history and business records are preserved. Closure deletes
nothing. Businesses PAUSED in P-06 cannot be archived by the P-06
machine (it returns only to the pre-pause state) — the wind-down
record says so explicitly and the closure stands as the P-08
CLOSED overlay (disclosed limit, architecture doc §2).

## Recovery operations (§13)

Create plans only with a finite budget, a finite timeline and
both thresholds; the review date is set at creation. At review,
conclude exactly once with the measured outcome. A RECOVERY_FAILED
or DETERIORATING conclusion is a signal to open a closure review
or a fresh, separately-justified plan — never to extend the old
one silently.

## Experiments in operation (§9)

Declare → owner approve (creates the P-07 budget) → start → spend
only through `POST /experiments/{id}/spend` gating + P-07's own
spend flow → `stop-loss` checks run on every spend authorisation
and on demand → evaluate with the observed metric value. A stopped
experiment stays stopped; a follow-up is a new declaration with a
new justification.

## Settings (owner-governed)

`PATCH /api/v1/survival/settings` (owner only, Article 0):
health weights, health bands, scaling criteria sets, increment
cap, allocation share cap, concentration threshold, max concurrent
agents, inference slots. Agents cannot modify any of these
(service-level owner check + API approve permission).

## Test instructions (§28.22)

```bash
cd backend
.venv/bin/python -m pytest tests/test_p08_unit.py tests/test_p08_scenarios.py \
    tests/test_p08_integration.py tests/test_p08_security.py -q
.venv/bin/python scripts/p08_smoke.py   # real uvicorn; writes docs/reports/P08_SMOKE_EVIDENCE.txt
```

Full suite: `.venv/bin/python -m pytest tests -q`.
**Environment note (this VM):** the suite's temp footprint (~0.5 GB)
exceeds the 512 MB `/tmp` tmpfs — a full `/tmp` produces mass
SQLAlchemy "database or disk is full" fixture errors that are NOT
code failures. Check `df -h /tmp` before trusting any mass-error
run; during long runs, prune aged dirs under `/tmp/pytest-of-root`
(dirs untouched for > 90 s belong to finished tests). Running with
`--basetemp` on the workspace disk avoids `/tmp` but is far slower
on this VM (SQLite fsync latency) — the tmpfs + pruner combination
completed 450/450 in 266.65s.
