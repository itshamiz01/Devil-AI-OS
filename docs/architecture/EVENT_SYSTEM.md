# Event System (P-01 §8) — as implemented

In-process async `EventBus` (`app/events/`); no distributed broker in this phase. Event model: unique ID, type, UTC timestamp, source component, correlation ID, optional task ID, validated payload dict, severity.

**Types:** ApplicationStarted/Ready/Stopping/Stopped, TaskCreated/Queued/Started/ProgressUpdated/Completed/Failed/Cancelled, ApprovalRequested/Granted/Rejected, PermissionDenied, SystemWarning, SystemError, DatabaseUnavailable, ResourceThresholdExceeded.

**Guarantees (all unit-tested):**
- Multiple subscribers per type plus a `*` wildcard.
- **Subscriber failure isolation** — a raising subscriber is logged and counted; other subscribers still receive the event; the publisher never crashes.
- **Recursion guard** — publish depth is tracked with a context variable; beyond `event_max_depth` (default 3) events are dropped and counted.
- **Flood protection** — a per-second rate limit (default 200/s); excess events are dropped and counted (`bus.dropped_count`), never queued in memory.
- **Critical persistence** — a built-in subscriber writes the critical set (approvals, permission denials, warnings/errors, DB-unavailable, resource-threshold, task failures, app start/stop) to `system_events`, deduplicated by event ID, independently of in-memory delivery. `GET /api/v1/events` exposes exactly this persisted set.
