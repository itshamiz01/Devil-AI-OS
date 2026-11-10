# Product Creation Workflow (P-06 §10–§12)

## Specification before creation (§10)

No product work starts before a specification exists. `generate_blueprint`
creates the product row (§11 fields: type, description, target customer,
problem solved, core/excluded features, pricing as data, delivery method,
support requirements) and its requirements (§12: functional, quality,
technical, operational, legal — each with priority and acceptance
criteria). `BLUEPRINT_READY` is guarded: the lifecycle refuses the state
without a stored blueprint.

## Development coordination (§11)

- Agents come from the P-04 factory, **reuse-first**. P-06 requests
  portfolio staff (no business binding on the agent itself — the factory
  never reuses an agent bound to another business) and records the
  binding in `business_agent_assignments`.
- Capability grants flow through the factory's governed path; Risk-2
  capabilities are approved by the owner principal who approved the
  creation (never by the requesting agent, §21).
- Every build step is a P-05 execution request inside the template
  workflow — filesystem/documents writes and, for the SaaS template, a
  `code_python.run` verification step executed under P-05's process
  controls (isolation honestly labelled `process_controls_only` in P-05).

## Quality gates (§12)

After the workflow completes, assets are registered only after a
hash-verification read through the execution engine returns a digest.
The quality review (recorded on the product, reviewer = the QA agent
assignment) checks: every asset exists and hash-verifies; no
secret-shaped content (generation redaction + the security suite's
scan); no fabricated claims (templates contain no testimonials, reviews
or invented credentials). Generated ≠ tested: the business moves to
`INTERNAL_TESTING` only with this review recorded, and readiness
dimension B fails closed when required checks are missing or failed
(Scenario F).

## Website creation (§13)

The template workflow writes a static site package into
`website/` in the business workspace. Website truth is five separate
fields on the business — `planned`, `generated`, `verified_locally`,
`deployed`, `publicly_available` — and they are never collapsed.
Staging can only ever set the first three: there is no deployment
adapter, so `deployed` and `publicly_available` remain false, and the
generated page itself says so.
