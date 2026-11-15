# Employee Performance Model — Devil AI OS Workforce (§14)

**Weights (configurable per profile, seeded identically):**
Quality 25 · Verified success 20 · Deadline adherence 15 · Reliability
15 · Resource efficiency 10 · Collaboration 10 · Policy compliance 5
(sum = 100; stored on every `workforce_profiles.kpi_weights`).

**Data sources — real records only:**
- `quality` — mean of `quality_score` metrics recorded at manager
  review (the manager's 0–100 rating on acceptance).
- `verified_success` — `verified_success` ÷ (`tasks_completed` +
  `tasks_failed`) metric counts. A deliverable counts ONLY after
  manager acceptance; self-reported submissions never count.
- `deadline_adherence` — mean of `deadline_adherence` metrics (1/0,
  recorded on acceptance when the work order had a deadline).
- `reliability` — completed ÷ terminal assignments from the P-04
  `agent_assignments` table.
- `resource_efficiency`, `collaboration`, `policy_compliance` — read
  from same-named `agent_metrics` when such measurements exist.

**Honesty rules (enforced in the read model):**
- Components with no data are EXCLUDED and the remaining weights are
  renormalized; the response names exactly which weights were used.
- An employee with no verified outcomes returns
  `{"data_status": "no_data", "score": null}` — never an invented
  number. (Verified by test: every freshly seeded employee reports
  `no_data`.)
- Only `measurement_type="measured"` metrics are read; estimates are
  never presented as measurements (existing P-04 convention).
- Agents cannot edit their own performance: metrics are written by
  the review path (manager action) and the factory's task-outcome
  sync, and there is no employee-facing metric write API.
- A critical security violation cannot be offset by productivity:
  policy compliance is a separate component, and P-10 restrictions
  act independently of scores.

**Manager / CEO rollups:** department performance averages only
members who HAVE scores and reports `members_with_data`; the CEO
consolidation reports verified work-order outcomes per department,
not scores it cannot substantiate.
