"""P-11 live smoke: boots the real application under uvicorn (which
serves the BUILT Command Center frontend at /app) and drives the
Premium Command Center surface over HTTP. Run:

    .venv/bin/python scripts/p11_smoke.py

Writes a transcript to docs/reports/P11_SMOKE_EVIDENCE.txt (relative
to the repository root). Uses a throwaway data directory.

Order matters (staging honesty): FIRST the zero state of a fresh
install (Scenario 12) and the authentication boundary; then the
dashboard's figures cross-checked against the owning engines'
endpoints (§28.2); a real pending approval flowing through the
unified inbox, attention queue and notifications (Scenario 5);
preferences round-trip; the emergency mode shown only after backend
confirmation (Scenario 10); and finally the built frontend itself,
served by this same process.
"""
from __future__ import annotations

import json
import os
import random
import re
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


def show(title: str, response: httpx.Response,
         keys: tuple[str, ...] = ()) -> dict:
    try:
        data = response.json().get("data") or {}
    except Exception:
        data = {}
    picked = {k: data.get(k) for k in keys} if keys else data
    log(f"[{title}] HTTP {response.status_code} -> "
        f"{json.dumps(picked, default=str)[:400]}")
    return data


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p11-smoke-"))
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(tmp / "data"),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{tmp}/smoke.db",
        "AUTONOMUS_ADMIN_PASSWORD": "smoke-owner-password-123",
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
    client = httpx.Client(base_url=BASE, timeout=60, trust_env=False)
    root_client = httpx.Client(base_url=ROOT, timeout=60, trust_env=False)
    try:
        for _ in range(60):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("=== AUTONOMUS P-11 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")

        # ---- 1. Authentication boundary + migration state
        log("--- 1. Auth boundary and migrated schema")
        unauth = client.get("/dashboard/overview")
        check("dashboard overview requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 139 tables (137 + 2 dashboard)",
              tables == 139, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        service = {"Authorization": "Bearer smoke-service-token"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        # ---- 2. Zero state honesty (Scenario 12)
        log("--- 2. Fresh-install zero state (Scenario 12)")
        overview = show("overview", client.get(
            "/dashboard/overview", headers=auth), ("operating_state", "counts"))
        check("zero businesses", overview["counts"]["businesses_total"] == 0)
        check("zero pending approvals",
              overview["counts"]["pending_approvals"] == 0)
        kpis = {k["key"]: k for k in overview["kpis"]}
        check("collected revenue is a true zero",
              kpis["collected_revenue"]["value"] == 0)
        check("available cash honestly unavailable (not invented)",
              kpis["available_cash"]["state"] == "unavailable"
              and kpis["available_cash"]["value"] is None)
        health = show("system health", client.get(
            "/dashboard/system-health", headers=auth), ("overall",))
        checks = {c["key"]: c for c in health["checks"]}
        check("database check ok", checks["database"]["state"] == "ok")
        check("GPU honestly unavailable (no fabricated telemetry)",
              checks["gpu"]["state"] == "unavailable")

        # ---- 3. Dashboard figures equal the owning engines (§28.2)
        log("--- 3. Cross-checks against source endpoints")
        fin = client.get("/financial/overview", headers=auth,
                         params={"currency": "INR"}).json()["data"]
        check("overview finance totals == P-07 /financial/overview totals",
              overview["finance"]["totals"] == fin["totals"])
        summary = client.get("/dashboard/finance/summary", headers=auth,
                             params={"currency": "INR"}).json()["data"]
        check("finance summary totals == P-07 totals",
              summary["totals"] == fin["totals"])

        # ---- 4. Preferences round-trip
        log("--- 4. Dashboard preferences (flat typed body, per-principal)")
        put = client.put("/dashboard/preferences", headers=auth,
                         json={"sidebar_collapsed": True, "currency": "USD"})
        check("preference update accepted", put.status_code == 200)
        got = client.get("/dashboard/preferences",
                         headers=auth).json()["data"]["preferences"]
        check("preferences persisted",
              got["sidebar_collapsed"] is True and got["currency"] == "USD")
        bad = client.put("/dashboard/preferences", headers=auth,
                         json={"theme": "pink"})
        check("unknown preference key rejected (422)",
              bad.status_code == 422)
        other = client.get("/dashboard/preferences",
                           headers=service).json()["data"]["preferences"]
        check("service principal has its own (default) preferences",
              other["sidebar_collapsed"] is False)

        # ---- 5. A real pending approval in the unified inbox (Scen. 5)
        log("--- 5. Pending approval surfaces (Scenario 5)")
        created = client.post("/approvals", headers=service, json={
            "action": "config.change", "resource": "system:settings",
            "risk_classification": "high", "reason": "p11 smoke",
            "requested_permissions": ["modify_system_config"],
            "parameters": {"setting": "alert_threshold", "value": 3}})
        check("approval created by service principal (201)",
              created.status_code == 201)
        approval = created.json()["data"]
        inbox = client.get("/approvals", headers=auth,
                           params={"status": "pending"}).json()["data"]
        mine = [a for a in inbox if a["id"] == approval["id"]]
        check("approval present in unified inbox with exact parameters",
              len(mine) == 1
              and mine[0]["parameters"] == {"setting": "alert_threshold",
                                            "value": 3}
              and mine[0]["parameters_hash"] == approval["parameters_hash"])
        appr_summary = client.get("/dashboard/approvals/summary",
                                  headers=auth).json()["data"]
        check("approvals summary counts it",
              appr_summary["core_pending"] >= 1)
        attention = client.get("/dashboard/attention",
                               headers=auth).json()["data"]
        check("attention queue contains it",
              any(i["kind"] == "approval" and i["ref_id"] == approval["id"]
                  for i in attention["items"]))
        notes = client.get("/dashboard/notifications",
                           headers=auth).json()["data"]
        nid = f"approval:{approval['id']}"
        check("notification derived for it (unread)",
              any(n["id"] == nid and n["is_read"] is False
                  for n in notes["items"]))
        read = client.post(f"/dashboard/notifications/{nid}/read",
                           headers=auth)
        check("mark-read persists", read.status_code == 200)
        decided = client.post(f"/approvals/{approval['id']}/decision",
                              headers=auth,
                              json={"approve": True, "notes": "smoke ok"})
        check("owner decision confirmed by backend",
              decided.status_code == 200
              and decided.json()["data"]["status"] == "approved")
        notes2 = client.get("/dashboard/notifications",
                            headers=auth).json()["data"]
        check("decided approval leaves the notification list",
              all(n["id"] != nid for n in notes2["items"]))

        # ---- 6. Emergency state only after backend confirmation (Sc. 10)
        log("--- 6. Emergency mode round-trip (Scenario 10)")
        mode = client.post("/security/emergency/mode", headers=auth, json={
            "mode": "safe_mode", "reason": "p11 smoke verification"})
        check("P-10 confirms safe_mode",
              mode.status_code == 200
              and mode.json()["data"]["mode"] == "safe_mode")
        sec = client.get("/dashboard/security/summary",
                         headers=auth).json()["data"]
        check("dashboard security summary reads safe_mode from P-10",
              sec["mode"] == "safe_mode")
        overview2 = client.get("/dashboard/overview",
                               headers=auth).json()["data"]
        check("overview operating state reflects safe mode",
              overview2["security_mode"] == "safe_mode")
        back = client.post("/security/emergency/mode", headers=auth, json={
            "mode": "normal", "reason": "smoke complete"})
        check("returned to normal",
              back.json()["data"]["mode"] == "normal")

        # ---- 7. The built frontend, served by this process
        log("--- 7. Built Command Center served at /app")
        page = root_client.get("/app/")
        check("GET /app/ returns the built index (200)",
              page.status_code == 200 and 'id="root"' in page.text)
        asset = re.search(r'src="[^"]*?(/app/assets/[^"]+\.js)"', page.text)
        if asset is None:
            asset = re.search(r'src="(\./assets/[^"]+\.js)"', page.text)
        check("index references a JS bundle", asset is not None)
        if asset is not None:
            href = asset.group(1)
            url = href if href.startswith("/") else f"/app/{href[2:]}"
            bundle = root_client.get(url)
            check("JS bundle loads (200)", bundle.status_code == 200,
                  f"({len(bundle.content)} bytes)")
            check("bundle is the Command Center build",
                  "Command Center" in bundle.text)

        # ---- 8. Search validation
        log("--- 8. Unified search")
        short = client.get("/dashboard/search", headers=auth,
                           params={"q": "a"})
        check("one-character query rejected (422)",
              short.status_code == 422)
        none = client.get("/dashboard/search", headers=auth,
                          params={"q": "zzz-no-match"})
        check("no-match search returns an honest zero",
              none.status_code == 200
              and none.json()["data"]["total"] == 0)

        log(f"=== SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 0 if FAIL == 0 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        evidence = REPO / "docs" / "reports" / "P11_SMOKE_EVIDENCE.txt"
        evidence.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"evidence written to {evidence}")


if __name__ == "__main__":
    raise SystemExit(main())
