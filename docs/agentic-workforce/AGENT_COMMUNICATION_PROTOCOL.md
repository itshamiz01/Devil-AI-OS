# Agent Communication Protocol — Devil AI OS Workforce

All organizational communication is structured and recorded; there are
no hidden execution channels (§7/§17).

**Owner → CEO.** `POST /workforce/objectives` (owner/system principal
only). Carries: title, objective description, optional department
selection. Produces a PLAN — never automatic execution.

**CEO → Managers.** The plan names, per department: departmental goal,
manager, rationale, and a `requires_approval` flag when the objective
contains restricted-action language.

**Manager → Employee (work order, §7 fields).**
`POST /workforce/work-orders` with: objective ID (the plan), employee
code, objective, instructions, expected deliverable, priority,
deadline, restricted flag. Persisted as a P-01 task (parked in
WAITING_FOR_APPROVAL) + a P-04 `agent_assignments` contract row
(objective, input refs incl. instructions, expected output, quality
requirements, assigned-by = the manager). Only the employee's own
manager, the CEO, or the owner may dispatch; cross-department direct
assignment is refused.

**Employee → Manager.** Accept (`/work-orders/{id}/accept`) then a
§10-standard deliverable (`/work-orders/{id}/deliverable`): objective,
work performed, result, evidence, limitations, outstanding issues,
verification status (`self_reported` until reviewed).

**Manager → CEO.** Review verdicts (`/deliverables/{id}/review`:
accept → `manager_verified`, metrics recorded, parked task released;
or rework, which returns the assignment to the employee) and the
consolidated objective report assembled from those records.

**Cross-department.** ONLY via P-09 handoffs (`POST /workforce/handoffs`):
sending employee, receiving employee, task ref, objective, work
completed, next actions. Append-only history. Creators are restricted
to the sending/receiving employee, their managers, or the owner.

**Escalations.** Restricted work orders (publishing, payments,
external sends, deletions, …) are not messages — they become P-01
Approvals requested by the CEO agent and stay pending until an
owner-authority decision. Every step above writes an `audit_events`
row.
