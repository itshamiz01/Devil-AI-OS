# P-16 — Asset Commercialization (§7)

**Module:** `app/economy/ventures.py` · **Tables:** `commercial_assets`,
`commercialization_proposals`

## The asset register

Owner-declared internal assets: software, templates, content
libraries, automations, datasets, brand assets, research and
documentation. Each record carries an **ownership status** and a
**commercial-use permission flag** — the two facts that decide
whether commercialization may even be proposed for approval.

## The rights gate

A commercialization proposal can only be **approved** when the
asset's `ownership_status` is `verified_owner` **and**
`commercial_use_permitted` is true. Anything else — unverified
ownership, unclear rights, third-party material — is refused at
approval time with the reason named. This is §7's rule enforced
mechanically, not a reminder.

## Handoff — into governance, not around it

An approved proposal hands off to **P-03** (`create_opportunity`,
category `digital_products`): the commercial idea enters the same
discovery pipeline as any other opportunity. P-16 creates **no
business** and sells **nothing**; P-06's gates (including the
evidence-level eligibility rules that blocked real creation in
P-06) still decide whether anything is ever built. A scenario test
pins this: after a full commercialization handoff, the business
count is unchanged.

Pricing models (`one_time`, `subscription`, `licence`,
`usage_based`, …) are recorded as proposal data. No price is ever
presented as achievable revenue; projected figures stay in P-03/
P-07's projected fields, separate from collected.
