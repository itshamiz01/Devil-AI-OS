# P-17 — Implementation Changelog (§28)

## Added — backend

- `app/growth/` package:
  - `constants.py` — vocabularies (30 channels, lead sources +
    forbidden set, stages, kinds), settings defaults, the
    8-surface integrations catalogue (all not configured), the 17
    §12 agent-role definitions, `RECOMMENDATION_KIND_RANK`.
  - `scoring.py` — pure mathematics: weighted scores, lead bands,
    CAC, LTV (actual/projected split), retention/churn, funnel
    rates, customer health, A/B conclusion discipline.
  - `service.py` — GrowthService core: settings, audit, owner/
    reader gates, P-16 gate consumption, hash-bound approvals,
    P-07 spend reads (campaign + eligible), agent-template seeding,
    engine status, serializers for all 18 models.
  - `intelligence.py` — brand profiles, personas, ICPs, channel
    evaluations, strategies (gate-respecting decisions).
  - `campaigns.py` — campaigns (lifecycle, gate-respecting
    approval, P-07 spend-request preparation, metrics + alerts,
    level-4-only auto-pause), content workflow with the mechanical
    brand check and owner-attested release, growth experiments
    (pre-declared, P-08 handoff, declared-observation conclusions).
  - `pipeline.py` — leads (authorised sources, dedupe, consent,
    suppression, import), lead scoring, sales pipeline, CRM
    (conversion, customers, P-07 purchase history, interactions,
    explained health).
  - `engagement.py` — funnel events/summary, SEO records, communi-
    cation templates (deceptive-pattern refusal) + queue (consent/
    suppression/frequency) + honestly blocked dispatch,
    partnerships (governed stages, referral attribution).
  - `analytics.py` — overview, per-business growth, attribution,
    budget view, retention analytics, recommendations, portfolio
    growth.
- `app/database/models/growth.py` — 18 tables; registered in
  `models/__init__.py`.
- Migration `afe062122eb5` (revises `ccd744b29e54`): additive,
  cycle-verified 191 ↔ 209 physical tables.
- `app/api/routes/growth.py` — 63 route paths under
  `/api/v1/growth`; wired in `app/main.py`; `GrowthService`
  constructed in `app/core/application.py` after EconomyService
  (settings + agent templates seeded at startup).
- `scripts/p17_smoke.py`; `tests/p17_support.py` +
  `test_p17_{unit,integration,security,scenarios}.py` (36 tests).

## Added — frontend

- `src/views/Growth.tsx` (six tabs on real endpoints) +
  `Growth.test.tsx` (3 tests); route case `"growth"` in
  `App.tsx`; nav entry "Acquisition & Growth" (Portfolio section)
  in `components/shell.tsx`.

## Changed — earlier phases (disclosed, strictness preserved)

- Alembic-head pins → `afe062122eb5` (P-02…P-05 suites) and table
  counts 191 → 209 / 190 → 208 (P-11…P-16 suites), each with a
  P-17 disclosure comment in the established style.

## Not changed

P-07 (financial authority), P-06 (lifecycle), P-08 (experiments),
P-13 (portfolio), P-16 (economy + gate), P-10 (security),
Constitution/ADRs — no earlier authority was modified; P-17 only
reads them or calls their governed paths.
