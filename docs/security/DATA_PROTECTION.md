# Data Protection (P-10)

## Classification

Five levels (1 public → 5 critical) with per-path overrides in
`security_data_classifications`. Defaults live in
ASSET_INVENTORY.md. Guards consult classifications for filesystem
decisions; the secret registry requires classification on every
entry.

## In transit

The staging deployment is local (loopback). Any remote exposure
is the owner's deployment decision and must terminate TLS at the
host — the application sets no insecure-transport exceptions.

## At rest — PARTIALLY IMPLEMENTED

- Passwords: scrypt hashes (P-01). Session tokens: SHA-256
  hashes (P-01). Approval parameters: SHA-256 bound (P-01).
- Secret *values* are never at rest in AUTONOMUS at all
  (metadata + broker).
- Database-file encryption is **platform** protection: on the
  owner's Windows machine this means BitLocker / DPAPI-backed
  storage — REQUIRES OWNER CONFIGURATION. The application ships
  no home-grown file encryption (deliberately: unreviewed crypto
  is worse than an honest platform dependency).
- Backups inherit the data directory's protection; their SHA-256
  manifests detect corruption/tampering of the copy.

## Minimization and retention

- Security events record pattern names and identifiers, never
  secret values or screened text.
- Login attempts are operational records; the owner may purge
  them as part of routine maintenance (they are not part of the
  sealed audit chain unless sealed while present).
- Memory retention/deletion follows P-09's lifecycle; P-10 adds
  no copies of memory content.
