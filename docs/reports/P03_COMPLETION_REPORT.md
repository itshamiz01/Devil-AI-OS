# P-03 Completion Report (§35)

- **Phase:** P-03 — Opportunity Discovery, Research and Analysis
- **Date:** 2026-11-03
- **Branch:** `arena/0a4e9e66-devil-ai-os`, HEAD `26cd88d`
- **Verdict:** **Implementation complete. The phase cannot deliver real market research, and does not pretend to.**
- **Gate:** Work stops here per §36. **P-04 has not been begun.**

## 1. The one thing to read first

**No P-03 output describes a real market.** Not one figure, price, review count,
competitor name, market size, search volume or trend anywhere in this phase's code,
tests, fixtures, documentation or sample report was observed in the world.

The reason is environmental and was established by probe rather than assumed. Outbound
network access is limited to six hosts — `github.com`, `codeload.github.com`,
`api.github.com`, `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`. None is a
search engine, marketplace, forum, trend service, government statistics site or vendor
pricing page. An HTTPS-GET probe of 16 research URLs found **2 usable**, and neither is
a market source. The full evidence is at
[`P03_SOURCE_ACCESS_PROBE.txt`](P03_SOURCE_ACCESS_PROBE.txt).

A subtlety worth recording because it nearly produced a false conclusion: a
**TCP-connect probe reports a false positive in this environment.** A transparent proxy
completes the handshake and then drops the TLS negotiation, so 28 of 29 hosts appeared
"reachable" at the socket level. Only an HTTP-level probe tells the truth. Any future
assessment of this environment's network access must probe at the application layer.

Given that, three responses were possible: fabricate plausible market data so the
pipeline has something to chew on; ship a catalog of realistic-looking sources that fail
at runtime; or build the real acquisition layer, configure it to deny all egress, and
make every absence explicit in the output. The third was chosen and is recorded in
[ADR-0018](../decisions/ADR-0018-NO-INVENTED-MARKET-DATA.md).

The consequence is that **the thing this phase actually tests is the system's behaviour
under absence** — and that behaviour is the part that matters. With zero evidence the
system returns `INSUFFICIENT_EVIDENCE`, not recommendable, attractiveness `0`, TAM and
SOM `None`, no invented business model, validation level 0, market verdict
`insufficient_data`, saturation `unknown`, and nine report sections each stating what
could not be determined. It does not guess, does not default to an optimistic figure,
and does not fail silently.

## 2. What was delivered

Seventeen modules totalling 9,743 lines under `backend/app/opportunities/`; twelve
database tables across two migrations; fifteen HTTP paths with seventeen operations; one
new task handler; four new permission codes; ten new event types; nine new configuration
settings; ten architecture documents; five ADRs; five reports; and an OpenAPI artifact.

**504 tests pass, 0 fail**, of which 99 are new in this phase. P-02's 405 tests pass
unchanged, so nothing regressed.

The pipeline runs end to end: discovery produces candidates from six methods, screening
blocks prohibited candidates *before* any acquisition stage, research collects evidence
or records refusals, four analysers interpret what was collected, commercial feasibility
projects three scenarios and checks the budget, risk and governance evaluate what may be
pursued, scoring produces an explainable classification, the validation ladder states
what has actually been demonstrated, and the report renders all nine sections with its
own epistemic status declared.

## 3. Decisions that need the owner's ratification

These are choices made during implementation that the brief did not settle. Each is
listed so it can be accepted, changed or overruled; none is hidden in code.

**Structural**

1. A **flat** `app/opportunities/` package rather than §4's nested tree — ADR-0019.
2. §16 rendered as **10 weighted dimensions summing to 100**, with `evidence_quality`
   scored but excluded from attractiveness and reported separately.
3. **Monetary values stored as decimal text**, because SQLite has no decimal type —
   ADR-0022.
4. Assessment-level **summaries stored as JSON on the opportunity row**, independently of
   their child rows, because zero risk findings and a blocked assessment are otherwise
   indistinguishable.
5. The engine is reached from the task handler via an explicit **`set_research_backend`
   binding**, failing loudly when unbound — ADR-0021.
6. A research sweep that reaches **no source completes rather than fails**, because the
   refusals are the finding and a failure would be retried pointlessly.
7. `research.sweep` is **`essential=False`**, so an owner emergency stop denies it.
8. **`enqueue-research` schedules nothing** — it is an owner-requested immediate
   submission only.
9. `POST /{id}/report` returns **409** when the opportunity has not been analysed.
10. `_persist()` treats a storage failure as **non-fatal**, returning
    `persistence_errors` rather than discarding an already-computed analysis.
11. The history endpoint returns **`persisted` and `in_memory` separately**, each with
    its own count.
12. Recovery restores **visibility only** — no sweep dispatched on boot, nothing
    re-scored, no state advanced.

**Numeric thresholds with no external authority**

13. `MINIMUM_CONTRIBUTION_MARGIN = Decimal("0.20")`.
14. `MIN_EVIDENCE_COVERAGE_PCT = 60`.
15. `MIN_RECOMMEND_ATTRACTIVENESS = Decimal("3.0000")`.
16. `MIN_ADMISSIBLE_PER_LEVEL = {0:0, 1:1, 2:1, 3:2, 4:1, 5:1}` — level 3 requires two
    admissible records, the rest one.
17. `PERMITTED_LEVEL_4_INPUTS` (6) and `PERMITTED_LEVEL_5_INPUTS` (3) — §18 names the
    levels but not the input vocabulary.
18. `RELIABILITY_MULTIPLIER` and `CLASSIFICATION_VALUE` — the two evidence-weighting
    tables.
19. **The lower-median price rule** — for an even number of observations the lower of the
    two middle values, biasing estimates conservatively.
20. **`EvidenceExtractor`'s `supporting` classification ceiling** — no machine-extracted
    figure can alone justify `verified`.
21. Defence-eligible prohibited terms in a genuinely defensive context escalate to
    severity **`high`, non-blocking**, rather than `blocking`.

**Known approximations and gaps**

22. `default_source_catalog()` **ships empty** — ADR-0018.
23. `research_permitted_hosts` **defaults to empty = deny all**.
24. `research_max_response_bytes` is mapped onto `NetworkPolicy.max_response_chars`;
    **bytes versus characters is an approximation**.
25. `strategic_fit` is **unscored unless the owner states capabilities**, so coverage is
    typically 95% rather than 100%.
26. Budget-driven discovery archetypes **assert affordability only** and start at
    validation level 0.
27. The **P-02 evidence bridge is one-way and lossy on time**; `last_load_refusals`
    records what it declined.
28. `opportunities.recommendable` is a **derived column**, not a schema field.
29. Enum member lists for §6, §7 and §9 were **reconstructed from the brief's prose**,
    which describes them narratively rather than enumerating them.
30. 8 of the 14 documents §2 names **do not exist** in this repository; the equivalents
    that do are listed in ADR-0019.

**Still open from earlier phases:** D-01, D-11 (`pyproject.toml` declares
`requires-python = ">=3.13"` while the environment runs 3.11.2 — unmet and unenforced),
D-12, D-14 (**no lockfile**; `requirements.txt` carries 12 exact pins), D-15, and the
merge of PR #2.

## 4. Defects found and fixed

Nine were real product defects. The most consequential:

* **`GET /{id}` omitted `business_model` and `distribution`**, so report sections E and
  G described data the API would not return.
* **A NOT NULL column added without `server_default`** made revision `72ee9705e18f` fail
  on a populated database. `default=dict` is Python-side and never reaches DDL. An
  empty-database round trip passed regardless, which is why the defect survived its first
  test — and why a populated-database test now exists.
* **Pydantic models in a JSON column** raised `TypeError` at commit. Fixed once with a
  shared serialisation pair applied to all five sites, rather than five times.
* **A `.value`-versus-`.name` bug in `governance.py`** made both the permitted and
  prohibited frozensets empty. The tests **passed vacuously** until the set sizes were
  printed — a reminder that a passing test over an empty collection proves nothing.
* **A duplicated `mapped_column` declaration** was silent dead code; the migration was
  correct and the source was wrong.

## 5. On the test suite's own honesty

`test_opportunities_engine.py` failed 20 of 59 tests on its first run. **Every failure
was an invented name in the test file** — `EvidenceType.MODEL_INFERENCE`,
`NetworkPolicy.permits`, `BreakEvenResult.reachable`, `BudgetCompatibility.affordable`,
`outcome.score.weights_fingerprint`, and others. Each was corrected by introspecting
`model_fields`, `Enum.__members__` and `inspect.signature` before rewriting the
assertion.

**No assertion was weakened, and two became stronger.** The `RetrievedContent` test now
asserts a *refusal* where it had assumed a coercion, and the break-even test now pins
three derived figures where it previously pinned one. Three further failures were the
test being wrong about the domain rather than the API: terminal states may be archived,
`discovered → researching` is illegal by design because screening is mandatory, and an
estimated cost must state the assumption behind it.

Two validators caught defects in the tests rather than in the code —
`problem_importance_basis` and `rating_provenance`. In both cases the fix was to supply
the missing justification, not to relax the validator. That is the intended dynamic, and
it is recorded here because it is the strongest available evidence that the validators
are doing their job.

## 6. The roadmap's own exit criterion is not met

[`DEVELOPMENT_ROADMAP.md`](DEVELOPMENT_ROADMAP.md) states P-03's exit criterion as:

> *"Real opportunities ranked with traceable evidence and declared coverage"*

and lists *"live authorized-source sample"* among its verification methods.

**Neither is satisfied, and this report does not claim otherwise.**

The two halves of that criterion fail for different reasons, and the distinction matters:

| Half | Status | Why |
|---|---|---|
| *ranked with traceable evidence* | **Mechanism proven, content absent** | Ranking is deterministic and reproducible across identical calls, every dimension carries its `evidence_ids` and `justification`, and `coverage_pct` reports what could not be assessed. What has never been ranked is *real* evidence, because none could be acquired |
| *declared coverage* | **Met** | Coverage is declared and is not inflated: `strategic_fit` is reported unscored rather than awarded a neutral value, so coverage reads 95% instead of 100%. The sample report demonstrates this |
| *live authorized-source sample* | **Not possible here** | No market source is reachable — L-31. The acquisition layer is implemented and unit-tested through an injected transport, but has never contacted a real host (L-33) |

The roadmap also lists P-03's principal risks as *"fabricated demand, stale sources,
injection, unlawful collection"*. Three of the four are now structurally addressed:
fabricated demand is prevented by the epistemic floor and the empty catalog; injection is
addressed by `RetrievedContent` refusing a non-`external` trust domain; unlawful
collection is addressed by the required `licensing` field on every source descriptor and
the 13 prohibited categories. **Stale sources cannot be exercised at all**, because there
are no sources — `mark_stale` is implemented and tested against fixtures only.

The honest reading is that P-03 delivered the *capability* the roadmap describes and
could not deliver the *demonstration*, for an environmental reason that is documented,
probed and reversible by configuration rather than by code.

## 7. Recommendation

**P-03 is complete as far as this environment permits, and should not be extended to
produce market findings.** The correct next step is the owner's §36 gate decision.

Two options are worth putting plainly:

* **Accept the phase as built** — a fully implemented, fully tested opportunity pipeline
  whose research layer is configured to deny all egress, and which reports absence
  honestly. It becomes useful the moment the owner supplies permitted hosts and source
  descriptors; no code change is required.
* **Re-run the research layer from an environment with market-source access** — the
  acquisition, extraction, corroboration and analysis paths are implemented and unit
  tested, but they have **never run against real-world data**. Until they do, the claim
  "this system finds real business opportunities" is unverified, and no P-03 artifact
  asserts it.

What should **not** happen is treating the passing test suite as evidence that the
research capability works against live sources. It is evidence that the pipeline behaves
correctly under the conditions it was given — which, in this environment, is the
condition of having no sources at all.

## 8. Documents in this set

| Document | Purpose |
|---|---|
| [`P03_IMPLEMENTATION_REPORT.md`](P03_IMPLEMENTATION_REPORT.md) | What was built, commit by commit, and the defects fixed |
| [`P03_TEST_REPORT.md`](P03_TEST_REPORT.md) | Suite composition, coverage, how the 59 engine tests reached green |
| [`P03_TEST_RESULTS.xml`](P03_TEST_RESULTS.xml) | Machine-readable JUnit evidence — 504 tests, 0 failures |
| [`P03_SECURITY_REPORT.md`](P03_SECURITY_REPORT.md) | Egress, untrusted content, credentials, authority boundaries |
| [`P03_SOURCE_ACCESS_PROBE.txt`](P03_SOURCE_ACCESS_PROBE.txt) | The network probe that established the central constraint |
| [`P03_SAMPLE_OPPORTUNITY_REPORT.md`](P03_SAMPLE_OPPORTUNITY_REPORT.md) | A generated report, labelled synthetic — §21 |
| [`P03_COMPLETION_CHECKLIST.md`](P03_COMPLETION_CHECKLIST.md) | §34, requirement by requirement |
