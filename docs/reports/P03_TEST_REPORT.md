# P-03 Test Report

**Run:** 9 November 2026 · **Command:** `backend/.venv/bin/python -m pytest tests/ -q` · **Result: 172 passed, 0 failed (31.25s, one run)**

## Counts

| Suite | Tests | Result |
|---|---|---|
| P-01 regression (`test_api.py`, `test_core_unit.py`, `test_security.py`) | 76 | ✅ all pass, untouched |
| P-02 regression (`test_p02_unit.py`, `test_p02_integration.py`, `test_p02_security.py`) | 35 | ✅ all pass; 2 assertions updated for documented additive change (migration head, handler registry) — see implementation report |
| **P-03 unit** (`test_p03_unit.py`) | 26 | ✅ |
| **P-03 integration** (`test_p03_integration.py`) | 21 | ✅ |
| **P-03 security** (`test_p03_security.py`) | 14 | ✅ |
| **Total** | **172** | ✅ |

Baseline before building (Stage-1 audit): 111/111 passed in 18.25s — matches the P-02 gate exactly.

## Acceptance-scenario mapping (§29)

| Scenario | Test / demonstration |
|---|---|
| A — $50-budget discovery | `test_scenario_a_fifty_dollar_discovery` + smoke brief |
| B — India-specific research | `test_scenario_b_india_brief_scopes_candidates` + smoke Investigation 3 (GST tool) |
| C — competitor-gap analysis | `test_scenario_c_competitor_gap_analysis` |
| D — attractive idea, no evidence | `test_scenario_d_attractive_idea_without_evidence` + smoke (AI Astrology → NEEDS_MORE_EVIDENCE, EQ 0.0) |
| E — budget-incompatible | `test_scenario_e_budget_incompatible` + smoke (POD $120, inventory $2,000 → INCOMPATIBLE) |
| F — saturated market | `test_scenario_f_saturated_market_scores_lower` |
| G — untrusted webpage injection | `test_injection_in_web_page_is_quarantined` (MockTransport) + `test_injection_fixture_document_quarantined` + smoke (forum fixture quarantined live in the pipeline) |
| H — no reliable market info | `test_scenario_h_no_reliable_market_information` (market size "cannot be established") |
| I — strong research, no verified sales | `test_scenario_i_strong_research_without_sales_caps_below_5` (Level 4 reachable with owner evidence; Level 5 refused without payment proof) |

## Coverage highlights of the new suites

- **Unit (26):** lifecycle transition guards; slug dedup; compliance prohibited/high-risk patterns; SSRF guard (scheme, loopback, private IP, metadata host); robots allow/disallow; HTML price extraction verbatim (incl. comma amounts, per-month flags, multi-price lines); commercial math incl. negative unit economics and unknown-cost handling; evidence-quality computation; validation ladder rungs 0–3 from synthetic records; ADR-005 weights present and summing to 1.0.
- **Integration (21):** migration head + all 25 tables on a fresh DB; discovery screening outcomes for the full candidate library (duplicate, 2× incompatible, 1× compliance-blocked); geography/category scoping; research-as-P-01-task with corroboration promotion (KDP royalty → CORROBORATED across independent groups); contradiction clustering (Etsy 6.5% vs forum 0.5%); full pipeline market → commercial → score → validate; claimed Level 4/5 refusals (422) and the owner-evidence path to Levels 4 and 5; saturation effect; rankings reproducibility (identical re-score); lifecycle API guards; recheck dedup; report structure (facts/estimates separated, gaps listed).
- **Security (14):** injection quarantine via fixture and via web page (document contributes zero claims; security event exists; audit record exists); SSRF rejections; robots disallow refusal; auth-required source never fetched; simulation mode blocks live sources; agent principal cannot edit scoring weights (403); agent/service cannot record owner-grade evidence (403); service principal forbidden from the opportunities API (403); unauthenticated request rejected (401); emergency mode blocks research submission.

## Smoke evidence

`docs/reports/P03_SMOKE_EVIDENCE.txt` — real uvicorn (supervised mode) transcript: health, owner login, P-02 mission (planning 422, recorded honestly), $50 brief → discovery (14 opportunities) → three full-pipeline investigations → prohibited candidate hard-rejected → no-evidence candidate to NEEDS_MORE_EVIDENCE → injection events → live Shopify fetch evidence → rankings + engine status. Live fetch outcomes recorded as they happened (Shopify 200; Etsy/NPCI 403; KDP/Gumroad timeout).

## Not covered / not claimed

- No test claims a real market fact: all evidence fixtures are labelled test data.
- Live-fetch tests use `MockTransport`; real-network behaviour is demonstrated only by the smoke run (and is environment-dependent by nature).
- Windows execution remains unverified (carried P-00 item).
