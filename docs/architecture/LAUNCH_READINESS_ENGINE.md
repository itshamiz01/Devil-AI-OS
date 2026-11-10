# Launch Readiness Engine (P-06 §20)

`app/business/readiness.py` — a pure, deterministic evaluator over
facts assembled from stored state (blueprint, product, assets,
channels, playbook, assignments, declaration, P-03 validation level).

## Dimensions

- **A Market** — computed validation level ≥ the owner-governed
  minimum; customer defined; competitor research or market analysis on
  file; pricing documented.
- **B Product** — product exists (assets bound to it, not merely a
  blueprint); quality review present with no failed and no missing
  required checks; limitations documented; documentation assets exist.
- **C Brand** — identity (blueprint) exists; brand assets prepared;
  accurate product description asset exists; no unresolved asset-rights
  conflicts.
- **D Distribution** — primary channel selected; platform-gate outcomes
  recorded for every channel; channel assets prepared. A primary gate
  of `BLOCKED` is an *external* blocker. Non-primary gates requiring
  human action (e.g. KDP) are warnings.
- **E Customer** — onboarding/support documentation prepared; support
  procedures exist; refund/complaint process documented.
- **F Operational** — monitoring, backup and recovery approaches
  recorded in the playbook; dependencies identified; responsible
  agents assigned.
- **G Legal/compliance** — requirements identified; policy templates
  prepared; platform terms reviewed via gate records. The review
  carries the standing disclaimer: readiness is an internal checklist
  outcome and is **not independently certified**.
- **H Financial inputs** — costs documented as financial values; risks
  recorded; the P-07 payload validates; **and the declaration test**:
  the startup estimate must fit the pre-declared budget cap. Launch is
  judged against the declaration, never against checklist completion.

## Results and precedence

`BLOCKED` (any external blocker) > `NOT_READY` (any internal blocker) >
`OWNER_REVIEW_REQUIRED` (compliance flags professional review) >
`READY_WITH_WARNINGS` > `READY`. Hard blockers override any score —
there is no score. Every review stores its dimensions, blockers,
warnings, outstanding requirements, evidence references and the
declaration comparison, so a refusal is always explainable.
