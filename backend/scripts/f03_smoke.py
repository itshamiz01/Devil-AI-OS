"""Expansion Feature 3 live smoke: boots the real application
under uvicorn (auto-migrating a throwaway database through the
new F03 migration, serving the built Command Center at /app) and
drives the Voice Assistant surface over HTTP:

honest capability states (no speech model exists in staging) ->
session -> audio upload -> transcription refused honestly (422,
requires_owner_configuration) -> manual-entry fallback ->
interpretation executes a low-risk command through the plan
pipeline -> a consequential command waits, a spoken "approve"
does NOT confirm it, the stop phrase cancels a pending command,
and on-screen confirmation executes exactly what was shown ->
audit trail carries the voice events -> session deletion removes
the stored audio files.

The pipeline over a speech provider is exercised in-process by
the F03 integration suite against the LABELLED test double; a
separate uvicorn process cannot (and must not) attach it — there
is no HTTP route for attaching providers, by design.

Run:

    .venv/bin/python scripts/f03_smoke.py

Writes a transcript to docs/reports/F03_SMOKE_EVIDENCE.txt
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
import wave
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

PORT = random.randint(20000, 45000)
ROOT = f"http://127.0.0.1:{PORT}"
BASE = f"{ROOT}/api/v1"
PASSWORD = "smoke-owner-" + "password-123"
SERVICE_TOKEN = "smoke-service-" + "token"

LINES: list[str] = []
PASS = 0
FAIL = 0


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)
    return buffer.getvalue()


WAV_BYTES = _wav_bytes()


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
    tmp = Path(tempfile.mkdtemp(prefix="f03-smoke-"))
    db_path = tmp / "smoke.db"
    data_dir = tmp / "data"
    database_url = "sqlite:///" + str(db_path)
    env = dict(os.environ)
    env.update({
        "AUTONOMUS_MODE": "controlled",
        "AUTONOMUS_DATA_DIR": str(data_dir),
        "AUTONOMUS_DATABASE_URL": database_url,
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
        log("== Expansion Feature 3 smoke: Voice Assistant ==")
        check("server ready", ready)

        # The fresh database was auto-migrated through F03.
        con = sqlite3.connect(db_path)
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        con.close()
        check("migration head is F03", head == "c41f7a9d03e6", f"({head})")
        check("232 physical tables", tables == 232, f"({tables})")

        headers = owner_login(client)

        # --- honest capability states: no speech model exists here
        status = data_of(client.get("/voice/status", headers=headers)) or {}
        check("voice status reports API version 1.3.0",
              status.get("api_version") == "1.3.0")
        check("STT honestly requires owner configuration",
              status.get("stt", {}).get("state")
              == "requires_owner_configuration",
              f"({status.get('stt', {}).get('state')})")
        check("TTS honestly requires owner configuration",
              status.get("tts", {}).get("state")
              == "requires_owner_configuration")
        check("DEF-A2 is stated on the status surface",
              "DEF-A2" in (status.get("stt", {}).get("detail") or ""))
        providers = {p["name"]: p for p in status.get("providers", [])}
        check("the real local candidate is attached but unavailable",
              providers.get("local_whisper", {}).get("available") is False
              and providers.get("local_whisper", {}).get("is_fixture") is False)
        check("no fixture provider is attached",
              "fixture_speech_double" not in providers)

        # --- session + audio intake
        session = data_of(client.post(
            "/voice/sessions", headers=headers,
            json={"title": "smoke session", "language": "en"})) or {}
        session_id = session.get("id")
        check("session created", bool(session_id))

        audio = data_of(client.post(
            f"/voice/sessions/{session_id}/audio?filename=cmd.wav",
            headers={**headers, "Content-Type": "audio/wav"},
            content=WAV_BYTES)) or {}
        check("audio uploaded and hashed", bool(audio.get("sha256"))
              and audio.get("size_bytes") == len(WAV_BYTES))

        # --- transcription with no provider: honest refusal
        resp = client.post(f"/voice/audio/{audio.get('id')}/transcribe",
                           headers=headers)
        body = resp.json() if resp.headers.get("content-type", "").startswith(
            "application/json") else {}
        check("transcription refused honestly (422 + state)",
              resp.status_code == 422
              and (body.get("error") or {}).get("details", {}).get("state")
              == "requires_owner_configuration",
              f"(HTTP {resp.status_code})")
        transcripts = data_of(client.get(
            f"/voice/sessions/{session_id}/transcripts",
            headers=headers)) or []
        check("the refused attempt is recorded, not fabricated",
              len(transcripts) == 1
              and transcripts[0]["status"] == "not_configured"
              and transcripts[0]["text"] == "")

        # --- manual-entry fallback -> low-risk command executes
        manual = data_of(client.post(
            f"/voice/sessions/{session_id}/transcripts/manual",
            headers=headers, json={"text": "echo over smoke"})) or {}
        check("manual entry labelled as fallback, not transcription",
              manual.get("source") == "manual_entry"
              and "not speech recognition" in (manual.get("model_label") or ""))
        command = data_of(client.post(
            f"/voice/transcripts/{manual.get('id')}/interpret",
            headers=headers)) or {}
        check("low-risk voice command executed via the plan pipeline",
              command.get("status") == "completed"
              and bool(command.get("plan_id"))
              and bool(command.get("broker_decision_id")),
              f"({command.get('status')})")
        check("spoken response honestly unavailable at completion",
              command.get("speech_state") == "requires_owner_configuration")

        # --- consequential command: waits; spoken approval does NOT
        # confirm; the stop phrase cancels a pending command
        risky = data_of(client.post(
            f"/voice/sessions/{session_id}/transcripts/manual",
            headers=headers,
            json={"text": "echo delete the old backups"})) or {}
        risky_command = data_of(client.post(
            f"/voice/transcripts/{risky.get('id')}/interpret",
            headers=headers)) or {}
        check("consequential command waits for on-screen confirmation",
              risky_command.get("status") == "awaiting_confirmation"
              and risky_command.get("category") == "high_risk"
              and risky_command.get("requires_confirmation") is True)
        yes = data_of(client.post(
            f"/voice/sessions/{session_id}/transcripts/manual",
            headers=headers, json={"text": "yes approve it"})) or {}
        yes_command = data_of(client.post(
            f"/voice/transcripts/{yes.get('id')}/interpret",
            headers=headers)) or {}
        still = data_of(client.get(
            f"/voice/commands/{risky_command.get('id')}",
            headers=headers)) or {}
        check("a spoken 'approve' confirms nothing",
              yes_command.get("status") == "needs_clarification"
              and still.get("status") == "awaiting_confirmation")

        confirmed = data_of(client.post(
            f"/voice/commands/{risky_command.get('id')}/confirm",
            headers=headers)) or {}
        check("on-screen confirmation executes exactly what was shown",
              confirmed.get("status") == "completed"
              and bool(confirmed.get("confirmed_at")))

        pending = data_of(client.post(
            f"/voice/sessions/{session_id}/transcripts/manual",
            headers=headers,
            json={"text": "echo delete the old backups"})) or {}
        pending_command = data_of(client.post(
            f"/voice/transcripts/{pending.get('id')}/interpret",
            headers=headers)) or {}
        stop = data_of(client.post(
            f"/voice/sessions/{session_id}/transcripts/manual",
            headers=headers, json={"text": "stop"})) or {}
        stop_command = data_of(client.post(
            f"/voice/transcripts/{stop.get('id')}/interpret",
            headers=headers)) or {}
        cancelled = data_of(client.get(
            f"/voice/commands/{pending_command.get('id')}",
            headers=headers)) or {}
        check("the stop phrase cancels the session's pending command",
              stop_command.get("detail", {}).get("stop_applied") is True
              and cancelled.get("status") == "cancelled")

        # --- a financial request never reaches money
        fin = data_of(client.post(
            f"/voice/sessions/{session_id}/transcripts/manual",
            headers=headers,
            json={"text": "transfer the payment to the wallet"})) or {}
        fin_command = data_of(client.post(
            f"/voice/transcripts/{fin.get('id')}/interpret",
            headers=headers)) or {}
        check("financial request classifies and stops at clarification",
              fin_command.get("category") == "financial_operation"
              and fin_command.get("status") == "needs_clarification"
              and fin_command.get("plan_id") is None)

        # --- audit trail carries the voice acts
        audit = client.get("/security/audit", headers=headers,
                           params={"action_prefix": "voice.", "limit": 200})
        actions = {row["action"] for row in (data_of(audit) or [])}
        check("audit trail records voice events",
              {"voice.session_created", "voice.audio_stored",
               "voice.transcript_manual_entry",
               "voice.transcription_unavailable",
               "voice.command_executed",
               "voice.command_confirmation_required",
               "voice.command_confirmed",
               "voice.stop_applied"} <= actions,
              f"({sorted(actions)})")
        # NB: voice.transcribed (a successful transcription) is
        # covered by the in-process F03 suite over the labelled
        # test double — it cannot occur in this live scenario,
        # where no provider exists; only the honest refusal can.

        # --- OpenAPI version + permission metadata for a voice route
        schema = root_client.get("/openapi.json").json()
        check("OpenAPI reports version 1.3.0",
              schema["info"]["version"] == "1.3.0")
        op = schema["paths"]["/api/v1/voice/commands/{command_id}/confirm"]["post"]
        check("confirm route carries x-required-permission=approve_actions",
              op.get("x-required-permission") == "approve_actions")

        # --- the built Command Center is served
        spa = root_client.get("/app/")
        check("Command Center served at /app", spa.status_code == 200)

        # --- retention deletion removes the stored files
        audio_dir = data_dir / "voice-audio"
        check("audio files exist before deletion",
              audio_dir.is_dir() and any(audio_dir.iterdir()))
        deleted = client.delete(f"/voice/sessions/{session_id}",
                                headers=headers)
        check("session deletion succeeds", deleted.status_code == 200)
        check("audio files removed by deletion",
              not audio_dir.is_dir() or not any(audio_dir.iterdir()))

        log(f"\n== F03 SMOKE: {PASS} passed, {FAIL} failed ==")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = REPO / "docs" / "reports" / "F03_SMOKE_EVIDENCE.txt"
    out.write_text("\n".join(LINES) + "\n")
    log(f"transcript written to {out}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
