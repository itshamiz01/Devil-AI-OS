"""P-12 live smoke: boots the real application under uvicorn (which
also serves the built Command Center frontend at /app, now including
the Autonomous Operations section) and drives the P-12 surface over
HTTP. Run:

    .venv/bin/python scripts/p12_smoke.py

Writes a transcript to docs/reports/P12_SMOKE_EVIDENCE.txt (relative
to the repository root). Uses a throwaway data directory.

Order matters (staging honesty): FIRST the zero state of a fresh
install and the authentication boundary; then a template workflow
run end-to-end (verified completion + a P-09 learning record); a
restricted step parking at a REAL P-01 approval and completing only
after the owner's decision; a due trigger fired by a tick without
duplication; the global emergency stop composing P-10 (and the
owner-only resume); and finally the built frontend itself, served
by this same process.
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
    tmp = Path(tempfile.mkdtemp(prefix="p12-smoke-"))
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
        log("=== AUTONOMUS P-12 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")

        # ---- 1. Honesty check: fresh install zero state
        log("--- 1. Honesty check: fresh-install zero state + auth boundary")
        unauth = client.get("/operations/overview")
        check("operations overview requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 153 tables (152 + alembic_version)",
              tables == 153, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        overview = show("overview (zero state)", client.get(
            "/operations/overview", headers=auth),
            ("workflows", "pending_approvals", "open_dead_letters", "engine"))
        check("zero workflows on a fresh install",
              sum(overview["workflows"].values()) == 0)
        check("zero pending approvals", overview["pending_approvals"] == 0)
        check("zero dead letters", overview["open_dead_letters"] == 0)
        check("scheduler engine running (background loop, non-test env)",
              overview["engine"]["running"] is True)
        safety = show("safety (zero state)", client.get(
            "/operations/safety", headers=auth),
            ("security_mode", "constitution_mode", "financial_suspended"))
        check("security mode normal", safety["security_mode"] == "normal")

        # ---- 2. Template workflow end-to-end
        log("--- 2. Template workflow: create -> validate -> start -> verified")
        created = show("create workflow", client.post(
            "/operations/workflows", headers=auth, json={
                "name": "Smoke monitoring", "template": "monitoring_report",
                "autonomy_level": 2}), ("id", "status"))
        workflow_id = created["id"]
        validated = show("validate", client.post(
            f"/operations/workflows/{workflow_id}/validate", headers=auth),
            ("status",))
        check("workflow READY after validation",
              validated["status"] == "READY")
        started = show("start", client.post(
            f"/operations/workflows/{workflow_id}/start", headers=auth),
            ("status", "verified_outcome", "learning_record_id"))
        check("workflow COMPLETED", started["status"] == "COMPLETED")
        check("outcome independently VERIFIED",
              started["verified_outcome"] == "verified")
        check("learning recorded from the verified outcome only",
              bool(started["learning_record_id"]))
        detail = show("workflow detail", client.get(
            f"/operations/workflows/{workflow_id}", headers=auth),
            ("status",))
        check("every step verified",
              all(t["verification_status"] == "verified"
                  for t in detail["tasks"]))
        check("checkpoint records the completed steps",
              len(detail["checkpoints"]) >= 1
              and len(detail["checkpoints"][0]["completed_steps"]) == 3)

        # ---- 3. Restricted step: real P-01 approval gate
        log("--- 3. Restricted step parks at a P-01 approval; owner decides")
        created2 = show("create publish workflow", client.post(
            "/operations/workflows", headers=auth, json={
                "name": "Smoke publish", "autonomy_level": 2,
                "definition": {"steps": [{
                    "step_key": "publish", "name": "Publish",
                    "kind": "task_handler", "action_class": "content.publish",
                    "substrate": {"handler": "core.echo_check",
                                  "payload": {"message": "smoke publish"}},
                    "acceptance_criteria": {"task_status": "completed"}}]}}),
            ("id", "status"))
        wf2 = created2["id"]
        client.post(f"/operations/workflows/{wf2}/validate", headers=auth)
        parked = show("start publish workflow", client.post(
            f"/operations/workflows/{wf2}/start", headers=auth), ("status",))
        check("restricted workflow WAITING_FOR_APPROVAL",
              parked["status"] == "WAITING_FOR_APPROVAL")
        links = show("operations approvals", client.get(
            "/operations/approvals", headers=auth), ("note",))
        link_count = len(client.get(
            "/operations/approvals", headers=auth).json()["data"]["items"])
        check("an approval link references the P-01 store",
              link_count >= 1, f"(got {link_count})")
        link_items = client.get("/operations/approvals",
                                headers=auth).json()["data"]["items"]
        approval_id = next(
            item["approval_id"] for item in link_items
            if item["workflow_id"] == wf2 and item["status"] == "pending")
        decision = client.post(f"/approvals/{approval_id}/decision",
                               headers=auth, json={"approve": True})
        check("owner decision recorded in P-01", decision.status_code == 200)
        processed = show("process approvals", client.post(
            "/operations/approvals/check", headers=auth), ("driven",))
        check("check pass drove the approved workflow",
              wf2 in processed["driven"])
        after = show("publish workflow after approval", client.get(
            f"/operations/workflows/{wf2}", headers=auth),
            ("status", "verified_outcome"))
        check("publish workflow COMPLETED after approval",
              after["status"] == "COMPLETED")

        # ---- 4. Trigger + tick (no duplicate fire)
        log("--- 4. Due trigger fires once through the tick")
        trigger = show("create trigger", client.post(
            "/operations/triggers", headers=auth, json={
                "name": "smoke once", "trigger_type": "time",
                "schedule": {"kind": "once", "at": "2020-01-01T00:00:00Z"},
                "workflow_template": {
                    "name": "Triggered monitoring",
                    "template": "monitoring_report",
                    "autonomy_level": 2}}), ("id", "status"))
        tick = show("tick", client.post("/operations/scheduler/tick", headers=auth),
                    ("fired",))
        fired = [f for f in tick["fired"]
                 if f.get("trigger_id") == trigger["id"]]
        check("due trigger fired exactly once", len(fired) == 1)
        tick2 = show("second tick", client.post(
            "/operations/scheduler/tick", headers=auth), ("fired",))
        fired2 = [f for f in tick2["fired"]
                  if f.get("trigger_id") == trigger["id"]]
        check("second tick does not re-fire (fire-key dedupe)",
              len(fired2) == 0)

        # ---- 5. Emergency stop composes P-10; owner-only resume
        log("--- 5. Global emergency stop and owner resume")
        stopped = show("emergency stop (global)", client.post(
            "/operations/emergency/stop", headers=auth,
            json={"scope": "global", "scope_ref": None}), ("scope",))
        safety2 = show("safety during stop", client.get(
            "/operations/safety", headers=auth), ("security_mode",))
        check("P-10 security mode is emergency_stop",
              safety2["security_mode"] == "emergency_stop")
        resumed = show("emergency resume (owner)", client.post(
            "/operations/emergency/resume", headers=auth,
            json={"scope": "global", "scope_ref": None}), ("scope",))
        safety3 = show("safety after resume", client.get(
            "/operations/safety", headers=auth), ("security_mode",))
        check("security mode back to normal after owner resume",
              safety3["security_mode"] == "normal")

        # ---- 6. Recovery + reports surfaces
        log("--- 6. Recovery center and operational reports")
        recovery = show("recovery", client.get(
            "/operations/recovery", headers=auth),
            ("dead_letter_total", "checkpoints"))
        check("recovery center responds with real counters",
              recovery["checkpoints"] >= 1)
        report = show("generate report", client.post(
            "/operations/reports", headers=auth, json={
                "kind": "daily"}), ("id", "kind"))
        check("report generated from live data", bool(report["id"]))
        overview2 = show("overview (final)", client.get(
            "/operations/overview", headers=auth), ("workflows",))
        check("overview counts match reality (3 completed workflows)",
              overview2["workflows"].get("COMPLETED") == 3,
              f"(got {overview2['workflows']})")

        # ---- 7. The built frontend, served by this process
        log("--- 7. Built Command Center (with Autonomous Operations) at /app")
        app_page = root_client.get("/app/")
        check("GET /app/ serves the SPA", app_page.status_code == 200)
        asset = re_search_asset(app_page.text)
        if asset:
            js = root_client.get(asset)
            check("bundle contains the Autonomous Operations section",
                  "Autonomous Operations" in js.text)
        else:
            check("bundle asset discoverable from index", False)

        log(f"=== SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 0 if FAIL == 0 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        out = REPO / "docs" / "reports" / "P12_SMOKE_EVIDENCE.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"transcript: {out}")


def re_search_asset(html: str) -> str | None:
    import re
    match = re.search(r'src="(/app/assets/[^"]+\.js)"', html)
    if match:
        return match.group(1)
    match = re.search(r'src="(?:\./)?(assets/[^"]+\.js)"', html)
    return f"/app/{match.group(1)}" if match else None


if __name__ == "__main__":
    raise SystemExit(main())
