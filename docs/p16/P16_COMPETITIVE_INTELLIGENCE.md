# P-16 — Competitive Intelligence (§13)

**Module:** `app/economy/markets.py` · **Table:** `competitor_profiles`

## Declared sources only

A competitor profile cannot be created without `source_refs` —
the public or authorised sources the profile rests on. P-16 in
staging gathers **no** competitive data itself: no scraping, no
monitoring, no feeds. Profiles record what the owner (or a future
authorised process) observed, with the receipts attached.

## The comparison report

`GET /economy/competitor-comparison?market=<market>` returns the
recorded profiles for one market plus `identified_gaps`: for each
recorded competitor weakness, a gap entry labelled as a *reading*
("potential gap to compete on through pricing, function,
experience, speed, specialisation or automation — verify before
acting"). The response states its basis verbatim: "declared
public/authorized sources only".

## Boundaries (§13/§19)

- Strengths and weaknesses are recorded claims with sources, not
  system-verified facts; the API never upgrades them.
- No competitor figure (pricing, revenue, share) is ever blended
  into P-16's own economic views — those read P-07 only.
- Nothing here feeds a score automatically. A human judgement
  recorded as an opportunity factor (§4.3 competitive advantage)
  is the only path from competitive notes to prioritisation.
