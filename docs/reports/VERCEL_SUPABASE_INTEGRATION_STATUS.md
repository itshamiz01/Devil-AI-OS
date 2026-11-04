# Vercel + Supabase integration status

**Checked:** 2026-11-04 05:15 UTC · **Branch:** `arena/0a4e9e66-devil-ai-os` · Every figure below was read from a live API response or a build log this session. Nothing is inferred unless labelled as such.

## Timeline

| When (UTC) | Event | Source |
|---|---|---|
| 2026-11-03 23:07:19 | Production deployment created from `main@6dd3359` | `list_deployments` |
| 2026-11-03 23:07:46 | …reached READY, substate `PROMOTED` | `list_deployments` |
| 2026-11-03 23:18:04 | 14 `POSTGRES_*` / `SUPABASE_*` variables written by a Vercel integration (`configurationId icfg_JLlKVJhFNLPHA90PXilI6Hk7`) | `list_env_vars` |
| 2026-11-04 00:00:37 | Preview deployment created from `arena/0a4e9e66-devil-ai-os@4677963` | `list_deployments` |
| 2026-11-04 00:00:55 | …reached READY in **18 s**, substate `STAGED` | `get_deployment` |
| 2026-11-04 05:12:21 | **`AUTONOMUS_DATABASE_URL` created** — type `sensitive`, target `["production"]` | `list_env_vars` |

## Verified state

**Vercel project `backend`** (`prj_WAq5Y7UGoG3iohPgdJaAapGmDxNU`, team `hamidansari1795-9853s-projects`, hobby plan, framework `fastapi`):

- Two deployments, both READY. Production still serves `main@6dd3359` — the P-01 baseline. The newer one is a **preview** (`environment: preview`, `target: null`, `public: false`) built from the Postgres commit `4677963`.
- The build **succeeds without any deployment manifest**: one Python lambda, Python **3.14** from `backend/pyproject.toml`, uv 0.13.5, region **iad1**, function timeout 300 s, fluid compute.
- Requesting the preview URL returns Vercel's **"Protected Deployment"** SSO login page, so whether the application actually serves has **not** been observed.
- `AUTONOMUS_DATABASE_URL` exists and is **Production-scoped only**. Preview deployments do not receive it.
- The 14 integration variables are **dead config**: zero matches for `POSTGRES`, `SUPABASE`, `DATABASE_URL` in the codebase. *Inferred, not verified* — their values were never decrypted — that they point at the unrelated **Fit Life Bro** project.

**Supabase project `Devil-AI-OS`** (`mnezhftfapubgebnyrvev`, ap-southeast-1):

- **Not reachable through the connector.** `get_project` returns `400 Invalid project ref` and `list_projects` still returns only *Fit Life Bro* (`wuinqktcerhgbtqirpvu`, eu-west-1, org `wofbunyzjiezwncvwhul`). The connector token does not cover the organisation that owns the new project.
- Consequently **no migration has been applied** and no table count can be reported. The schema exists only as rendered SQL (ADR-0023, L-46).

**GitHub:** PR #2 is **OPEN**, head `4677963`. `main` is at `6dd3359`, 14 commits behind.

## Blockers, in the order they must clear

1. **PR #2 is unmerged.** Production deploys from `main`, which contains no Postgres support, so `AUTONOMUS_DATABASE_URL` is inert there regardless of its value.
2. **The connector cannot see the Supabase project.** Until it is re-authorised against the owning organisation, no migration can be applied or verified through this toolchain.
3. **`psycopg` was missing from `pyproject.toml`** — fixed in this commit. Any lambda built before it would have failed at import the moment the database URL was set.
4. **Serving is unverified** behind Deployment Protection (L-48).

## Cost of the region split

Functions run in **iad1** (Washington D.C.); the database is in **ap-southeast-1** (Singapore). Every query crosses continents. This API issues many small queries per request, so the latency is paid repeatedly rather than once (L-52). Either the function region or the database region should move — the database is empty today, which is the cheapest moment to change it.

## Post-publication verification

Commit `9d9e375` added the `psycopg[binary]==3.3.7` pin to `backend/pyproject.toml` and triggered deployment `dpl_2pUr6uyKzqGXEBr7owrRAEv98ovr`. It reached **READY in 20 s** with a clean log — `Installing required dependencies from pyproject.toml...` → `Compiling Python bytecode...` → `Build Completed in /vercel/output [9s]`, no warnings or errors. The build cache grew from **14.63 MB to 20.13 MB**, consistent with the driver and its binary wheel being newly installed.

So the driver resolves on **Python 3.14** under uv 0.13.5. What is still *not* proven is that the application imports and serves: the lambda has never been invoked, because the deployment is protected and no request has reached it (L-48).
