"""P-06 live smoke: boots the real application under uvicorn and drives
Scenarios D, A, F, G and J over HTTP against it. Run:

    .venv/bin/python scripts/p06_smoke.py

Writes a transcript to docs/reports/P06_SMOKE_EVIDENCE.txt (relative to
the repository root). Uses a throwaway data directory; nothing persists.

Scenario D runs FIRST and uses a REAL P-03 investigation (the seed
e-book opportunity): the eligibility gate must block it. Scenarios that
need a qualifying opportunity use a clearly-labelled FIXTURE
opportunity whose evidence is stored through the real P-03 API, so its
validation level is computed by P-03 — never asserted here.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PORT = random.randint(20000, 45000)  # fresh port per run: no stale servers
BASE = f"http://127.0.0.1:{PORT}/api/v1"

LINES: list[str] = []


def log(line: str = "") -> None:
    print(line)
    LINES.append(line)


def show(title: str, response: httpx.Response, keys: tuple[str, ...] = ()) -> dict:
    try:
        data = response.json().get("data") or {}
    except Exception:
        data = {}
    picked = {k: data.get(k) for k in keys} if keys else data
    log(f"[{title}] HTTP {response.status_code} -> "
        f"{json.dumps(picked, default=str)[:700]}")
    return data


def wait_research(client, headers, session_id: str) -> dict:
    for _ in range(120):
        resp = client.get(f"/research/{session_id}", headers=headers)
        data = resp.json()["data"]
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.25)
    raise RuntimeError("research session did not finish")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p06-smoke-"))
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(tmp / "data"),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{tmp}/smoke.db",
        "AUTONOMUS_ADMIN_PASSWORD": "smoke-owner-password-123",
        "AUTONOMUS_AUTO_MIGRATE": "true",
        # Same admission setting the test-suite uses: this shared VM runs
        # at >90% RAM, and the P-01 monitor would otherwise (correctly)
        # queue nonessential agent creation. Noted in the transcript.
        "AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD": "false",
        "TMPDIR": "/tmp",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(PORT)],
        cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = httpx.Client(base_url=BASE, timeout=60, trust_env=False)
    try:
        for _ in range(60):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("=== AUTONOMUS P-06 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        log("note: AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD=false (test-suite "
            "setting; this VM's RAM pressure would otherwise queue agent creation)")
        log("note: fixture opportunities are labelled FIXTURE; their evidence is "
            "stored through the real P-03 API and their levels are computed by "
            "P-03, never asserted. Real-opportunity behaviour is Scenario D.")

        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        # ------------------------------------------------ Scenario D FIRST
        log()
        log("--- Scenario D: REAL opportunity must be BLOCKED by eligibility ---")
        brief = show("D brief", client.post("/opportunities/briefs", headers=auth,
                     json={"title": "Smoke investigation",
                           "objective": "find a digital business",
                           "budget_amount": 50, "currency": "USD",
                           "geography": "global"}), ("id",))
        discovered = client.post("/opportunities/discover", headers=auth,
                                 json={"brief_id": brief["id"]}).json()["data"]
        ebook = [o for o in discovered["opportunities"]
                 if o["name"] == "Beginner fitness e-book series (KDP)"][0]
        log(f"[D discover] real seed opportunity: {ebook['name']} "
            f"(status {ebook['status']})")
        session = client.post(f"/opportunities/{ebook['id']}/research",
                              headers=auth, json={
                                  "source_keys": ["owner_research_notes",
                                                  "industry_blog_fixture"]}
                              ).json()["data"]
        done = wait_research(client, auth, session["id"])
        log(f"[D research] session completed via P-01 task "
            f"(status {done['status']}): {done.get('findings_summary')}")
        client.post(f"/opportunities/{ebook['id']}/market-analysis",
                    headers=auth, json={
                        "customer_segment": "beginners",
                        "demand_indicators": ["search interest (fixture blog claim)"],
                        "market_size": {"value": "cannot be established",
                                        "classification": "unknown"},
                        "saturation": "unknown", "sources": []})
        client.post(f"/opportunities/{ebook['id']}/commercial-analysis",
                    headers=auth, json={
                        "startup_costs": [{"name": "design tool", "amount": 15,
                                           "classification": "estimate"}],
                        "recurring_costs_monthly": [
                            {"name": "store fees", "amount": 5,
                             "classification": "estimate"}],
                        "variable_costs_per_sale": [
                            {"name": "delivery", "amount": 0.5,
                             "classification": "estimate"}],
                        "price": {"amount": 19, "classification": "estimate",
                                  "basis": "stated assumption"},
                        "platform_fee_pct": 10, "payment_fee_pct": 3,
                        "budget_amount": 50,
                        "scenario_sales": {
                            "conservative": {"sales_per_month": 2},
                            "base": {"sales_per_month": 6},
                            "optimistic": {"sales_per_month": 15}},
                        "proposed_channels": ["own website", "Amazon KDP"]})
        client.post(f"/opportunities/{ebook['id']}/score", headers=auth, json={})
        validation = show("D validate (P-03 computes the level)",
                          client.post(f"/opportunities/{ebook['id']}/validate",
                                      headers=auth, json={}), ("level", "decision"))
        eligibility = show("D eligibility", client.post(
            "/business/eligibility", headers=auth, json={
                "opportunity_id": ebook["id"],
                "template_name": "ebook_digital_product"}),
            ("decision", "validation_level", "min_validation_level"))
        for check in eligibility.get("checks", []):
            if check["outcome"] == "fail":
                log(f"    gate check FAIL: {check['check']}: {check['reason']}")
        blocked = show("D create attempt (must be refused)", client.post(
            "/business/businesses", headers=auth, json={
                "opportunity_id": ebook["id"],
                "template_name": "ebook_digital_product"}))
        listing = client.get("/business/businesses", headers=auth,
                             params={"opportunity_id": ebook["id"]}).json()
        log(f"[D verify] businesses for the real opportunity: "
            f"{listing['meta']['total']} (zero infrastructure created)")
        assert eligibility["decision"] in (
            "REQUIRES_MORE_RESEARCH", "REQUIRES_MORE_VALIDATION")
        assert listing["meta"]["total"] == 0

        # ------------------------------------------------------ Scenario A
        log()
        log("--- Scenario A: FIXTURE digital-product business, end to end ---")
        fixture = show("A fixture opportunity", client.post(
            "/opportunities", headers=auth, json={
                "name": "FIXTURE — Beginner Fitness Ebook",
                "category": "digital_products",
                "description": "FIXTURE — synthetic opportunity for P-06 "
                               "acceptance; evidence is fixture data stored "
                               "through P-03 machinery.",
                "target_customer": "fitness beginners (fixture)",
                "geography": "global",
                "problem_statement": "Beginners lack a simple starter plan "
                                     "(fixture claim).",
                "proposed_solution": "A short beginner fitness ebook.",
                "revenue_model": "one-time digital product sales",
                "discovery_method": "manual"}), ("id", "status"))
        fid = fixture["id"]
        for group, classification in (("fixture-interviews", "SUPPORTING"),
                                      ("fixture-survey", "CORROBORATED")):
            client.post(f"/opportunities/{fid}/evidence", headers=auth, json={
                "category": "problem", "evidence_kind": "source_claim",
                "claim": f"fixture evidence from {group}",
                "source_name": f"src-{group}", "independence_group": group,
                "classification": classification})
        s2 = client.post(f"/opportunities/{fid}/research", headers=auth,
                         json={"source_keys": []}).json()["data"]
        wait_research(client, auth, s2["id"])
        client.post(f"/opportunities/{fid}/market-analysis", headers=auth,
                    json={"customer_segment": "fitness beginners (fixture)",
                          "demand_indicators": ["fixture indicator"],
                          "market_size": {"value": "cannot be established",
                                          "classification": "unknown"},
                          "saturation": "unknown", "sources": []})
        client.post(f"/opportunities/{fid}/commercial-analysis", headers=auth,
                    json={"startup_costs": [{"name": "design tool", "amount": 15,
                                             "classification": "estimate"}],
                          "recurring_costs_monthly": [
                              {"name": "store fees", "amount": 5,
                               "classification": "estimate"}],
                          "variable_costs_per_sale": [
                              {"name": "delivery", "amount": 0.5,
                               "classification": "estimate"}],
                          "price": {"amount": 19, "classification": "estimate",
                                    "basis": "fixture assumption"},
                          "platform_fee_pct": 10, "payment_fee_pct": 3,
                          "budget_amount": 50,
                          "scenario_sales": {
                              "conservative": {"sales_per_month": 2},
                              "base": {"sales_per_month": 6},
                              "optimistic": {"sales_per_month": 15}},
                          "proposed_channels": ["own website", "Amazon KDP"]})
        client.post(f"/opportunities/{fid}/score", headers=auth, json={})
        fvalidation = show("A fixture validate (level computed by P-03)",
                           client.post(f"/opportunities/{fid}/validate",
                                       headers=auth, json={}), ("level",))
        approval = show("A creation approval request", client.post(
            "/business/creation-approvals", headers=auth, json={
                "opportunity_id": fid,
                "template_name": "ebook_digital_product"}), ("approval_id",))
        client.post(f"/approvals/{approval['approval_id']}/decision",
                    headers=auth, json={"approve": True})
        log("[A approval] owner approved the hash-bound creation approval")
        business = show("A create business", client.post(
            "/business/businesses", headers=auth, json={
                "opportunity_id": fid,
                "template_name": "ebook_digital_product",
                "approval_id": approval["approval_id"]}),
            ("id", "status", "is_fixture", "validation_level_at_creation"))
        bid = business["id"]
        show("A pre-declaration", client.post(
            f"/business/businesses/{bid}/declarations", headers=auth, json={
                "success_criteria": ["prepared package hash-verifies",
                                     "10 reader tests at the declared price"],
                "budget_cap_amount": 50, "budget_currency": "USD",
                "duration_days": 30, "min_test_volume": 10}), ("status",))
        show("A blueprint", client.post(
            f"/business/businesses/{bid}/blueprint", headers=auth),
            ("version", "product_id"))
        run = show("A creation run", client.post(
            f"/business/businesses/{bid}/creation-run", headers=auth),
            ("workflow_status",))
        log(f"[A assets] {len(run.get('assets', []))} assets registered, "
            f"hash-verified via the execution engine")
        channels = show("A channel evaluation", client.post(
            f"/business/businesses/{bid}/channels/evaluate", headers=auth))
        kdp = [c for c in channels["channels"] if c["platform"] == "Amazon KDP"][0]
        log(f"[A KDP gate] outcome={kdp['platform_gate']['outcome']} "
            f"publish_state={kdp['publish_state']}")
        attempt = show("A KDP publish attempt", client.post(
            f"/business/businesses/{bid}/channels/{kdp['id']}/publish",
            headers=auth), ("published", "gate_outcome", "requires_human_action"))
        assert attempt["published"] is False
        assert attempt["requires_human_action"] is True
        review = show("A readiness", client.post(
            f"/business/businesses/{bid}/readiness", headers=auth),
            ("overall_status", "warnings"))

        # ------------------------------------------------------ Scenario F
        log()
        log("--- Scenario F: readiness NOT_READY blocks launch path ---")
        fixture2 = show("F fixture opportunity", client.post(
            "/opportunities", headers=auth, json={
                "name": "FIXTURE — Unready Planner",
                "category": "digital_products",
                "description": "FIXTURE — second fixture for Scenario F.",
                "target_customer": "planners (fixture)", "geography": "global",
                "problem_statement": "fixture problem",
                "proposed_solution": "fixture planner",
                "revenue_model": "one-time sales",
                "discovery_method": "manual"}), ("id",))
        f2 = fixture2["id"]
        for group, classification in (("fixture-interviews", "SUPPORTING"),
                                      ("fixture-survey", "CORROBORATED")):
            client.post(f"/opportunities/{f2}/evidence", headers=auth, json={
                "category": "problem", "evidence_kind": "source_claim",
                "claim": f"fixture evidence {group}",
                "source_name": f"src-{group}", "independence_group": group,
                "classification": classification})
        s3 = client.post(f"/opportunities/{f2}/research", headers=auth,
                         json={"source_keys": []}).json()["data"]
        wait_research(client, auth, s3["id"])
        client.post(f"/opportunities/{f2}/market-analysis", headers=auth,
                    json={"customer_segment": "fixture",
                          "demand_indicators": ["fixture"],
                          "market_size": {"value": "cannot be established",
                                          "classification": "unknown"},
                          "saturation": "unknown", "sources": []})
        client.post(f"/opportunities/{f2}/commercial-analysis", headers=auth,
                    json={"startup_costs": [{"name": "design tool", "amount": 15,
                                             "classification": "estimate"}],
                          "recurring_costs_monthly": [
                              {"name": "store fees", "amount": 5,
                               "classification": "estimate"}],
                          "variable_costs_per_sale": [
                              {"name": "delivery", "amount": 0.5,
                               "classification": "estimate"}],
                          "price": {"amount": 19, "classification": "estimate",
                                    "basis": "fixture"},
                          "platform_fee_pct": 10, "payment_fee_pct": 3,
                          "budget_amount": 50,
                          "scenario_sales": {
                              "conservative": {"sales_per_month": 2},
                              "base": {"sales_per_month": 6},
                              "optimistic": {"sales_per_month": 15}},
                          "proposed_channels": ["own website"]})
        client.post(f"/opportunities/{f2}/score", headers=auth, json={})
        client.post(f"/opportunities/{f2}/validate", headers=auth, json={})
        approval2 = client.post("/business/creation-approvals", headers=auth,
                                json={"opportunity_id": f2,
                                      "template_name": "ebook_digital_product"}
                                ).json()["data"]
        client.post(f"/approvals/{approval2['approval_id']}/decision",
                    headers=auth, json={"approve": True})
        business2 = show("F create business (blueprint only, no run)",
                         client.post("/business/businesses", headers=auth,
                                     json={"opportunity_id": f2,
                                           "template_name": "ebook_digital_product",
                                           "approval_id": approval2["approval_id"]}),
                         ("id", "status"))
        b2 = business2["id"]
        client.post(f"/business/businesses/{b2}/declarations", headers=auth,
                    json={"success_criteria": ["package verifies"],
                          "budget_cap_amount": 50, "budget_currency": "USD",
                          "duration_days": 30, "min_test_volume": 10})
        client.post(f"/business/businesses/{b2}/blueprint", headers=auth)
        review_f = show("F readiness (no creation run)", client.post(
            f"/business/businesses/{b2}/readiness", headers=auth),
            ("overall_status",))
        for blocker in review_f.get("blockers", []):
            log(f"    blocker [{blocker['dimension']}]: {blocker['blocker']}")
        assert review_f["overall_status"] == "NOT_READY"
        refused = client.post(f"/business/businesses/{b2}/transition",
                              headers=auth, json={"target": "READY_FOR_LAUNCH"})
        log(f"[F transition READY_FOR_LAUNCH] HTTP {refused.status_code} "
            "(refused: readiness is NOT_READY)")
        assert refused.status_code == 409

        # ------------------------------------------------------ Scenario G
        log()
        log("--- Scenario G: cross-business isolation ---")
        assignments = client.get(f"/business/businesses/{bid}/assignments",
                                 headers=auth).json()["data"]
        agent_a = assignments[0]["agent_id"]
        probe = show("G agent-of-A probes business-F workspace", client.post(
            f"/business/businesses/{b2}/workspace-access", headers=auth,
            json={"agent_id": agent_a}), ("allowed",))
        assert probe["allowed"] is False
        log("[G verify] denial recorded as a persisted critical event "
            "(BusinessIsolationViolation in system_events; asserted by the "
            "P-06 security suite)")

        # ------------------------------------------------------ Scenario J
        log()
        log("--- Scenario J: launch requires the owner approval ---")
        show("J transition", client.post(
            f"/business/businesses/{bid}/transition", headers=auth,
            json={"target": "READY_FOR_LAUNCH",
                  "reason": "readiness recorded"}), ("status",))
        launch_req = show("J launch request", client.post(
            f"/business/businesses/{bid}/launch/request", headers=auth),
            ("approval_id", "status"))
        early = client.post(f"/business/businesses/{bid}/launch",
                            headers=auth,
                            json={"approval_id": launch_req["approval_id"]})
        log(f"[J launch before owner decision] HTTP {early.status_code} "
            "(refused: approval still pending)")
        assert early.status_code in (401, 403)
        client.post(f"/approvals/{launch_req['approval_id']}/decision",
                    headers=auth, json={"approve": True})
        launched = show("J launch after owner approval (staging demo)",
                        client.post(f"/business/businesses/{bid}/launch",
                                    headers=auth,
                                    json={"approval_id":
                                          launch_req["approval_id"]}),
                        ("status", "deployment_state", "public_availability"))
        assert launched["status"] == "OPERATIONAL"
        assert launched["deployment_state"] == "local_package_only"
        assert launched["public_availability"] is False
        log()
        log("SMOKE COMPLETE: D blocked the real opportunity; A built a "
            "fixture package end-to-end; F refused launch; G denied "
            "cross-business access; J launched only after owner approval. "
            "Nothing was published, deployed, sold or sent.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        out = REPO / "docs" / "reports" / "P06_SMOKE_EVIDENCE.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"transcript written to {out}")


if __name__ == "__main__":
    raise SystemExit(main())
