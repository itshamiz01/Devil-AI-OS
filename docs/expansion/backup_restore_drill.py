"""Gate 2 readiness review — backup & restore drill (audit-only).

Exercises the EXISTING P-10 backup mechanism end to end against
scratch databases under /tmp (no live data is touched):

  1. boot a source Application on a scratch DB
  2. BackupService.create_backup (owner) -> real SQLite backup + SHA-256
  3. BackupService.verify_backup -> integrity + manifest + inventory
  4. negative control: tamper with a backup file -> verify must FAIL
  5. guarded restore_preview: hash-bound approval required, executes
     nothing itself, takes a pre-restore snapshot
  6. the documented manual restore (INCIDENT_RESPONSE_PLAYBOOK §5):
     stop app -> copy backup into place -> start app -> verify status
  7. restored app must answer an owner login and report healthy

Writes BACKUP_RESTORE_EVIDENCE.txt beside this script.
"""
from __future__ import annotations

import asyncio
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.application import Application  # noqa: E402
from app.permissions.models import Principal, PrincipalType  # noqa: E402
from tests.conftest import make_settings  # noqa: E402

OUT = Path(__file__).resolve().parent / "BACKUP_RESTORE_EVIDENCE.txt"
ROOT = Path("/tmp/g2drill")
OWNER = Principal(PrincipalType.OWNER, "owner")
LINES: list[str] = []
CHECKS = [0, 0]  # pass, fail


def log(s: str = "") -> None:
    LINES.append(s)
    print(s, flush=True)


def check(label: str, ok: bool, detail: str = "") -> None:
    CHECKS[0 if ok else 1] += 1
    log(f"  [{'PASS' if ok else 'FAIL'}] {label} {detail}")


def ro_counts(db_path: Path, tables: list[str]) -> dict[str, int]:
    db_path = Path(db_path).resolve()
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        counts = {}
        for t in tables:
            counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        counts["__tables__"] = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        counts["__integrity__"] = con.execute(
            "PRAGMA integrity_check").fetchone()[0]
        try:
            counts["__alembic__"] = con.execute(
                "SELECT version_num FROM alembic_version").fetchone()[0]
        except Exception:
            counts["__alembic__"] = None
        return counts
    finally:
        con.close()


SENTINELS = ["system_config", "security_policy_versions", "audit_events",
             "app_sessions", "permissions", "agents", "tasks"]


async def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    src_root = ROOT / "src"
    src_root.mkdir(parents=True)

    log("=== Gate 2 backup & restore drill ===")
    log(f"scratch root: {ROOT}")

    # ---- 1. source application --------------------------------------
    # Production posture: auto_migrate=True (the smoke scripts' boot
    # mode) so the DB carries alembic_version and 224 physical tables.
    src_settings = make_settings(src_root, mode="controlled",
                                 auto_migrate=True)
    app = Application(src_settings)
    await app.startup()
    from urllib.parse import urlparse
    src_db = Path(urlparse(src_settings.effective_database_url).path)
    log(f"\n[1] source application booted; db = {src_db}")
    before = ro_counts(src_db, SENTINELS)
    log(f"    source: tables={before['__tables__']} "
        f"integrity={before['__integrity__']} alembic={before['__alembic__']}")
    for t in SENTINELS:
        log(f"      {t}: {before[t]} rows")
    check("source db has 224 physical tables", before["__tables__"] == 224,
          f"(got {before['__tables__']})")
    check("source db at migration head 218ddd92a0aa",
          before["__alembic__"] == "218ddd92a0aa")

    backup = app.security.backup

    # ---- 2. create + verify backup A --------------------------------
    log("\n[2] create_backup (owner principal, service layer)")
    rec_a = backup.create_backup(OWNER)
    log(f"    A: status={rec_a['status']} tables={rec_a['table_count']} "
        f"size={rec_a['size_bytes']} sha256={str(rec_a['sha256'])[:16]}...")
    check("backup A created", rec_a["status"] == "created")
    check("backup A inventory = 224 tables", rec_a["table_count"] == 224)
    ver_a = backup.verify_backup(OWNER, rec_a["id"])
    log(f"    verify A: status={ver_a['status']} detail={ver_a['detail']}")
    check("backup A verifies", ver_a["status"] == "verified")

    # non-owner must be refused
    from app.core.exceptions import PermissionDeniedError
    agent = Principal(PrincipalType.AGENT, "agent-1")
    try:
        backup.create_backup(agent)
        check("non-owner backup refused", False, "(agent was allowed!)")
    except PermissionDeniedError:
        check("non-owner backup refused", True)

    # ---- 3. negative control: tamper --------------------------------
    log("\n[3] negative control: corrupt backup A's file, re-verify")
    path_a = Path(rec_a["location"])
    with path_a.open("ab") as fh:
        fh.write(b"TAMPERED")
    ver_a2 = backup.verify_backup(OWNER, rec_a["id"])
    log(f"    verify A after tamper: status={ver_a2['status']} "
        f"detail={ver_a2['detail']}")
    check("tampered backup FAILS verification",
          ver_a2["status"] == "verify_failed")

    # ---- 4. backup B + guarded restore preview ----------------------
    log("\n[4] backup B + restore_preview (hash-bound approval guard)")
    rec_b = backup.create_backup(OWNER)
    ver_b = backup.verify_backup(OWNER, rec_b["id"])
    check("backup B verifies", ver_b["status"] == "verified")
    approval = app.approvals.create(
        OWNER, "security.restore_backup", "backup",
        "level_3", "Gate 2 drill restore", ["approve_actions"],
        {"backup_id": rec_b["id"]})
    app.approvals.decide(approval.id, OWNER, True)
    plan = app.security.restore_preview(OWNER, rec_b["id"], approval.id)
    log(f"    plan: executed={plan['executed']} "
        f"snapshot={plan['pre_restore_snapshot_id'][:8]}... "
        f"steps={len(plan['manual_steps'])}")
    check("restore_preview executes nothing itself",
          plan["executed"] is False)
    check("restore_preview took a pre-restore snapshot",
          bool(plan["pre_restore_snapshot_id"]))
    # an approval bound to a DIFFERENT backup must be refused
    approval2 = app.approvals.create(
        OWNER, "security.restore_backup", "backup",
        "level_3", "wrong binding", ["approve_actions"],
        {"backup_id": "some-other-backup"})
    app.approvals.decide(approval2.id, OWNER, True)
    from app.core.exceptions import ValidationError
    try:
        app.security.restore_preview(OWNER, rec_b["id"], approval2.id)
        check("mis-bound approval refused", False, "(was accepted!)")
    except ValidationError:
        check("mis-bound approval refused", True)

    backup_b_path = Path(rec_b["location"])
    in_backup = ro_counts(backup_b_path, SENTINELS)
    log(f"    backup B contents: tables={in_backup['__tables__']} "
        f"integrity={in_backup['__integrity__']}")
    for t in SENTINELS:
        log(f"      {t}: {in_backup[t]} rows")

    await app.shutdown()
    log("\n[5] source application stopped (playbook §5 step 1)")

    # ---- 5. manual restore into a fresh home -------------------------
    rst_root = ROOT / "restored"
    rst_root.mkdir(parents=True)
    rst_settings = make_settings(rst_root, mode="controlled",
                                 auto_migrate=True)
    rst_db = Path(urlparse(rst_settings.effective_database_url).path)
    rst_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src_db, ROOT / "source-live-copy-aside.db")  # copy aside
    shutil.copy(backup_b_path, rst_db)
    log(f"    live DB copied aside; backup B copied into place ({rst_db})")

    app2 = Application(rst_settings)
    await app2.startup()
    log("    restored application started")
    healthy = app2.monitor.database_healthy()
    check("restored app reports database healthy", healthy is True)
    # Row counts BEFORE any login: a login legitimately creates a
    # session row, so counts are read first and login checked after.
    after = ro_counts(rst_db, SENTINELS)
    log(f"    restored: tables={after['__tables__']} "
        f"integrity={after['__integrity__']} alembic={after['__alembic__']}")
    for t in SENTINELS:
        log(f"      {t}: backup={in_backup[t]} restored={after[t]}")
    check("restored table count = 224", after["__tables__"] == 224)
    check("restored integrity ok", after["__integrity__"] == "ok")
    # audit_events legitimately grows during the restored boot (startup
    # writes its own audit rows); every other sentinel must match the
    # backup exactly.
    stable = [t for t in SENTINELS if t != "audit_events"]
    check("sentinel row counts match backup (excl. audit_events, which "
          "the restored boot appends to)",
          all(after[t] == in_backup[t] for t in stable),
          "; ".join(f"{t}: {in_backup[t]}->{after[t]}" for t in stable))
    check("audit_events in restored DB >= backup (boot appended, none lost)",
          after["audit_events"] >= in_backup["audit_events"],
          f"({in_backup['audit_events']} -> {after['audit_events']})")
    token = app2.auth.login("owner", "test-owner-password-123")
    check("owner login succeeds against restored DB", bool(token))
    principal = app2.auth.resolve_bearer(token)
    check("restored session resolves to the owner principal",
          principal is not None and principal.type == PrincipalType.OWNER)
    await app2.shutdown()

    log(f"\n=== DRILL RESULT: {CHECKS[0]} passed, {CHECKS[1]} failed ===")
    OUT.write_text("\n".join(LINES) + "\n")
    print(f"wrote {OUT}")
    return 0 if CHECKS[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
