"""P-08 live smoke: boots the real application under uvicorn and
drives the Survival and Scaling Engine over HTTP. Run:

    .venv/bin/python scripts/p08_smoke.py

Writes a transcript to docs/reports/P08_SMOKE_EVIDENCE.txt (relative
to the repository root). Uses a throwaway data directory.

Order matters (§32 rule + the owner's staging-honesty test):
1. FIRST, a fixture business exactly as it exists in staging —
   no verified revenue — must evaluate to INSUFFICIENT_DATA with
   scaling NOT_READY and no growth capital recommended.
2. Then the §26.4 scenarios S1, S2, S4, S5, S7, S9, S12, S15 on
   clearly-labelled fixtures whose financial history is seeded
   THROUGH P-07's own HTTP machinery: opening balances and expenses
   via the financial API, verified collected revenue ONLY via
   signature-verified fake-provider webhooks (the internal verified
   path). Nothing is written to the ledger directly.
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
sys.path.insert(0, str(BACKEND))

PORT = random.randint(20000, 45000)  # fresh port per run: no stale servers
BASE = f"http://127.0.0.1:{PORT}/api/v1"

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
        f"{json.dumps(picked, default=str)[:600]}")
    return data


def wait_research(client, headers, session_id: str) -> dict:
    for _ in range(120):
        resp = client.get(f"/research/{session_id}", headers=headers)
        data = resp.json()["data"]
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.25)
    raise RuntimeError("research session did not finish")


def fixture_opportunity(client, headers, name: str) -> str:
    """The proven P-06 HTTP fixture path (imported from the P-06
    integration suite): evidence through the real P-03 API, so the
    validation level is computed by P-03 — never asserted here."""
    from tests.test_p06_integration import _fixture_opportunity_http
    root_client = httpx.Client(
        base_url=f"http://127.0.0.1:{PORT}", timeout=60, trust_env=False)
    return _fixture_opportunity_http(root_client, headers, name)


DECLARATION = None  # loaded in main from tests.p06_support


def make_business(client, headers, name: str) -> str:
    opp_id = fixture_opportunity(client, headers, name)
    resp = client.post("/business/creation-approvals", headers=headers,
                       json={"opportunity_id": opp_id,
                             "template_name": "ebook_digital_product"})
    assert resp.status_code == 200, resp.text
    approval_id = resp.json()["data"]["approval_id"]
    resp = client.post(f"/approvals/{approval_id}/decision",
                       headers=headers, json={"approve": True})
    assert resp.status_code == 200, resp.text
    resp = client.post("/business/businesses", headers=headers,
                       json={"opportunity_id": opp_id,
                             "template_name": "ebook_digital_product",
                             "approval_id": approval_id})
    assert resp.status_code == 201, resp.text
    business_id = resp.json()["data"]["id"]
    resp = client.post(f"/business/businesses/{business_id}/declarations",
                       headers=headers, json=DECLARATION)
    assert resp.status_code == 201, resp.text
    resp = client.put("/business/settings", headers=headers,
                      json={"values": {"default_currency": "INR"}})
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/business/businesses/{business_id}/blueprint",
                       headers=headers)
    assert resp.status_code == 200, resp.text
    return business_id


def onboard_operational(client, headers, business_id: str) -> None:
    for step, path in (
            ("creation-run", f"/business/businesses/{business_id}/creation-run"),
            ("channels", f"/business/businesses/{business_id}/channels/evaluate"),
            ("readiness", f"/business/businesses/{business_id}/readiness")):
        resp = client.post(path, headers=headers)
        assert resp.status_code in (200, 201), (step, resp.text)
    resp = client.post(f"/business/businesses/{business_id}/transition",
                       headers=headers,
                       json={"target": "READY_FOR_LAUNCH",
                             "reason": "readiness passed"})
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/business/businesses/{business_id}/launch/request",
                       headers=headers)
    assert resp.status_code in (200, 201), resp.text
    approval_id = resp.json()["data"]["approval_id"]
    resp = client.post(f"/approvals/{approval_id}/decision",
                       headers=headers, json={"approve": True})
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/business/businesses/{business_id}/launch",
                       headers=headers, json={"approval_id": approval_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "OPERATIONAL", resp.text


def profile(client, headers, business_id: str) -> None:
    resp = client.post(f"/financial/businesses/{business_id}/profile",
                       headers=headers, json={})
    assert resp.status_code in (200, 201), resp.text


def opening_balance(client, headers, business_id: str, amount: str) -> None:
    resp = client.post(
        f"/financial/businesses/{business_id}/opening-balance",
        headers=headers,
        json={"amount": amount, "currency": "INR",
              "entry_date": "2026-11-01", "account_ref": "bank:primary",
              "source": "bank_statement", "verification_status": "verified"})
    assert resp.status_code == 201, resp.text


def expense(client, headers, business_id: str, amount: str,
            budget_id: str | None = None) -> None:
    resp = client.post("/financial/expenses", headers=headers, json={
        "business_id": business_id, "category": "operational",
        "amount": amount, "currency": "INR", "expense_date": "2026-11-06",
        "directness": "indirect", "cost_behavior": "variable",
        "budget_id": budget_id, "payment_status": "paid"})
    assert resp.status_code in (200, 201), resp.text


def webhook_sale(client, business_id: str, amount_minor: int,
                 customer: str, ref: str) -> None:
    """Verified collected revenue through the signature-verified
    fake-provider webhook — P-07's internal verified path."""
    from app.financial.payments import fake_webhook_headers
    body = json.dumps({
        "event_id": f"evt-{ref}", "type": "payment.settled",
        "payment_ref": ref, "business_id": business_id,
        "amount_minor": amount_minor, "currency": "INR",
        "occurred_date": "2026-11-05", "customer_ref": customer,
    }).encode()
    headers = fake_webhook_headers("fake-provider-test-secret", body,
                                   int(time.time()))
    headers["Content-Type"] = "application/json"
    resp = client.post("/financial/payments/webhooks/fake-provider",
                       content=body, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "processed", resp.text


def evaluate(client, headers, business_id: str) -> dict:
    resp = client.post(f"/survival/businesses/{business_id}/evaluate",
                       headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["snapshot"]


def main() -> int:
    global DECLARATION
    from tests.p06_support import DECLARATION as _DECL
    DECLARATION = _DECL
    tmp = Path(tempfile.mkdtemp(prefix="p08-smoke-"))
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(tmp / "data"),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{tmp}/smoke.db",
        "AUTONOMUS_ADMIN_PASSWORD": "smoke-owner-password-123",
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
    try:
        for _ in range(60):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("=== AUTONOMUS P-08 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        log("note: AUTONOMUS_BLOCK_NONESSENTIAL_ON_THRESHOLD=false "
            "(test-suite setting; this VM's RAM pressure would "
            "otherwise queue agent creation)")
        log("note: fixture businesses are labelled FIXTURE; verified "
            "revenue arrives ONLY through signature-verified "
            "fake-provider webhooks (P-07's internal verified path)")

        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        token = login.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        status = show("survival status", client.get(
            "/survival/status", headers=auth), ("engine", "frontend"))
        check("engine reports API-only frontend (P-11 owns UI)",
              "NOT IMPLEMENTED" in str(status.get("frontend")))

        # --------------------------------- HONESTY CHECK FIRST (§32)
        log()
        log("--- HONESTY CHECK FIRST: a staging fixture business as it "
            "actually exists (no verified revenue) ---")
        real_id = make_business(client, auth, "FIXTURE — Staging As-Is")
        profile(client, auth, real_id)
        snapshot = evaluate(client, auth, real_id)
        log(f"[honesty] classification={snapshot['classification']} "
            f"overlay={snapshot['overlay_state']}")
        check("health is INSUFFICIENT_DATA",
              snapshot["classification"] == "INSUFFICIENT_DATA")
        resp = client.post(
            f"/survival/businesses/{real_id}/scaling/assess",
            headers=auth)
        assessment = resp.json()["data"]
        check("scaling is NOT_READY at stage 0",
              assessment["status"] == "NOT_READY"
              and assessment["stage"] == 0,
              f"status={assessment['status']} stage={assessment['stage']}")
        resp = client.post("/survival/portfolio/allocations",
                           headers=auth, json={
                               "currency": "INR",
                               "source_kind": "available_capital",
                               "requests": [{"business_id": real_id,
                                             "amount_minor": 100000,
                                             "purpose": "growth"}]})
        proposals = resp.json()["data"]["proposals"]
        check("no growth capital recommended (proposal 0/BLOCKED)",
              proposals and proposals[0]["amount_minor"] == 0)

        # ------------------------------------------------- S1
        log()
        log("--- S1: revenue ₹10,000 → ₹30,000, expenses ₹8,000 → "
            "₹35,000 (growth without profitability) ---")
        s1 = make_business(client, auth, "FIXTURE — S1 Growth No Profit")
        profile(client, auth, s1)
        opening_balance(client, auth, s1, "50000.00")
        webhook_sale(client, s1, 1_000_000, "cust-a", "s1-sale-1")
        expense(client, auth, s1, "8000.00")
        evaluate(client, auth, s1)
        webhook_sale(client, s1, 2_000_000, "cust-b", "s1-sale-2")
        expense(client, auth, s1, "27000.00")
        snapshot = evaluate(client, auth, s1)
        gates = {g["gate"] for g in snapshot["hard_gates"]}
        log(f"[S1] gates={sorted(gates)}")
        check("loss-making deterioration flagged", "loss_making" in gates)
        resp = client.post(f"/survival/businesses/{s1}/scaling/assess",
                           headers=auth)
        assessment = resp.json()["data"]
        check("scaling NOT recommended",
              assessment["status"] in ("NOT_READY", "BLOCKED"),
              f"status={assessment['status']}")
        resp = client.post(f"/survival/businesses/{s1}/decisions",
                           headers=auth, json={
                               "decision_type": "INVESTIGATE",
                               "trigger": "loss-making gate raised"})
        check("cost investigation opened (INVESTIGATE decision)",
              resp.status_code == 201
              and resp.json()["data"]["decision_type"] == "INVESTIGATE")

        # ------------------------------------------------- S2
        log()
        log("--- S2: vanity metrics (traffic/followers, no paying "
            "customers) ---")
        s2 = make_business(client, auth, "FIXTURE — S2 Vanity")
        profile(client, auth, s2)
        resp = client.post(f"/survival/businesses/{s2}/observations",
                           headers=auth, json={
                               "kind": "traffic", "source": "imported",
                               "reliability": "verified",
                               "metrics": {"page_views": 120000,
                                           "followers": 48000}})
        observation = resp.json()["data"]
        check("vanity observation capped at tentative reliability",
              observation["reliability"] == "tentative"
              and observation["is_vanity"] is True)
        snapshot = evaluate(client, auth, s2)
        commercial = {d["dimension"]: d["status"]
                      for d in snapshot["dimensions"]}
        check("commercial dimension NOT validated",
              commercial["commercial"] == "INSUFFICIENT_DATA")
        resp = client.post(f"/survival/businesses/{s2}/scaling/assess",
                           headers=auth)
        check("not scaling-ready",
              resp.json()["data"]["status"] == "NOT_READY")

        # ------------------------------------------------- S4
        log()
        log("--- S4: failed experiment — stop-loss blocks further "
            "spend ---")
        s4 = make_business(client, auth, "FIXTURE — S4 Stop-Loss")
        profile(client, auth, s4)
        opening_balance(client, auth, s4, "10000.00")
        resp = client.post(f"/survival/businesses/{s4}/experiments",
                           headers=auth, json={
                               "name": "smoke-experiment",
                               "hypothesis": "a clearer page converts",
                               "problem": "visitors leave",
                               "target_customer": "beginners",
                               "expected_outcome": "5 verified sales",
                               "success_metric": "verified_sales >= 5",
                               "failure_metric": "verified_sales < 2",
                               "minimum_evidence": "P-07 verified "
                                                   "records",
                               "max_duration_days": 14,
                               "approved_budget_minor": 200000,
                               "max_acceptable_loss_minor": 100000,
                               "evaluation_schedule": "daily",
                               "currency": "INR"})
        experiment = resp.json()["data"]
        resp = client.post(f"/survival/experiments/{experiment['id']}/approve",
                           headers=auth, json={})
        budget_id = resp.json()["data"]["budget_id"]
        resp = client.post(f"/survival/experiments/{experiment['id']}/start",
                           headers=auth)
        check("experiment running", resp.status_code == 200)
        expense(client, auth, s4, "1000.00", budget_id=budget_id)
        resp = client.post(
            f"/survival/experiments/{experiment['id']}/stop-loss",
            headers=auth)
        outcome = resp.json()["data"]
        check("stop-loss tripped at max loss",
              outcome["stop_loss_tripped"] is True,
              f"reasons={outcome.get('reasons')}")
        resp = client.post(f"/survival/experiments/{experiment['id']}/spend",
                           headers=auth, json={"amount_minor": 10000})
        check("further spend blocked (HTTP 403)",
              resp.status_code == 403, f"HTTP {resp.status_code}")
        resp = client.get(f"/survival/businesses/{s4}/experiments",
                          headers=auth)
        check("failed experiment preserved as a record",
              resp.json()["meta"]["total"] == 1)

        # ------------------------------------------------- S5
        log()
        log("--- S5: genuinely ready business — readiness report + "
            "incremental plan + approval ---")
        s5 = make_business(client, auth, "FIXTURE — S5 Ready")
        onboard_operational(client, auth, s5)
        profile(client, auth, s5)
        opening_balance(client, auth, s5, "100000.00")
        for index, customer in enumerate(
                ("cust-a", "cust-b", "cust-c", "cust-a")):
            webhook_sale(client, s5, 250_000, customer, f"s5-sale-{index}")
        expense(client, auth, s5, "2000.00")
        for kind, metrics in (
                ("operations", {"delivery_completion_rate": "0.95",
                                "failed_runs": 1}),
                ("product", {"satisfaction": "0.7"}),
                ("market", {"demand_signal": "steady"}),
                ("compliance", {"violation": False})):
            resp = client.post(f"/survival/businesses/{s5}/observations",
                               headers=auth, json={
                                   "kind": kind, "source": "operator",
                                   "reliability": "corroborated"
                                   if kind != "market" else "supporting",
                                   "metrics": metrics})
            assert resp.status_code == 201, resp.text
        evaluate(client, auth, s5)
        snapshot = evaluate(client, auth, s5)
        log(f"[S5] classification={snapshot['classification']}")
        resp = client.post(f"/survival/businesses/{s5}/scaling/assess",
                           headers=auth)
        assessment = resp.json()["data"]
        check("readiness report READY with satisfied conditions listed",
              assessment["status"] == "READY"
              and len(assessment["satisfied"]) >= 8,
              f"status={assessment['status']} "
              f"satisfied={len(assessment['satisfied'])}")
        resp = client.post("/financial/budgets", headers=auth, json={
            "scope_type": "business", "business_id": s5,
            "name": "Growth budget", "amount": "10000.00",
            "currency": "INR", "period_start": "2026-11-01",
            "period_end": "2026-11-30", "approval_requirement": "level_1"})
        assert resp.status_code in (200, 201), resp.text
        budget_id = resp.json()["data"]["id"]
        resp = client.post(f"/survival/businesses/{s5}/scaling/plans",
                           headers=auth, json={
                               "budget_id": budget_id,
                               "proposed_amount_minor": 5000000,
                               "strict": True})
        check("₹10,000 → ₹50,000 in one step REFUSED in strict mode",
              resp.status_code in (400, 422), f"HTTP {resp.status_code}")
        resp = client.post(f"/survival/businesses/{s5}/scaling/plans",
                           headers=auth, json={
                               "budget_id": budget_id,
                               "proposed_amount_minor": 5000000})
        plan = resp.json()["data"]
        check("incremental plan clamped to ₹15,000 (+50% cap, §10.4)",
              plan["proposed_amount_minor"] == 1_500_000
              and plan["clamped"] is True,
              f"proposed={plan['proposed_amount_minor']}")
        resp = client.post(f"/survival/scaling/plans/{plan['id']}/approve",
                           headers=auth)
        check("owner approval recorded; plan APPROVED",
              resp.status_code == 200
              and resp.json()["data"]["status"] == "APPROVED")
        resp = client.get(f"/financial/budgets/{budget_id}/utilisation",
                          headers=auth)
        if resp.status_code == 200:
            check("P-07 budget itself unchanged by P-08 approval (§16.4)",
                  resp.json()["data"]["approved_minor"] == 1_000_000)

        # ------------------------------------------------- S7
        log()
        log("--- S7: platform concentration across businesses ---")
        s7 = make_business(client, auth, "FIXTURE — S7 Second Book")
        onboard_operational(client, auth, s7)
        resp = client.get("/survival/portfolio/concentration",
                          headers=auth)
        concentration = resp.json()["data"]
        platforms = {r.get("platform") for r in concentration["risks"]
                     if r["kind"] == "platform_dependency"}
        log(f"[S7] platform risks={sorted(p for p in platforms if p)}")
        check("shared-platform dependency named as portfolio risk",
              len(platforms) >= 1)
        check("record count is not called diversification",
              "diversification" in concentration["diversification_note"])

        # ------------------------------------------------- S9
        log()
        log("--- S9: closure REVIEW for an unviable business; closure "
            "refused without the Level 4 owner flow ---")
        s9 = make_business(client, auth, "FIXTURE — S9 Unviable")
        onboard_operational(client, auth, s9)
        profile(client, auth, s9)
        opening_balance(client, auth, s9, "3000.00")
        expense(client, auth, s9, "2500.00")
        resp = client.post(f"/survival/businesses/{s9}/closure/propose",
                           headers=auth, json={
                               "reason": "no verified demand after "
                                         "repeated attempts"})
        review = resp.json()["data"]
        check("closure review proposed with obligations inventoried",
              review["stage"] == "PROPOSED_CLOSURE"
              and review["inventory"] is not None)
        resp = client.post(f"/survival/closure/reviews/{review['id']}/execute",
                           headers=auth, json={})
        check("execution refused before OWNER_APPROVAL stage",
              resp.status_code in (400, 422), f"HTTP {resp.status_code}")
        business = client.get(f"/business/businesses/{s9}",
                              headers=auth).json()["data"]
        check("business NOT closed", business["status"] == "OPERATIONAL")
        for _ in range(4):
            resp = client.post(
                f"/survival/closure/reviews/{review['id']}/advance",
                headers=auth)
            review = resp.json()["data"]
        check("review walked to OWNER_APPROVAL",
              review["stage"] == "OWNER_APPROVAL")
        resp = client.post(f"/survival/closure/reviews/{review['id']}/execute",
                           headers=auth, json={})
        closed = resp.json()["data"]
        check("owner flow closes; history preservation recorded",
              resp.status_code == 200 and closed["stage"] == "CLOSED"
              and closed["wind_down"]["financial_history_preserved"]
              is True)
        business = client.get(f"/business/businesses/{s9}",
                              headers=auth).json()["data"]
        check("P-06 business archived through its validated path",
              business["status"] == "ARCHIVED")

        # ------------------------------------------------- S12
        log()
        log("--- S12: protected-reserve allocation BLOCKED ---")
        resp = client.post("/financial/reserves", headers=auth, json={
            "reserve_type": "emergency", "amount": "5000.00",
            "currency": "INR", "business_id": s5})
        assert resp.status_code in (200, 201), resp.text
        resp = client.post("/survival/portfolio/allocations",
                           headers=auth, json={
                               "currency": "INR",
                               "source_kind": "protected_reserves",
                               "requests": [{"business_id": s5,
                                             "amount_minor": 500000,
                                             "purpose": "scale ads"}]})
        outcome = resp.json()["data"]
        check("allocation from protected reserves BLOCKED and recorded",
              outcome["blocked"] is True
              and outcome["proposals"][0]["status"] == "BLOCKED")
        resp = client.get(
            f"/financial/businesses/{s5}/available-cash?currency=INR",
            headers=auth)
        check("reserve untouched (₹5,000 still protected)",
              resp.json()["data"]["protected_reserves_minor"] == 500_000)

        # ------------------------------------------------- S15
        log()
        log("--- S15: emergency pause blocks execution; records "
            "preserved; owner-only resume ---")
        resp = client.post(f"/survival/businesses/{s5}/pause",
                           headers=auth, json={
                               "reason": "suspected credential compromise"})
        paused = resp.json()["data"]
        check("pause engaged", paused["state"] == "PAUSED")
        resp = client.post(f"/survival/businesses/{s5}/decisions",
                           headers=auth, json={
                               "decision_type": "MONITOR",
                               "trigger": "pre-incident review"})
        decision = resp.json()["data"]
        resp = client.post(f"/survival/decisions/{decision['id']}/execute",
                           headers=auth, json={
                               "idempotency_key": "during-pause"})
        check("decision execution blocked during pause (HTTP 403)",
              resp.status_code == 403, f"HTTP {resp.status_code}")
        resp = client.get(f"/survival/businesses/{s5}/health/snapshots",
                          headers=auth)
        check("health history preserved and readable during pause",
              resp.status_code == 200
              and resp.json()["meta"]["total"] >= 1)
        resp = client.post(f"/survival/businesses/{s5}/evaluate",
                           headers=auth)
        snapshot = resp.json()["data"]["snapshot"]
        gates = {g["gate"] for g in snapshot["hard_gates"]}
        check("paused business carries the security-incident gate",
              "security_incident" in gates
              and snapshot["classification"] == "CRITICAL")
        resp = client.post(f"/survival/businesses/{s5}/resume",
                           headers=auth)
        check("owner resume restores ACTIVE",
              resp.status_code == 200
              and resp.json()["data"]["state"] == "ACTIVE")

        log()
        log(f"=== P-08 SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 1 if FAIL else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        out = REPO / "docs" / "reports" / "P08_SMOKE_EVIDENCE.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
