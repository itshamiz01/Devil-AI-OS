#!/usr/bin/env bash
# Oracle Cloud VM provisioning for Devil-AI-OS.
#
# Runs on an Oracle Linux 8/9 VM (the OCI free-tier shape) as a user with
# sudo. It installs Docker, pulls the images, and starts the stack defined in
# deploy/oracle/docker-compose.yml. The app and PostgreSQL then run together
# on this one VM.
#
# Usage:
#   git clone <your-repo-url> devil-ai-os
#   cd devil-ai-os
#   sudo bash scripts/oracle_vm_setup.sh
#
# The script is idempotent: re-running it is safe.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="$REPO_DIR/deploy/oracle"

echo "==> Devil-AI-OS Oracle Cloud VM setup"
echo "    repo: $REPO_DIR"

# 1. Install Docker (Oracle Linux AppStream + Docker CE repo).
if ! command -v docker >/dev/null 2>&1; then
    echo "==> Installing Docker"
    sudo dnf install -y dnf-plugins-core
    sudo dnf config-manager --add-repo \
        https://download.docker.com/linux/oracle/oraclelinux8/stable/\$basearch/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
else
    echo "==> Docker already installed"
fi

# 2. Enable and start Docker, and let the current user use it without sudo.
echo "==> Starting Docker"
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
# Apply the group membership for this shell.
newgrp docker 2>/dev/null || true

# 3. Ensure the compose env file exists.
cd "$COMPOSE_DIR"
if [ ! -f .env ]; then
    echo "==> No .env found; copying .env.example"
    cp .env.example .env
    echo "    EDIT $COMPOSE_DIR/.env and set real POSTGRES_PASSWORD and OWNER_PASSWORD"
    echo "    then re-run: sudo bash scripts/oracle_vm_setup.sh"
    exit 1
fi

# 4. Build and start the stack.
echo "==> Building and starting the stack (Postgres + API)"
docker compose --env-file .env up -d --build

# 5. Wait for the API to become healthy.
echo "==> Waiting for the API to become healthy..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/api/v1/health/live >/dev/null 2>&1; then
        echo "==> API is healthy."
        echo
        echo "Deployment complete."
        echo "  API:     http://<YOUR-VM-PUBLIC-IP>:8000"
        echo "  Swagger: http://<YOUR-VM-PUBLIC-IP>:8000/docs"
        echo "  Login:   owner / (the OWNER_PASSWORD you set in .env)"
        echo
        echo "Logs:  docker compose logs -f"
        echo "Stop:  docker compose down"
        exit 0
    fi
    sleep 2
done

echo "==> API did not become healthy within 60s. Check logs:"
echo "    docker compose logs -f"
exit 1
