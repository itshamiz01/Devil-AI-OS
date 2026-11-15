# Organizational Structure — Devil AI OS Workforce

**Hierarchy (Prompt §3):** OWNER → CEO → DEPARTMENT MANAGERS → SPECIALIZED EMPLOYEES

| Position | Count | Codes |
|---|---|---|
| AI CEO | 1 | `DEV-CEO-001` |
| Department Managers | 10 | `DEV-MGR-001` … `DEV-MGR-010` |
| Specialized Employees | 100 | `DEV-<DEPT>-NNN` (see below) |
| **Total baseline** | **111** | owner is NOT counted |

**Employee code scheme:** workers carry their GLOBAL prompt number
(001–100) with a department prefix: STR (Strategy), RES (Research),
BUS (Business Creation), TEC (Technology), MAR (Marketing), SAL
(Sales), FIN (Finance), OPS (Operations), SEC (Security), CUS
(Customer Success). Examples: `DEV-STR-001` (Employee 001),
`DEV-RES-011` (Employee 011), `DEV-CUS-100` (Employee 100).

**Where it lives:** employees are rows in the existing P-01 `agents`
registry (`parent_agent_id` = reporting line: workers → their manager,
managers → CEO, CEO → none/owner). Departments are
`workforce_departments` rows; the §6 profile is the 1:1
`workforce_profiles` extension keyed to `agents.id`, unique on
`employee_code` — which is what makes the seed idempotent: re-running
it after any restart creates zero duplicates (verified by test).

**Rules enforced in code:**
- Exactly one CEO, exactly 10 managers, exactly 100 employees, exactly
  10 employees per manager (organization tests, §25).
- Every employee has one primary role, one reporting manager, defined
  permissions scope, and an individual performance record (P-04
  `agent_metrics`).
- Disabled employees are never deleted: profile, assignments, metrics
  and audit history persist.
- Cross-department collaboration happens only through P-09
  `agent_handoffs` records; a manager cannot directly assign work to
  another department's employee (refused in the service).
- Expansion beyond the 111 baseline is NOT part of this build; future
  employees must go through the P-04 Agent Factory governance and be
  labelled expansion employees (Prompt §15).
