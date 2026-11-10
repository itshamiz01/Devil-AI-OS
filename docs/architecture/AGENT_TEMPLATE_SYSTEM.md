# Agent Template System (§6)

Implemented in `backend/app/agents/templates.py` + `validation.py`.
Templates are the *only* way agents come into existence (creation
Modes A/B), except owner-approved Mode C proposals for taxonomy roles
that have no published template yet.

## Model

- `agent_templates` — identity (unique name, category, current
  `published_version`, `deprecated` flag).
- `agent_template_versions` — **immutable** version rows: full
  configuration JSON, `validation_status` (`valid`/`invalid`),
  structured validation report, publisher, timestamps. Editing a
  template appends a new version; history is never rewritten.
- Agents are **pinned** (`agents.template_id` + `agents.template_version`)
  to the published version at creation. Publishing v2 never changes a
  running agent; re-pinning is an explicit, audited configuration
  update that only accepts the template's published + valid version.

## Configuration shape (validated)

Required: `version`, `role`, `system_instruction`, `objective`,
`responsibilities[]`, `allowed_capabilities[]`, `restricted_capabilities[]`,
`tool_requirements.handlers[]`, `model_requirements.preferred_profile`,
`resource_budget` (all seven fields), `output_requirements`,
`quality_requirements`, `escalation_rules`, `security_classification`.

The validator rejects (non-exhaustive): missing fields; unknown roles;
unknown or Level-3/prohibited capabilities in the allowed list;
allowed ∩ restricted overlap; handlers not registered in the P-01 task
registry; model profiles that do not exist; budgets above the factory
ceilings (concurrency, task seconds, memory, child agents — sized for
the owner's CPU-only hardware, inference concurrency ceiling 1);
unknown security classifications.

## Lifecycle operations (API + service)

create · read · update (new version) · clone (new template at v1) ·
validate (report on any version) · publish (only a `valid` version;
invalid templates can never publish and never produce agents) ·
deprecate (creation via a deprecated template is rejected) · restore
(an older version's configuration appended as a *new* version, then
publishable) · compare (field-level diff between two versions) ·
version history listing.

## Seed templates (10, internal capabilities only)

Research, Market Analysis, Competitor Analysis, Business Strategy,
Opportunity Evaluation, Content Writing, Documentation, Quality
Assurance, Financial Analysis, Security Review — seeded idempotently
at startup, validated, and published as v1. Their capability sets use
only Level 0/1 internal capabilities; the one Level-1 grant
(`financial_data_read` in Financial Analysis) is granted at creation
under the §8.3 template policy.
