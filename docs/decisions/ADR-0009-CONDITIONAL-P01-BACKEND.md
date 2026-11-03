# ADR-0009: Conditional backend-only P-01

- **Decision ID:** ADR-0009
- **Status:** Accepted for conditional implementation by owner selection on 2026-11-03
- **Context:** P-00 ended partially complete; Windows audit and independent review were pending.
- **Problem:** Proceed safely without pretending full P-01 acceptance.
- **Options considered:** Pause until full P-00 closure; implement conditional backend-only core; implement full desktop scope immediately.
- **Selected decision:** Implement backend core, database, tasks, events, permissions, monitoring and API in the Linux workspace with no external/financial/model execution. Windows/full acceptance remains pending.
- **Reasons:** Owner explicitly authorized conditional progression; backend can be tested independently.
- **Consequences:** P-01 is Partially Complete. Frontend/desktop, Windows certification and independent audit remain open. No P-02 authorization is implied.
