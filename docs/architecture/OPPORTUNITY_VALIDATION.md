# P-03 — Opportunity Validation Framework (§18)

Implemented in `app/opportunities/validation.py`. Levels are **computed from stored evidence** on every validation run and persisted in `validation_records` with the reasoning. They are never asserted by a caller: a caller may *claim* a level, and the claim is refused (HTTP 422) when the computed evidence does not support it.

| Level | Name | Evidence gate (all from stored records) |
|---|---|---|
| 0 | Hypothesis | Always available |
| 1 | Research-supported | ≥1 supporting record at SUPPORTING or better |
| 2 | Problem validated | Problem evidence at SUPPORTING+ from ≥2 independent sources |
| 3 | Commercial model validated | Level 2 **and** a commercial analysis whose break-even is computable |
| 4 | Real-world demand validated | Level 3 **and** an owner-recorded `owner_real_world` record classified VERIFIED |
| 5 | Revenue validated | Level 4 **and** an owner-recorded `owner_payment` record classified VERIFIED **and** reviewed by the owner principal |

## Non-negotiable rules (§18.2)

- Level 4 **cannot** be claimed from search volume, page views, social engagement or personas — those categories never enter the owner-evidence gate.
- Level 5 requires independently verifiable payment evidence recorded by the owner. **P-03 never conducts transactions** (§26); it records owner-provided proofs only.
- A claimed level above the computed level is refused and the refusal is returned with the computed level and its reasoning (smoke: e-book claimed Level 4 → HTTP 422; test: Level 5 claim without payment evidence → 422).
- Owner-grade evidence (`owner_real_world` / `owner_payment`) can only be recorded by the owner principal — enforced in the API (403 for agent/service) and covered by a dedicated security test.

## Staging outcomes

All three smoke investigations compute to **Level 1** (supporting fixture evidence exists; problem evidence lacks a second independent source at the required strength, so Level 2 is honestly not met). The full ladder — Levels 2, 3, 4 and 5 — is exercised in integration tests with progressively recorded evidence, including owner-recorded real-world and payment proofs reaching Level 5 (acceptance scenario I: strong research without verified sales caps below 5, proven by the Level-4-without-payment state in the same test).
