# Business Creation Operations (P-06)

## Operating the engine (API, `/api/v1`)

1. `GET /business/status` — engine posture (mode, counts, and the three
   "none" statements: no publishing, no money movement, no outreach).
2. `GET/PUT /business/settings` — owner-governed settings; the minimum
   validation level lives here (`business.settings` in system_config).
   Lowering it is an owner decision with audit; it never rewrites P-03
   levels.
3. `POST /business/eligibility` — evaluate before creating anything.
   Persisted evaluations are the record of *why* a decision was made.
4. `POST /business/creation-approvals` → owner decides via
   `POST /approvals/{id}/decision` → `POST /business/businesses`.
5. `POST .../declarations` (owner-created = approved; others use
   `.../declarations/{id}/approve`) — required before any run.
6. `POST .../blueprint` → optional `POST .../blueprint/approve`.
7. `POST .../creation-run` — the workflow; watch `WorkflowRun` state via
   the P-05 API and `business_lifecycle_events` for stage truth.
8. `POST .../channels/evaluate`; publish attempts via
   `POST .../channels/{id}/publish` always return the gate outcome.
9. `POST .../readiness` → read blockers, fix causes (never edit the
   review) → `POST .../transition {READY_FOR_LAUNCH}` →
   `POST .../launch/request` → owner decides → `POST .../launch`.

## Failure handling

- Run failure → business `BLOCKED` with the workflow status recorded;
  inspect step runs via the P-05 execution API. Re-running a *completed*
  run is refused; a blocked business can be re-driven only after the
  cause is fixed (the run creates a fresh workflow definition per
  attempt).
- Eligibility regressions (an opportunity's level drops after new
  evidence) do not rewrite history: `validation_level_at_creation`
  stays as recorded, and readiness dimension A uses it — re-evaluation
  is an explicit owner action.
- Emergency mode halts creation at the gate; existing businesses are
  untouched.

## Rollback

`alembic downgrade 6ffcc7e899fa` removes exactly the 18 P-06 tables
(verified in the migration-cycle test, exact table-set comparison).
Removing the router include in `app/main.py` reverts the API surface.
The one additive P-05 change (`WorkflowRunIn.business_ref`, default
`None`) is inert when unused.
