# Opportunity Risk and Governance (P-03)

Covers `backend/app/opportunities/risk.py` — §14 — and `governance.py` — §15 and §26. For the system-wide governance model see [AGENT_GOVERNANCE.md](AGENT_GOVERNANCE.md); this document covers the two components P-03 adds.

## 1. Two different questions

These modules are frequently conflated and are not the same thing:

* **`RiskEngine`** asks *"is this opportunity risky?"* — legal, regulatory, tax, IP, platform, payment, privacy, consumer-protection, ethical, reputational, and prohibited-category exposure. Its answer can be `acceptable` with findings attached.
* **`ComplianceScreen` / `GovernanceGate`** ask *"may the system pursue this at all?"* — and their answer is a hard stop.

A high-risk opportunity is still analysed and reported, with its risks named. A prohibited one is blocked before any research runs.

## 2. `RiskEngine`

`assess(*, text, category=None, jurisdictions=(), platforms=(), extra_findings=())` → `RiskAssessment`.

`RiskAssessment`: `blocked`, `data_gaps`, `findings`, `highest_severity`, `jurisdictions_considered`, `prohibited_category_matched`, `reasons`, `verdict`.

`RiskFinding` requires `category`, `severity` and `description`, and optionally carries `finding_id`, `jurisdiction`, `platform`, `mitigation`, `evidence_ids` and `blocks_recommendation`.

`category` is a `Literal` of eleven values — **not an enum**: `legal`, `regulatory`, `tax`, `intellectual_property`, `platform_policy`, `payment_policy`, `data_privacy`, `consumer_protection`, `ethical`, `reputational`, `prohibited_category`.

`severity` is the five-value `RiskSeverity`: `negligible`, `low`, `medium`, `high`, `blocking`, ordered by `RISK_SEVERITY_RANK`. `RiskLevel` (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`) is the separate four-value vocabulary used for aggregate reporting.

`blocks_recommendation` is per-finding, so a single `blocking` finding can prevent a recommendation while the rest of the analysis still stands and is still reported.

### The 13 prohibited categories

`PROHIBITED_CATEGORIES` maps a category name to the terms that identify it. 91 terms in total:

| Category | Terms |
|---|---|
| illegal goods or services | 8 |
| weapons and explosives | 7 |
| controlled substances | 7 |
| adult and pornographic content | 5 |
| fraud, deception and astroturfing | 14 |
| unauthorised intrusion and abuse tooling | 10 |
| academic dishonesty | 6 |
| unlicensed financial or medical practice | 9 |
| sanctions and tax evasion | 5 |
| gambling without a licence | 4 |
| exploitation of minors | 5 |
| plagiarism and content theft | 6 |
| deceptive dropshipping and misrepresentation | 5 |

When a category matches, `prohibited_category_matched` names it and `verdict` becomes `blocked`. **A block must always name the category it matched** — an unexplained block is not actionable by the owner.

### Context-sensitive matching

A naive keyword blocklist over-rejects, because the same term appears in legitimate defensive work. "Detect credential stuffing" and "credential stuffing for hire" contain the same phrase and mean opposite things.

Matching therefore uses a bounded window of `CONTEXT_WINDOW = 80` characters around each hit and consults two marker sets:

* `DEFENSIVE_MARKERS` — 28 terms: `against`, `anti`, `analysis`, `audit`, `awareness`, `compliance`, `detect`, `detection`, …
* `OFFENSIVE_MARKERS` — 16 terms: `buy`, `crack`, `download`, `for hire`, `hire`, `kit for`, `order`, `provide access`, …

Only the 18 `DEFENCE_ELIGIBLE_TERMS` may be downgraded by defensive context at all; a term describing harm to a person is never eligible. **Offensive markers win ties** — where both appear, the term is treated as offensive. And where the surrounding text is genuinely ambiguous, the **default is to block**.

A defence-eligible term found in a defensive context escalates to severity `high` rather than `blocking`. That is a design choice, listed for owner ratification: it keeps legitimate security-analysis opportunities workable while ensuring they carry a prominent finding rather than passing silently.

### Regulated categories and platform rules

`REGULATED_CATEGORIES` (6) — `data handling`, `education and certification`, `financial services`, `food and consumables`, `gambling and gaming`, `health and medical` — produce `regulatory` findings via `regulated_findings`. These do **not** block. Operating in a regulated space is legal; operating in it unknowingly is not, so the finding exists to make the owner aware.

`PLATFORM_POLICY_RULES` (8) produce `platform_policy` findings via `platform_findings`, keyed on the platform named in the input. A channel that violates a platform's terms is a real risk to the opportunity even where nothing illegal is involved.

`jurisdictions_considered` records which jurisdictions were actually evaluated, so an assessment performed with no jurisdiction supplied is visibly unscoped rather than silently global.

## 3. `ComplianceScreen`

Two methods: `scan_candidate(...)` and `scan_text(...)`. This is the component `OpportunityEngine.screen` calls immediately after opening a candidate.

Its output is a `ScreeningResult`: `passed`, `compliance_blocked`, `rejections`, `missing_constraints`, `duplicate_of`, `next_state`.

The ordering is the important part. A candidate that fails the compliance screen is moved to `blocked_by_compliance` and the research workflow **halts at `initial_screening`** — no source selection, no acquisition, no evidence extraction. The state is terminal for practical purposes: `blocked_by_compliance` may only transition to `archived`, never back into research.

Acquiring evidence for a prohibited opportunity would be a step toward pursuing it. Refusing to look is the point.

## 4. `GovernanceGate`

`authorize(action, *, detail=None)` → `GovernanceDecision`: `action`, `permitted`, `reason`, `detail`, `decided_at`.

`GovernanceAction` has **12 permitted** and **13 prohibited** members — 25 total. The enum *values* are the bare wire form with no prefix (`purchase_domain`, not `PROHIBITED_PURCHASE_DOMAIN`); classification is done on `.name`. Getting this backwards silently produces two empty sets, and a test that only checked "did it refuse" would pass vacuously — so the gate runs an import-time self-check and the tests print the set sizes.

Permitted: `PERMITTED_SEARCH_AUTHORIZED_SOURCE`, `PERMITTED_GENERATE_CANDIDATE`, `PERMITTED_ESTIMATE_COST`, `PERMITTED_ANALYSE_COMPETITOR`, `PERMITTED_ANALYSE_MARKET`, `PERMITTED_COLLECT_EVIDENCE`, `PERMITTED_SCORE_OPPORTUNITY`, `PERMITTED_VALIDATE_OPPORTUNITY`, `PERMITTED_GENERATE_REPORT`, `PERMITTED_RANK_OPPORTUNITY`, `PERMITTED_RECOMMEND_OPPORTUNITY`, `PERMITTED_SCHEDULE_RESEARCH`.

Prohibited: `PROHIBITED_PURCHASE_DOMAIN`, `PROHIBITED_BUY_SUBSCRIPTION`, `PROHIBITED_PAY_FOR_DATASET`, `PROHIBITED_RUN_ADVERTISEMENT`, `PROHIBITED_PLACE_ORDER`, `PROHIBITED_REGISTER_BUSINESS`, `PROHIBITED_SIGN_CONTRACT`, `PROHIBITED_COLLECT_PAYMENT`, `PROHIBITED_LAUNCH_CAMPAIGN`, `PROHIBITED_CREATE_FINANCIAL_OBLIGATION`, `PROHIBITED_TRANSFER_FUNDS`, `PROHIBITED_SHARE_CREDENTIAL_TO_MODEL`, `PROHIBITED_EXECUTE_RETRIEVED_CODE`.

`PROHIBITION_REASONS` gives every prohibited action its own explanation, e.g.:

> `purchase_domain` → *"purchasing a domain creates a financial obligation; §26 reserves all spend to the owner"*

A refusal that says only "not permitted" leaves the owner unable to judge whether the rule is right.

`GOVERNANCE_VERB_PATTERNS` and `OBLIGATION_PATTERNS` let the gate also inspect free text for spending and obligation language, producing a `GovernanceViolation`: `action`, `label`, `matched_text`, `reason`, `detected_at`. `matched_text` records the exact fragment, so a violation is reviewable rather than asserted.

### The prohibition is structural

`authorize` accepts **no autonomy level parameter at all** — its signature is `(self, action, *, detail=None)`. There is therefore no setting, no privilege and no autonomy level that could weaken §26. This is verified by a test that inspects the signature.

The same is true one layer up: there is **no permission code, no configuration key and no HTTP endpoint** anywhere in the system that implies money can be spent. A test asserts that no path or operation summary in the whole OpenAPI document contains `purchase`, `buy`, `order`, `pay`, `checkout`, `invoice`, `subscribe`, `contract`, `campaign`, `advert` or `domain`. Recorded in [ADR-0020](../decisions/ADR-0020-NO-SPENDING-SURFACE.md).

The last two prohibited actions are not about money and matter just as much:

* `PROHIBITED_SHARE_CREDENTIAL_TO_MODEL` — a credential must never enter a prompt. See [CONTEXT_AND_PROMPT_SECURITY.md](CONTEXT_AND_PROMPT_SECURITY.md).
* `PROHIBITED_EXECUTE_RETRIEVED_CODE` — text fetched from a source is data. Executing it would make every permitted host a remote code execution path.
