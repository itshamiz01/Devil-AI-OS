"""P-17 live smoke: boots the real application under uvicorn
(which also serves the built Command Center at /app, now including
the Acquisition & Growth section) against a throwaway
auto-migrated database seeded in-process through governed paths,
and drives the P-17 surface over HTTP. Run:

    .venv/bin/python scripts/p17_smoke.py

Writes a transcript to docs/reports/P17_SMOKE_EVIDENCE.txt
(relative to the repository root).

The story: a profitable fixture business runs the full acquisition
lifecycle — brand, persona, ICP, channel, strategy, campaign,
P-07 spend through a prepared spending request, channel-tagged
verified revenue, leads, conversion — and every figure the API
returns is P-07's: spend is recorded expense, attributed revenue
is verified collected revenue by channel tag, CAC divides real
spend by real conversions. A second, heavily loss-making fixture
business then closes the owner's P-16 profitability gate, and the
smoke proves an expansion campaign approval is refused live —
until the owner records a per-item override with a reason.
Communications queue but dispatch is honestly blocked; a
purchased-list lead and a deceptive template are refused.
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
    """Governed fixture lifecycle in-process: one profitable
    business runs acquisition end to end; a big loss-maker is added
    last so the P-16 gate is CLOSED when the HTTP phase starts."""
    from app.core.application import Application
    from app.core.config import Settings
    from tests.conftest import OWNER
    from tests.p17_support import (
        customer_revenue, lead_payload, marketing_expense,
        profitable_business,
    )
    from tests.p07_support import paid_expense, verified_revenue

    settings = Settings(
        environment="test", mode="controlled",
        data_dir=tmp / "data",
        database_url=f"sqlite:///{tmp}/smoke.db",
        admin_password="<MASKED_SECRET_001>",
        dev_token="smoke-dev-token", service_token="smoke-service-token",
        log_file=str(tmp / "logs" / "seed.log"),
        auto_migrate=True, block_nonessential_on_threshold=False,
        retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.05)
    app = Application(settings)
    await app.startup()
    try:
        svc = app.growth
        winner = await profitable_business(
            app, name="Smoke Winner (fixture)", revenue="20000.00",
            expense="3000.00", opening="8000.00")
        svc.set_brand_profile(OWNER, winner, {
            "brand_name": "Smoke Winner", "tone_of_voice": "direct",
            "prohibited_claims": ["guaranteed results"]})
        svc.create_persona(OWNER, winner, {
            "segment": "fitness beginners",
            "budget_sensitivity": "medium",
            "evidence": [{"kind": "hypothesis",
                          "note": "seeded for the smoke"}]})
        svc.create_icp(OWNER, winner, {
            "kind": "b2c", "segment": "beginners 25-40",
            "factor_scores": {"product_fit": 90, "demand": 85,
                              "commercial_potential": 90}})
        svc.create_channel_evaluation(OWNER, winner, {
            "channel_key": "seo", "status": "recommended",
            "factor_scores": {"audience_fit": 90, "economics": 95}})
        strategy = svc.create_strategy(OWNER, winner, {
            "title": "Organic content engine", "kind": "improve",
            "approach": "content",
            "sections": {"objectives": "first customers"}})
        svc.decide_strategy(OWNER, strategy["id"], "approve")
        campaign = svc.create_campaign(OWNER, winner, {
            "name": "Beginner Guide Launch", "purpose": "acquisition",
            "channel_key": "seo", "budget_ceiling_minor": 300000,
            "expected_results": {"max_cac_minor": 25000}})
        svc.approve_campaign(OWNER, campaign["id"])
        svc.transition_campaign(OWNER, campaign["id"], "active")
        svc.prepare_spend_request(OWNER, campaign["id"],
                                  {"amount_minor": 120000})
        await marketing_expense(app, winner, "1200.00",
                                campaign_id=campaign["id"])
        await verified_revenue(app, winner, "4500.00",
                               channel="p17-beginner-guide-launch")
        lead_ids = []
        for idx in range(3):
            lead = svc.create_lead(OWNER, winner, lead_payload(
                contact={"email": f"smoke{idx}@example.com",
                         "name": f"Smoke User {idx}"},
                campaign_id=campaign["id"]))
            lead_ids.append(lead["id"])
        svc.transition_lead(OWNER, lead_ids[0], "converted")
        customer = svc.convert_lead(OWNER, lead_ids[0])
        await customer_revenue(app, winner, "999.00",
                               customer_ref=customer["p07_customer_ref"],
                               channel="p17-beginner-guide-launch")
        svc.record_funnel_event(OWNER, winner, {
            "stage": "awareness", "count": 1000, "source": "declared",
            "period_start": "2026-11-01", "period_end": "2026-11-07"})
        # the loss-maker that closes the gate for the HTTP phase
        from tests.p16_support import lossmaking_business
        loser = await lossmaking_business(
            app, name="Smoke Loser (fixture)", revenue="1000.00",
            expense="30000.00")
        return {"winner": winner, "loser": loser,
                "campaign": campaign["id"], "lead": lead_ids[1],
                "customer": customer["id"]}
    finally:
        await app.shutdown()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p17-smoke-"))
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
        # Liveness is not readiness: this uvicorn serves requests
        # while the lifespan startup is still running, and a login
        # landing in that window is refused (observed repeatedly
        # during this build; the identical credentials succeed once
        # startup completes). /health/ready only returns 200 when
        # the lifecycle reaches ready/degraded at the END of
        # startup, so gate on it (service-token authorised) before
        # authenticating.
        service_auth = {"Authorization": "Bearer smoke-service-token"}
        for _ in range(120):
            try:
                if client.get("/health/ready",
                              headers=service_auth).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("=== AUTONOMUS P-17 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        log(f"seeded: {seeded}")
        winner = seeded["winner"]
        campaign_id = seeded["campaign"]

        # ---- 1. Auth boundary + schema
        log("--- 1. Auth boundary, schema")
        unauth = client.get("/growth/status")
        check("growth status requires auth (401)",
              unauth.status_code == 401)
        conn = sqlite3.connect(str(tmp / "smoke.db"))
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        check("auto-migrated schema has 209 tables (208 + alembic_version)",
              tables == 209, f"(got {tables})")

        login = client.post("/auth/login", json={
            "username": "owner",
            "password": "smoke-owner-password-123"})
        # Login can transiently refuse the CORRECT credentials in
        # the first seconds after a fresh boot in this environment
        # (probed during this build: the stored hash and password
        # are correct and verify True in any other process, while
        # the booted server's scrypt verify returns False for a
        # short, load-dependent window, then flips to True). Retry
        # patiently — spaced out so the P-10 login guard's
        # throttle is not tripped by the retries themselves — and
        # log the attempt count with the result.
        attempts = 1
        while login.status_code != 200 and attempts < 6:
            time.sleep(5)
            attempts += 1
            login = client.post("/auth/login", json={
                "username": "owner",
                "password": "<MASKED_SECRET_001>"})
        log(f"[login attempts] {attempts}")
        token = (login.json().get("data") or {}).get("access_token")
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)"
            if token else
            f"[login] HTTP {login.status_code} FAILED: "
            f"{login.text[:300]}")

        # ---- 2. Status: gate closed by the loss-maker; honest surface
        log("--- 2. Engine status, gate, roles, integrations")
        status = show("growth status", client.get(
            "/growth/status", headers=auth),
            ("autonomy_level", "profitability_gate", "counts"))
        gate = status.get("profitability_gate") or {}
        check("profitability gate CLOSED (aggregate profit negative)",
              gate.get("state") == "closed", f"({gate.get('reason')})")
        check("counts show the seeded lifecycle",
              (status.get("counts") or {}).get("leads") == 3
              and (status.get("counts") or {}).get("customers") == 1)
        roles = show("agent roles", client.get(
            "/growth/agent-roles", headers=auth), ("count",))
        check("17 §12 agent roles seeded as P-04 templates",
              roles.get("count") == 17)
        integrations = show("integrations", client.get(
            "/growth/integrations", headers=auth), ("note",))
        check("every integration honestly not_configured",
              all(i.get("state") == "not_configured"
                  for i in integrations.get("items") or []))

        # ---- 3. The lifecycle figures are P-07's
        log("--- 3. Campaign metrics / budget / attribution from P-07")
        metrics = show("campaign metrics", client.get(
            f"/growth/campaigns/{campaign_id}/metrics", headers=auth),
            ("spend", "attributed_revenue_minor", "cac"))
        check("campaign spend is the recorded P-07 expense (₹1,200)",
              (metrics.get("spend") or {}).get("actual_spend_minor")
              == 120000)
        check("attributed revenue is P-07 verified by channel tag (₹5,499)",
              metrics.get("attributed_revenue_minor") == 549900)
        check("CAC computed from real spend / real conversions",
              (metrics.get("cac") or {}).get("cac_minor") == 120000)
        budget = show("budget view", client.get(
            f"/growth/businesses/{winner}/budget", headers=auth),
            ("total_ceiling_minor", "actual_spend"))
        check("ceiling (proposal) kept distinct from actual spend",
              budget.get("total_ceiling_minor") == 300000
              and (budget.get("actual_spend") or {}).get(
                  "actual_spend_minor") == 120000)
        attribution = show("attribution", client.get(
            f"/growth/businesses/{winner}/attribution", headers=auth),
            ("methods",))
        check("multi-touch honestly not_available",
              ((attribution.get("methods") or {}).get("multi_touch")
               or {}).get("status") == "not_available")
        funnel = show("funnel", client.get(
            f"/growth/businesses/{winner}/funnel", headers=auth),
            ("declared_counts", "system_counts"))
        check("declared funnel counts kept distinct from system counts",
              (funnel.get("declared_counts") or {}).get("awareness")
              == 1000
              and (funnel.get("system_counts") or {}).get(
                  "leads_recorded") == 3)
        overview = show("growth overview", client.get(
            "/growth/overview", headers=auth), ("totals",))
        totals = overview.get("totals") or {}
        check("overview totals are P-07 figures",
              totals.get("spend_minor") == 120000
              and totals.get("attributed_revenue_minor") == 549900
              and totals.get("customers") == 1)

        # ---- 4. The gate refuses expansion live; override is per-item
        log("--- 4. Profitability gate enforcement over HTTP")
        expansion = show("expansion campaign", client.post(
            "/growth/businesses/" + winner + "/campaigns",
            headers=auth, json={
                "name": "Paid Expansion Push", "purpose": "expansion",
                "channel_key": "search_ads",
                "budget_ceiling_minor": 100000}), ("id", "status"))
        refused = client.post(
            f"/growth/campaigns/{expansion.get('id')}/approve",
            headers=auth, json={})
        check("expansion approval REFUSED while the gate is closed",
              refused.status_code in (400, 422)
              and "profitability gate" in refused.text,
              f"(HTTP {refused.status_code})")
        overridden = show("override approval", client.post(
            f"/growth/campaigns/{expansion.get('id')}/approve",
            headers=auth, json={
                "gate_override_reason":
                    "smoke: owner accepts a bounded test"}),
            ("status", "gate_override"))
        check("per-item owner override with a recorded reason approves",
              overridden.get("status") == "approved"
              and (overridden.get("gate_override") or {}).get(
                  "reason", "").startswith("smoke: owner accepts"))

        # ---- 5. Lead + template discipline; dispatch honestly blocked
        log("--- 5. Communications discipline")
        bad_lead = client.post(
            f"/growth/businesses/{winner}/leads", headers=auth, json={
                "source": "purchased_list",
                "contact": {"email": "bought@example.com"},
                "consent_status": "granted"})
        check("purchased-list lead refused", bad_lead.status_code
              in (400, 422), f"(HTTP {bad_lead.status_code})")
        bad_template = client.post("/growth/templates", headers=auth,
                                   json={
                                       "name": "Pushy",
                                       "kind": "sales_outreach",
                                       "business_id": winner,
                                       "subject": "Act now or lose it",
                                       "body": "Guaranteed results!"})
        check("deceptive template refused",
              bad_template.status_code in (400, 422),
              f"(HTTP {bad_template.status_code})")
        template = show("template", client.post(
            "/growth/templates", headers=auth, json={
                "name": "Welcome", "kind": "welcome",
                "business_id": winner, "subject": "Welcome",
                "body": "Thanks for your interest."}), ("id",))
        queued = show("queued message", client.post(
            "/growth/communications", headers=auth, json={
                "template_id": template.get("id"),
                "lead_id": seeded["lead"]}), ("status", "dispatch_note"))
        check("message queues with the blocked-dispatch note attached",
              queued.get("status") == "queued"
              and "no email/SMS/social transport" in (
                  queued.get("dispatch_note") or ""))
        messages = show("message list", client.get(
            f"/growth/businesses/{winner}/communications",
            headers=auth), ("count",))
        message_id = (messages.get("items") or [{}])[0].get("id")
        dispatched = show("dispatch attempt", client.post(
            f"/growth/communications/{message_id}/dispatch",
            headers=auth), ("status", "dispatched"))
        check("dispatch is honestly blocked, never 'sent'",
              dispatched.get("dispatched") is False
              and dispatched.get("status") == "dispatch_blocked")

        # ---- 6. Content brand block + the SPA
        log("--- 6. Content brand check; Command Center")
        content = show("content", client.post(
            f"/growth/businesses/{winner}/content", headers=auth,
            json={"kind": "landing_copy", "title": "Landing",
                  "body": "Get guaranteed results fast!"}), ("id",))
        review = show("brand review", client.post(
            f"/growth/content/{content.get('id')}/review",
            headers=auth, json={"section": "brand_consistency",
                                "status": "pass"}),
            ("brand_check",))
        check("brand pass mechanically refused for a prohibited claim",
              review.get("brand_check") == "failed_mechanically")
        spa = root_client.get("/app/")
        check("Command Center SPA is served at /app",
              spa.status_code == 200 and "root" in spa.text)
        recs = show("recommendations", client.get(
            "/growth/recommendations", headers=auth), ("count",))
        expansion_recs = [r for r in recs.get("items") or []
                          if r.get("kind") == "expansion"]
        check("recommendations hold expansion behind the gate",
              bool(expansion_recs)
              and expansion_recs[0].get("gate_blocked") is True)

        log(f"=== P-17 SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 0 if FAIL == 0 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        evidence = REPO / "docs" / "reports" / "P17_SMOKE_EVIDENCE.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"transcript: {evidence}")


if __name__ == "__main__":
    raise SystemExit(main())
