# P-15 RELIABILITY DESIGN (§4.4 / §10)

## Health model

Component health states (healthy / degraded / unavailable /
recovering / maintenance per §4.4A) are consumed from the P-14
system-health surface, which already derives per-component and
per-module states from named checks with named sources. P-15 does
not re-derive them; the readiness reliability category scores the
same states the Command Center displays (ok = 1.0, degraded = 0.5,
unavailable = 0.25, down = 0), so the score can never disagree
with the UI.

## Heartbeats

The sampler *is* the heartbeat for the platform process: a sample
row with a fresh timestamp proves the monitor path is alive, and
the stability report makes gaps visible (span vs sample count).
Per-service heartbeat tables were not added — in this
single-process architecture the services share the process
lifecycle (P-01 LifecycleManager), and inventing per-service
heartbeats for components that cannot die independently would be
theatre, not telemetry. On the target Windows deployment the same
sample stream detects a stalled process from outside (missing
samples), which is the property that matters.

## Circuit breakers (§4.4C)

P-12's `CircuitBreaker` (closed/open/half-open, threshold +
cooldown, per dependency target) is the only breaker
implementation. P-15 reads breaker views through
`OperationsService.safety_status`, opens a P1 incident while any
breaker is open (auto-resolving when it closes), scores breaker
presence/state in the fault-tolerance category, and functionally
probes the real class in every benchmark run.

## Retry management (§4.4D)

Owned by P-12 (`classify_failure`, `retry_eligible`,
`retry_delay`: exponential backoff + jitter, caps, non-retryable
classes for permission/budget/policy failures) on top of P-01's
task retry. P-15 changes none of it; the benchmark suite probes
classification and backoff monotonicity/cap against the real
functions. Irreversible actions are protected by the existing
rules §3.9: retries never replay financial postings (P-07
idempotency + approval consumption), completed purchases or
executions (P-05 recovery marks INTERRUPTED instead of repeating).

## Graceful degradation (§4.4E)

Existing behaviour, now observed: cloud unavailable → the P-02
router reports provider truth and the deterministic planner keeps
working; analytics/report failures never block execution (P-12
report snapshots are artefacts, not gates); memory indexing
failures preserve original records (P-09). P-15's contribution is
that each of these conditions is *visible* — provider state in
panel B, dead letters in panel E/F, incidents in the register —
instead of silent.

## Incident management (§10)

`reliability_incidents` records detection time, component,
severity (P0 critical / P1 major / P2 partial / P3 minor), root
cause, response, recovery actions, resolution time and preventive
notes. Detection rules (evaluator, deduplicated on
component+kind while open):

| Condition | Severity | Auto-resolve |
|---|---|---|
| Database connectivity failed | P0 | yes, when healthy |
| Circuit breaker open | P1 | yes, when closed |
| Resource threshold violated | P2 | yes, when under thresholds |
| Operations dead letters open | P2 | yes, when drained |
| Event dead letters on record | P3 | no (cumulative record) |
| No backups recorded | P3 | yes, when one exists |
| Latest backup stale | P3 | yes, when fresh |

Manual incidents (owner-created) are never auto-resolved.
Detection never performs recovery: recovery actions stay with the
owning engines and the owner (§4.5 prohibitions are preserved —
nothing in P-15 deletes data, moves money, changes permissions or
restores backups).
