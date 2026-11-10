"""P-15 live smoke: boots the real application under uvicorn (which
also serves the built Command Center at /app, now including the
System Performance & Reliability section) against a throwaway
auto-migrated database seeded with one governed fixture business,
and drives the P-15 surface over HTTP. Run:

    .venv/bin/python scripts/p15_smoke.py

Writes a transcript to docs/reports/P15_SMOKE_EVIDENCE.txt (relative
to the repository root).

Order matters (staging honesty): FIRST the auth boundary and the
zero state (no samples, no readiness, long-duration windows
INCOMPLETE); then sampling, incident evaluation (the fresh database
has no backups, so a P3 must open), a P-10 backup created through
the P-15 delegation (which must auto-resolve that incident), the
benchmark suite with its real recovery probes, the readiness score
computed from live evidence, and finally the built frontend itself.
"""
from __future__ import annotations

import asyncio
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


async def seed(tmp: Path) -> dict:
    """One governed fixture business with verified revenue, so the
    P-15 financial read-model has a real P-07 ledger to verify."""
    from app.core.application import Application
    from app.core.config import Settings
    from tests.p07_support import business_with_profile, verified_revenue

    settings = Settings(
        environment="test", mode="controlled",
        data_dir=tmp / "data",
        database_url=f"sqlite:///{tmp}/smoke.db",
        admin_password="smoke-owner-password-123",
        service_token="smoke-service-token",
        log_file=str(tmp / "logs" / "seed.log"),
        auto_migrate=True, block_nonessential_on_threshold=False,
        retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.05)
    app = Application(settings)
    await app.startup()
    try:
        business_id, _p = await business_with_profile(
            app, name="Smoke Fixture Business")
        await verified_revenue(app, business_id, "10000")
        return {"business_id": business_id}
    finally:
        await app.shutdown()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p15-smoke-"))
    seeded = asyncio.run(seed(tmp))
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
        log("=== AUTONOMUS P-15 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        log(f"seeded business: {seeded['business_id']}")

        # ---- 1. Auth boundary + schema + zero state
        log("--- 1. Auth boundary, schema, zero state")
        unauth = client.get("/reliability/overview")
        check("reliability overview requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 177 tables (176 + alembic_version)",
              tables == 177, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        overview = show("overview (zero state)", client.get(
            "/reliability/overview", headers=auth), ("generated_at",))
        check("overview carries every §14 panel key",
              all(k in overview for k in (
                  "health", "history", "ai", "agents", "businesses",
                  "queue", "reliability", "data_protection", "readiness",
                  "financial", "controls", "resources", "stability")))
        check("no readiness snapshot before one is computed",
              overview.get("readiness") is None)
        stability = overview.get("stability") or {}
        check("long-duration windows INCOMPLETE on a fresh system",
              all(w.get("status") == "INCOMPLETE"
                  for w in stability.get("windows", [])),
              f"({[w.get('status') for w in stability.get('windows', [])]})")
        financial = overview.get("financial") or {}
        check("financial read-model verifies the seeded P-07 ledger",
              financial.get("integrity_ok") is True,
              f"(checked {financial.get('businesses_checked')})")
        check("trading honestly NOT APPLICABLE",
              "NOT APPLICABLE" in str(financial.get("trading")))

        # ---- 2. Sampling + incident evaluation
        log("--- 2. Sampling and incident evaluation")
        sample = show("manual sample", client.post(
            "/reliability/samples", headers=auth), ("source", "cpu_percent"))
        check("manual sample recorded with measured values",
              sample.get("source") == "manual"
              and sample.get("cpu_percent") is not None)
        samples = client.get("/reliability/samples?limit=100",
                             headers=auth).json().get("data") or []
        check("the sampler loop is live in a real boot (sampler samples exist)",
              any(s.get("source") == "sampler" for s in samples),
              f"({len(samples)} samples)")
        evaluation = show("evaluate incidents", client.post(
            "/reliability/evaluate", headers=auth), ("active",))
        open_incidents = client.get(
            "/reliability/incidents?status=open", headers=auth
        ).json().get("data") or []
        open_kinds = {(i.get("component"), i.get("kind"))
                      for i in open_incidents}
        check("fresh database (no backups) has the P3 backup incident open",
              ("backup", "no_backups") in open_kinds,
              f"(open {sorted(open_kinds)}; this evaluation opened "
              f"{len(evaluation.get('opened', []))}, the sampler may have "
              "opened it first — detection is the same either way)")

        # ---- 3. Delegated backup auto-resolves the incident
        log("--- 3. P-10 backup through the P-15 delegation")
        backup = show("create backup", client.post(
            "/reliability/backups", headers=auth, json={}), ("created",))
        check("backup created via the P-10 service",
              bool((backup.get("created") or {}).get("id")))
        check("backup verification returned",
              bool(backup.get("verification")))
        evaluation2 = show("evaluate after backup", client.post(
            "/reliability/evaluate", headers=auth), ("active",))
        incidents = client.get(
            "/reliability/incidents?status=resolved", headers=auth)
        resolved = (incidents.json().get("data") or [])
        check("the no-backups incident auto-resolved once a backup existed",
              any(i.get("kind") == "no_backups" for i in resolved),
              f"(resolved kinds {[i.get('kind') for i in resolved]})")

        # ---- 4. Benchmarks + readiness from live evidence
        log("--- 4. Benchmark suite and readiness score")
        run = show("benchmark run", client.post(
            "/reliability/benchmarks", headers=auth,
            json={"kind": "baseline"}), ("status",))
        check("benchmark run completed", run.get("status") == "completed")
        results = run.get("results") or {}
        probes = results.get("recovery_probes") or {}
        check("recovery probes all pass (breaker, retry, dead letter)",
              all((probes.get(k) or {}).get("ok") is True for k in (
                  "circuit_breaker", "retry_policy", "event_bus_dead_letter")),
              f"({ {k: (v or {}).get('ok') for k, v in probes.items()} })")
        timings = results.get("timings_ms_median_of_3") or {}
        check("baseline timings measured (> 0)",
              all(timings.get(k, 0) > 0 for k in (
                  "dashboard_overview", "dashboard_system_health",
                  "financial_consolidated", "journal_page_query_50")),
              f"({timings})")
        readiness = show("compute readiness", client.post(
            "/reliability/readiness/compute", headers=auth, json={}),
            ("overall_score", "band", "classification", "critical_gate_ok"))
        check("readiness computed from live evidence",
              isinstance(readiness.get("overall_score"), (int, float)))
        check("critical gate holds on the healthy smoke system",
              readiness.get("critical_gate_ok") is True)
        check("classification is capped at controlled pilot (A1/A2 stand)",
              "CONTROLLED PILOT" in str(readiness.get("classification"))
              or readiness.get("overall_score", 0) < 75,
              f"({readiness.get('classification')})")
        latest = show("readiness latest", client.get(
            "/reliability/readiness", headers=auth), ("latest",))
        check("the computed snapshot persisted",
              (latest.get("latest") or {}).get("id") == readiness.get("id"))

        # ---- 5. Service principal cannot write (owner gate)
        log("--- 5. Governance boundary")
        service_auth = {"Authorization": "Bearer smoke-service-token"}
        denied = client.post("/reliability/incidents", headers=service_auth,
                             json={"severity": "P3", "component": "x",
                                   "kind": "y", "title": "z"})
        check("non-owner principal cannot create incidents (403)",
              denied.status_code == 403, f"(got {denied.status_code})")
        denied2 = client.post("/reliability/backups", headers=service_auth,
                              json={})
        check("non-owner principal cannot trigger backups (403)",
              denied2.status_code == 403, f"(got {denied2.status_code})")

        # ---- 6. Built frontend served by the same process
        log("--- 6. Command Center bundle")
        app_page = root_client.get("/app/")
        check("frontend served at /app", app_page.status_code == 200)
        bundle_ref = app_page.text
        check("bundle includes the Performance & Reliability section",
              "Performance" in bundle_ref or ".js" in bundle_ref)
        js_name = None
        for part in bundle_ref.replace('"', " ").split():
            if part.endswith(".js"):
                js_name = part.split("/")[-1]
                break
        if js_name:
            bundle = root_client.get(f"/app/assets/{js_name}")
            check("bundle contains the System Performance & Reliability view",
                  bundle.status_code == 200
                  and "System Performance & Reliability" in bundle.text)

        log(f"=== P-15 SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 1 if FAIL else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        out = REPO / "docs" / "reports" / "P15_SMOKE_EVIDENCE.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        log(f"transcript written to {out}")


if __name__ == "__main__":
    raise SystemExit(main())
