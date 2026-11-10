# P-03 — Research Source Architecture (§8)

## Principles

- **Provider-independent adapters** over a pluggable transport. No code depends on a specific search provider; there is no search-provider dependency at all in P-03.
- **Registered sources only.** Research can only fetch sources present in the `research_sources` catalogue (seeded from the owner-provided/seed catalogue; owners may register more via `POST /sources`). There is no endpoint that fetches an arbitrary URL.
- **Access rules are hard constraints (§8.2):** no authentication bypass (sources declaring `auth_required` are never fetched — the system holds no credentials), no paywall/CAPTCHA/rate-limit circumvention, a light `robots.txt` check before web fetches (a Disallow for the path refuses the fetch), and HTTP errors (403/404/…) are recorded as *unavailable* with no content used.
- **SSRF guard:** only http/https; `localhost`, `*.local`, `*.internal`, and loopback/private/link-local/reserved literal IPs are refused. The single escape hatch (`research_allow_private_hosts`) is test/staging-only and refused by config validation in production.
- **Every fetch outcome is recorded** per source in the research session: fetched (with document count and evidence added), unavailable (with the truthful reason), or quarantined (injection).

## Transports

| Transport | Use |
|---|---|
| `HttpTransport` | Real HTTP via httpx. Explicit optional proxy (`AUTONOMUS_RESEARCH_PROXY_URL`) for sandboxes whose egress requires one. TLS verification uses an explicit `ssl` default context (platform CA bundle, e.g. `SSL_CERT_FILE`) — verification is never disabled. Response size capped (`research_max_fetch_bytes`, default 512 KB). Custom User-Agent identifies the research client honestly. |
| `MockTransport` | Deterministic fixture transport for tests; unmapped URLs fail truthfully instead of touching the network. |

## Adapters

| Adapter | Access method | Behaviour |
|---|---|---|
| `SeedDocumentAdapter` | `seed_document` | Owner-provided/seed research documents; no network. Documents carry authored claims with a starting classification ceiling and `applies_to` scoping. |
| `WebPageAdapter` | `web_page` | robots check → fetch → HTML-to-text (stdlib parser, scripts/styles stripped) → deterministic price-mention extraction only. In simulation mode it refuses (live fetching disabled). |
| `RssAdapter` | `rss` | Feed fetch → RSS/Atom item extraction (stdlib XML). Publication dates come only from the feed itself. |

## Source catalogue (seeded)

| Key | Type | Reliability | Access | Notes |
|---|---|---|---|---|
| `kdp_official` | official platform docs | primary_official | web_page | https://kdp.amazon.com |
| `etsy_sell` | official platform docs | primary_official | web_page | https://www.etsy.com/sell |
| `gumroad_pricing` | official platform docs | primary_official | web_page | https://gumroad.com/pricing |
| `shopify_pricing` | official platform docs | primary_official | web_page | https://www.shopify.com/pricing |
| `npci_official` | government/industry body | government_regulatory | web_page | https://www.npci.org.in |
| `owner_research_notes` | owner material | owner_provided | seed_document | Fixture documents (labelled) |
| `industry_blog_fixture` | secondary analysis | secondary_analysis | seed_document | Fixture documents (labelled) |
| `community_forum_fixture` | community discussion | unverified_claim | seed_document | Fixture documents (labelled, UNTRUSTED; contains the injection test document) |

## Provenance (§8.4)

Every evidence record stores: source id, source URL, retrieval timestamp (set at extraction), publication date (only when the source states one — otherwise null, never invented), extraction method, reliability-driven classification ceiling, and the source's independence group (used by corroboration; sources sharing a group are not independent).

## Observed live behaviour in this sandbox (9 Nov 2026 smoke)

Shopify pricing fetched successfully (HTTP 200, genuine price mentions extracted). Etsy and NPCI returned HTTP 403 (bot protection) — recorded unavailable, **not** bypassed. KDP and Gumroad timed out through the sandbox egress proxy — recorded unavailable. On the owner's own machine (no sandbox proxy) these outcomes will differ; the recording behaviour is the same.
