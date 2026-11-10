"""Expansion Feature 2 live smoke: boots the real application
under uvicorn (auto-migrating a throwaway database through the
new F02 migration, serving the built Command Center at /app) and
drives the Universal Integration Framework surface over HTTP:

seeded registry (reference connector configured; the P-07/P-17/
P-18 surfaces honestly requires_owner_configuration) -> health ->
broker-authorized echo invocation -> idempotent replay -> honest
failures (unconfigured Stripe, bad payload) -> disable/enable ->
custom registration that cannot be enabled without an adapter ->
the API catalogue + OpenAPI permission metadata -> the audit
trail carries the framework's events.

Run:

    .venv/bin/python scripts/f02_smoke.py

Writes a transcript to docs/reports/F02_SMOKE_EVIDENCE.txt
(relative to the repository root).
"""
from __future__ import annotations

import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

PORT = random.randint(20000, 45000)
ROOT = f"http://127.0.0.1:{PORT}"
BASE = f"{ROOT}/api/v1"
PASSWORD = "smoke-owner-password-123"

LINES: list[str] = []
PASS = 0
FAIL = 0


def log(line: str = "") -> None:
    print(line)
    LINES.append(line)


def check(label: str, condition: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if condition:
        PASS += 1
        log(f"  [PASS] {label} {detail}")
    else:
        FAIL += 1
        log(f"  [FAIL] {label} {detail}")
    return condition


def data_of(response: httpx.Response):
    try:
        return response.json().get("data")
    except Exception:
        return None


def owner_login(client: httpx.Client) -> dict:
    """Patient owner login behind the readiness gate (the P-17
    boot-window observation: log the attempt count, never patch
    around auth)."""
    for attempt in range(1, 31):
        resp = client.post("/auth/login", json={
            "username": "owner", "password": PASSWORD})
        if resp.status_code == 200:
            log(f"owner login succeeded on attempt {attempt}")
            token = resp.json()["data"]["access_token"]
            return {"Authorization": f"Bearer {token}"}
        time.sleep(1.0)
    raise RuntimeError("owner login never succeeded")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="f02-smoke-"))
    db_path = tmp / "smoke.db"
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(tmp / "data"),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{db_path}",
        "AUTONOMUS_ADMIN_PASSWORD": PASSWORD,
        "AUTONOMUS_SERVICE_TOKEN": "smoke-service-token",
        "AUTONOMUS_AUTO_MIGRATE": "true",
        "AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD": "false",
        "TMPDIR": "/tmp",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host",
         "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    client = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
    root_client = httpx.Client(base_url=ROOT, timeout=60, trust_env=False)
    try:
        for _ in range(60):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        service_auth = {"Authorization": "Bearer smoke-service-token"}
        ready = False
        for _ in range(120):
            try:
                if client.get("/health/ready",
                              headers=service_auth).status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("== Expansion Feature 2 smoke: Universal Integration Framework ==")
        check("server ready", ready)

        # The fresh database was auto-migrated through F02.
        con = sqlite3.connect(db_path)
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        con.close()
        check("migration head is F02", head == "3f7a1c9e52b4", f"({head})")
        check("228 physical tables", tables == 228, f"({tables})")

        headers = owner_login(client)

        # --- framework status + seeded registry
        status = data_of(client.get("/integrations/framework/status",
                                    headers=headers)) or {}
        check("framework reports API version 1.2.0",
              status.get("api_version") == "1.2.0")
        check("18 connectors seeded", status.get("connector_count") == 18,
              f"({status.get('connector_count')})")
        check("exactly one has an adapter", status.get("with_adapter") == 1)

        connectors = data_of(client.get("/integrations", headers=headers,
                                        params={"limit": 100})) or []
        by_key = {row["key"]: row for row in connectors}
        echo = by_key.get("local_echo", {})
        check("reference connector enabled + configured",
              echo.get("lifecycle_status") == "enabled"
              and echo.get("state") == "configured")
        stripe = by_key.get("stripe", {})
        check("Stripe honestly requires owner configuration",
              stripe.get("state") == "requires_owner_configuration"
              and stripe.get("has_adapter") is False)
        check("P-17 + P-18 surfaces registered",
              sum(1 for k in by_key if k.startswith("growth_")) == 8
              and sum(1 for k in by_key if k.startswith("experience_")) == 8)

        # --- health + broker-authorized invocation
        resp = client.post("/integrations/local_echo/health", headers=headers)
        check("health check on the reference connector",
              resp.status_code == 200
              and data_of(resp)["state"] == "configured")

        resp = client.post("/integrations/local_echo/invoke", headers=headers,
                           json={"capability": "echo",
                                 "payload": {"message": "framework online"}})
        invoked = data_of(resp) or {}
        check("echo invocation succeeds through the broker",
              resp.status_code == 200 and invoked.get("outcome") == "success"
              and invoked.get("result", {}).get("echo") == "framework online")
        check("invocation carries its broker decision",
              invoked.get("broker_decision_id") is not None)

        resp = client.post("/integrations/local_echo/invoke", headers=headers,
                           json={"capability": "echo",
                                 "payload": {"message": "framework online"},
                                 "idempotency_key": "smoke-req-1"})
        first = data_of(resp) or {}
        resp = client.post("/integrations/local_echo/invoke", headers=headers,
                           json={"capability": "echo",
                                 "payload": {"message": "framework online"},
                                 "idempotency_key": "smoke-req-1"})
        replay = data_of(resp) or {}
        check("idempotent replay returns the recorded result",
              first.get("outcome") == "success"
              and replay.get("outcome") == "duplicate"
              and replay.get("result") == first.get("result"))

        # --- honest failure paths
        resp = client.post("/integrations/stripe/invoke", headers=headers,
                           json={"capability": "balances", "payload": {}})
        check("unconfigured Stripe invocation fails honestly (502)",
              resp.status_code == 502
              and resp.json()["error"]["details"]["outcome"]
              == "requires_owner_configuration")
        resp = client.post("/integrations/local_echo/invoke", headers=headers,
                           json={"capability": "echo",
                                 "payload": {"message": 42}})
        check("schema-violating payload refused (422)",
              resp.status_code == 422)

        resp = client.post("/integrations/local_echo/disable", headers=headers)
        check("owner disables the reference connector",
              resp.status_code == 200
              and data_of(resp)["lifecycle_status"] == "disabled")
        resp = client.post("/integrations/local_echo/invoke", headers=headers,
                           json={"capability": "echo",
                                 "payload": {"message": "while disabled"}})
        check("invocation while disabled fails honestly (502)",
              resp.status_code == 502)
        resp = client.post("/integrations/local_echo/enable", headers=headers)
        check("owner re-enables the reference connector",
              resp.status_code == 200
              and data_of(resp)["state"] == "configured")

        # --- a declaration alone is never a working connector
        resp = client.post("/integrations", headers=headers, json={
            "key": "smoke_custom", "name": "Smoke Custom",
            "provider": "Example", "kind": "rest_api",
            "capabilities": [{"name": "ping", "permission": "execute_tools",
                              "risk_action": "network.fetch"}]})
        check("custom connector registers as a declaration",
              resp.status_code == 201
              and data_of(resp)["state"] == "requires_owner_configuration")
        resp = client.post("/integrations/smoke_custom/enable",
                           headers=headers)
        check("enabling an adapter-less connector is refused (422)",
              resp.status_code == 422)

        # --- API catalogue + OpenAPI metadata (review §2 fixes)
        catalogue = data_of(client.get("/integrations/api-catalogue",
                                       headers=headers)) or {}
        invoke_op = next((op for op in catalogue.get("operations", [])
                          if op["path"] == "/api/v1/integrations/{key}/invoke"
                          and op["method"] == "POST"), {})
        check("catalogue names the invoke permission",
              invoke_op.get("required_permission") == "execute_tools"
              and invoke_op.get("authorization_depth") == "route")
        check("catalogue counts exactly 3 public operations",
              catalogue.get("by_authorization_depth", {}).get("public") == 3)
        schema = root_client.get("/openapi.json").json()
        check("OpenAPI version is 1.2.0",
              schema["info"]["version"] == "1.2.0")
        op = schema["paths"]["/api/v1/integrations/{key}/invoke"]["post"]
        check("OpenAPI carries x-required-permission",
              op.get("x-required-permission") == "execute_tools")

        # --- invocation ledger + audit trail
        invocations = data_of(client.get(
            "/integrations/local_echo/invocations", headers=headers)) or []
        outcomes = {row["outcome"] for row in invocations}
        check("invocation ledger records success, duplicate, refusal",
              {"success", "duplicate", "not_configured",
               "invalid_request"} <= outcomes, f"({sorted(outcomes)})")
        audit = client.get("/security/audit", headers=headers,
                           params={"action_prefix": "integration.",
                                   "limit": 100})
        actions = {row["action"] for row in (data_of(audit) or [])}
        check("audit trail records framework events",
              {"integration.invoked", "integration.connector_enabled",
               "integration.connector_registered"} <= actions,
              f"({sorted(actions)})")

        # --- the built Command Center is served
        spa = root_client.get("/app/")
        check("Command Center served at /app", spa.status_code == 200)

        log(f"\n== F02 SMOKE: {PASS} passed, {FAIL} failed ==")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = REPO / "docs" / "reports" / "F02_SMOKE_EVIDENCE.txt"
    out.write_text("\n".join(LINES) + "\n")
    log(f"transcript written to {out}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
