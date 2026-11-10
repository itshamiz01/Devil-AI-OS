# Command Execution Security (P-10)

Execution remains P-05's. P-10's `CommandGuard` is the
deterministic pre-execution decision layer, and the two compose:
a command runs only if both allow it.

## Rules

1. **Structured argv only** — commands are argument arrays. A
   shell string, or any argument containing shell metacharacters
   (`; & | \` $ ( ) < >` or newlines), is refused outright: there
   is no shell to inject into.
2. **Denylist (checked before the allowlist)** — regex patterns
   for: disk formatting/imaging, shutdown/restart, security-tool
   disabling, registry modification, firewall changes,
   recursive/forced deletion, encoded PowerShell
   (`-EncodedCommand` and friends), credential extraction
   (mimikatz/sekurlsa), user-account manipulation, and
   download-piped-to-shell. A denylist hit is `blocked: true`.
3. **Allowlist** — the executable (basename, `.exe` stripped,
   case-insensitive) must be in `security.settings
   .command_allowlist` (defaults: git, python, node, npm, pytest,
   pip, ls/dir, type/cat, echo, mkdir). Unlisted executables are
   denied even when innocuous — fail closed.
4. **Mode** — safe_mode denies command execution for non-owners.
5. **Auditing** — when a denial-audit callback is wired, denials
   are recorded on the P-01 trail as
   `security.command_blocked` / `security.command_check`.

## Honest sandbox statement

P-05 executes commands as ordinary processes with timeouts and
environment controls. That is **process control, not a strong
sandbox**: there is no container, VM, or OS-level isolation, and
an allowed executable runs with the host user's rights. The
guard's job is to keep dangerous and unreviewed commands from
ever reaching that executor. Owners must treat the allowlist as
the security boundary it is. Strong sandboxing remains future
work (see the P-05 report's standing limitation).
