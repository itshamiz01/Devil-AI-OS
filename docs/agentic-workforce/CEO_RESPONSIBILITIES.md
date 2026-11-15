# CEO Responsibilities — DEV-CEO-001

The CEO is the highest-ranking AI employee and reports directly to the
human owner. Its profile (responsibilities, instructions, limits) is
seeded from Prompt §4 into `workforce_profiles` for agent `DEV-CEO-001`.

**Operating cycle (implemented):**
1. Owner submits an objective (`POST /workforce/objectives`).
2. The CEO layer builds a departmental PLAN: required departments
   (explicit selection, or mission/keyword match; portfolio-wide if no
   department matches), each with its manager and a departmental goal.
3. **A plan is not authorization.** Nothing is dispatched by planning.
4. Managers (or CEO/owner) dispatch work orders from the plan.
5. Managers review deliverables; only accepted deliverables count.
6. The CEO consolidation (`POST /workforce/objectives/{id}/consolidate`)
   assembles the executive report ONLY from recorded assignments and
   reviewed deliverables — it cannot invent progress (§8).

**The CEO can:** receive owner objectives, plan departmental goals,
coordinate managers (dispatch within a plan), request consolidation,
escalate restricted work to the owner approval path.

**The CEO cannot (structurally enforced, tested):**
- Decide approvals — `ApprovalService.decide` requires the
  `approve_actions` authority; agent principals do not hold it. The
  CEO's own restricted-work escalations stay pending until the owner
  decides.
- Override P-10 security policy or P-07 financial authority; access
  credentials (prohibited capabilities are catalogue level-3 and can
  never be granted, even by the owner); modify its own permissions or
  authorization limits; create unlimited agents (baseline is fixed at
  111; expansion is a P-04 governed, owner-approved process); delete
  audit records (the audit API is append-only).

**Executive reporting cadence (§8):** morning briefing / end-of-day /
weekly review are REPORT TYPES the consolidation supports from live
records; no scheduler invents them autonomously in this build — they
are produced when the owner (or CEO principal) requests consolidation.
Classified PARTIALLY IMPLEMENTED in the implementation report.
