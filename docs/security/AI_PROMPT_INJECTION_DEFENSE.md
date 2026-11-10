# AI and Prompt-Injection Defence (P-10)

## Principle

Content is data. Instructions exist only at the top of a fixed
trust hierarchy, and nothing lower can raise itself:

```
owner instructions > developer instructions > user requests
> system tool output > business data > stored memory (P-09)
> external content (web, email, documents, other agents)
```

Unknown sources are assigned the lowest level. `may_instruct` is
true only for owner/developer/user origins.

## Mechanisms

1. **Screening** — `screen_content` classifies text from any
   source with deterministic patterns (instruction override,
   privilege claims, credential requests, secret exfiltration,
   approval forgery, policy manipulation). Findings are pattern
   **names only**; the text itself is never copied into events.
2. **Memory is never authority** — content retrieved from P-09
   memory is screened and classified as data. Even text stored as
   an "owner instruction" record type by an agent is refused at
   write time by P-09's own gate; and text the *owner* stores
   that happens to contain an attack string changes nothing,
   because no P-10 decision path reads instructions from memory
   (the security package holds no reference to approvals/
   permissions mutation through memory — enforced structurally:
   `app/security/` contains no `.decide(` call of its own; only
   the broker verifies bindings).
   Tested: Scenario/Article-0 tests poison memory both ways and
   show policy, limits and approval state unchanged.
3. **Handoff validation** — inter-agent handoff payloads are
   validated: owner-only permissions in a handoff make it
   invalid; a handoff cannot grant, delegate or approve anything.
4. **Outbound screening** — content heading to external parties
   passes the shared secret detector (P-09's); secret-shaped
   values block the send.
5. **No LLM as security authority** — no model output is an input
   to the broker, the guards, or the financial guard. Security
   decisions are code, lists and hashes.

## What this does not claim

Pattern screening catches known phrasings; a novel phrasing can
pass the *screener*. The actual security boundary is that
screened content has no path to authority at all — the worst a
missed injection can do is be stored as inert data (subject to
P-09's own gates), never executed as policy.
