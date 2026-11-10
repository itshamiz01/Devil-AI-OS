# P-15 WINDOWS OPERATIONS (§7)

## Status: design + platform-agnostic supervision — Windows
## behaviour UNVERIFIED from this Linux staging (P-14 DEF-A1).

Nothing in this document claims a Windows behaviour that was
executed. The P-15 build ran entirely on the Linux staging VM;
every Windows-specific item below is either (a) already true of
the platform-agnostic code, or (b) an explicit owner-machine
verification step for the pilot.

## Operating modes (§7)

The prompt's modes map onto mechanisms that already exist:

| Mode | Mechanism |
|---|---|
| A — Manual | The owner starts/stops the app (uvicorn process / future desktop shell); lifecycle states are explicit (P-01) |
| B — Scheduled | P-12 triggers feed the P-01 task substrate on schedules; P-15's sampler runs with the process |
| C — Continuous | The process runs with its loops (P-12 operations loop + P-15 sampler); health/readiness are live in the Command Center |
| D — Controlled Autonomous | P-12 autonomy modes under P-10 governance (Simulation → Supervised → Controlled → Emergency); P-15 changes none of it |

## What is platform-agnostic and verified in staging

- Graceful startup/shutdown with lifecycle transitions and a
  FAILED state on a broken foundation (P-01).
- Startup recovery of operational state after an unclean exit:
  interrupted tasks paused, executions marked INTERRUPTED,
  workflows parked RECOVERY_PENDING.
- Log rotation (size-capped, count-capped, secret-redacting —
  P-01 logging configuration).
- Process visibility: nothing is hidden — lifecycle state,
  running work, samples and incidents are all in the Command
  Center, and shutdown is always available to the owner.
- The P-15 sampler starts/stops with the application and resumes
  recording after a restart; sample history is durable (SQLite),
  so an unexpected shutdown leaves a visible gap in the stability
  report rather than a silent one.

## Owner-machine verification steps (pilot, DEF-A1)

1. Install/run under Windows 10/11; confirm startup, the Command
   Center and the sampler's samples accumulating.
2. Register the app for start-at-login **only if the owner wants
   Mode C** (Task Scheduler or Startup folder — an owner action;
   the application never registers itself).
3. Sleep/wake: confirm the sampler resumes and the stability
   report shows the sleep gap honestly.
4. Unexpected power loss: restart and confirm the recovery scans
   park interrupted work and the first P-15 evaluation reflects
   the restored state.
5. Confirm resource behaviour on the target hardware
   (i7-4712HQ / 16 GB / CPU-only inference per the P-04 verdict).

## Not implemented (stated, not implied)

- No Windows service wrapper, no auto-start registration, no
  update mechanism ships with P-15. These are packaging decisions
  for the pilot, deliberately not improvised inside a reliability
  phase.
