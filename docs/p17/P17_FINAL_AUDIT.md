# P-17 — Final Audit

**Phase:** P-17, Customer Acquisition, Marketing & Revenue Growth
Engine (§21 of the P-17 prompt: Final Audit).

**Classification: READY FOR CONTROLLED PILOT** (unchanged from
P-14/P-15/P-16). Production remains withheld while DEF-A1
(Windows UNVERIFIED) and DEF-A2 (no real LLM ever exercised)
stand — both are owner-machine items, unchanged by this phase.

## 1. What was built

One new coordinating module, `app/growth/`, in the house shape:
a `GrowthService` over `Application` composing five mixins
(intelligence, campaigns, pipeline, engagement, analytics), pure
scoring functions (`scoring.py`, unit-tested without a database),
and vocabulary in `constants.py`. **18 new tables** (`growth_*`),
all registered through the existing models package; **no money
columns anywhere** — asserted over the schema by test. Additive
Alembic migration `afe062122eb5` (down_revision `ccd744b29e54`)
with the house upgrade/downgrade cycle test: **191 → 209 → 191 →
209 physical tables** (208 metadata + alembic_version at head).
**64 new HTTP routes** under `/api/v1/growth` (589 paths total),
and a Command Center **Acquisition & Growth** view (six tabs) on
the P-11 shell patterns.

The lifecycle runs end to end: brand profile with prohibited
claims → personas with typed evidence → ICPs scored by the §6
formula → 30 channels evaluated by the §7 formula and ranked →
strategies decided **through the P-16 profitability gate** →
campaigns with ceilings → spend as **P-07 spending requests and
recorded expenses only** → leads with lawful-basis enforcement,
suppression and dedupe → scoring by the §11 formula → the §13
pipeline (probability-weighted from P-07 terms) → one-CRM-record
conversion → retention from real purchase behaviour → funnel
(declared vs system counts, always distinct) → SEO as declared
records → communications that **queue but never send** → partner
records whose agreements need approval — with attribution,
retention and recommendations computed **from P-07 figures**.

## 2. Requirement-by-requirement evidence (§21)

| # | Requirement | Evidence |
|---|---|---|
| 1 | No campaign presents projected revenue as actual | Attributed revenue is P-07 verified collected revenue by channel tag; CAC/LTV carry `INSUFFICIENT_DATA`/ESTIMATE status; smoke §3 checks the figures are P-07's exactly (₹1,200 spend / ₹5,499 attributed). |
| 2 | No marketing recommendation ignores profitability | Strategy/campaign decisions pass `_check_gate` (P-16); recommendations are gate-derived, kind-ordered improve → diversify → capital_efficiency → expansion with expansion `gate_blocked`; smoke §2/§4/§6 verify live under a closed gate. |
| 3 | No spend exists outside the financial system | Spend exists only as P-07 spending requests (`prepare_spend_request`) and recorded P-07 expenses read back per campaign; P-17 tables carry no money columns (schema test); P-07 totals byte-equal after P-17 writes (security test). |
| 4 | No customer total depends on manually entered revenue | `customer_purchases` reads P-07 `list_revenue` filtered by customer_ref; retention/LTV inputs are those records only. |
| 5 | Every campaign has purpose, audience, budget, measurement, stop/review conditions | Creation requires purpose + ceiling; `expected_results`/review fields carried; metrics raise low-response / CAC-breach alerts from declared expectations; the scenario test runs the full lifecycle. |
| 6 | Purchased/scraped/coerced contacts cannot be imported | Forbidden sources mechanically refused (`purchased_list` et al.); suppression refuses re-import; smoke §5 verifies the purchased-list refusal live. |
| 7 | A suppressed contact cannot be re-imported or messaged | Suppression checked at import and at queue time (test + service paths). |
| 8 | Deceptive claims cannot pass brand/compliance review | Brand-owned prohibited claims block mechanically at content review (`failed_mechanically`); deceptive template patterns refused at creation; smoke §5/§6 verify both live. |
| 9 | A customer has one CRM record (dedupe) | Lead dedupe by email → phone → name\|company slug; conversion links lead → customer 1:1 and refuses reconversion. |
| 10 | Cross-business data stays isolated unless authorised | Integration + security tests: business B cannot read/mutate business A's growth records; owner-wide views are principal-scoped. |
| 11 | Experiment conclusions distinguish significance from noise | `ab_result` reports `statistically_significant_95` and `insufficient_data` verdicts below declared minimum observations; conclusions are owner-declared observations, never invented metrics. |
| 12 | Every growth figure traces to source records | Metrics/attribution/analytics responses carry their source records' ids and the P-07 figures they were computed from; transcripts in `docs/reports/P17_SMOKE_EVIDENCE.txt`. |

## 3. Verification totals (final code)

- **Backend: 909 passed / 0 failed** (873 P-16 baseline + 36 new
  P-17 tests), run in two halves over a C-locale-sorted file
  list — 466 + 443, each agreeing with its own collection —
  after the shared /tmp tmpfs filled during earlier attempts
  (checked `df -h /tmp` first, per the standing lesson; mass
  fixture errors were disk, not code). An unattributed "484
  passed" delivery from a stale background process matched no
  invocation and was discarded, not used.
- **Frontend: 49/49** (46 baseline + 3 new Growth view tests);
  strict TypeScript `npm run build` clean.
- **Live smoke: 22/22** against real uvicorn in controlled
  mode (transcript: `docs/reports/P17_SMOKE_EVIDENCE.txt`).

## 4. Honest limitations and observations

- **No real marketing platform is connected.** Every §26
  surface reports `not_configured` / REQUIRES OWNER
  CONFIGURATION; communications queue with the blocked-dispatch
  note and dispatch returns `dispatch_blocked` — nothing is
  ever sent. Fixtures are labelled fixtures.
- **Attribution is first-touch only** (CRM acquisition
  channel); last-touch and multi-touch are exposed as
  `not_available`, never estimated.
- **No real LLM** (DEF-A2) and **Windows UNVERIFIED**
  (DEF-A1): unchanged, owner-machine items. Persona/ICP/
  content assistance is deterministic machinery over
  owner-supplied inputs.
- **Boot-window login observation (not P-17 code):** during
  this build, a freshly booted server transiently refused the
  correct owner credentials for a short, load-dependent window
  (probed in-process: stored hash and password correct, scrypt
  verify False in the booted process while True in every other
  process; self-heals, and a restarted server accepts
  immediately). The smoke therefore readiness-gates on
  `/health/ready` and retries login patiently (attempt count
  logged in the transcript). Auth behaviour itself — wrong
  passwords refused, guard throttling, session issuance — is
  unchanged P-01/P-10 machinery, covered by the suite; the
  observation is recorded here for the pilot phase rather than
  silently worked around.
- Thresholds (score bands, CAC/LTV conventions, frequency
  caps) are owner-governed defaults in `growth.settings`,
  seeded conservatively and never calibrated against a real
  business — there is no real business yet (DEF-A8).

## 5. §30 sequence handling

The prompt's internal approval steps were handled P-14-style
under the owner's standing one-by-one instruction: the
architecture/audit stage ran first inside the build
(`docs/p17/P17_ARCHITECTURE.md` — data findings, reuse map,
decisions D1–D8), conservative minimal options were taken, and
the choices are reported in the gate summary. No structural
change was made to P-03/P-06/P-07/P-08/P-13/P-16; P-17 only
composes them.
