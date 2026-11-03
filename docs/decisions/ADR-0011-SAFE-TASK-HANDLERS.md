# ADR-0011: Registered safe task handlers only

- **Decision ID:** ADR-0011
- **Status:** Implemented for P-01 conditional backend
- **Context:** Task engine could become an unrestricted command executor if arbitrary payloads were trusted.
- **Problem:** Provide real task execution without enabling P-05 tool execution or unsafe host control.
- **Options considered:** Arbitrary shell/code tasks; no execution; registered validated internal handlers.
- **Selected decision:** Only `system.noop`, `system.echo`, and `system.wait` handlers with Pydantic payload validation.
- **Reasons:** Demonstrates queue/lifecycle/retry/cancellation safely while preserving phase boundaries.
- **Consequences:** No external side effects, browser/desktop automation or model calls. Future handlers require explicit permission, isolation and idempotency design.
