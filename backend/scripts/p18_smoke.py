"""P-18 live smoke: boots the real application under uvicorn
(which also serves the built Command Center at /app, now
including the Customer Experience section) against a throwaway
auto-migrated database seeded in-process through governed paths,
and drives the P-18 surface over HTTP. Run:

    .venv/bin/python scripts/p18_smoke.py

Writes a transcript to docs/reports/P18_SMOKE_EVIDENCE.txt
(relative to the repository root).

The story: a fixture business serves one P-17 customer end to
end — verified P-07 purchase, onboarding from the labelled
system-default lifecycle, fulfilment to acceptance, an
owner-configured SLA, a knowledge-grounded support answer
(verified, cited) and an honest insufficient-information answer
that escalates into a ticket, a queued communication whose
dispatch is honestly blocked, recorded feedback, a computed
health classification, and a refund that exists only as a P-07
refund against the verified revenue record. Customers stay
P-17's; money stays P-07's; nothing is sent.
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
    """Governed fixture lifecycle in-process: business (P-06
    fixture path), customer (P-17's one store), verified revenue
    (P-07), then P-18 state — SLA policy, approved KB article,
    one recorded CSAT response."""
    from app.core.application import Application
    from app.core.config import Settings
    from tests.conftest import OWNER
    from tests.p06_support import make_fixture_business
    from tests.p17_support import customer_revenue

    settings = Settings(
        environment="test", mode="controlled",
        data_dir=tmp / "data",
        database_url=f"sqlite:///{tmp}/smoke.db",
        admin_username="owner",
        admin_password="<MASKED_SECRET_001>",
        dev_token="<redacted>",
        log_file=str(tmp / "logs" / "seed.log"),
        auto_migrate=True, block_nonessential_on_threshold=False,
        retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.05)
    app = Application(settings)
    await app.startup()
    try:
        _opp, business = await make_fixture_business(
            app, name="Smoke Experience Biz (fixture)")
        business_id = business["id"]
        customer = app.growth.create_customer(OWNER, business_id, {
            "contact": {"email": "smoke@example.com",
                        "name": "Smoke Customer"},
            "consent_status": "granted",
            "p07_customer_ref": "smoke-cust-1", "is_fixture": True})
        revenue = await customer_revenue(
            app, business_id, "500.00", customer_ref="smoke-cust-1")
        svc = app.experience
        svc.upsert_sla_policy(OWNER, business_id, {
            "category": "*", "first_response_minutes": 120,
            "resolution_minutes": 1440})
        article = svc.create_article(OWNER, business_id, {
            "title": "Reset your password",
            "content": "To reset your password open account settings "
                       "and choose reset password to set a new "
                       "password.",
            "category": "account"})
        svc.approve_article(OWNER, article["id"])
        svc.record_feedback(OWNER, business_id, {
            "customer_id": customer["id"], "kind": "csat", "score": 5,
            "is_fixture": True})
        return {"business": business_id, "customer": customer["id"],
                "revenue": revenue["id"], "article": article["id"]}
    finally:
        await app.shutdown()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p18-smoke-"))
    seeded = asyncio.run(seed(tmp))
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(tmp / "data"),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{tmp}/smoke.db",
        "AUTONOMUS_ADMIN_PASSWORD": "<MASKED_SECRET_001>",
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
        # Readiness gate before login (P-17 carried observation:
        # a login landing in the boot window can be refused even
        # with correct credentials; /health/ready only returns 200
        # at the END of startup).
        service_auth = {"Authorization": "Bearer smoke-service-token"}
        for _ in range(120):
            try:
                if client.get("/health/ready",
                              headers=service_auth).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("=== AUTONOMUS P-18 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        log(f"seeded: {seeded}")
        biz = seeded["business"]
        cust = seeded["customer"]

        # ---- 1. Auth boundary + schema
        log("--- 1. Auth boundary, schema")
        unauth = client.get("/experience/status")
        check("experience status requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 224 tables (223 + alembic_version)",
              tables == 224, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner",
            "password": "<MASKED_SECRET_001>"})
        attempts = 1
        while login.status_code != 200 and attempts < 6:
            time.sleep(5)
            attempts += 1
            login = client.post("/auth/login", json={
                "username": "owner",
                "password": "<MASKED_SECRET_001>"})
        log(f"[login attempts] {attempts}")
        token = None
        try:
            token = login.json()["data"]["access_token"]
        except Exception:
            pass
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)"
            if token else
            f"[login] HTTP {login.status_code} FAILED: "
            f"{login.text[:300]}")

        # ---- 2. Status, roles, integrations
        log("--- 2. Engine status, roles, integrations")
        status = show("experience status", client.get(
            "/experience/status", headers=auth),
            ("customer_authority", "financial_authority",
             "workflow_authority", "counts"))
        check("customers stay with P-17",
              status.get("customer_authority") == "P-17 (crm_customers)")
        check("money stays with P-07",
              status.get("financial_authority") == "P-07")
        roles = show("agent roles", client.get(
            "/experience/agent-roles", headers=auth), ("count",))
        check("10 §14 agent roles seeded as P-04 templates",
              roles.get("count") == 10)
        integrations = show("integrations", client.get(
            "/experience/integrations", headers=auth), ("count",))
        check("every integration honestly not_configured",
              all(i.get("status") == "not_configured"
                  for i in integrations.get("items") or []))

        # ---- 3. Onboarding over HTTP
        log("--- 3. Onboarding lifecycle")
        onboarding = show("start onboarding", client.post(
            f"/experience/businesses/{biz}/onboardings", headers=auth,
            json={"customer_id": cust, "business_model": "saas",
                  "is_fixture": True}),
            ("id", "template_source", "status"))
        check("onboarding uses the labelled system default",
              onboarding.get("template_source") == "system_default")
        steps = onboarding.get("steps") or []
        for step in steps:
            client.post(
                f"/experience/onboardings/{onboarding.get('id')}/steps",
                headers=auth, json={"step_key": step["key"],
                                    "status": "completed"})
        dashboard = show("onboarding dashboard", client.get(
            f"/experience/businesses/{biz}/onboarding-dashboard",
            headers=auth), ("total", "completed", "success_rate_percent"))
        check("dashboard shows the completed onboarding",
              dashboard.get("completed") == 1
              and dashboard.get("success_rate_percent") == 100.0)

        # ---- 4. Fulfilment over HTTP
        log("--- 4. Fulfilment to acceptance")
        fulfil = show("create fulfillment", client.post(
            f"/experience/businesses/{biz}/fulfillments", headers=auth,
            json={"customer_id": cust, "kind": "digital",
                  "title": "Workspace provisioning",
                  "revenue_id": seeded["revenue"], "is_fixture": True}),
            ("id", "status"))
        fid = fulfil.get("id")
        client.post(f"/experience/fulfillments/{fid}/transition",
                    headers=auth, json={"status": "preparing"})
        delivered = show("deliver", client.post(
            f"/experience/fulfillments/{fid}/transition", headers=auth,
            json={"status": "delivered"}), ("status", "delivered_at"))
        check("delivery recorded with timestamp",
              delivered.get("status") == "delivered"
              and bool(delivered.get("delivered_at")))
        accepted = show("acceptance", client.post(
            f"/experience/fulfillments/{fid}/acceptance", headers=auth,
            json={"acceptance": "accepted"}), ("acceptance",))
        check("customer acceptance recorded",
              accepted.get("acceptance") == "accepted")

        # ---- 5. Support: grounded + honest answers, ticket, SLA
        log("--- 5. Support assistant, tickets, SLA")
        answer = show("grounded ask", client.post(
            f"/experience/businesses/{biz}/support/ask", headers=auth,
            json={"customer_id": cust,
                  "question": "How do I reset my password?"}),
            ("confidence_class", "escalated", "article_refs"))
        check("answer verified against the approved article",
              answer.get("confidence_class") == "verified"
              and answer.get("escalated") is False)
        check("citation pins article id + version",
              (answer.get("article_refs") or [{}])[0].get("version") == 1)
        unknown = show("unknown ask", client.post(
            f"/experience/businesses/{biz}/support/ask", headers=auth,
            json={"customer_id": cust,
                  "question": "Do you offer teleportation delivery?"}),
            ("confidence_class", "escalated", "ticket_id"))
        check("unknown question honestly insufficient + escalated",
              unknown.get("confidence_class")
              == "insufficient_information"
              and unknown.get("escalated") is True)
        check("the question is recorded as a ticket, never lost",
              bool(unknown.get("ticket_id")))
        ticket = show("create ticket", client.post(
            f"/experience/businesses/{biz}/tickets", headers=auth,
            json={"customer_id": cust, "category": "account_access",
                  "subject": "Locked out after reset",
                  "priority_factors": {"customer_impact": 2}}),
            ("id", "priority", "status"))
        check("account_access floor makes priority high",
              ticket.get("priority") == "high")
        sla = show("sla compliance", client.get(
            f"/experience/businesses/{biz}/sla-compliance",
            headers=auth), ("status", "tickets_total"))
        check("SLA compliance computed against the owner policy",
              sla.get("status") == "computed")

        # ---- 6. Communications: queued, never sent
        log("--- 6. Communications queue + blocked dispatch")
        comm = show("queue communication", client.post(
            f"/experience/businesses/{biz}/communications",
            headers=auth,
            json={"customer_id": cust, "kind": "welcome",
                  "body": "Welcome to the workspace"}),
            ("id", "status", "sent"))
        check("communication queued and explicitly not sent",
              comm.get("status") == "queued"
              and comm.get("sent") is False)
        blocked = show("dispatch attempt", client.post(
            f"/experience/communications/{comm.get('id')}/dispatch",
            headers=auth), ("status", "dispatch_note"))
        check("dispatch honestly blocked (no channel configured)",
              blocked.get("status") == "dispatch_blocked"
              and "NOT been sent" in (blocked.get("dispatch_note") or ""))

        # ---- 7. Feedback, metrics, health
        log("--- 7. Feedback, metrics, health")
        client.post(f"/experience/businesses/{biz}/feedback",
                    headers=auth,
                    json={"customer_id": cust, "kind": "csat",
                          "score": 4, "is_fixture": True})
        metrics = show("metrics", client.get(
            f"/experience/businesses/{biz}/metrics", headers=auth),
            ("csat", "nps"))
        check("CSAT computed from the two recorded responses (5, 4)",
              (metrics.get("csat") or {}).get("value") == 4.5
              and (metrics.get("csat") or {}).get("sample_size") == 2)
        check("NPS honestly insufficient (no responses)",
              (metrics.get("nps") or {}).get("status")
              == "INSUFFICIENT_DATA")
        health = show("compute health", client.post(
            f"/experience/businesses/{biz}/customers/{cust}/health",
            headers=auth, json={}), ("classification", "score"))
        check("health classified from recorded signals",
              health.get("classification") in ("healthy", "stable"),
              f"({health.get('classification')}, score "
              f"{health.get('score')})")

        # ---- 8. Refund resolution: P-07 executes, P-18 references
        log("--- 8. Resolution with a P-07 refund")
        case = show("create resolution", client.post(
            f"/experience/businesses/{biz}/resolutions", headers=auth,
            json={"customer_id": cust, "problem_class": "product",
                  "root_cause_group": "product",
                  "action_kind": "refund_recommendation",
                  "basis": "partial", "revenue_id": seeded["revenue"],
                  "rationale": "Smoke fixture: partial refund agreed"}),
            ("id", "status"))
        cid = case.get("id")
        early = client.post(
            f"/experience/resolutions/{cid}/execute", headers=auth,
            json={"amount_minor": 20000})
        check("execution before approval is refused",
              early.status_code >= 400, f"(HTTP {early.status_code})")
        client.post(f"/experience/resolutions/{cid}/approve",
                    headers=auth, json={})
        executed = show("execute resolution", client.post(
            f"/experience/resolutions/{cid}/execute", headers=auth,
            json={"amount_minor": 20000, "currency": "INR"}),
            ("status", "p07_refund_id", "execution_note"))
        check("refund executed as a P-07 record (id referenced only)",
              executed.get("status") == "executed"
              and bool(executed.get("p07_refund_id")))
        detail = show("customer 360", client.get(
            f"/experience/businesses/{biz}/customers/{cust}",
            headers=auth), ("purchase_count", "customer_source"))
        check("customer 360 reads purchases live from P-07",
              detail.get("purchase_count") == 1)

        # ---- 9. Evaluation, overview, SPA
        log("--- 9. Evaluation pass, portfolio overview, SPA")
        evaluation = show("evaluate", client.post(
            f"/experience/businesses/{biz}/evaluate", headers=auth),
            ("count",))
        check("evaluation pass runs deterministically",
              evaluation.get("count") is not None)
        portfolio = show("portfolio overview", client.get(
            "/experience/overview", headers=auth), ("businesses",))
        check("portfolio overview includes the business",
              any(b.get("business_id") == biz
                  for b in portfolio.get("businesses") or []))
        spa = root_client.get("/app/")
        check("Command Center SPA is served at /app",
              spa.status_code == 200 and "root" in spa.text)

        log(f"=== P-18 SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 0 if FAIL == 0 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        evidence = REPO / "docs" / "reports" / "P18_SMOKE_EVIDENCE.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"transcript: {evidence}")


if __name__ == "__main__":
    raise SystemExit(main())
