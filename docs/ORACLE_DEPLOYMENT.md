# Deploying Devil-AI-OS on Oracle Cloud

This deploys the **entire stack on a single Oracle Cloud (OCI) VM**: the FastAPI
app and PostgreSQL run side by side on the same machine. There is no Supabase
and no Vercel — the app connects to a PostgreSQL that lives on the VM itself.

This is the simplest, most reliable setup: one VM, one public IP, no
per-project limits, no account switching.

## What runs where

| Component | Where | Notes |
|---|---|---|
| FastAPI app | Oracle VM (Docker) | Binds `0.0.0.0:8000`, hosted mode on |
| PostgreSQL 17 | Oracle VM (Docker) | Internal compose network, not exposed publicly |
| Migrations + 111-employee workforce seed | On app startup | Automatic, idempotent |

## Prerequisites

- An **Oracle Cloud (OCI) account** with access to the free tier.
- Ability to create a VM and SSH into it.

## Step 1 — Create an Oracle Cloud free-tier VM

1. Sign in to the **Oracle Cloud Console** at https://console.oraclecloud.com
2. Create a **compartment** (or use the default one).
3. Go to **Compute → Instances → Create**.
4. Choose the **Always Free** shape — typically **`VM.Standard.E2.1.Micro`**
   (1/8 OCPU, 1 GB RAM). This fits the app + Postgres.
5. **Image**: Oracle Linux 8 (or 9), x86.
6. **Networking**: keep the default VCN and subnet. The VM gets a public IP by
   default. Note the **public IP** — you'll need it.
7. **Security list / NSG**: add two ingress rules so the VM is reachable:
   - **SSH (22)** from your IP (to log in)
   - **HTTP (8000)** from `0.0.0.0/0` (to reach the API)
8. Create the instance, wait for it to reach **Running** state, and copy the
   SSH key/command from the instance details.

## Step 2 — SSH into the VM

```bash
ssh -i <your-key.pem> opc@<VM-PUBLIC-IP>
```

## Step 3 — Run the provisioning script

On the VM, install Git, clone the repo, and run the setup script:

```bash
# Install Git (Oracle Linux uses dnf)
sudo dnf install -y git

# Clone your repo (push your branch first, then clone)
git clone <your-repo-url> devil-ai-os
cd devil-ai-os

# Provision: installs Docker, builds the app, starts Postgres + API
sudo bash scripts/oracle_vm_setup.sh
```

The script will:
1. Install Docker (Oracle Linux + Docker CE).
2. Copy `deploy/oracle/.env.example` to `.env` if none exists — **edit it** to
   set a real `POSTGRES_PASSWORD` and `OWNER_PASSWORD`, then re-run.
3. Build the app image and start Postgres + the API.
4. Wait for the API health check to pass.

## Step 4 — Open the firewall (if not done in Step 1)

If you didn't add the ingress rules during VM creation, add them now in the
OCI console (**Compute → Instances → your VM → Virtual cloud network**):
- Ingress rule: TCP **8000**, source `0.0.0.0/0`
- Ingress rule: TCP **22**, source your IP

## Step 5 — Verify

Open in your browser (use the VM's public IP):

| URL | What it is |
|---|---|
| `http://<VM-PUBLIC-IP>:8000/api/v1/health/live` | Health check → `{"status":"alive"}` |
| `http://<VM-PUBLIC-IP>:8000/docs` | Swagger UI |
| `http://<VM-PUBLIC-IP>:8000/api/v1/workforce/overview` | 111-employee organization |

**Log in** (owner account created from `OWNER_PASSWORD` in `.env`):
- Username: `owner`
- Password: whatever you set for `OWNER_PASSWORD`

## Managing the deployment

All commands run from `deploy/oracle/`:

```bash
cd deploy/oracle

# View logs
docker compose logs -f

# Follow API logs only
docker compose logs -f api

# Restart the app
docker compose restart api

# Stop everything (data preserved in the pgdata volume)
docker compose down

# Stop and wipe the database (destructive — deletes all data)
docker compose down -v
```

## Configuration

All runtime configuration is in `deploy/oracle/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER` | `devil` | Postgres role |
| `POSTGRES_PASSWORD` | *(set it)* | Postgres password |
| `POSTGRES_DB` | `devil` | Postgres database name |
| `OWNER_USERNAME` | `owner` | Owner account created on first start |
| `OWNER_PASSWORD` | *(set it)* | Owner password (12+ chars) |

The app reads its full configuration from `AUTONOMUS_*` environment variables
(see `docs/architecture/CONFIGURATION_REFERENCE.md`). The compose file sets the
hosted-mode, database, and owner-bootstrap values; you can add more
`AUTONOMUS_*` variables to the `api` service's `environment:` block as needed.

## Notes

- **PostgreSQL, not Oracle Database.** Oracle Cloud does not offer a managed
  Postgres, so PostgreSQL 17 runs in a container on the VM. The app's external
  DB path is Postgres-only (the `psycopg` driver and Postgres migrations);
  Oracle Database (ADB) is not compatible with the app's schema.
- **Backups.** The Postgres data lives in the `pgdata` Docker volume on the VM.
  For durability, take periodic `pg_dump` backups or snapshot the VM's block
  volume. The app's own SQLite backup path is not used here (the DB is
  Postgres, not SQLite).
- **Resource use.** The free-tier `VM.Standard.E2.1.Micro` (1 GB RAM) runs the
  app + Postgres comfortably. If you scale up the VM, no code changes are
  needed.
- **Upgrades.** `git pull` on the VM, then `docker compose up -d --build` in
  `deploy/oracle/`. Migrations apply automatically on startup if the schema is
  not at head.
