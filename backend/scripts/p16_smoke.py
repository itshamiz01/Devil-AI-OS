"""P-16 live smoke: boots the real application under uvicorn
(which also serves the built Command Center at /app, now including
the AI Economy & Expansion section) against a throwaway
auto-migrated database seeded with two governed fixture businesses
— one profitable, one loss-making, aggregate profit negative — and
drives the P-16 surface over HTTP. Run:

    .venv/bin/python scripts/p16_smoke.py

Writes a transcript to docs/reports/P16_SMOKE_EVIDENCE.txt
(relative to the repository root).

The story is the owner's priority, end to end: the profitability
gate is CLOSED on aggregate-negative fixtures, so a new-business
strategy cannot be approved, the growth allocation scenario is
refused, and a new-business opportunity cannot advance past
financial evaluation — while an improvement strategy approves, a
balanced allocation approves WITHOUT moving a single P-07 unit
(overview totals byte-equal across the decision), discovery finds
the loss-maker, risk computes with its ten SIMULATION scenarios,
and recommendations lead with fixing what exists.
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
    """Two governed fixture businesses in P-07: a modest winner and
    a bigger loser, so aggregate verified profit is negative and the
    owner's profitability gate starts CLOSED."""
    from app.core.application import Application
    from app.core.config import Settings
    from tests.p07_support import (
        business_with_profile, paid_expense, verified_revenue)
    from tests.p08_support import opening_balance

    settings = Settings(
        environment="test", mode="controlled",
        data_dir=tmp / "data",
        database_url=f"sqlite:///{tmp / 'smoke.db'}",
        admin_password="smoke-owner-password-123",
        service_token="smoke-service-token",
        log_file=str(tmp / "logs" / "seed.log"),
        auto_migrate=True, block_nonessential_on_threshold=False,
        retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.05)
    app = Application(settings)
    await app.startup()
    try:
        winner, _p = await business_with_profile(
            app, name="Smoke Winner (fixture)")
        opening_balance(app, winner, "1000.00")
        await verified_revenue(app, winner, "5000.00")
        await paid_expense(app, winner, "3000.00")
        loser, _p2 = await business_with_profile(
            app, name="Smoke Loser (fixture)")
        await verified_revenue(app, loser, "2000.00")
        await paid_expense(app, loser, "8000.00")
        return {"winner": winner, "loser": loser}
    finally:
        await app.shutdown()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p16-smoke-"))
    seeded = asyncio.run(seed(tmp))
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(tmp / "data"),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{tmp / 'smoke.db'}",
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
    root_client = httpx.Client(base_url=ROOT, timeout=60,
                               trust_env=False)
    try:
        for _ in range(60):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("=== AUTONOMUS P-16 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        log(f"seeded: winner={seeded['winner']} loser={seeded['loser']}")

        # ---- 1. Auth boundary + schema
        log("--- 1. Auth boundary, schema")
        unauth = client.get("/economy/status")
        check("economy status requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 191 tables (190 + alembic_version)",
              tables == 191, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner",
            "password": "smoke-owner-password-123"})
        token = (login.json().get("data") or {}).get("access_token")
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        # ---- 2. The gate on aggregate-negative fixtures
        log("--- 2. Profitability gate (owner priority)")
        status = show("economy status", client.get(
            "/economy/status", headers=auth),
            ("autonomy_level", "profitability_gate"))
        gate = status.get("profitability_gate") or {}
        check("gate CLOSED while aggregate verified profit is negative",
              gate.get("state") == "closed",
              f"({gate.get('reason')})")
        overview = show("economy overview", client.get(
            "/economy/overview", headers=auth),
            ("global_economic_overview",))
        geo = overview.get("global_economic_overview") or {}
        check("overview reads P-07: collected ₹7,000, net −₹4,000",
              geo.get("total_verified_collected_revenue_minor") == 700000
              and geo.get("total_net_profit_minor") == -400000,
              f"(got {geo})")
        check("combined cash never summed",
              geo.get("combined_available_cash") is None)

        # ---- 3. Evidence discipline: markets, competitors, countries
        log("--- 3. Market / competitor / country intelligence")
        no_source = client.post("/economy/markets", headers=auth, json={
            "title": "Unsourced", "sector": "other",
            "classification": "emerging"})
        check("market report without evidence sources refused (422)",
              no_source.status_code == 422)
        market = show("market report", client.post(
            "/economy/markets", headers=auth, json={
                "title": "Smoke market scan (fixture)",
                "sector": "digital_products",
                "classification": "growing",
                "evidence_sources": [{"ref": "fixture://smoke/market-1",
                                      "label": "fixture scan"}]}),
            ("id", "title"))
        check("sourced market report created",
              bool(market.get("id")))
        competitor = client.post("/economy/competitors", headers=auth,
                                 json={
                                     "name": "Rival (fixture)",
                                     "source_refs": ["fixture://smoke/rival"],
                                     "strengths": ["brand"],
                                     "weaknesses": ["slow support"]})
        check("competitor with sources created",
              competitor.status_code == 201)
        comparison = show("competitor comparison", client.get(
            "/economy/competitor-comparison?market=", headers=auth),
            ("identified_gaps",))
        check("comparison derives gaps from recorded weaknesses",
              any(g.get("recorded_weakness") == "slow support"
                  for g in comparison.get("identified_gaps") or []))
        country = client.post("/economy/countries", headers=auth, json={
            "country": "IN",
            "entry_checklist": {
                "payments": "UPI and cards recorded (fixture)",
                "tax": "GST on digital services — owner to verify "
                       "(fixture note)",
                "language": "English/Hindi (fixture)"},
            "criteria_scores": {"demand": 80, "purchasing_power": 60,
                                "regulation": 55, "tax": 50,
                                "payments": 85, "language": 90,
                                "currency_risk": 45, "competition": 50,
                                "distribution_cost": 70,
                                "data_protection": 60,
                                "ip_protection": 65}})
        check("country assessment scored", country.status_code == 201
              and (country.json().get("data") or {}).get("total_score")
              is not None)

        # ---- 4. Discovery + the gate on the pipeline
        log("--- 4. Discovery and gate enforcement")
        discovery = show("discovery run", client.post(
            "/economy/discovery/run", headers=auth), ("created",))
        kinds = {o.get("kind") for o in discovery.get("created") or []}
        check("discovery flags the loss-making business",
              "existing_business_expansion" in kinds, f"({kinds})")
        factors = {"market_demand": 80, "profitability_potential": 75,
                   "competitive_advantage": 70, "scalability": 75,
                   "capital_efficiency": 70, "operational_feasibility": 80,
                   "revenue_diversification": 60,
                   "strategic_compatibility": 75, "risk_profile": 30}
        evidence = [{"kind": "market_data", "source_ref": "fixture://s/1",
                     "summary": "fixture"},
                    {"kind": "market_data", "source_ref": "fixture://s/2",
                     "summary": "fixture"},
                    {"kind": "customer_signal", "source_ref": "fixture://s/3",
                     "summary": "fixture"}]
        venture = client.post("/economy/opportunities", headers=auth,
                              json={"title": "Second venture (fixture)",
                                    "kind": "new_business",
                                    "factor_scores": factors,
                                    "evidence": evidence})
        venture_id = (venture.json().get("data") or {}).get("id")
        check("venture scored with evidence-derived confidence",
              venture.status_code == 201
              and (venture.json().get("data") or {}).get(
                  "classification_band") == "controlled_experimentation")
        stage = None
        for target in ("under_research", "market_validation",
                       "financial_evaluation"):
            moved = client.post(
                f"/economy/opportunities/{venture_id}/advance",
                headers=auth, json={"target_stage": target})
            stage = (moved.json().get("data") or {}).get("stage")
        check("venture advances to financial_evaluation",
              stage == "financial_evaluation")
        blocked = client.post(
            f"/economy/opportunities/{venture_id}/advance",
            headers=auth, json={"target_stage": "risk_assessment"})
        check("gate blocks advancing a new-business venture (403)",
              blocked.status_code == 403, f"(got {blocked.status_code})")
        strategy = client.post("/economy/strategies", headers=auth,
                               json={"title": "Launch venture (fixture)",
                                     "horizon": "medium",
                                     "kind": "new_business"})
        strategy_id = (strategy.json().get("data") or {}).get("id")
        denied = client.post(
            f"/economy/strategies/{strategy_id}/approve", headers=auth,
            json={})
        check("gate blocks approving a new-business strategy (403)",
              denied.status_code == 403)
        fix = client.post("/economy/strategies", headers=auth, json={
            "title": "Fix the loser (fixture)", "horizon": "short",
            "kind": "improve_existing"})
        fix_id = (fix.json().get("data") or {}).get("id")
        approved = client.post(
            f"/economy/strategies/{fix_id}/approve", headers=auth,
            json={})
        check("improvement strategy approves under the closed gate",
              approved.status_code == 200
              and (approved.json().get("data") or {}).get("status")
              == "approved")

        # ---- 5. Capital: growth refused, balanced approved, no money moved
        log("--- 5. Capital allocation and the P-07 invariant")
        growth = client.post("/economy/allocations", headers=auth, json={
            "scenario": "growth", "business_id": seeded["winner"],
            "proposed": {"amount_minor": 10000, "purpose": "expand",
                         "target_kind": "business"}})
        check("growth scenario refused while the gate is closed (403)",
              growth.status_code == 403, f"(got {growth.status_code})")
        before = show("overview before allocation", client.get(
            "/economy/overview", headers=auth),
            ("global_economic_overview",))
        balanced = client.post("/economy/allocations", headers=auth,
                               json={
                                   "scenario": "balanced",
                                   "business_id": seeded["winner"],
                                   "proposed": {"amount_minor": 10000,
                                                "purpose": "tooling (fixture)",
                                                "target_kind": "business"}})
        alloc_id = (balanced.json().get("data") or {}).get("id")
        decided = client.post(
            f"/economy/allocations/{alloc_id}/decide", headers=auth,
            json={"approve": True})
        check("balanced allocation approved as a PROPOSAL",
              decided.status_code == 200
              and (decided.json().get("data") or {}).get("status")
              == "approved")
        after = show("overview after allocation", client.get(
            "/economy/overview", headers=auth),
            ("global_economic_overview",))
        check("P-07 totals byte-equal across the P-16 approval",
              before.get("global_economic_overview")
              == after.get("global_economic_overview"))
        plan = show("reinvestment plan", client.post(
            "/economy/reinvestment", headers=auth,
            json={"business_id": seeded["winner"]}), ("figures_snapshot",))
        figures = plan.get("figures_snapshot") or {}
        expected_distributable = max(
            min(figures.get("accounting_net_profit_minor") or 0,
                figures.get("available_cash_minor") or 0)
            - (figures.get("owner_declared_adjustments_minor") or 0), 0)
        check("reinvestment distributable = min(verified profit, "
              "available cash) less adjustments (§10)",
              figures.get("distributable_cash_minor")
              == expected_distributable,
              f"(profit {figures.get('accounting_net_profit_minor')}, "
              f"cash {figures.get('available_cash_minor')}, "
              f"distributable {figures.get('distributable_cash_minor')})")

        # ---- 6. Experiments: pre-declaration, handoff to P-08
        log("--- 6. Economic experiments")
        incomplete = client.post("/economy/experiments", headers=auth,
                                 json={"title": "Vague (fixture)",
                                       "hypothesis": "growth",
                                       "budget_ceiling_minor": 10000,
                                       "duration_days": 7})
        check("experiment without pre-declaration refused (422)",
              incomplete.status_code == 422)
        proposal = client.post("/economy/experiments", headers=auth,
                               json={
                                   "title": "Pricing test (fixture)",
                                   "hypothesis": "a lower tier lifts volume",
                                   "business_id": seeded["winner"],
                                   "market_tag": "pricing",
                                   "budget_ceiling_minor": 20000,
                                   "duration_days": 14,
                                   "success_metrics": ["volume +10%"],
                                   "failure_metrics": ["volume flat"],
                                   "stop_conditions": ["ceiling reached"],
                                   "problem": "flat volume",
                                   "target_customer": "readers",
                                   "expected_outcome": "volume +10%",
                                   "minimum_evidence": "100 sessions",
                                   "evaluation_schedule": "day 14"})
        proposal_id = (proposal.json().get("data") or {}).get("id")
        check("pre-declared experiment proposal created",
              proposal.status_code == 201 and bool(proposal_id))
        client.post(f"/economy/experiments/{proposal_id}/approve",
                    headers=auth, json={})
        client.patch("/economy/settings", headers=auth,
                     json={"autonomy_level": 3})
        handed = show("experiment handoff", client.post(
            f"/economy/experiments/{proposal_id}/handoff", headers=auth),
            ("status", "p08_experiment_id"))
        check("handoff creates a governed P-08 experiment",
              handed.get("status") == "handed_off"
              and bool(handed.get("p08_experiment_id")))

        # ---- 7. Risk + recommendations
        log("--- 7. Risk intelligence and recommendations")
        risk = show("risk assessment", client.post(
            "/economy/risk/compute", headers=auth), ("detectors", "scenarios"))
        detector_kinds = {d.get("kind") for d in risk.get("detectors") or []}
        check("risk detectors flag the loss-maker",
              "loss_making_business" in detector_kinds,
              f"({detector_kinds})")
        check("ten labelled SIMULATION stress scenarios",
              len(risk.get("scenarios") or []) == 10)
        recs = show("recommendations", client.get(
            "/economy/recommendations", headers=auth), ("items",))
        items = recs.get("items") or []
        check("recommendations lead with improving what exists",
              bool(items) and items[0].get("kind") == "improve_existing",
              f"({[i.get('kind') for i in items[:3]]})")

        # ---- 8. Built frontend
        log("--- 8. Command Center bundle")
        app_page = root_client.get("/app/")
        check("frontend served at /app", app_page.status_code == 200)
        js_name = None
        for part in app_page.text.replace('"', " ").split():
            if part.endswith(".js"):
                js_name = part.split("/")[-1]
                break
        if js_name:
            bundle = root_client.get(f"/app/assets/{js_name}")
            check("bundle contains the AI Economy & Expansion view",
                  bundle.status_code == 200
                  and "AI Economy & Expansion" in bundle.text)

        log(f"=== P-16 SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 1 if FAIL else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        evidence = REPO / "docs" / "reports" / "P16_SMOKE_EVIDENCE.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
