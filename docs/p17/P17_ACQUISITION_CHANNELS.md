# P-17 — Acquisition Channels (§4.3)

**Surface:** `POST /api/v1/growth/businesses/{id}/channels`,
`GET …/channels` (ranking).

## Catalogue

Thirty channel keys in four categories (`constants.CHANNELS`):
organic (SEO, content marketing, educational articles, YouTube,
social organic, community, referral programs, organic partnerships,
directories, newsletter), paid (search/social/display ads, sponsored
content, influencer, industry publications, paid directories),
direct (business partnerships, authorised outreach, sales
conversations, networking, B2B prospecting, inbound sales) and
product-led (free trial, freemium, demos, referral features, free
tools, education resources).

## Evaluation

Each evaluation holds declared estimates (target audience,
estimated reach, estimated acquisition cost, conversion potential,
time to results, competition, platform dependency, compliance,
workload) labelled ESTIMATE, plus six factor scores (audience fit,
economics, conversion potential, speed, independence, feasibility).
`scoring.channel_value` computes the expected-value score; the
economics factor carries weight 3 so a channel is never recommended
merely because it can generate traffic — the ranking response
explicitly directs the reader to recorded CAC (budget view) before
committing spend.

## Honest state

No channel implies a connected platform. Every channel response
carries `integration_state: not_configured`; the integrations read
model lists all eight external surfaces as REQUIRES OWNER
CONFIGURATION. Channels not yet evaluated are listed as such.
