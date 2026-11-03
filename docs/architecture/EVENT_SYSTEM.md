# P-01 Event System

The internal event bus is asynchronous and bounded. Events have ID, type, timestamp, source, correlation ID, optional task ID, severity and payload. System events are persisted to SQLite. Subscriber exceptions are isolated and logged. The bus rejects unknown event types and applies backpressure when full.

Implemented event types (21) include application lifecycle, task lifecycle, approval, permission denial, system warning/error, database unavailable, resource threshold, and the two emergency-stop types `EmergencyActivated` / `EmergencyDeactivated` added beyond the P-01 §8 initial list of 19 so that a security-critical state change is observable through the same bus (ADR-0013). Critical audit records are written separately by permission/task/approval services and do not depend only on in-memory event delivery.

This is not a distributed broker. Recursive flooding is bounded by queue capacity and subscriber limits, but P-01 does not implement a distributed outbox.
