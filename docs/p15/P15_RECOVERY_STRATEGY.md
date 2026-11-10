# P-15 RECOVERY STRATEGY (§4.5 / §5)

## What already recovered, before P-15

| Failure | Existing mechanism | Owner |
|---|---|---|
| Process restart with tasks in flight | Interrupted tasks PAUSED for operator review (never blindly re-run) | P-01 TaskManager.recover_interrupted |
| Interrupted executions | Marked INTERRUPTED at startup; completed irreversible steps are never repeated | P-05 ExecutionService.recover_interrupted |
| Interrupted workflows | Parked RECOVERY_PENDING; resume is individual and revalidated, owner-authorised | P-12 OperationsService |
| Failed event deliveries | Durable dead letters (P-14 DEF-I4) + in-process record | P-01 event bus |
| Failed workflow tasks | Operations dead-letter store with owner-driven handling | P-12 |

## What P-15 adds

1. **Detection with memory.** The evaluator turns transient
   conditions into a durable incident register with an audit
   trail, and auto-resolves auto-detected incidents when the
   condition genuinely clears — so recovery is *evidenced*, not
   anecdotal.
2. **Recovery success measurement.** The register yields the
   recovery rate consumed by the reliability dashboard and the
   fault-tolerance readiness category.
3. **Functional proof, repeatedly.** Every benchmark run probes
   the real breaker (open → half-open → close), the real retry
   policy (classification + capped monotonic backoff) and the
   real bus dead-letter path, so the mechanisms are re-proven on
   demand rather than trusted from their original phase tests.
4. **Stuck-work detection.** Tasks RUNNING beyond
   `stuck_task_minutes` are listed in the stability report —
   the input an operator needs to use the existing pause/review
   paths.

## What P-15 deliberately does not do

- No automatic restarts of workers/agents: in this single-process
  substrate a "restart" is a process lifecycle action owned by
  the operator (and, on Windows, by the service manager — see
  P15_WINDOWS_OPERATIONS.md). Automated restarts are recorded as
  a limitation, not simulated.
- No automatic backup restoration (P-14 A4 stands: restore
  execution is the owner's manual step after the guarded
  preview).
- No replay of completed steps, no duplicate financial actions,
  no permission or security changes — §4.5's prohibitions are
  preserved verbatim in the design: the evaluator's only writes
  are samples, incidents, snapshots and benchmark rows in P-15's
  own tables.
