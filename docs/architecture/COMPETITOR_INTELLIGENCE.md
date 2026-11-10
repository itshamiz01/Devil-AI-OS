# P-03 — Competitor Intelligence (§11)

## Model

`competitors` rows: opportunity, name, website, offer, target audience, price (recorded value only), strengths, weaknesses, distribution channels, differentiation, and `evidence_record_ids` linking every claim to stored evidence. Competitors enter the system as research finds them (recorded with their evidence) — the candidate library deliberately contains **zero** fabricated competitor entries; competitor depth in staging comes only from what tests/smoke explicitly record.

## Analysis (`GET /opportunities/{id}/competitor-analysis`)

- **Coverage statement first**: number of competitors recorded; zero competitors is reported as a research gap, never as "no competition exists".
- **Evidence gaps (§11.4)**: competitor-linked evidence below CORROBORATED is listed per competitor as an explicit gap.
- **Unserved audiences**: competitor audiences vs the opportunity's target segment (set difference over recorded data only).
- **Common weaknesses / complaints**: frequency-counted from recorded weakness/complaint fields.
- **Price positioning**: min/max/median over recorded competitor prices only.
- **Distribution channels in use**: union of recorded channels.
- **Saturation input**: competitor count feeds the market analysis saturation level, which feeds the competitive-opportunity score (0 recorded → saturation *unknown*, scored neutrally, not as an empty market).

## Acceptance mapping

Acceptance scenario C (competitor-gap analysis) is covered by an integration test: two recorded competitors with evidence produce identified gaps (an unserved audience and an uncorroborated competitor claim), and the empty case states its gap honestly.
