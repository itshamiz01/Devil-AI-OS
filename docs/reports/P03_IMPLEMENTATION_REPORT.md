# P-03 Implementation Report

- **Phase:** P-03 — Opportunity Discovery, Research and Analysis
- **Branch:** `arena/0a4e9e66-devil-ai-os`
- **Status:** Implementation complete; **awaiting the owner's §36 gate decision**
- **Tests:** 504 passed / 0 failed — see [`P03_TEST_REPORT.md`](P03_TEST_REPORT.md)
- **API surface:** 53 paths / 58 operations (P-02: 38 / 41) — [`shared/openapi-p03.json`](../../shared/openapi-p03.json)

## 1. What was built

Seventeen modules under `backend/app/opportunities/` totalling 9,743 lines, twelve
database tables across two migrations, fifteen HTTP paths with seventeen operations,
one new task handler, four new permission codes, ten new event types, nine new
configuration settings, ten architecture documents, five ADRs and this report set.

The layer takes an owner's stated capabilities, budget, jurisdictions and observed
problems, and produces ranked, evidence-backed opportunities — or an explicit,
section-by-section statement of what could not be determined.

## 2. Commit chain

| Commit | Stage | Content |
|---|---|---|
| `551bcf7` | P-02 baseline | 405 tests passing |
| `186e574` | 1–3 | `schemas.py` (2091 lines), `sources.py`, `commercial.py`, `risk.py`, `scoring.py` |
| `b6e7e29` | 4–6 | `validation.py`, `evidence.py`, `lifecycle.py`, `discovery.py` |
| `8744b21` | 7 | `governance.py` |
| `16eb11c` | 8 | `analysis.py` |
| `ed4fea4` | 9–11 | `research.py`, `reports.py`, `engine.py`, `__init__.py`, `EvidenceExtractor` |
| `564f3c1` | 12 | Persistence — **a parallel implementation produced on the remote**; adopted rather than discarded |
| `395e270` | 12b | Audit script, 16 persistence tests, migration-safety fix, assumption serialisation fixes |
| `2d3f113` | 13 | Full wiring: task handler, routes, config, permissions, events, factory, OpenAPI, 24 API tests |
| `26cd88d` | 14 | 59 engine unit tests |

`564f3c1` deserves a note. A push was rejected because the remote already held a
different stage-12 implementation of the same work. Rather than force-push, the local
branch was reset to the remote, the remote's implementation was adopted, and the unique
local contributions — the static persistence audit, the 16 persistence tests, the
populated-database migration fix — were layered on top as `395e270`. **No pushed commit
was ever amended or rewritten.**

## 3. Stage 13 wiring

The modules existed but were not part of the running OS. Stage 13 connected them:

* **`app/tasks/handlers.py`** gained a fourth handler, `research.sweep`
  (`essential=False`, `retryable=True`), plus `RESEARCH_STAGES`,
  `ResearchSweepPayload`, and the `set_research_backend` / `clear_research_backend`
  binding. `HANDLERS` went from 3 to 4. See
  [ADR-0021](../decisions/ADR-0021-RESEARCH-HANDLER-BACKEND-BINDING.md).
* **`core/application.py`** binds the backend after `initialize_opportunities` and
  clears it in the shutdown `finally` before `services.db.dispose()`.
* **`routes/opportunities.py`** — 17 endpoints. Literal paths are declared before
  `/{opportunity_id}`. Every request model is `ConfigDict(extra="forbid")`. Domain
  `ValueError`s are converted to `ConflictError` at the boundary so a state-machine
  refusal is a 409, not a 500.
* **`POST /{id}/enqueue-research`** — owner-requested immediate submission only. It
  publishes `ResearchSweepCompleted` only when a task was actually dispatched, and
  returns `autonomous_scheduling: false`.
* **`config.py`** +9 settings (54 total), **`policies.py`** +4 permissions (28 total),
  **`events.py`** +10 event types (41 total), **`factory.py`** the composition root.

## 4. Configuration added

| Setting | Default | Purpose |
|---|---|---|
| `opportunities_enabled` | `True` | Phase flag |
| `research_permitted_hosts` | `""` | **Empty = deny all egress** |
| `research_max_sources_per_sweep` | `10` | Sweep bound |
| `research_timeout_seconds` | `15.0` | Per-request timeout |
| `research_max_response_bytes` | `1000000` | Response cap |
| `research_max_evidence_per_sweep` | `200` | Evidence bound |
| `opportunity_minimum_validation_level` | `3` | Recommendation gate |
| `opportunity_max_open` | `50` | Concurrency bound |
| `evidence_stale_after_days` | `180` | Default shelf life |

All nine are documented in [`CONFIGURATION_REFERENCE.md`](../architecture/CONFIGURATION_REFERENCE.md)
and `.env.example`; `scripts/audit_config_docs.py` reports OK — 54 fields, 54
documented, 47 `.env.example` keys, 1 inert.

`research_max_response_bytes` is mapped onto `NetworkPolicy.max_response_chars`.
**Bytes versus characters is an approximation**, and is listed for owner ratification.

## 5. Defects found and fixed

Nine were real product defects rather than test errors:

1. **`GET /{id}` omitted `business_model` and `distribution`**, so report sections E
   and G described data the API would not return. Both added.
2. **`Opportunity.recommendable` was declared twice** — silent dead code, last
   declaration winning. The migration had only one column, so behaviour was correct and
   the source was wrong.
3. **A NOT NULL column added without `server_default`** made revision `72ee9705e18f`
   fail on a populated database with `Cannot add a NOT NULL column with default value
   NULL`. `default=dict` is Python-side and never reaches DDL. An empty-database round
   trip passed regardless, which is why the defect survived the first test. Rewritten
   with `server_default=sa.text("'{}'")` and a populated-database test added.
4. **Pydantic models in a JSON column** raised `TypeError` at commit, surfacing as
   `StatementError`. Fixed once with a shared `_assumptions()` / `_to_assumptions()`
   pair applied to all five read and write sites.
5. **`EvidenceQualityStats.model_dump()`** — it is a plain class, not a model. Fixed to
   `as_dict()`.
6. **`self.screen` shadowed a method** on the engine, silently.
7. **A `.value`-versus-`.name` prefix bug in `governance.py`** made both the permitted
   and prohibited frozensets empty. The tests passed vacuously until the set sizes were
   printed.
8. **Storing only child rows lost the parent verdict** — zero risk findings and a
   blocked assessment read back identically. Summaries are now persisted independently
   on the opportunity row, and the repository raises on an unknown parent.
9. **A workflow stage that counted instead of producing** hid a missing implementation.

## 6. Design decisions recorded as ADRs

| ADR | Decision |
|---|---|
| [ADR-0018](../decisions/ADR-0018-NO-INVENTED-MARKET-DATA.md) | No invented market data — empty source catalog, deny-all egress allowlist |
| [ADR-0019](../decisions/ADR-0019-FLAT-OPPORTUNITY-PACKAGE.md) | A flat `app/opportunities/` package rather than §4's nested tree |
| [ADR-0020](../decisions/ADR-0020-NO-SPENDING-SURFACE.md) | §26's spending prohibition is structural — no endpoint, permission or config key |
| [ADR-0021](../decisions/ADR-0021-RESEARCH-HANDLER-BACKEND-BINDING.md) | Explicit handler-to-engine binding; a no-source sweep completes rather than fails |
| [ADR-0022](../decisions/ADR-0022-MONETARY-VALUES-AS-DECIMAL-TEXT.md) | Monetary values as decimal text; assessment summaries stored independently |

## 7. Limitations

The dominant one is environmental and cannot be fixed in code: **no live market source
is reachable from this build environment**, so no P-03 output describes a real market.
`default_source_catalog()` ships empty, `research_permitted_hosts` defaults to deny-all,
and every acquisition attempt produces a refusal. See
[`P03_SOURCE_ACCESS_PROBE.txt`](P03_SOURCE_ACCESS_PROBE.txt) and
[ADR-0018](../decisions/ADR-0018-NO-INVENTED-MARKET-DATA.md).

Further limitations, all listed for owner ratification:

* **No opportunity can reach validation level 4 or 5** in this phase. Both rungs require
  a `transaction_record`, and §26 prohibits collecting payment.
* **`ResearchScheduler` does not decide timing.** `autonomous_scheduling` is `False`;
  §24 defers scheduling to P-12.
* **Recovery restores visibility only.** No sweep is dispatched on boot, nothing is
  re-scored, no state is advanced.
* **The P-02 evidence bridge is one-way and lossy on time.** `EvidenceStore.to_p02`
  converts into the P-02 vocabulary; `last_load_refusals` records what the bridge
  declined.
* **`strategic_fit` is unscored unless the owner states capabilities**, so coverage is
  typically 95% rather than 100%.
* Several numeric thresholds have **no external authority** and are the author's
  choices: `MINIMUM_CONTRIBUTION_MARGIN = 0.20`, `MIN_EVIDENCE_COVERAGE_PCT = 60`,
  `MIN_RECOMMEND_ATTRACTIVENESS = 3.0000`, the `MIN_ADMISSIBLE_PER_LEVEL` table, and the
  level-4 and level-5 input allowlists.
* **The lower-median price rule is a choice**, biasing estimates conservatively rather
  than reporting a market average.
* **`EvidenceExtractor`'s `supporting` classification ceiling is a choice** — no
  machine-extracted figure can alone justify `verified`.
* **`pyproject.toml` declares `requires-python = ">=3.13"`** while the environment runs
  3.11.2. This is unmet and unenforced, and predates P-03.
* **No lockfile** exists (D-14, still open); `requirements.txt` carries 12 exact pins.
