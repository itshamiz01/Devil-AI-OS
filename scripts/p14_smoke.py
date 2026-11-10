#!/usr/bin/env python
"""P-14 Stage B live smoke — real uvicorn over HTTP.

Seeds a scratch database in-process (labelled FIXTURE data through the
real services: two portfolio businesses with verified collected
revenue, one P-10 security incident), then boots the real server
against the same data directory and asserts the repaired paths over
HTTP:

- DEF-F1: portfolio finance gross collected == net collected
  (the P-13 smoke showed gross 0; Stage B must show the true gross).
- DEF-I1/I2: the security incident's SecurityIncidentDetected event
  is persisted and listable with the full §6 envelope fields.
- DEF-I3: financial events are persisted (revenue/journal activity
  from seeding is visible through the events API).
- DEF-A3: /dashboard/system-health returns resources, per-module
  health and the dead-letter count.
- DEF-A5: the ai_provider health check is present in system health.
- The built Command Center is served at /app and its bundle carries
  the Stage B System-health surface ("Resource utilization").
- Schema carries the Stage B migration's table (event_dead_letters
  among the 172 model tables).

Writes docs/p14/P14_SMOKE_EVIDENCE.txt. Exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tests.conftest import OWNER, make_settings  # noqa: E402
from tests.p13_support import business_with_collected, make_portfolio  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), label))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} {detail}")


def req(method: str, url: str, token: str | None = None,
        body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if data:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


async def seed(settings) -> dict:
    from app.core.application import Application

    app = Application(settings)
    await app.startup()
    try:
        a = await business_with_collected(
            app, name="P14 Smoke Alpha", amount="9000.00")
        b = await business_with_collected(
            app, name="P14 Smoke Beta", amount="1000.00")
        portfolio = await make_portfolio(app, business_ids=[a, b])
        incident = app.security.create_incident(OWNER, {
            "title": "P14 smoke probe incident",
            "category": "access", "severity": "high",
            "description": "Smoke-seeded incident (fixture) proving the "
                           "SecurityIncidentDetected event path.",
            "related_ref": a})
        return {"portfolio_id": portfolio["id"],
                "incident_id": incident["id"]}
    finally:
        await app.shutdown()


def main() -> int:
    print("=== AUTONOMUS P-14 STAGE B SMOKE (real uvicorn, "
          "controlled mode) ===")
    scratch = ROOT / ".tmp" / f"p14-smoke-{int(time.time())}"
    settings = make_settings(scratch / "data", mode="controlled")
    seeded = asyncio.run(seed(settings))

    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    tables = conn.execute("SELECT COUNT(*) FROM sqlite_master "
                          "WHERE type='table'").fetchone()[0]
    has_dead_letters = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name='event_dead_letters'").fetchone()[0] == 1
    conn.close()

    from app.main import create_app
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(
        create_app(settings), host="127.0.0.1", port=port,
        log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}/api/v1"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    print(f"server: {base}  data_dir: {settings.data_dir}")

    try:
        print("--- 1. Boundaries and schema")
        status, _ = req("GET", f"{base}/portfolio/portfolios")
        check(status == 401, "portfolio list requires auth (401)",
              f"(got {status})")
        check(tables == 172 and has_dead_letters,
              "schema has the 172 model tables incl. event_dead_letters "
              "(Stage B migration table, DEF-I4)",
              f"(got {tables}, dead_letters={has_dead_letters})")
        status, login = req("POST", f"{base}/auth/login", body={
            "username": settings.admin_username,
            "password": settings.admin_password})
        token = (login or {}).get("data", {}).get("access_token") \
            if isinstance(login, dict) else None
        check(status == 200 and token, "owner login over HTTP",
              f"(HTTP {status})")

        print("--- 2. DEF-F1: portfolio finance gross is true")
        status, fin = req(
            "GET",
            f"{base}/portfolio/portfolios/{seeded['portfolio_id']}/finance",
            token=token)
        totals = (fin or {}).get("data", {}).get("totals", {})
        print(f"[finance] HTTP {status} -> {json.dumps(totals)[:220]}")
        check(status == 200
              and totals.get("collected_minor") == 1000000
              and totals.get("net_collected_minor") == 1000000,
              "gross collected == net collected == ₹10,000 "
              "(P-13 smoke showed gross 0)",
              f"(got gross={totals.get('collected_minor')}, "
              f"net={totals.get('net_collected_minor')})")

        print("--- 3. DEF-I1/I2/I3: events persisted with envelope")
        status, ev = req(
            "GET",
            f"{base}/events?event_type=SecurityIncidentDetected",
            token=token)
        rows = (ev or {}).get("data", []) if isinstance(ev, dict) else []
        if isinstance(rows, dict):
            rows = rows.get("events", [])
        check(status == 200 and len(rows) >= 1,
              "SecurityIncidentDetected persisted and listable",
              f"(got {len(rows)} rows)")
        if rows:
            row = rows[0]
            check(all(k in row for k in (
                "business_id", "workflow_id", "processing_status",
                "correlation_id", "created_at")),
                "event row carries the §6 envelope fields",
                f"(keys: {sorted(row.keys())[:8]}...)")
        status, fev = req("GET", f"{base}/events", token=token)
        frows = (fev or {}).get("data", []) if isinstance(fev, dict) else []
        if isinstance(frows, dict):
            frows = frows.get("events", [])
        fin_types = {r.get("event_type") for r in frows}
        check(any(t and ("Revenue" in t or "Journal" in t)
                  for t in fin_types),
              "financial events persisted (journal/revenue activity)",
              f"(types seen: {sorted(t for t in fin_types if t)[:6]})")

        print("--- 4. DEF-A3/A5: system health surface")
        status, health = req("GET", f"{base}/dashboard/system-health",
                             token=token)
        hdata = (health or {}).get("data", {}) \
            if isinstance(health, dict) else {}
        check(status == 200 and "resources" in hdata
              and "cpu_percent" in hdata.get("resources", {}),
              "system-health returns resource utilisation (A3)")
        mods = {m.get("module") for m in hdata.get("modules", [])}
        check("P-01" in mods and len(mods) >= 3,
              "system-health derives per-module health (A3)",
              f"(modules: {sorted(m for m in mods if m)})")
        check("event_dead_letters" in hdata,
              "system-health exposes the dead-letter count (A3/I4)")
        checks = {c.get("key"): c for c in hdata.get("checks", [])}
        check("ai_provider" in checks,
              "ai_provider probe check present (A5)",
              f"(state={checks.get('ai_provider', {}).get('state')})")

        print("--- 5. Built Command Center at /app")
        status, html = req("GET", f"http://127.0.0.1:{port}/app/")
        check(status == 200 and isinstance(html, str)
              and "<div id=\"root\">" in html,
              "GET /app serves the built frontend")
        asset = re.search(r"(?:\./|/app/)(assets/[^\"]+\.js)",
                          html if isinstance(html, str) else "")
        if asset:
            status, bundle = req(
                "GET", f"http://127.0.0.1:{port}/app/{asset.group(1)}")
            check(status == 200 and isinstance(bundle, str)
                  and "Resource utilization" in bundle,
                  "served bundle carries the Stage B System-health "
                  "surface (A3)")
        else:
            check(False, "frontend bundle asset referenced from /app")
    finally:
        server.should_exit = True
        thread.join(timeout=15)

    passed = sum(1 for ok, _ in RESULTS if ok)
    line = f"=== SMOKE RESULT: {passed} passed, " \
           f"{len(RESULTS) - passed} failed ==="
    print(line)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
