# AI Infrastructure — Devil AI OS Workforce (§12/§24)

**One shared inference layer.** The 111 employees are persistent
organizational identities — registry rows + role-specific instruction
profiles — NOT 111 processes and NOT 111 model instances. All
inference, when a task requires it, goes through the existing P-02
model router with its model profiles (local Ollama by default,
optional cloud), exactly as every prior phase. This build adds no
provider, no key, and no per-agent model binding; an employee's
identity is independent of whichever model serves a given task.

**Execution architecture (as built):**
- Central P-01 task queue (the `tasks` table) with its existing
  capacity bound and backpressure; workforce work orders enter it
  parked (WAITING_FOR_APPROVAL) and are released only on manager
  acceptance, so the queue can never be flooded by unreviewed work.
- Concurrency is bounded by the existing TaskManager settings
  (`max_concurrency`, queue capacity, resource admission guard) —
  modest-hardware safe by construction.
- Role-specific system instructions are generated per employee from
  that employee's actual §5 responsibilities (asserted unique across
  all 111 profiles in tests).
- Per-task context = the work order's input refs + the employee's
  scoped memory (P-09 scopes; credentials never enter memory).

**Modes (§24):** Normal — as above. Low-resource — the existing
resource admission guard blocks nonessential task admission under
threshold pressure (P-01 mechanism, unchanged). Emergency — P-10
emergency mode blocks new workforce dispatch (tested). Maintenance —
owner pauses employees/departments via lifecycle controls while
inspection continues.

**Monitoring:** workforce overview counts come from live DB queries;
task latency/token/cost telemetry remains with the existing P-02/P-15
monitors. No workforce-specific resource telemetry was added in this
build (classified in the implementation report).
