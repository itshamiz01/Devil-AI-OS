# Windows Setup (P-05, §27)

How P-05 is installed and verified on the owner's Windows machine (the
staging build runs on Linux; items marked **[verify on Windows]** have
never been executed on Windows and must not be assumed working).

## Prerequisites

- Windows 10 22H2+ / Windows 11 (owner's machine: i7-4712HQ, 16 GB RAM).
- Python 3.12 (the backend `.venv`), Node 20+ only if a later phase
  needs it — P-05 itself needs no Node.
- The staging tree transferred and the backend installed exactly as in
  the P-01–P-04 run guides (venv, dependencies, Alembic upgrade to head
  `6ffcc7e899fa`).

## Startup health report (§27)

On first boot, open `GET /api/v1/execution/health-report` and confirm
each adapter's stated status matches the machine:

- `filesystem`, `documents`, `api_http` → available/healthy.
- `code_python` → available, health `degraded` **by design**: the
  degraded flag carries the isolation note (`process_controls_only`).
  On Windows the POSIX rlimit bootstrap is skipped; timeout +
  process-tree termination (`taskkill /T /F`) still apply.
  **[verify on Windows]** first code run: a `time.sleep` snippet at a
  2-second timeout must end TIMED_OUT with no orphan `python.exe` in
  Task Manager.
- `browser` → degraded (fetch backend) until the interactive backend
  below is installed and tested.
- `desktop` → disabled (see below).

## Optional: interactive browser backend **[verify on Windows]**

1. Install Playwright + Chromium on the machine
   (`pip install playwright && playwright install chromium`) — the
   download that fails in the staging sandbox is expected to work on a
   normal connection.
2. Only after a supervised local test (open a session, navigate an
   allowlisted public page, run one approved click on a harmless test
   page) may a future change wire the Playwright backend into
   `BrowserAdapter` behind the existing session/policy layer.
3. The §11.5 rule does not change: CAPTCHA/MFA/login walls remain
   human-only; the adapter must keep returning
   REQUIRES_HUMAN_AUTHENTICATION.

## Desktop adapter evaluation (§12) **[plan only — nothing enabled]**

The §12 evaluation path for a later, separately-approved change:

- Candidate stack: Windows UI Automation via `pywinauto` (UIA backend),
  screenshots via the OS graphics stack, input only through approved,
  window-verified actions.
- Hard rules that any implementation must keep: no UAC bypass, no
  credential capture, no interaction with secure desktops / MFA /
  banking authentication / OS password prompts; an action requiring
  elevation returns REQUIRES_HUMAN_ACTION; the adapter starts disabled
  and is enabled only by an owner action after on-machine tests.
- Until that work is separately built and gated, the desktop tool stays
  DISABLED on Windows exactly as in staging.

## Owner configuration checklist

- [ ] Set `api_allowlist` / `browser_allowlist` deliberately (empty =
      nothing external reachable).
- [ ] Place API credentials in the server process environment under
      known names; agents reference them only as `env:NAME`.
- [ ] Confirm the execution workspace root location
      (`<data_dir>/execution_workspaces/`) is on a disk with room for
      quarantine + snapshots; include it in backups if the audit trail
      matters (audit itself lives in the database).
- [ ] Run the emergency-stop drill once (Operations doc) before
      granting any Level-2 capability.
