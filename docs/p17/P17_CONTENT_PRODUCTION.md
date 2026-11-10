# P-17 — Content Production (§6)

**Surface:** `/api/v1/growth/businesses/{id}/content`,
`/api/v1/growth/content/{id}/review|approve|schedule|release`.

## Workflow

Content kinds follow the prompt (blog article, landing copy,
product description, email, newsletter, ad copy, social caption,
educational, case study, announcement, sales material, graphics,
creatives, infographic, banner, presentation, video/podcast
scripts, other). Every item moves through explicit review state —
`fact_check`, `brand_consistency`, `copyright_licensing`,
`quality`, each `pending | pass | fail` — and cannot be approved
until all four pass.

## The mechanical brand check

A brand-consistency "pass" is checked mechanically against the
owning business's own brand profile: if the body contains any of
that business's `prohibited_claims`, the pass is refused, the
review is recorded as failed with the violations listed, and the
refusal is audited. Brands never mix: business A's claims are never
checked against business B's profile.

## Release honesty

The system publishes nothing — no platform is connected. Release
records an *owner-attested external reference* supplied by the
owner and labels the response accordingly ("AUTONOMUS posted
nothing"). Scheduling records an intended time only.
