# Network Security (P-10)

All egress decisions are deterministic — scheme rules, domain
lists, and IP range checks. No LLM participates.

## Egress validator (`network.py`)

For a URL to be allowed, ALL must hold:

1. **Scheme** — `https` by default; `http` only when
   `security.settings.egress_allow_http` is set (owner policy).
2. **No URL credentials** — `user:pass@host` forms are refused.
3. **Domain policy** — deny list first, then the allow list when
   one is configured; matching is exact or subdomain.
4. **Resolution** — the host is resolved (resolver injectable for
   tests) and **every** resulting address is range-checked:
   loopback, private (RFC1918), link-local, reserved, multicast,
   unspecified, and the cloud metadata addresses
   `169.254.169.254` / `100.100.100.200` are all blocked.
   Resolution failure denies (fail closed).
5. **Redirects** — a redirect chain is re-validated hop by hop
   under the same rules; a chain that turns internal at any hop
   is denied at that hop, and chains are length-capped.

This is the SSRF defence for server-side fetches (§13): an
attacker-controlled URL that resolves — directly, by DNS
rebinding to a second answer, or via redirect — to an internal
address never passes (Scenario 9; unit tests with fake resolvers
cover multi-answer and redirect cases).

## Download guard

Executable extensions (`.exe .msi .bat .cmd .ps1 .sh .scr .dll
.com .jar …`) are rejected outright; other files are capped by
`download_max_bytes` and land with a `quarantine` disposition for
owner review. Filenames with traversal segments are stripped to
their basename.

## Scope note

The validator decides; it does not itself fetch. Callers (P-05
API tool, P-02 research) pass URLs through it before use. Direct
socket use outside these callers is out of P-10's reach and is
recorded as a standing limitation in the implementation report.
