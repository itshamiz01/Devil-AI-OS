# Known Limitations and Risk Register

**Phase:** P-00 · **Updated:** 2026-11-03

## Verified limitations

| ID | Limitation / risk | Severity | Current treatment | Required resolution |
|---|---|---|---|---|
| L-01 | Owner Windows PC is inaccessible; no Windows build/runtime evidence | Critical for P-01 | Linux audit clearly scoped; read-only Windows helper supplied | Run audit and target smoke tests |
| L-02 | No Ollama/model installed; no inference benchmark | High | No local-model performance claim; shared-inference design only | Hardware review, approved model and benchmark |
| L-03 | Approximately 1.94 GiB total sandbox RAM, no exposed GPU | High for local AI | Defer heavyweight inference; no model downloads | Use a suitable target or smaller approved experiments |
| L-04 | Node 20 is past its published support end date | High for frontend | Candidate supported Node LTS documented | Owner-approved upgrade and toolchain test |
| L-05 | TypeScript 7 conflicts with current typescript-eslint peer range | Medium | TypeScript 6.0.3 candidate, not installed/locked | Resolve/build/lint/type-check exact versions |
| L-06 | No application, database, agent, wallet or business workflow exists | Expected P-00 limitation | All such capabilities labelled planned | Implement and verify in later phases |
| L-07 | Governance documents are conversation-sourced transcriptions | Medium | Provenance disclosed; owner authorized reuse | Owner review; replace with signed/canonical originals if desired |
| L-08 | Conceptual phase numbers differ from prompt IDs | Medium | Proposed mapping; Constitution unchanged | D-02 approval |
| L-09 | Accounting terms/formulas need reconciliation | Critical before live finance | Cash/accrual distinction and safeguards documented | D-04 approval and P-07 tests |
| L-10 | Security/financial full phases occur later than some dependent capabilities | Critical | Early minimum-control gates proposed; live execution disabled | D-03 approval and phase acceptance tests |
| L-11 | Windows execution sandbox not selected/verified | Critical before untrusted execution | No unrestricted computer control created | D-07 design and adversarial tests |
| L-12 | No independent external audit or owner approval yet | Critical for full P-00 closure | Separate same-assistant review is explicitly not external certification | D-10 review and approval |
| L-13 | No live GitHub account connection; current checkout has no configured remote | Medium for delivery | Work remains local; no push claimed | Owner pushes/uploads an exported package or restores authorized remote later |
| L-14 | Business jurisdiction, platform/account eligibility and tax rules unknown | Critical before live business operation | No live operation attempted | D-09 owner input and appropriate professional review |
| L-15 | Package versions are registry observations, not an installed compatibility matrix | Medium | Candidate baseline and evidence recorded | P-01 lockfiles and Windows integration tests |
| L-16 | Local audit tamper evidence cannot defeat a compromised host administrator | Residual security risk | Trust assumptions disclosed | Stronger external trust anchor if required |

## Product and economic limits

- $50 is illustrative experimental capital, not proof of sufficient runway or a revenue guarantee.
- Creating products, websites or agents does not establish demand, distribution or profitability.
- Customer acquisition, quality, support, fees, refunds and legal eligibility can dominate model costs.
- Market research must declare source coverage and uncertainty; it cannot inspect the entire economy.
- Simulated revenue cannot satisfy the real business acceptance test.
- High-risk financial activities remain separately gated; P-00 authorizes none.

## Preservation and delivery

The original README and MIT license were inspected before edits. The README is archived and the license is unchanged. No application code was replaced because none existed. No packages/models were installed, no financial accounts connected and no remote push performed.

The final completion report distinguishes structural checks from runtime verification and lists the exact remaining gate.
