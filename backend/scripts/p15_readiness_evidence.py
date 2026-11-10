"""P-15 readiness evidence run: boot a fresh controlled-mode app
in-process, record a sample, create a verified backup through the
P-15 delegation, run the benchmark suite, compute the readiness
score from live evidence, and dump the result as JSON for the
P-15 production readiness report. Throwaway data directory."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


async def main() -> int:
    from app.core.application import Application
    from app.permissions.models import Principal, PrincipalType
    from tests.conftest import make_settings

    owner = Principal(PrincipalType.OWNER, "owner")
    tmp = Path(tempfile.mkdtemp(prefix="p15-evidence-"))
    app = Application(make_settings(tmp, mode="controlled"))
    await app.startup()
    try:
        svc = app.reliability
        svc.record_sample(source="manual")
        svc.evaluate_incidents()
        backup = svc.create_backup(owner)
        svc.evaluate_incidents()
        run = await svc.run_benchmark(owner)
        readiness = await svc.compute_readiness()
        evidence = {
            "context": "fresh controlled-mode staging app, in-process; "
                       "one manual sample, one verified P-10 backup, "
                       "one baseline benchmark run, then readiness "
                       "computed from live evidence",
            "backup_verification": backup["verification"],
            "benchmark": {"status": run["status"],
                          "results": run["results"]},
            "readiness": {k: readiness[k] for k in (
                "overall_score", "band", "classification",
                "critical_gate_ok", "categories", "failed_checks",
                "blockers", "recommendations")},
            "incidents_after_evaluation": svc.incident_summary(),
            "stability": svc.stability_report(),
        }
        out = BACKEND.parent / "docs" / "p15" / "P15_READINESS_EVIDENCE.json"
        out.write_text(json.dumps(evidence, indent=2, default=str),
                       encoding="utf-8")
        print(f"score={readiness['overall_score']} band={readiness['band']}")
        print(f"classification={readiness['classification']}")
        print(f"gate_ok={readiness['critical_gate_ok']}")
        for key, cat in readiness["categories"].items():
            print(f"  {key}: {cat['score']} (failed: {cat['failed_checks']})")
        print(f"evidence written to {out}")
        return 0
    finally:
        await app.shutdown()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
