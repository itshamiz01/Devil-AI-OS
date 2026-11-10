"""Expansion Feature 1 live smoke: boots the real application
under uvicorn (auto-migrating a throwaway database through the
new F01 migration, serving the built Command Center at /app) and
drives the Identity & Device Security surface over HTTP:

enrol (untrusted, secret shown once) -> device login refused
while untrusted -> trust -> bad-secret login refused -> device-
bound login -> session list shows the binding -> recovery codes
(generate once, verify, single-use) -> secret rotation (old
secret and its sessions die) -> revocation (terminal; sessions
die) -> the audit trail carries every event.

Run:

    .venv/bin/python scripts/f01_smoke.py

Writes a transcript to docs/reports/F01_SMOKE_EVIDENCE.txt
(relative to the repository root).
"""
from __future__ import annotations

import json
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
PASSWORD = "<MASKED_SECRET_002>"

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


def login(client: httpx.Client, **extra) -> httpx.Response:
    return client.post("/auth/login", json={
        "username": "owner", "password": PASSWORD, **extra})


def owner_login(client: httpx.Client) -> dict:
    """Patient owner login behind the readiness gate (the P-17
    boot-window observation: log the attempt count, never patch
    around auth)."""
    for attempt in range(1, 31):
        resp = login(client)
        if resp.status_code == 200:
            log(f"owner login succeeded on attempt {attempt}")
            token = data_of(resp)["access_token"]
            return {"Authorization": f"Bearer {token}"}
        time.sleep(1.0)
    raise RuntimeError("owner login never succeeded")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="f01-smoke-"))
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
        log("== Expansion Feature 1 smoke: Identity & Device Security ==")
        check("server ready", ready)

        # The fresh database was auto-migrated through F01.
        con = sqlite3.connect(db_path)
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        con.close()
        check("migration head is F01", head == "85b7a9805207", f"({head})")
        check("226 physical tables", tables == 226, f"({tables})")

        headers = owner_login(client)

        # --- enrolment: untrusted, secret shown exactly once here
        resp = client.post("/security/devices", headers=headers, json={
            "label": "Smoke laptop (fixture)", "platform": "windows"})
        device = data_of(resp) or {}
        secret = device.get("device_secret", "")
        check("enrol returns 201", resp.status_code == 201)
        check("new device is untrusted", device.get("trust_status") == "untrusted")
        check("device secret shown at enrolment", len(secret) >= 32)
        device_id = device.get("id")

        listed = data_of(client.get("/security/devices", headers=headers)) or []
        check("device list shows the device",
              any(d["id"] == device_id for d in listed))
        check("list never leaks secret or hash",
              all("device_secret" not in d and "secret_hash" not in d
                  for d in listed))

        # --- refusal paths at login
        resp = login(client, device_id=device_id, device_secret=secret)
        check("login refused while device untrusted",
              resp.status_code == 401)

        resp = client.post(f"/security/devices/{device_id}/trust",
                           headers=headers)
        check("owner trusts the device",
              resp.status_code == 200
              and data_of(resp)["trust_status"] == "trusted")

        resp = login(client, device_id=device_id, device_secret="wrong")
        check("login refused with a bad device secret",
              resp.status_code == 401)

        # --- device-bound login + session visibility
        resp = login(client, device_id=device_id, device_secret=secret)
        check("device-bound login succeeds", resp.status_code == 200)
        bound_token = data_of(resp)["access_token"]
        bound_auth = {"Authorization": f"Bearer {bound_token}"}
        me = client.get("/auth/me", headers=bound_auth)
        check("bound token resolves", me.status_code == 200)
        sessions = data_of(client.get("/security/auth/sessions",
                                      headers=headers)) or []
        check("session list shows the device binding",
              any(s.get("device_id") == device_id for s in sessions))

        # --- recovery codes: generate once, verify, single-use
        resp = client.post("/security/auth/recovery-codes/generate",
                           headers=headers, json={"count": 5})
        batch = data_of(resp) or {}
        codes = batch.get("codes") or []
        check("recovery batch generated", resp.status_code == 201
              and len(codes) == 5)
        status = data_of(client.get("/security/auth/recovery-codes",
                                    headers=headers)) or {}
        check("recovery status counts only (no codes)",
              status.get("unused") == 5 and "codes" not in status)
        resp = client.post("/security/auth/recovery-codes/verify",
                           headers=headers, json={"code": codes[0]})
        check("first use of a code verifies",
              data_of(resp) == {"verified": True})
        resp = client.post("/security/auth/recovery-codes/verify",
                           headers=headers, json={"code": codes[0]})
        check("the same code never verifies twice",
              data_of(resp) == {"verified": False})

        # --- rotation: old secret + bound sessions die
        resp = client.post(f"/security/devices/{device_id}/rotate-secret",
                           headers=headers)
        rotated = data_of(resp) or {}
        new_secret = rotated.get("device_secret", "")
        check("rotation returns a fresh secret once",
              resp.status_code == 200 and new_secret
              and new_secret != secret)
        me = client.get("/auth/me", headers=bound_auth)
        check("rotation killed the previously bound session",
              me.status_code == 401)
        resp = login(client, device_id=device_id, device_secret=secret)
        check("old secret refused after rotation", resp.status_code == 401)
        resp = login(client, device_id=device_id, device_secret=new_secret)
        check("new secret binds a session", resp.status_code == 200)
        second_token = data_of(resp)["access_token"]
        second_auth = {"Authorization": f"Bearer {second_token}"}

        # --- revocation: terminal, sessions die
        resp = client.post(f"/security/devices/{device_id}/revoke",
                           headers=headers)
        check("owner revokes the device",
              resp.status_code == 200
              and data_of(resp)["trust_status"] == "revoked")
        me = client.get("/auth/me", headers=second_auth)
        check("revocation killed the bound session", me.status_code == 401)
        resp = login(client, device_id=device_id, device_secret=new_secret)
        check("login refused for a revoked device", resp.status_code == 401)
        resp = client.post(f"/security/devices/{device_id}/trust",
                           headers=headers)
        check("a revoked device cannot be trusted again",
              resp.status_code == 409)

        # --- audit trail carries the whole story (existing machinery)
        audit = client.get("/security/audit", headers=headers,
                           params={"action_prefix": "security.device",
                                   "limit": 100})
        actions = {row["action"] for row in (data_of(audit) or [])}
        expected = {"security.device_enrolled", "security.device_trusted",
                    "security.device_login",
                    "security.device_credential_refused",
                    "security.device_secret_rotated",
                    "security.device_revoked"}
        check("audit trail records the device lifecycle",
              expected <= actions, f"({sorted(expected - actions)} missing)")
        audit = client.get("/security/audit", headers=headers,
                           params={"action_prefix": "security.recovery",
                                   "limit": 100})
        actions = {row["action"] for row in (data_of(audit) or [])}
        check("audit trail records recovery-code events",
              {"security.recovery_codes_generated",
               "security.recovery_code_used",
               "security.recovery_code_refused"} <= actions)

        # --- the built Command Center is served
        spa = root_client.get("/app/")
        check("Command Center served at /app", spa.status_code == 200)

        log(f"\n== F01 SMOKE: {PASS} passed, {FAIL} failed ==")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = REPO / "docs" / "reports" / "F01_SMOKE_EVIDENCE.txt"
    out.write_text("\n".join(LINES) + "\n")
    print(f"transcript written to {out}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
