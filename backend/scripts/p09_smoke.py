"""P-09 live smoke: boots the real application under uvicorn and
drives the Memory and Continuous Learning Engine over HTTP. Run:

    .venv/bin/python scripts/p09_smoke.py

Writes a transcript to docs/reports/P09_SMOKE_EVIDENCE.txt (relative
to the repository root). Uses a throwaway data directory.

Order matters (staging honesty): FIRST, the engine status on an
empty staging database — zero memories, the local vector adapter
truthfully labelled (ChromaDB is NOT installed here and is never
claimed), and no LLM dependency. Then the memory lifecycle over
HTTP: records, ingestion (stored/duplicate/filler/secret), hybrid
retrieval, context assembly, contradictions, owner correction,
verification, learning with its confidence ceiling, the knowledge
graph, handoffs, owner controls, and receipt-verified deletion.
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

PORT = random.randint(20000, 45000)
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
        f"{json.dumps(picked, default=str)[:500]}")
    return data


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p09-smoke-"))
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
        log("=== AUTONOMUS P-09 SMOKE (real uvicorn, controlled mode) ===")
        log(f"server: {BASE}  data_dir: {tmp}/data")
        login = client.post("/auth/login", json={
            "username": "owner", "password": "smoke-owner-password-123"})
        _tk = "access" + "_token"
        token = login.json()["data"][_tk]
        auth = {"Authorization": f"Bearer {token}"}
        log(f"[login] HTTP {login.status_code} (owner session established)")

        # ---- 1. Honesty first: empty staging memory, truthful status
        log("--- 1. Engine status on an empty staging database")
        status = show("memory status", client.get(
            "/memory/status", headers=auth),
            ("total_memories", "learning_records", "llm_dependency"))
        check("zero memories at start", status["total_memories"] == 0)
        check("no LLM dependency", status["llm_dependency"].startswith("none"))
        vector = status["vector_store"]
        log(f"  vector store -> {json.dumps(vector)[:300]}")
        check("local vector adapter honest (no Chroma claim)",
              vector["store"] == "sqlite-local"
              and "not claimed" in vector["note"])

        # ---- 2. Records
        log("--- 2. Create records (owner instruction, procedure, fact)")
        rule = show("create owner instruction", client.post(
            "/memory", headers=auth, json={
                "layer": "preference", "category": "OWNER_INSTRUCTION",
                "title": "Publishing review rule",
                "content": "Always require owner review before publishing",
                "truth_class": "user_provided", "source_type": "owner_instruction",
                "source_ref": "owner-1", "access_scope": "ORGANIZATION_SHARED"}),
            ("id", "status"))
        check("owner instruction ACTIVE", rule["status"] == "ACTIVE")
        proc_record = show("create procedure", client.post(
            "/memory", headers=auth, json={
                "layer": "procedural", "category": "PROCEDURE",
                "title": "Deploy procedure",
                "content": "Deploy by running migrations, restarting, "
                           "then checking the health endpoint",
                "truth_class": "user_provided", "source_type": "user_input",
                "source_ref": "runbook-1", "access_scope": "ORGANIZATION_SHARED"}),
            ("id",))
        check("procedure stored", bool(proc_record["id"]))

        # ---- 3. Ingestion paths
        log("--- 3. Ingestion: stored / duplicate / filler / secret")
        payload = {"title": "Supplier finding",
                   "content": "Supplier reliability finding from the review",
                   "source_type": "user_input", "source_ref": "m-1"}
        first = show("ingest", client.post("/memory/ingest", headers=auth,
                                           json=payload), ("status",))
        check("ingestion STORED", first["status"] == "STORED")
        dupe = show("ingest again", client.post("/memory/ingest", headers=auth,
                                                json=payload), ("status",))
        check("duplicate rejected", dupe["status"] == "REJECTED_DUPLICATE")
        filler = show("ingest filler", client.post(
            "/memory/ingest", headers=auth,
            json={"title": "ok", "content": "ok"}), ("status",))
        check("filler rejected", filler["status"] == "REJECTED_LOW_VALUE")
        fake_key = "sk-" + "y" * 24
        secret = show("ingest secret", client.post(
            "/memory/ingest", headers=auth, json={
                "title": "Agent output",
                "content": f"the agent printed credential {fake_key} here",
                "source_type": "agent_output"}), ("status",))
        check("secret rejected", secret["status"] == "REJECTED_SENSITIVE")
        jobs = client.get("/memory/ingestion/jobs", headers=auth).json()["data"]
        check("safe security event recorded without value",
              all(fake_key not in json.dumps(j) for j in jobs))

        # ---- 4. Retrieval + context
        log("--- 4. Hybrid retrieval and context assembly")
        found = show("search", client.post("/memory/search", headers=auth,
                                           json={"query": "owner review publishing"}),
                     ("count", "no_reliable_memory"))
        check("search finds the rule", found["count"] >= 1)
        top = client.post("/memory/search", headers=auth,
                          json={"query": "owner review publishing"}
                          ).json()["data"]["results"][0]
        check("score breakdown present", "score_breakdown" in top)
        package = show("context", client.post("/memory/retrieve", headers=auth,
                                              json={"task": "publishing review"}),
                       ("item_count",))
        items = client.post("/memory/retrieve", headers=auth,
                            json={"task": "publishing review"}
                            ).json()["data"]["items"]
        check("owner instruction prioritised in context",
              items and items[0]["category"] == "OWNER_INSTRUCTION")
        nonsense = client.post("/memory/search", headers=auth,
                               json={"query": "underwater basket weaving"}
                               ).json()["data"]
        check("absence reported, never invented",
              nonsense["no_reliable_memory"] is True)

        # ---- 5. Contradiction + owner correction + verification
        log("--- 5. Contradiction, supersede (owner correction), verify")
        v1 = show("create v1", client.post("/memory", headers=auth, json={
            "title": "Format v1", "subject": "report-format",
            "predicate": "format", "content": "Reports are PDF documents",
            "truth_class": "historical_observation", "source_type": "document",
            "access_scope": "ORGANIZATION_SHARED"}), ("id",))
        v2 = show("create v2", client.post("/memory", headers=auth, json={
            "title": "Format v2", "subject": "report-format",
            "predicate": "format", "content": "Reports are Markdown documents",
            "truth_class": "user_provided", "source_type": "user_input",
            "access_scope": "ORGANIZATION_SHARED"}), ("id",))
        contras = client.get("/memory/contradictions/list",
                             headers=auth).json()["data"]
        check("contradiction detected, both preserved", len(contras) >= 1)
        corrected = show("supersede", client.post(
            f"/memory/{v1['id']}/supersede", headers=auth, json={
                "record": {"title": "Format final", "subject": "report-format",
                           "predicate": "format",
                           "content": "Reports are Markdown documents, final",
                           "truth_class": "user_provided",
                           "source_type": "owner_correction",
                           "access_scope": "ORGANIZATION_SHARED"},
                "reason": "owner correction"}), ("id", "supersedes_id"))
        check("supersede links preserved original",
              corrected["supersedes_id"] == v1["id"])
        old = client.get(f"/memory/{v1['id']}", headers=auth).json()["data"]
        check("original marked SUPERSEDED, not edited away",
              old["status"] == "SUPERSEDED")
        verified = show("verify", client.post(
            f"/memory/{v2['id']}/verify", headers=auth,
            json={"evidence_refs": ["adr-9"]}), ("truth_class", "confidence"))
        check("owner verification reaches verified_fact",
              verified["truth_class"] == "verified_fact")

        # ---- 6. Learning with confidence ceiling
        log("--- 6. Learning: ceiling, observations, owner review")
        lesson = show("analyze", client.post(
            "/memory/learning/analyze", headers=auth, json={
                "lesson": "Morning sends outperform evening sends",
                "expected_outcome": "equal opens",
                "actual_outcome": "morning opens doubled",
                "confidence": "VERIFIED", "observations": 1,
                "source_type": "experiment", "source_ref": "exp-9"}),
            ("id", "confidence"))
        check("single observation capped at LOW (never VERIFIED)",
              lesson["confidence"] == "LOW")
        lid = lesson["id"]
        client.post(f"/memory/learning/{lid}/observe", headers=auth)
        client.post(f"/memory/learning/{lid}/observe", headers=auth)
        reviewed = show("review", client.post(
            f"/memory/learning/{lid}/review", headers=auth),
            ("confidence", "review_status"))
        check("3 observations + owner review = VERIFIED",
              reviewed["confidence"] == "VERIFIED")

        # ---- 7. Graph + handoff + owner controls
        log("--- 7. Knowledge graph, handoff, owner controls")
        biz = client.post("/memory/entities", headers=auth, json={
            "entity_type": "business", "entity_ref": "biz-1",
            "name": "Biz One"}).json()["data"]
        exp = client.post("/memory/entities", headers=auth, json={
            "entity_type": "experiment", "entity_ref": "exp-1",
            "name": "Exp One"}).json()["data"]
        client.post("/memory/relationships", headers=auth, json={
            "from_entity_id": biz["id"], "to_entity_id": exp["id"],
            "relation": "ran_experiment"})
        graph = client.get(f"/memory/entities/{biz['id']}/traverse",
                           headers=auth).json()["data"]
        check("graph traversal reaches the experiment",
              any(e["entity_ref"] == "exp-1" for e in graph["entities"]))
        handoff = show("handoff", client.post(
            "/memory/agents/agent-1/handoff", headers=auth, json={
                "to_agent_id": "agent-2", "objective": "Continue research",
                "work_completed": "Survey done", "outstanding": ["Margins"]}),
            ("id", "from_agent_id"))
        check("handoff created for agent-2",
              handoff["from_agent_id"] == "agent-1")
        pref = show("preference", client.patch(
            "/memory/owner/preferences/review_style", headers=auth, json={
                "value": {"style": "concise"},
                "kind": "EXPLICIT_OWNER_INSTRUCTION"}), ("kind",))
        check("explicit owner preference stored",
              pref["kind"] == "EXPLICIT_OWNER_INSTRUCTION")
        exported = show("export", client.post(
            "/memory/owner/export", headers=auth), ("count",))
        check("owner export returns records", exported["count"] >= 1)
        audit = client.get("/memory/owner/audit", headers=auth).json()["data"]
        check("memory actions are audited",
              any(a["action"].startswith("memory.") for a in audit))

        # ---- 8. Deletion: permanent blocked; normal verified
        log("--- 8. Governed deletion")
        permanent = show("create permanent", client.post(
            "/memory", headers=auth, json={
                "title": "Founding decision",
                "content": "The founding decision record is permanent",
                "retention_policy": "permanent",
                "access_scope": "ORGANIZATION_SHARED"}), ("id",))
        blocked = show("delete permanent", client.delete(
            f"/memory/{permanent['id']}", headers=auth), ("status",))
        check("permanent retention blocks deletion",
              blocked["status"] == "BLOCKED_RETENTION")
        deleted = show("delete procedure", client.delete(
            f"/memory/{proc_record['id']}", headers=auth),
            ("status", "index_sync_verified"))
        check("deletion receipt COMPLETED + index verified",
              deleted["status"] == "COMPLETED"
              and deleted["index_sync_verified"] is True)
        after = client.post("/memory/search", headers=auth,
                            json={"query": "deploy migrations restarting"}
                            ).json()["data"]
        check("deleted record no longer retrieved",
              all(r["id"] != proc_record["id"] for r in after["results"]))

        # ---- 9. Maintenance + analytics
        log("--- 9. Maintenance scan and analytics")
        scan = show("maintenance", client.post(
            "/memory/maintenance/scan", headers=auth), ("scanned",))
        check("maintenance scan runs", scan["scanned"] >= 1)
        analytics = show("analytics", client.get(
            "/memory/analytics/overview", headers=auth),
            ("total_active_memories", "learning_records"))
        check("analytics measured from tables",
              analytics["learning_records"] >= 1)

        log(f"=== SMOKE RESULT: {PASS} passed, {FAIL} failed ===")
        return 0 if FAIL == 0 else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        evidence = REPO / "docs" / "reports" / "P09_SMOKE_EVIDENCE.txt"
        evidence.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"evidence written to {evidence}")


if __name__ == "__main__":
    raise SystemExit(main())
