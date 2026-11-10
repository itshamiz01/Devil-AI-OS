# Execution Adapter Architecture (P-05, §5.1 F / §7)

An adapter performs **one validated action** and returns a structured
`AdapterResult` (`success`, `output`, `summary`, `exit_code`,
`evidence[]`, `warnings[]`, `error_category`, `resource_usage`). Adapters
never decide policy — the policy engine has already run — and never talk
to the API layer. An adapter that cannot perform an action in this
environment returns `ADAPTER_UNAVAILABLE`; it never simulates success.

Every adapter implements `health()` returning
`{status, health_status, details}`; the registry records the outcome at
startup and the startup health report republishes it verbatim.

## The six tools (§7 seeds, `execution/constants.TOOL_SEEDS`)

### filesystem — `adapters/filesystem.py` — OPERATIONAL
Actions: `list read metadata hash search` (Risk 0), `mkdir create write
append copy move delete` (Risk 1), `delete_permanent` (Risk 2).
Capabilities: `file_read` / `file_write`.
Every path is re-validated inside the adapter (defense in depth):
Windows-lexical validation, then resolved containment in the workspace.
Writes are atomic (temp file + `os.replace`, fsync); overwrites snapshot
the previous version under `temporary/snapshots/<request_id>/` and record
before/after SHA-256. `delete` moves the target into the quarantine
workspace (reversible, named `<agent>__<timestamp>__<name>`);
`delete_permanent` applies only to files already in quarantine.

### documents — `adapters/documents.py` — OPERATIONAL (stdlib only)
Actions: `read_text read_csv summarize_csv` (Risk 0), `create_text
create_csv transform_csv` (Risk 1). Capabilities: `file_read`/`file_write`.
CSV transforms stream row-wise with a 100k-row processing bound.
**Deferred:** PDF and presentation formats — no existing project
dependency supports them and P-05 adds none.

### code_python — `adapters/code.py` — OPERATIONAL, PROCESS CONTROLS ONLY
Action: `run` (Risk 1, escalated by the §10.4 screen). Capability:
`sandboxed_code_execution`. Python only (the application interpreter,
argv-only exec, never a shell). Dedicated temp directory per run as cwd;
scrubbed environment built from an allowlist; stdout/stderr captured to
files and read back under caps; timeout enforced by process-tree
termination; POSIX CPU/file-size rlimits applied by a pre-exec bootstrap
where supported; the run directory is deleted after every run (evidence
= code hash, exit code, captured output, file names + hashes).
Isolation is labelled `process_controls_only` in the registry, the
health report, the evidence, and the docs — see
`docs/security/CODE_SANDBOX_SECURITY.md`. **Deferred languages:**
JavaScript/Node and PowerShell (not represented as available anywhere).

### api_http — `adapters/api.py` — OPERATIONAL
Actions: `get` (Risk 1, `api_read`), `post put patch delete` (Risk 2,
`api_write`). The transport (`HttpTransport`) follows redirects manually
(max 3) and **re-validates every hop**: scheme/host SSRF guard (P-03
`assert_url_allowed`) plus the owner-governed host allowlist.
Response bodies are capped while streaming. Retries apply only to
idempotent methods with bounded backoff; POST is never blindly retried.
Credential references (`env:NAME`) are resolved by the broker inside the
adapter and placed in the configured header; the value never reaches
results, logs, or tables. `trust_env=False`: proxy use is an explicit
setting (wired from the P-03 `research_proxy_url`), never ambient env.

### browser — `adapters/browser.py` — PARTIAL
Actions: `open_session navigate inspect extract screenshot close_session`
(Risk 0–1 reads), `interact` (Risk 2). Capability: `browser_interaction`.
Implemented: the full session model (per-session domain allowlists,
lifecycle, persistence in `execution_browser_sessions`), read-only
navigation/inspection/extraction over the SSRF-guarded transport, HTML
evidence snapshots into the agent's workspace (labelled as snapshots,
not rendered screenshots), authentication/CAPTCHA/MFA detection →
session `requires_human` + request REQUIRES_HUMAN_ACTION (§11.5), and
prompt-injection flagging of page content (§11.8).
**Unavailable here:** a live browser engine. Evidence (audit §7):
Playwright's package installs but its Chromium binary cannot be
downloaded from this sandbox's network (0 bytes from
cdn.playwright.dev), so `interact` returns ADAPTER_UNAVAILABLE. On the
owner's Windows machine a Playwright/Chromium backend attaches behind
this same session/policy layer (see `docs/operations/WINDOWS_SETUP.md`).

### desktop — `adapters/desktop.py` — DISABLED
Actions are named in the registry (`list_windows screenshot action`) so
the system can refuse them explicitly. The adapter reports `disabled`
with the reason and contains **no elevation path**: no UAC bypass, no
credential capture, no MFA interaction, no automation library at all.
Enablement is an owner decision on the Windows machine after the §12
evaluation (WINDOWS_SETUP.md).

## Registry lifecycle

Seeded from `TOOL_SEEDS`; `apply_health` records adapter health at
startup. Health can never resurrect an owner-disabled tool. Discovery
view (agents) exposes descriptions, actions, risk, required
capabilities — never `config_ref` contents or credentials; the admin
view (owner) adds health details and configuration references.
