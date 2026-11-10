# P-15 RESOURCE MANAGEMENT (§4.2 / §8)

## Principle

P-15 does **not** schedule. Scheduling, admission and concurrency
belong to the P-01 TaskManager and the P-12 operations engine, and
a second scheduler is explicitly forbidden (§3 rule 5). P-15's
resource layer therefore does three things only: **classify,
measure, and report admission state** — and it surfaces the one
real control that already exists (the P-01 monitor's admission
guard) instead of inventing another.

## Priority classes (§4.2)

| Class | Meaning | Examples |
|---|---|---|
| 1 — Critical | security monitoring, financial transaction integrity, emergency shutdown, data consistency | P-10 monitoring, P-07 posting, P-15's own DB integrity evidence |
| 2 — High | approved business execution, time-sensitive workflows, scheduled financial processes | P-12 workflows under owner approval |
| 3 — Normal | standard agent activity, analysis, routine automation, reporting | P-02 missions, P-13 coordination |
| 4 — Background | research, enrichment, memory indexing, historical analytics | P-03 research, P-09 indexing |

The classes are published in the overview read-model
(`resources.priority_classes`) so every consumer classifies
consistently. Task rows already carry `priority` and `essential`
(P-01); the P-01 admission guard already blocks **nonessential**
admissions when resource thresholds are exceeded
(`SystemMonitor.admission_block_reason`, wired into the TaskManager
since P-01) — class 4/3 nonessential work is exactly what that
guard sheds first.

## Backpressure (§5)

Derived, not enforced anew: the overview computes queue
depth/capacity and reports `backpressure` as none (<60%),
elevated (≥60%) or high (≥90%), alongside the live admission-block
reason from the P-01 monitor. Operators and the readiness
performance category consume the same numbers the sampler records,
so the signal is identical in the UI, the score and the history.

## Concurrency

`max_concurrency` and `queue_capacity` remain P-01 settings
(read-only in P-15's surface). Dynamic adjustment of the running
TaskManager's concurrency is **not** implemented: mutating a live
substrate's limits from a monitoring layer would be a governance
change, not an optimisation. It is recorded as a limitation with
the safe path (owner changes P-01 settings at restart) in the
readiness report.

## Multi-agent / multi-business fairness (§8)

Isolation already exists where it matters: P-12 workflow recovery
parks per-workflow, P-13 quotas/allocations are per-business, and
P-04 agents are logical configurations over one router. P-15 adds
the missing observability: per-agent and per-business counts in
the overview (panels C/D, from the P-11 dashboard summaries) and
stuck-task detection (tasks RUNNING beyond
`stuck_task_minutes`, surfaced in the stability report) so a
monopolising or hung workload is visible instead of silent.
