# Publish Script Validation Report

**Date:** 2026-11-03
**Script:** `scripts/publish_to_github.ps1`
**Validation engine:** PowerShell 7.6.9 on Linux (parser + functional harness against a local bare Git remote)

## Scope and honesty note

The script targets Windows and refuses to run on non-Windows systems. To validate its logic, a harness copy was executed on Linux with **only** the operating-system guard removed. Path handling was made separator-aware, so the same code paths were exercised. Windows-specific behaviour (Credential Manager prompt, NTFS hidden attribute, drive paths) is **not** certified by this report.

## Defects found and fixed during validation

| # | Defect | Impact | Fix |
|---|---|---|---|
| 1 | `validate_environment.ps1` (shipped in P-01) used a bash heredoc `python - <<'PY'` | Script could not parse in PowerShell at all | Rewritten using a PowerShell here-string piped to `python -` |
| 2 | Zip-slip guard hardcoded `\` as the separator | Extraction aborted; guard was platform-fragile | Introduced `$Sep = [System.IO.Path]::DirectorySeparatorChar` throughout |
| 3 | Extraction reused `ZipArchiveEntry` objects from a disposed archive | "Cannot access a disposed object" on every run | Store entry names; re-resolve entries from the reopened archive |
| 4 | `Get-Item` / `Get-Content` without `-Force` | Could not read dotfiles such as `.env.example` | Added `-Force` |
| 5 | `Compress-Archive` cannot read hidden dotfiles | Backup step failed on re-runs | Replaced with a direct `System.IO.Compression.ZipArchive` writer |
| 6 | Backup list stored absolute paths, then re-joined them | Doubled path (`/repo/repo/README.md`) | Store relative paths |

Defect 1 was a genuine bug in previously delivered P-01 code and is now corrected.

## Tests executed

| Test | Expectation | Result |
|---|---|---|
| T1 Parse all `.ps1` files | No syntax errors | **Pass** — 7/7 scripts parse |
| T2 `-DryRun` on a fresh target | No clone, no extract, no commit | **Pass** — target folder not created |
| T3 Fresh publish | Clone, extract, safety gate, commit, push | **Pass** — commit pushed to the test remote |
| T3a Runtime isolation | No `data/`, `logs/`, `backups/` tracked | **Pass** |
| T3b Publisher included | `scripts/publish_to_github.ps1` present on remote | **Pass** |
| T4 Re-run same package | No duplicate commit | **Pass** — "Nothing new to commit" |
| T5 `-NoPush` | Commit local only | **Pass** — local ahead, remote unchanged |
| T6 Malicious package | Block `.env`, `logs/`, `data/`; detect credential in `docs/LEAK.md`; abort | **Pass** — files skipped, credential detected, staging reset, nothing pushed |

## Security behaviour verified

- Zip-slip paths rejected.
- Runtime and secret files skipped during extraction.
- Staged-path blocklist enforced before commit.
- Credential patterns (`ghp_`, `github_pat_`, `sk-`, `AKIA`, PEM private key headers) detected in staged text; on detection the script runs `git reset` and aborts.
- No `--force` push anywhere in the script.
- No credential input, storage, or transmission.

## Remaining limitations

- Not executed on Windows; Windows sign-in flow unverified.
- Pattern-based secret detection can produce false negatives; human review is still required.
- Requires existing write access to the GitHub repository.
- The backend test suite is unaffected by these script changes.
