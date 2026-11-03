# Publishing AUTONOMUS Work to GitHub (Windows)

`scripts/publish_to_github.ps1` publishes an AUTONOMUS work package to your GitHub repository in one command, using **your own** local Git authentication.

The script never asks for, stores, or transmits a password or token. Git Credential Manager or your browser handles sign-in.

## Easiest: double-click

Put `Publish-to-GitHub.cmd`, `publish_to_github.ps1` and the package ZIP in the same folder (Downloads is fine), then double-click **`Publish-to-GitHub.cmd`**.

A small menu appears:

| Choice | Action |
|---|---|
| `1` | Preview only — changes nothing, then returns to the menu |
| `2` | Publish now — commit and push |
| `3` | Publish + tests — run the backend tests first |
| `4` | Exit |

The window stays open after the run so you can read the result. Nothing is pushed until you pick `2` or `3`.

The launcher looks for `publish_to_github.ps1` beside itself first, then in `%USERPROFILE%\Devil-AI-OS\scripts\`, so it keeps working after the first publish even if you delete the Downloads copy.

## One command

Put the package ZIP in your Downloads folder and the script anywhere convenient, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\publish_to_github.ps1"
```

`-ExecutionPolicy Bypass` applies only to that single process. It does not change your machine's policy. If your organization forbids it, use the approved signing/policy process instead.

## What it does

1. Checks Git and your Git identity.
2. Finds the newest `AUTONOMUS_*.zip` in Downloads, Desktop, the current folder, or the script folder.
3. Inspects the package and rejects unsafe paths (zip-slip) and runtime/secret files.
4. Clones the repo if the target folder does not exist; otherwise reuses it.
5. Backs up files that will be overwritten into `backups/pre-publish-<timestamp>.zip` (gitignored).
6. Extracts only publishable files.
7. Optionally runs backend tests (`-RunTests`).
8. Stages only: `README.md`, `LICENSE`, `.gitignore`, `.env.example`, `backend`, `config`, `docs`, `scripts`, `shared`.
9. Blocks staged runtime/secret paths and scans staged text for credential patterns. On any hit it unstages everything and aborts.
10. Commits and pushes to `origin/main`. Never uses `--force`.

## Options

| Parameter | Purpose |
|---|---|
| `-PackagePath` | Explicit ZIP path instead of auto-detection |
| `-RepoDir` | Local repo folder (default `%USERPROFILE%\Devil-AI-OS`) |
| `-RepoUrl` | Clone URL (default `https://github.com/itshamiz01/Devil-AI-OS.git`) |
| `-Branch` | Target branch (default `main`) |
| `-CommitMessage` | Custom commit message |
| `-RunTests` | Run `python -m pytest -q` in `backend` before committing |
| `-DryRun` | Print the plan; make no changes |
| `-NoPush` | Commit locally without pushing |

## Recommended first run

Preview before changing anything:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\publish_to_github.ps1" -DryRun
```

Then publish with tests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\publish_to_github.ps1" -RunTests
```

## Never published

`data/`, `logs/`, `backups/`, `models/`, `secrets/`, `credentials/`, browser profiles, virtual environments, caches, `.git/`, real `.env` files, databases, model weights, `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*.log`, `*.bak`.

`.env.example` is published because it contains no secrets.

## If the push is rejected

Your commit is already safe locally. Usually the remote has newer commits:

```powershell
cd "$env:USERPROFILE\Devil-AI-OS"
git pull --rebase origin main
git push origin main
```

If authentication failed, sign in again through Git Credential Manager. Do not use `--force` and do not paste tokens into chat.

## Future phases

Each new phase produces a new package. Run the same command again. Re-publishing an unchanged package is a no-op ("Nothing new to commit").

## Limitations

- Windows-only by design; it refuses to run on other operating systems.
- The credential scan is a pattern-based safety net, not a complete secret scanner. Review `git show --stat` before pushing sensitive work.
- The script cannot grant repository access. You must already have write permission on the GitHub repo.
