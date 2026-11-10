"""P-14 Stage B (DEF-A7) — seeded-volume performance baseline.

Seeds a scratch staging database with labelled benchmark data
(100 businesses, 10,000 journal entries with 20,000 lines, 10,000
memory records — inserted directly as ORM rows, NOT produced by the
governed workflows; this measures read-path behaviour at volume, not
workflow throughput), then times the representative read paths.

Run:  PYTHONPATH=backend backend/.venv/bin/python \
          scripts/p14_volume_benchmark.py
Output: docs/p14/P14_BENCHMARK_RESULTS.json + a printed summary.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import insert, select  # noqa: E402

from app.core.application import Application  # noqa: E402
from app.dashboard.service import DashboardService  # noqa: E402
from app.database.models.business import Business, BusinessTemplate  # noqa: E402
from app.database.models.financial import (  # noqa: E402
    FinancialAccount, JournalEntry, JournalLine)
from app.database.models.memory import MemoryRecord  # noqa: E402
from app.database.models.opportunities import Opportunity  # noqa: E402
from app.permissions.models import Principal, PrincipalType  # noqa: E402
from tests.conftest import make_settings  # noqa: E402

OWNER = Principal(PrincipalType.OWNER, "owner")
N_BUSINESSES = 100
N_JOURNAL = 10_000
N_MEMORY = 10_000


def _uuid() -> str:
    return str(uuid.uuid4())


def seed(application) -> dict:
    session = application.session_factory()
    try:
        template_id = session.scalar(select(BusinessTemplate.id).limit(1))
        assert template_id, "no business template seeded by startup"
        opps, businesses = [], []
        for i in range(N_BUSINESSES):
            oid, bid = _uuid(), _uuid()
            opps.append({"id": oid, "name": f"Benchmark opportunity {i}",
                         "slug": f"benchmark-opp-{i}",
                         "category": "digital_products"})
            businesses.append({
                "id": bid, "opportunity_id": oid,
                "name": f"Benchmark business {i}",
                "slug": f"benchmark-business-{i}",
                "category": "digital_products", "template_id": template_id,
                "template_version": 1, "status": "OPERATING",
                "validation_level_at_creation": 3,
                "eligibility_decision": "ELIGIBLE", "is_fixture": True,
                "created_by": "benchmark"})
        session.execute(insert(Opportunity), opps)
        session.execute(insert(Business), businesses)
        acct_a, acct_b = _uuid(), _uuid()
        session.execute(insert(FinancialAccount), [
            {"id": acct_a, "business_id": businesses[0]["id"],
             "code": "1000", "name": "Benchmark cash",
             "account_type": "asset", "currency": "INR",
             "created_by": "benchmark"},
            {"id": acct_b, "business_id": businesses[0]["id"],
             "code": "4000", "name": "Benchmark revenue",
             "account_type": "revenue", "currency": "INR",
             "created_by": "benchmark"}])
        session.commit()

        entries, lines = [], []
        for i in range(N_JOURNAL):
            eid = _uuid()
            entries.append({
                "id": eid, "business_id": businesses[i % N_BUSINESSES]["id"],
                "entry_date": "2026-11-01", "description": f"benchmark {i}",
                "source_type": "manual", "kind": "standard",
                "idempotency_key": f"benchmark-{i}",
                "posted_by": "benchmark"})
            lines.append({"id": _uuid(), "entry_id": eid,
                          "account_id": acct_a, "debit_minor": 100,
                          "credit_minor": 0, "currency": "INR"})
            lines.append({"id": _uuid(), "entry_id": eid,
                          "account_id": acct_b, "debit_minor": 0,
                          "credit_minor": 100, "currency": "INR"})
            if len(entries) >= 2000:
                session.execute(insert(JournalEntry), entries)
                session.execute(insert(JournalLine), lines)
                session.commit()
                entries, lines = [], []
        if entries:
            session.execute(insert(JournalEntry), entries)
            session.execute(insert(JournalLine), lines)
            session.commit()

        records = []
        for i in range(N_MEMORY):
            content = ("Benchmark knowledge record about deployment "
                       f"runbooks and system health checks, item {i}.")
            records.append({
                "id": _uuid(), "layer": "semantic",
                "category": "TECHNICAL_KNOWLEDGE",
                "title": f"Benchmark record {i}",
                "content": content,
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                "subject": "deployment", "predicate": "procedure",
                "truth_class": "user_provided", "status": "active",
                "confidence": "medium", "source_type": "user_input",
                "access_scope": "ORGANIZATION_SHARED",
                "created_by": "benchmark"})
            if len(records) >= 2000:
                session.execute(insert(MemoryRecord), records)
                session.commit()
                records = []
        if records:
            session.execute(insert(MemoryRecord), records)
            session.commit()
        return {"businesses": N_BUSINESSES, "journal_entries": N_JOURNAL,
                "journal_lines": 2 * N_JOURNAL, "memory_records": N_MEMORY}
    finally:
        session.close()


def timed(fn, runs: int = 3) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(samples), 2)


async def timed_async(fn, runs: int = 3) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(samples), 2)


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="p14-bench-"))
    app = Application(make_settings(tmp, mode="controlled"))
    await app.startup()
    try:
        t0 = time.perf_counter()
        volumes = seed(app)
        seed_seconds = round(time.perf_counter() - t0, 2)

        dash = DashboardService(app)

        def journal_page():
            session = app.session_factory()
            try:
                return session.execute(
                    select(JournalEntry)
                    .order_by(JournalEntry.entry_date.desc())
                    .limit(50)).scalars().all()
            finally:
                session.close()

        results = {
            "volumes": volumes,
            "seed_seconds": seed_seconds,
            "timings_ms_median_of_3": {
                "dashboard_overview": timed(lambda: dash.overview()),
                "dashboard_system_health": await timed_async(dash.system_health),
                "financial_consolidated": timed(
                    lambda: app.financial.consolidated("INR")),
                "business_list_page50": timed(
                    lambda: app.business.list_businesses(limit=50)),
                "memory_search": timed(lambda: app.memory.retrieval.search(
                    OWNER, query="deployment runbook", limit=10)),
                "journal_page_query_50": timed(journal_page),
            },
            "notes": [
                "Seed data inserted directly as ORM rows (labelled "
                "is_fixture where the model supports it); it measures "
                "read-path behaviour at volume, not workflow throughput.",
                "Memory rows bypass the ingestion/vector path, so the "
                "semantic candidate set is empty; the timed search "
                "exercises the governed keyword/scan path over the "
                "record table.",
                "SQLite on Linux staging (this VM); Windows numbers "
                "remain an owner-machine activity (DEF-A1).",
            ],
        }
        out = (Path(__file__).resolve().parents[1]
               / "docs" / "p14" / "P14_BENCHMARK_RESULTS.json")
        out.write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
        print(f"\nwrote {out}")
    finally:
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
