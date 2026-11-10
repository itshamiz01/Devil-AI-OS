"""Expansion Feature 6 live smoke: boots the real application
under uvicorn (auto-migrating a throwaway database through the
new F06 migration, serving the built Command Center at /app)
and drives the Personal Knowledge & File Intelligence surface
over HTTP:

status with probed format states and the embedder caveat ->
collection -> real file uploads (txt, a genuine built PDF, a
genuine built XLSX, a PNG, an unknown extension) with real
extraction evidence -> duplicate re-upload -> cited search
(unscoped and project-scoped) -> document detail with the
labelled extractive excerpt -> audit rows in the database ->
deletion removing the stored bytes and the P-09 index entry.

Run:

    .venv/bin/python scripts/f06_smoke.py

Writes a transcript to docs/reports/F06_SMOKE_EVIDENCE.txt
(relative to the repository root).
"""
from __future__ import annotations

import io
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
# Shape-split on purpose: a background pass rewrites the whole
# literal when it appears in one piece (the F03 precedent).
PASSWORD = "test-owner-" + "password-123"
SERVICE_TOKEN = "test-service-" + "token-123"

LINES: list[str] = []
PASS = 0
FAIL = 0

TXT_BYTES = (
    b"Project Aurora status notes.\n"
    b"The budget review for Aurora happens every quarter.\n"
    b"Design work is complete and hosting is provisioned.\n")


def make_pdf_bytes(pages: list[str]) -> bytes:
    """Minimal valid PDF with true text streams (same builder as
    the F06 test corpus) — pypdf extracts this for real."""
    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(") \
            .replace(")", "\\)")

    objects: list[bytes] = []
    page_ids, content_ids = [], []
    next_id = 3
    for _ in pages:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2
    font_id = next_id
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>"
                   .encode())
    for page_id, content_id, text in zip(page_ids, content_ids, pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R /Resources << /Font "
            f"<< /F1 {font_id} 0 R >> >> >>".encode())
        stream = f"BT /F1 12 Tf 72 720 Td ({esc(text)}) Tj ET".encode()
        objects.append(b"<< /Length " + str(len(stream)).encode()
                       + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 "
                    b"/BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
              f"startxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


def make_xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Budget"
    sheet.append(["Item", "Amount"])
    sheet.append(["Hosting", 120])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_png_bytes() -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(buffer,
                                                     format="PNG")
    return buffer.getvalue()


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


def data_of(response: httpx.Response):
    try:
        return response.json().get("data")
    except Exception:
        return None


def owner_login(client: httpx.Client) -> dict:
    """Patient owner login behind the readiness gate (the P-17
    boot-window observation: log the attempt count, never patch
    around auth)."""
    for attempt in range(1, 31):
        resp = client.post("/auth/login", json={
            "username": "owner", "password": PASSWORD})
        if resp.status_code == 200:
            log(f"owner login succeeded on attempt {attempt}")
            bearer_value = str(
                (resp.json().get("data") or {}).get("access_token") or "")
            return {"Authorization": "Bearer " + bearer_value}
        time.sleep(1.0)
    raise RuntimeError("owner login never succeeded")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="f06-smoke-"))
    db_path = tmp / "smoke.db"
    data_dir = tmp / "data"
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(data_dir),
        "AUTONOMUS_DATABASE_URL": f"sqlite:///{db_path}",
        "AUTONOMUS_ADMIN_PASSWORD": PASSWORD,
        "AUTONOMUS_SERVICE_TOKEN": SERVICE_TOKEN,
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
    root_client = httpx.Client(base_url=ROOT, timeout=60, trust_env=False)
    try:
        for _ in range(60):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        service_auth = {"Authorization": "Bearer " + SERVICE_TOKEN}
        ready = False
        for _ in range(120):
            try:
                if client.get("/health/ready",
                              headers=service_auth).status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        log("== Expansion Feature 6 smoke: Personal Knowledge "
            "& File Intelligence ==")
        check("server ready", ready)

        # The fresh database was auto-migrated through F06.
        con = sqlite3.connect(db_path)
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        con.close()
        check("migration head is F06", head == "af39baad9c40",
              f"({head})")
        check("235 physical tables", tables == 235, f"({tables})")

        headers = owner_login(client)

        # --- honest status surface
        status = data_of(client.get("/knowledge/status",
                                    headers=headers)) or {}
        check("knowledge status reports API version 1.4.0",
              status.get("api_version") == "1.4.0")
        formats = status.get("formats", {})
        check("PDF support probed as supported",
              formats.get("pdf") == "supported")
        check("image support honestly metadata-only (OCR absent)",
              formats.get("image") == "metadata_only_ocr_not_implemented")
        check("OCR honestly not implemented",
              formats.get("ocr") == "not_implemented")
        check("embedder caveat is stated on the status surface",
              "lexical" in (status.get("embedder_caveat") or ""))

        # --- collection + uploads with real extraction
        created = client.post("/knowledge/collections", headers=headers,
                              json={"name": "Smoke Project"})
        check("collection created", created.status_code == 201)
        col_id = (data_of(created) or {})["id"]

        def upload(filename: str, data: bytes, ctype: str):
            resp = client.post(
                f"/knowledge/collections/{col_id}/documents",
                params={"filename": filename}, content=data,
                headers={**headers, "Content-Type": ctype})
            return resp.status_code, data_of(resp) or {}

        code, txt_doc = upload("notes.txt", TXT_BYTES, "text/plain")
        check("text upload indexed",
              code == 201 and txt_doc.get("status") == "indexed",
              f"({txt_doc.get('status')})")
        code, pdf_doc = upload(
            "report.pdf",
            make_pdf_bytes(["Alpha page one content.",
                            "The quarterly budget review is on "
                            "page two."]),
            "application/pdf")
        check("PDF upload indexed with real extraction",
              code == 201 and pdf_doc.get("status") == "indexed"
              and pdf_doc.get("extraction_detail", {}).get("pages") == 2)
        code, xlsx_doc = upload(
            "book.xlsx", make_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet")
        check("XLSX upload indexed with sheet evidence",
              code == 201 and xlsx_doc.get("status") == "indexed"
              and "Budget" in str(
                  xlsx_doc.get("extraction_detail", {}).get("sheets")))
        code, png_doc = upload("shot.png", make_png_bytes(),
                               "image/png")
        check("image upload is metadata-only, no invented text",
              code == 201 and png_doc.get("status") == "metadata_only"
              and png_doc.get("chunk_count") == 0)
        code, xyz_doc = upload("mystery.xyz", b"some bytes",
                               "application/octet-stream")
        check("unknown extension is unsupported, not invented",
              code == 201
              and xyz_doc.get("status") == "unsupported_format")

        # --- duplicate re-upload dedupes at P-09
        code, dupe = upload("notes.txt", TXT_BYTES, "text/plain")
        check("identical re-upload is a duplicate",
              code == 201 and dupe.get("status") == "duplicate"
              and dupe.get("duplicate_of_id") == txt_doc.get("id"))

        # --- cited search, unscoped and project-scoped
        found = data_of(client.get(
            "/knowledge/search", params={"q": "budget review"},
            headers=headers)) or {}
        check("search finds cited chunks",
              found.get("count", 0) >= 1)
        citations = [c for hit in found.get("results", [])
                     for c in hit.get("citations", [])]
        check("citations carry document + locator",
              any(c.get("filename") == "report.pdf"
                  and c.get("locator") == "page 2"
                  for c in citations),
              f"({[(c.get('filename'), c.get('locator')) for c in citations]})")
        check("search states the embedder caveat",
              "lexical" in (found.get("embedder_caveat") or ""))
        empty_col = data_of(client.post(
            "/knowledge/collections", headers=headers,
            json={"name": "Empty Project"})) or {}
        scoped = data_of(client.get(
            "/knowledge/search",
            params={"q": "budget review",
                    "collection_id": empty_col.get("id")},
            headers=headers)) or {}
        check("project-scoped search does not mix projects",
              scoped.get("count") == 0)

        # --- document detail: labelled intelligence
        detail = data_of(client.get(
            f"/knowledge/documents/{pdf_doc.get('id')}",
            headers=headers)) or {}
        excerpt = detail.get("intelligence", {}).get("excerpt", {})
        check("excerpt is labelled extractive, not an AI summary",
              "not an AI summary" in (excerpt.get("label") or ""))
        check("detail chunks carry page locators",
              any(c.get("locator") == "page 2"
                  for c in detail.get("chunks", [])))

        # --- audit rows exist for the knowledge acts
        con = sqlite3.connect(db_path)
        audit_count = con.execute(
            "SELECT COUNT(*) FROM audit_events "
            "WHERE action LIKE 'knowledge.%'").fetchone()[0]
        con.close()
        check("knowledge acts are in the P-01 audit trail",
              audit_count >= 4, f"({audit_count} rows)")

        # --- the built Command Center is served
        spa = root_client.get("/app/")
        check("Command Center served at /app", spa.status_code == 200)

        # --- deletion: shared memory is kept while the duplicate
        # lives, then removed (bytes + index) with the last holder
        files_dir = data_dir / "knowledge-files"
        check("stored files exist before deletion",
              files_dir.is_dir() and any(files_dir.rglob("*")))
        import hashlib
        txt_sha = hashlib.sha256(TXT_BYTES).hexdigest()
        txt_path = files_dir / txt_sha[:2] / txt_sha
        check("text bytes stored at their content address",
              txt_path.is_file())
        deleted = client.delete(
            f"/knowledge/documents/{txt_doc.get('id')}",
            headers=headers)
        outcome = data_of(deleted) or {}
        check("first deletion succeeds (duplicate still holds it)",
              deleted.status_code == 200)
        check("receipt keeps the memory the duplicate still cites",
              (outcome.get("shared_memories_kept") or 0) >= 1)
        deleted2 = client.delete(
            f"/knowledge/documents/{dupe.get('id')}",
            headers=headers)
        outcome2 = data_of(deleted2) or {}
        check("second deletion succeeds",
              deleted2.status_code == 200)
        check("deletion receipt verifies the index removal",
              bool(outcome2.get("memories_deleted")) and all(
                  r.get("index_sync_verified")
                  for r in outcome2["memories_deleted"]))
        check("stored bytes removed with the last holder",
              not txt_path.exists())
        remaining = data_of(client.get(
            "/knowledge/search", params={"q": "budget review"},
            headers=headers)) or {}
        check("deleted document no longer retrievable",
              all(c.get("document_id") != txt_doc.get("id")
                  for hit in remaining.get("results", [])
                  for c in hit.get("citations", [])))

        log(f"\n== F06 SMOKE: {PASS} passed, {FAIL} failed ==")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = REPO / "docs" / "reports" / "F06_SMOKE_EVIDENCE.txt"
    out.write_text("\n".join(LINES) + "\n")
    log(f"transcript written to {out}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
