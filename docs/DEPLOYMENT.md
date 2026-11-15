# Deployment Guide

Devil-AI-OS is a Python/FastAPI backend (no frontend). It deploys to Vercel (or
any container host) via the `Dockerfile` at the repository root, backed by an
external PostgreSQL database (Supabase or Vercel Postgres).

## What this release adds

The application was built as a local-first backend that bound loopback only and
required an interactive `init-owner`. This adds the hosted-deployment layer:

- **`Dockerfile`** — container image that runs uvicorn on `0.0.0.0`.
- **`vercel.json`** — Vercel config with a health check on `/api/v1/health/live`.
- **Hosted mode** (`AUTONOMUS_HOSTED=true`) — the approved opt-in that lets the
  process bind `0.0.0.0`. Loopback remains the secure default; any remote bind
  without hosted mode is refused at startup.
- **Non-interactive owner bootstrap** — `AUTONOMUS_OWNER_BOOTSTRAP_USERNAME` /
  `AUTONOMUS_OWNER_BOOTSTRAP_PASSWORD` create the owner at startup when no owner
  exists. An existing owner is never overwritten on redeploy.
- **Serverless-safe logging** — file logging is best-effort; a read-only or
  ephemeral filesystem never breaks startup (stream logs always go out).
- **PostgreSQL on startup** — the DB layer already supported an external
  `DATABASE_URL`; migrations run on startup by default.

## Deploy to Vercel

### 1. Prepare a PostgreSQL database

The backend needs PostgreSQL (SQLite is local-only and will not persist on a
serverless host). Create one — Supabase or Vercel Postgres both work:

- Copy the **connection string** (use the **direct** connection for migrations,
  not the transaction-pooler one — pgbouncer breaks multi-statement DDL).
- Note two connection strings if your provider exposes them:
  - `AUTONOMUS_DATABASE_URL` — runtime traffic (pooled OK).
  - `AUTONOMUS_DATABASE_URL_direct` — migrations only (direct connection).

### 2. Connect the repo to Vercel

- Import the repository on Vercel.
- Vercel detects the `Dockerfile` and builds the image automatically. No build
  command or framework to configure.

### 3. Set the environment variables

In the Vercel project → Settings → Environment Variables:

| Variable | Example value | Purpose |
|---|---|---|
| `AUTONOMUS_ENVIRONMENT` | `production` | Deployment environment. |
| `AUTONOMUS_HOSTED` | `true` | **Required.** Enables the `0.0.0.0` bind. |
| `AUTONOMUS_HOST` | `0.0.0.0` | Bind address (set by the image, override if needed). |
| `AUTONOMUS_PORT` | `8000` | Listen port. |
| `AUTONOMUS_DATABASE_URL` | `postgresql://user:pw@host:5432/db` | Runtime DB (pooled OK). |
| `AUTONOMUS_DATABASE_URL_direct` | `postgresql://user:pw@host:5432/db` | Migrations (direct). |
| `AUTONOMUS_OWNER_BOOTSTRAP_USERNAME` | `owner` | Owner name to create on first boot. |
| `AUTONOMUS_OWNER_BOOTSTRAP_PASSWORD` | a 12+ char secret | Owner password (never committed). |
| `AUTONOMUS_RUN_MIGRATIONS_ON_STARTUP` | `true` | Apply migrations on boot. Set `false` for a multi-instance serverless deploy and apply migrations deliberately. |
| `AUTONOMUS_DOCS_ENABLED` | `true` | Swagger at `/docs` (set `false` to disable in production). |

### 4. Deploy

Push to the connected branch (or run **Deploy** in Vercel). Vercel builds the
Docker image and starts it. The health check at `/api/v1/health/live` confirms
the process is alive.

### 5. Verify

- `GET /api/v1/health/live` → `{"data":{"status":"alive"}}`
- `POST /api/v1/auth/login` with the bootstrap owner credentials → returns a token.
- `GET /api/v1/workforce/overview` (with the token) → 111 employees.
- `GET /docs` → Swagger UI.

## Notes

- **Migrations on a serverless host.** With multiple instances, two cold starts
  can race on the same revision. Set `AUTONOMUS_RUN_MIGRATIONS_ON_STARTUP=false`
  and run `alembic upgrade head` once (via a one-off job or CLI) before scaling.
- **The execution engine (filesystem + code adapters) does not run on a
  Postgres-only host.** On Vercel/Supabase the DB + API layer (workforce,
  Command Center, NL commands, finance, agents, tasks) is the shippable
  surface. The local execution adapters remain for a self-hosted runtime.
- **Owner rotation.** The bootstrap only creates the owner if none exists. To
  rotate the password, change the env var and restart — but the existing owner
  is not overwritten automatically; use the CLI `init-owner` against the
  database or an explicit credential change.
- **Local run (unchanged).** `cd backend && python -m app.cli init-owner &&
  python -m app.cli serve` still binds `127.0.0.1:8000` with SQLite. Hosted
  mode is off by default, so the local secure boundary is intact.
