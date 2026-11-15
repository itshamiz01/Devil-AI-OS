# Workforce API Reference (§23)

Base: `/api/v1/workforce`. Existing bearer auth; authorization is
enforced in the service layer as noted. All responses use the standard
envelope (`success/data/error/correlation_id`, `meta` on lists).

**Organization**
- `POST /workforce/seed` — owner/system only. Idempotent 111-employee
  seed. Returns `{departments, agents, profiles, total_profiles}`
  created counts (zeros on re-run).
- `GET /workforce/overview` — counts FROM the database: totals by
  level, departments, status tallies, work-order total.
- `GET /workforce/departments` — departments with manager + headcount.
- `GET /workforce/departments/{code}/performance` — department rollup
  (score only over members with data; `no_data` otherwise).

**Employees**
- `GET /workforce/employees?level=&department_code=&status=&limit=&offset=`
- `GET /workforce/employees/{employee_code}` — full §6 profile +
  recent assignments + performance read model.
- `GET /workforce/employees/{employee_code}/performance` — KPI model
  (components, weights used, `data_status`).
- `POST /workforce/employees/{employee_code}/{action}` — owner-only;
  action ∈ pause | resume | disable | enable | block | unblock.

**CEO / objectives**
- `POST /workforce/objectives` — owner/system only. Body:
  `{title, description, department_codes?}`. Returns the plan
  (departments, managers, goals, `requires_approval` flags,
  restricted-action notes). Planning dispatches nothing.
- `GET /workforce/objectives`, `GET /workforce/objectives/{id}`
- `POST /workforce/objectives/{id}/consolidate` — owner or CEO
  principal. Builds the consolidated report from recorded
  assignments/deliverables; marks the objective completed only when
  every work order is completed.

**Tasks / work orders**
- `POST /workforce/work-orders` — manager-of-employee / CEO / owner.
  Body: `{objective_id, employee_code, objective, instructions,
  expected_deliverable, priority, deadline, restricted}`. Restricted
  orders return `{status: "escalated_to_owner_approval", approval_id}`
  and create NO assignment. Normal orders return
  `{status: "assigned", assignment_id, task_id, task_status:
  "waiting_for_approval"}`.
- `POST /workforce/work-orders/{assignment_id}/accept` — the assigned
  employee (or owner).
- `POST /workforce/work-orders/{assignment_id}/deliverable` — §10
  body: `{work_performed, result, evidence[], limitations,
  outstanding_issues}`.
- `POST /workforce/deliverables/{deliverable_id}/review` — the
  employee's manager (or owner). Body: `{accept, quality_score?,
  notes?}`. Acceptance records metrics and releases the parked task.

**Communication**
- `POST /workforce/handoffs` — `{from_code, to_code, objective,
  task_ref, work_completed, next_actions[]}`; creates a P-09
  `agent_handoffs` record.
