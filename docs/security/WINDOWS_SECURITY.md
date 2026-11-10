# Windows Security (P-10)

Status for every Windows-specific mechanism in this document:
**REQUIRES OWNER CONFIGURATION** — the staging host is Linux, so
these are designed, interfaced and fake-tested only. Nothing here
was exercised on Windows, and this document does not claim
otherwise.

## Credential storage (DPAPI / Credential Manager)

- Secret references may take the form `windows-vault:NAME`.
- `WindowsVaultBackend` is the interface: on a non-Windows host
  it reports `available: false` with status
  `REQUIRES OWNER CONFIGURATION` (verified in the smoke §1 and
  integration tests). On the owner's Windows machine, the
  intended binding is the Windows Credential Manager / DPAPI via
  a small platform adapter — to be implemented and verified
  during the owner's Windows deployment (P-00 environment work),
  not simulated here.
- Until then, `env:NAME` references with owner-managed
  environment variables are the working backend on any platform.

## Platform notes for the owner deployment

- Run AUTONOMUS under a dedicated low-privilege Windows user;
  the command guard's allowlist assumes host-user rights.
- Enable BitLocker on the data volume (this is the at-rest
  protection P-10 relies on — see DATA_PROTECTION.md).
- Windows Defender / firewall changes are on the command
  denylist by design; AUTONOMUS will refuse its own attempts to
  alter them.
- Windows Event Log forwarding of the audit chain head (an
  off-process anchor) is recommended but not implemented.
