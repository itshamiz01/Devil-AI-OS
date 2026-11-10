# Browser Security (P-10)

Browsing remains P-05's (browser actions: partial since P-05).
P-10 adds the governance checks around it:

## Domain policy

`validate_browser_domain(url)` applies the egress validator's
scheme and domain rules to page loads: http only where policy
allows it, deny-listed domains refused, credentials embedded in
URLs refused.

## Session/business binding (§15.3)

`check_browser_session_access(principal, session_business_ref)`:
when P-05's browser state carries a *logged-in business
identity*, an agent may operate it only for its own business.
Operating business A's logged-in dashboard while assigned to
business B is denied (Scenario 12) — this prevents one business's
authenticated session from becoming another agent's capability.

## Content from pages

Everything a page returns is untrusted content at the lowest
trust level: it is screened by the AI-security layer
(AI_PROMPT_INJECTION_DEFENSE.md) and can never instruct the
system. Downloads from pages pass the download guard
(executable extensions rejected, size ceiling, quarantine
disposition — see NETWORK_SECURITY.md).
