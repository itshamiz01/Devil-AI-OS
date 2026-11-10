# P-03 — Evidence Management (§9, §19)

## Record model

Every research claim is an `evidence_records` row: opportunity, source, category (demand / problem / market_size / pricing / platform_rule / competitor / cost / distribution / regulatory / payment / general), claim text, structured comparable value where applicable, **classification**, **reliability class of its source**, retrieval timestamp, source-stated publication date (or null), extraction method, independence group, corroborated-by note, supersedes pointer, and review metadata (reviewer, reviewed-at) for owner-recorded evidence.

## Classification ladder and ceilings

Classifications: VERIFIED > CORROBORATED > SUPPORTING > TENTATIVE > UNVERIFIED, with CONTRADICTED and OUTDATED as flags. A record can never exceed the ceiling its source's reliability permits (`RELIABILITY_CEILING`): official platform/government sources cap at CORROBORATED for extracted facts (VERIFIED is reserved for owner review of owner-grade evidence); secondary analysis caps at SUPPORTING; owner estimates and industry claims cap at TENTATIVE; unverified claims cap at UNVERIFIED. A single source can therefore never produce VERIFIED on its own.

## Corroboration (§9.7)

After each research session, claims sharing a comparable-value key (category + normalized value, e.g. a platform fee percentage) from **two or more independent groups** are promoted to CORROBORATED (bounded by ceiling and by the weakest contributing record). Independence is structural: sources seeded from the same origin share a group and cannot corroborate each other.

## Contradiction (§9.11)

Comparable values that disagree are grouped into clusters. When a majority cluster exists, it keeps/promotes its classification and the minority records are marked **CONTRADICTED**; on a tie both sides are CONTRADICTED. Contradicted evidence is never used by scoring (it is excluded from every supporting set) but remains visible in the report — disagreements are surfaced, not averaged away. Smoke example: Etsy fee claims of 6.5% (two independent fixture sources) vs 0.5% (forum post) → 6.5% CORROBORATED, 0.5% CONTRADICTED.

## Freshness (§9.10)

`fresh / stale / unknown` computed from the source-stated publication date: >540 days old is stale; no stated date is **unknown** — the system never fabricates a date to make evidence look fresh. Staleness is reported in the opportunity report; it does not silently delete evidence.

## Evidence quality — standalone (§16.3)

Computed separately from attractiveness, on a 0–5 scale from: source reliability mix, independent-source count, recency (fresh=1.0, unknown=0.5, stale=0.25 averaged), corroborated-claim ratio, and contradiction ratio. Reported alongside every score and ranking. Staging smoke values: e-book 3.46, planner 3.33, GST tool 2.86, unresearched manual idea 0.0.

## Gaps

`identify_gaps` produces the human-readable "Insufficient verified evidence" items that appear in research summaries and reports: missing demand evidence, missing purchasing-intent evidence, missing competitor evidence, missing commercial analysis, market-size impossibility, unresolved contradictions. Gaps are first-class output, never filled with invention (§32).

## Owner-grade evidence (§18, §22)

`owner_real_world` and `owner_payment` evidence kinds can only be recorded by the owner principal; the API and service both enforce this. They are the only path to validation levels 4 and 5. P-03 records them; it never creates them by transacting (§26).
