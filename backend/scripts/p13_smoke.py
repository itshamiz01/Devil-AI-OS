"""P-13 live smoke: seeds two businesses through the governed
P-06/P-07 paths in-process, then boots the real application under
uvicorn (which also serves the built Command Center frontend at
/app, now including the Business Portfolio section) and drives the
P-13 surface over HTTP. Run:

    .venv/bin/python scripts/p13_smoke.py

Writes a transcript to docs/reports/P13_SMOKE_EVIDENCE.txt (relative
to the repository root). Uses a throwaway data directory.

Order matters (staging honesty): FIRST the zero state and the
authentication boundary; then the seeded portfolio's overview and
finance — checked byte-for-byte against the P-07 figures the seed
created; concentration detection; evidence-gated analysis; an
internal allocation that provably moves no P-07 money; the
credentials grant refusal; and finally the built frontend itself,
served by this same process.
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
    """Seed through governed paths: P-06 fixture businesses, P-07
    profiles + verified revenue, a P-13 portfolio, one shared
    service used by one business, one registered agent."""
    from app.core.application import Application
    from app.core.config import Settings
    from app.permissions.models import Principal, PrincipalType
    from tests.p07_support import business_with_profile, verified_revenue
    from tests.p09_support import register_agent

    owner = Principal(PrincipalType.OWNER, "owner")
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
        big, _p = await business_with_profile(app, name="Smoke Alpha")
        await verified_revenue(app, big, "9000")
        small, _p = await business_with_profile(app, name="Smoke Beta")
        await verified_revenue(app, small, "1000")
        svc = app.portfolio
        portfolio = svc.create_portfolio(owner, {"name": "Smoke Portfolio"})
        svc.register_business(owner, portfolio["id"], {"business_id": big})
        svc.register_business(owner, portfolio["id"], {"business_id": small})
        service = svc.create_service(owner, {
            "name": "Smoke Analytics", "kind": "analytics"})
        access = svc.request_access(owner, service["id"],
                                    {"business_id": big})
        svc.decide_access(owner, access["id"], True)
        svc.activate_access(owner, access["id"])
        svc.record_usage(owner, service["id"],
                         {"business_id": big, "units": 12})
        register_agent(app, "smoke-agent", business_ref=big)
        return {"portfolio_id": portfolio["id"], "big": big,
                "small": small, "service_id": service["id"]}
    finally:
        await app.shutdown()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p13-smoke-"))
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
        log("=== AUTONOMUS P-13 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")

        # ---- 1. Honesty check: auth boundary + schema + zero state
        log("--- 1. Honesty check: auth boundary, schema, engine status")
        unauth = client.get("/portfolio/portfolios")
        check("portfolio list requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 172 tables (171 + alembic_version)",
              tables == 172, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        status = show("portfolio engine status", client.get(
            "/portfolio/status", headers=auth), ("engine",))
        check("P-13 engine is live", str(status.get("engine", ""))
              .startswith("P-13"))

        # ---- 2. Seeded portfolio: overview + finance == P-07 figures
        log("--- 2. Seeded portfolio overview and finance (P-07 truth)")
        pid = seeded["portfolio_id"]
        overview = show("overview", client.get(
            f"/portfolio/portfolios/{pid}/overview", headers=auth),
            ("total_businesses", "active_businesses", "stage_counts"))
        check("overview counts both seeded businesses",
              overview["total_businesses"] == 2)
        finance = show("finance", client.get(
            f"/portfolio/portfolios/{pid}/finance", headers=auth),
            ("totals", "combined_available_cash"))
        check("collected total equals the seeded P-07 revenue "
              "(9000 + 1000 = ₹10,000)",
              finance["totals"]["net_collected_minor"] == 10000_00,
              f"(got {finance['totals']['net_collected_minor']})")
        check("cash is never combined (combined_available_cash is null)",
              finance["combined_available_cash"] is None)

        # ---- 3. Concentration + analysis + risk
        log("--- 3. Concentration detection and evidence-gated analysis")
        conc = show("concentration", client.get(
            f"/portfolio/portfolios/{pid}/concentration", headers=auth),
            ("total_collected_minor", "threshold_bps"))
        shares = {r["business_id"]: r["share_bps"]
                  for r in conc["businesses"]}
        check("big business holds 90% of verified collected revenue",
              shares.get(seeded["big"]) == 9000)
        analysis = show("analyze", client.post(
            f"/portfolio/portfolios/{pid}/analyze", headers=auth),
            ("opportunities_created", "recommendations_created"))
        check("analysis created evidence-based findings",
              analysis["opportunities_created"] >= 1
              and analysis["recommendations_created"] >= 1)
        opps = client.get(f"/portfolio/portfolios/{pid}/opportunities",
                          headers=auth).json()["data"]["items"]
        check("shared-service opportunity detected for the unsubscribed "
              "business", any(o["category"] == "SHARED_SERVICE"
                              and o["evidence_status"] == "VERIFIED"
                              for o in opps))
        risk = show("risk assess", client.post(
            f"/portfolio/portfolios/{pid}/risk/assess", headers=auth),
            ("risk_level",))
        check("risk assessment flags the concentration",
              any(f.get("kind") == "concentration"
                  for f in risk.get("findings", [])))

        # ---- 4. Internal allocation moves no P-07 money
        log("--- 4. Internal allocation: labelled, and P-07 untouched")
        before = client.get(f"/portfolio/portfolios/{pid}/finance",
                            headers=auth).json()["data"]["totals"]
        alloc_resp = client.post("/portfolio/allocations", headers=auth,
                                 json={
                                     "service_id": seeded["service_id"],
                                     "portfolio_id": pid,
                                     "method": "equal",
                                     "total_cost_minor": 2000,
                                     "business_ids": [seeded["big"],
                                                      seeded["small"]]})
        alloc = show("create allocation", alloc_resp,
                     ("kind", "is_external_payment", "total_cost_minor"))
        check("allocation is labelled INTERNAL_ALLOCATION, not a payment",
              alloc.get("kind") == "INTERNAL_ALLOCATION"
              and alloc.get("is_external_payment") is False)
        client.post(f"/portfolio/allocations/{alloc['id']}/decision",
                    headers=auth, json={"approve": True})
        after = client.get(f"/portfolio/portfolios/{pid}/finance",
                           headers=auth).json()["data"]
        check("P-07 totals identical after the allocation",
              after["totals"] == before)
        check("allocation listed in finance as internal accounting",
              len(after["internal_allocations"]) == 2 and all(
                  a["kind"] == "INTERNAL_ALLOCATION"
                  for a in after["internal_allocations"]))

        # ---- 5. Grant governance: credentials refused, scoped grant ok
        log("--- 5. Cross-business grant governance (§20)")
        refused = client.post("/portfolio/access/grants", headers=auth,
                              json={
                                  "portfolio_id": pid,
                                  "grantee_agent_id": "smoke-agent",
                                  "business_id": seeded["small"],
                                  "categories": ["credentials"],
                                  "rationale": "smoke refusal check",
                                  "expires_at": "2999-01-01T00:00:00+00:00"})
        check("credentials grant refused (422 validation, house "
              "convention)", refused.status_code == 422
              and "never be granted" in refused.text,
              f"(got {refused.status_code})")
        granted = client.post("/portfolio/access/grants", headers=auth,
                              json={
                                  "portfolio_id": pid,
                                  "grantee_agent_id": "smoke-agent",
                                  "business_id": seeded["small"],
                                  "categories": ["aggregate_metrics"],
                                  "rationale": "smoke scoped grant",
                                  "expires_at": "2999-01-01T00:00:00+00:00"})
        grant = show("scoped grant", granted, ("status", "categories"))
        check("scoped aggregate grant created ACTIVE",
              granted.status_code == 201 and grant["status"] == "ACTIVE")
        grant_id = granted.json()["data"]["id"]
        revoked = client.post(
            f"/portfolio/access/grants/{grant_id}/revoke", headers=auth)
        check("grant revocation succeeds", revoked.status_code == 200)

        # ---- 6. Report reflects actual state
        log("--- 6. Portfolio report reflects the live state")
        report = show("generate FINANCIAL report", client.post(
            f"/portfolio/portfolios/{pid}/reports", headers=auth,
            json={"report_type": "FINANCIAL"}), ("report_type", "sources"))
        check("report totals equal the live finance totals",
              report["content"]["finance"]["totals"]
              == after["totals"])
        check("report names its sources",
              "p07.financial_service" in report.get("sources", []))

        # ---- 7. The built frontend, served by this process
        log("--- 7. Built Command Center served at /app")
        page = root_client.get("/app/", follow_redirects=True)
        check("GET /app returns the built frontend",
              page.status_code == 200 and "<div id=\"root\">" in page.text)
        import re as _re
        match = _re.search(r"assets/[^\"']+\.js", page.text)
        bundle = root_client.get(f"/app/{match.group(0)}") if match else None
        check("served bundle contains the Business Portfolio section",
              bundle is not None and bundle.status_code == 200
              and "Business Portfolio" in bundle.text)

        log(f"=== SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 1 if FAIL else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        evidence = REPO / "docs" / "reports" / "P13_SMOKE_EVIDENCE.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        log(f"evidence written to {evidence}")


if __name__ == "__main__":
    raise SystemExit(main())
