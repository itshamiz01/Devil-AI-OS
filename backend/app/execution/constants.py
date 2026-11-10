"""P-05 execution constants: §6.1 outcomes, §8 risk model, §7 tool seed
definitions, execution-settings defaults (§18) and the P-05 capability
support map (audit §6).

Honesty rules baked into the data:

- A tool action exists in the seed ONLY when an adapter in this build
  genuinely implements it. The desktop adapter's actions are seeded with
  the tool DISABLED — the registry must be able to *name* what it refuses.
- ``code_python.run`` is labelled with its true isolation strength
  (``process_controls_only``). Nothing anywhere in P-05 calls it a sandbox
  in the strong sense (§10.2).
- The browser tool's interactive actions are seeded, but their backend
  reports unavailable in this environment (audit §5); the tool's health
  is therefore DEGRADED, never healthy.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# §6.1 execution outcomes (request status vocabulary)
# ---------------------------------------------------------------------------
OUTCOMES = (
    "ACCEPTED", "VALIDATING", "AWAITING_APPROVAL", "QUEUED", "RUNNING",
    "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "REJECTED",
    "CANCELLED", "TIMED_OUT", "INTERRUPTED", "REQUIRES_HUMAN_ACTION",
    "REQUIRES_RECONCILIATION",
)

TERMINAL_OUTCOMES = {
    "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "REJECTED",
    "CANCELLED", "TIMED_OUT", "REQUIRES_RECONCILIATION",
}

# ---------------------------------------------------------------------------
# §15.3 workflow run states
# ---------------------------------------------------------------------------
WORKFLOW_STATES = (
    "DRAFT", "VALIDATING", "APPROVED", "QUEUED", "RUNNING", "PAUSED",
    "AWAITING_APPROVAL", "AWAITING_HUMAN", "COMPLETED", "FAILED",
    "CANCELLED", "RECOVERY_REQUIRED",
)

WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"VALIDATING", "QUEUED", "CANCELLED"},
    "VALIDATING": {"APPROVED", "QUEUED", "FAILED", "CANCELLED"},
    "APPROVED": {"QUEUED", "CANCELLED"},
    "QUEUED": {"RUNNING", "PAUSED", "CANCELLED"},
    "RUNNING": {"PAUSED", "AWAITING_APPROVAL", "AWAITING_HUMAN", "COMPLETED",
                "FAILED", "CANCELLED", "RECOVERY_REQUIRED"},
    "PAUSED": {"QUEUED", "RUNNING", "CANCELLED"},
    "AWAITING_APPROVAL": {"RUNNING", "PAUSED", "CANCELLED", "FAILED"},
    "AWAITING_HUMAN": {"RUNNING", "PAUSED", "CANCELLED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "RECOVERY_REQUIRED": {"QUEUED", "CANCELLED", "FAILED"},
}

# ---------------------------------------------------------------------------
# §7 tool seed definitions. Each action: name, risk (§8), capabilities,
# idempotent (§16.2 — only idempotent actions may ever be retried/resumed),
# description.
# ---------------------------------------------------------------------------
def _action(name, risk, capabilities, *, idempotent=False, description=""):
    return {"name": name, "risk_level": risk, "required_capabilities": capabilities,
            "approval_level": 2 if risk >= 2 else 0, "idempotent": idempotent,
            "description": description}


TOOL_SEEDS: list[dict] = [
    {
        "name": "filesystem", "adapter_type": "filesystem", "category": "filesystem",
        "version": "1.0.0",
        "description": "Controlled filesystem operations inside managed workspaces only (§9). Atomic writes, hash before/after, quarantine-based deletion.",
        "actions": [
            _action("list", 0, ["file_read"], idempotent=True, description="List a workspace directory."),
            _action("read", 0, ["file_read"], idempotent=True, description="Read an approved workspace file."),
            _action("metadata", 0, ["file_read"], idempotent=True, description="Retrieve file metadata."),
            _action("hash", 0, ["file_read"], idempotent=True, description="SHA-256 of a workspace file."),
            _action("search", 0, ["file_read"], idempotent=True, description="Search text within a workspace."),
            _action("mkdir", 1, ["file_write"], idempotent=True, description="Create a directory inside a workspace."),
            _action("create", 1, ["file_write"], idempotent=True, description="Create a new file (fails if it exists)."),
            _action("write", 1, ["file_write"], description="Atomically write (replace) a file; previous version snapshotted."),
            _action("append", 1, ["file_write"], description="Append content to a file."),
            _action("copy", 1, ["file_read", "file_write"], description="Copy a file within/between authorized workspaces."),
            _action("move", 1, ["file_write"], description="Move/rename a file within authorized workspaces."),
            _action("delete", 1, ["file_write"], description="Reversible deletion: move the file to the quarantine workspace."),
            _action("delete_permanent", 2, ["file_write"], description="Permanent deletion of a quarantined file. Risk 2: owner approval; standing authorizations never apply."),
        ],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "supported_os": ["windows", "linux", "darwin"],
        "resource_requirements": {"resource_class": "filesystem"},
        "timeout_default": 30.0, "retry_eligible": False, "idempotency_supported": True,
        "config_ref": "execution.adapters.filesystem",
    },
    {
        "name": "documents", "adapter_type": "documents", "category": "documents",
        "version": "1.0.0",
        "description": "Document and data operations (§14) on stdlib only: text/Markdown/CSV create, read, transform, summarize. PDF/presentation formats are DEFERRED (no existing dependency).",
        "actions": [
            _action("read_text", 0, ["file_read"], idempotent=True, description="Read a text/Markdown file in a workspace."),
            _action("read_csv", 0, ["file_read"], idempotent=True, description="Read a CSV file as structured rows."),
            _action("summarize_csv", 0, ["file_read"], idempotent=True, description="Deterministic CSV summary: row/column counts, headers, per-column type guess."),
            _action("create_text", 1, ["file_write"], idempotent=True, description="Create a text or Markdown document."),
            _action("create_csv", 1, ["file_write"], idempotent=True, description="Create a CSV file from structured rows."),
            _action("transform_csv", 1, ["file_read", "file_write"], description="Transform a CSV (select columns, filter rows by equality) into a new file."),
        ],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "supported_os": ["windows", "linux", "darwin"],
        "resource_requirements": {"resource_class": "filesystem"},
        "timeout_default": 30.0, "retry_eligible": False, "idempotency_supported": True,
        "config_ref": "execution.adapters.documents",
    },
    {
        "name": "code_python", "adapter_type": "code", "category": "code_execution",
        "version": "1.0.0",
        "description": "Controlled Python execution (§10). ISOLATION: process controls only (dedicated temp workspace, argv-only exec of the application interpreter, scrubbed environment, timeout with process-tree termination, output/input caps). This is NOT a strong sandbox (§10.2); arbitrary untrusted code is never grantable.",
        "actions": [
            _action("run", 1, ["sandboxed_code_execution"], description="Run an approved Python snippet in the controlled environment. Dangerous-pattern screen (§10.4) may escalate to Risk 2 (hash-bound approval) or reject."),
        ],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "supported_os": ["windows", "linux", "darwin"],
        "resource_requirements": {"resource_class": "subprocess", "isolation": "process_controls_only"},
        "timeout_default": 30.0, "retry_eligible": False, "idempotency_supported": False,
        "config_ref": "execution.adapters.code",
    },
    {
        "name": "api_http", "adapter_type": "api", "category": "api",
        "version": "1.0.0",
        "description": "Generic HTTP execution (§13) over the SSRF-guarded transport pattern: host allowlist, redirect re-validation, response caps, credential references resolved by the broker at execution time (values never stored or logged).",
        "actions": [
            _action("get", 1, ["api_read"], idempotent=True, description="GET an allowlisted host. Retried with backoff (idempotent)."),
            _action("post", 2, ["api_write"], description="POST to an allowlisted host. Risk 2. Never blindly retried."),
            _action("put", 2, ["api_write"], description="PUT to an allowlisted host. Risk 2."),
            _action("patch", 2, ["api_write"], description="PATCH an allowlisted host. Risk 2."),
            _action("delete", 2, ["api_write"], description="DELETE on an allowlisted host. Risk 2."),
        ],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "supported_os": ["windows", "linux", "darwin"],
        "resource_requirements": {"resource_class": "api"},
        "timeout_default": 30.0, "retry_eligible": True, "idempotency_supported": True,
        "config_ref": "execution.adapters.api",
    },
    {
        "name": "browser", "adapter_type": "browser", "category": "browser",
        "version": "1.0.0",
        "description": "Governed browser sessions (§11). Read path (navigate/inspect/extract/screenshot-reference) runs on the SSRF-guarded fetch backend and is genuinely tested. INTERACTIVE actions (click/type/submit) require the Playwright/Chromium backend, which is UNAVAILABLE in this environment (audit §5) — they fail truthfully as adapter-unavailable. Auth challenges are never bypassed: sessions enter REQUIRES_HUMAN_AUTHENTICATION.",
        "actions": [
            _action("open_session", 1, ["browser_interaction"], idempotent=True, description="Open a session with a domain allowlist."),
            _action("navigate", 1, ["browser_interaction"], idempotent=True, description="Read-only navigation to an allowlisted domain (fetch backend)."),
            _action("inspect", 1, ["browser_interaction"], idempotent=True, description="Inspect the current page (title, text, links)."),
            _action("extract", 1, ["browser_interaction"], idempotent=True, description="Extract visible text / price mentions from the current page."),
            _action("screenshot", 1, ["browser_interaction"], idempotent=True, description="Capture page evidence. Fetch backend stores an HTML snapshot reference (no rendered image without the interactive backend)."),
            _action("interact", 2, ["browser_interaction"], description="Click/type/submit. Risk 2 AND requires the interactive backend (unavailable in this environment)."),
            _action("close_session", 0, ["browser_interaction"], idempotent=True, description="Close a session."),
        ],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "supported_os": ["windows", "linux", "darwin"],
        "resource_requirements": {"resource_class": "browser"},
        "timeout_default": 30.0, "retry_eligible": False, "idempotency_supported": True,
        "config_ref": "execution.adapters.browser",
    },
    {
        "name": "desktop", "adapter_type": "desktop", "category": "desktop",
        "version": "1.0.0",
        "description": "Windows desktop automation (§12). DISABLED in this environment: Windows UI Automation cannot exist or be tested on the Linux staging sandbox. Interface only; every action is refused as adapter-disabled. On the owner's Windows machine the §12 evaluation (UI Automation/pywinauto) is the enablement path — see docs/operations/WINDOWS_SETUP.md.",
        "actions": [
            _action("list_windows", 1, [], idempotent=True, description="Enumerate approved application windows (Windows only)."),
            _action("screenshot", 1, [], idempotent=True, description="Capture a screenshot of a verified window (Windows only)."),
            _action("action", 2, [], description="Controlled desktop interaction (Windows only, sensitive actions owner-approved)."),
        ],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "supported_os": ["windows"],
        "resource_requirements": {"resource_class": "desktop"},
        "timeout_default": 30.0, "retry_eligible": False, "idempotency_supported": False,
        "config_ref": "execution.adapters.desktop",
        "seed_status": "disabled",
        "seed_health": "unavailable",
    },
]

TOOL_SEED_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOOL_SEEDS}

# ---------------------------------------------------------------------------
# Capabilities P-05 backs (audit §6). startup flips ``supported`` for these
# through the catalogue table; grants still flow ONLY through the P-04
# factory (owner approval for Level 2). ``code_generation`` stays P-06,
# ``memory_write`` stays P-09, ``external_communication`` stays unsupported
# (no messaging adapter exists in P-05), financial stays P-07.
# ---------------------------------------------------------------------------
P05_SUPPORTED_CAPABILITIES: dict[str, str] = {
    "file_read": "Reads through the P-05 filesystem/documents adapters, inside managed workspaces only (path-validated). Granted per agent via the factory.",
    "file_write": "Writes through the P-05 filesystem/documents adapters, inside managed workspaces only: atomic writes, integrity hashes, quarantine-based deletion; permanent deletion is Risk 2.",
    "api_read": "Read-only HTTP (GET) through the P-05 API adapter: host allowlist, SSRF guard, redirect re-validation, response caps.",
    "api_write": "Mutating HTTP (POST/PUT/PATCH/DELETE) through the P-05 API adapter. Risk 2 per call: owner approval or a narrow standing authorization.",
    "sandboxed_code_execution": "Controlled Python execution through the P-05 code adapter. Isolation is PROCESS CONTROLS ONLY (temp workspace, scrubbed env, timeout + process-tree kill, caps) — not a strong sandbox; dangerous-pattern screen applies.",
    "browser_interaction": "Governed browser sessions through the P-05 browser adapter: domain allowlists, read-only navigation/inspection/extraction via the SSRF-guarded fetch backend. Interactive automation requires a browser engine that is unavailable in the staging environment and is refused truthfully there.",
}

# ---------------------------------------------------------------------------
# Execution settings (§18) — stored in system_config under SETTINGS_KEY,
# writable ONLY by the owner (mirrors the P-04 factory settings pattern).
# ---------------------------------------------------------------------------
SETTINGS_KEY = "execution.settings"
SETTINGS_VERSION = "execution-settings-v1"

DEFAULT_SETTINGS: dict = {
    "max_concurrent_runs": 4,
    "max_concurrent_subprocesses": 2,
    "max_browser_sessions": 2,
    "max_api_concurrency": 4,
    "max_workflow_concurrency": 2,
    "default_timeout_seconds": 60,
    "max_timeout_seconds": 600,
    "max_input_bytes": 5_000_000,
    "max_output_bytes": 1_000_000,
    "approval_expiry_minutes": 30,
    "emergency_stop": False,
    "code_execution_enabled": True,
    # Owner-governed allowlists. Empty = nothing external is reachable.
    "browser_allowlist": [],
    "api_allowlist": [],
}

# Managed workspace layout under the execution root (§9.1, adapted).
WORKSPACE_KINDS = ("shared", "projects", "businesses", "agent_workspaces", "temporary", "quarantine")
SYSTEM_WORKSPACES = ("shared", "projects", "businesses", "temporary", "quarantine")

# Parameter keys that must never carry raw secret values (§19). A value is
# acceptable ONLY as a credential reference of the form ``env:NAME``.
SECRET_KEY_HINTS = ("password", "token", "secret", "api_key", "apikey", "authorization", "cookie", "private_key")
