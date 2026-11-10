"""Shared fixtures and helpers for the Expansion Feature 3
(Voice Assistant) suites.

Posture mirrors f02_support: a controlled-mode application (plan
execution is permitted in controlled mode; it is blocked in
simulation mode by the pipeline's own mode gate), owner HTTP
login through the real P-01 path, and the shared audit reader.

The fixture speech double is attached ONLY in-process through the
service's owner-only hook — exactly the boundary production keeps:
no startup path and no HTTP route can attach it.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.application import Application
from app.main import create_app
from tests.conftest import AGENT, EXTERNAL, OWNER, SERVICE, make_settings  # noqa: F401
from tests.p10_support import audit_events  # noqa: F401

PASSWORD = "test-owner-password-123"

# A tiny valid WAV of silence (0.1 s, 8 kHz, 16-bit mono) — real
# audio-shaped bytes for the intake path. The intake never decodes
# audio (no DSP in staging), so content beyond the header is
# irrelevant to the pipeline; provenance is what the tests assert.
def _wav_bytes() -> bytes:
    import io
    import wave
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)
    return buffer.getvalue()


WAV_BYTES = _wav_bytes()


@pytest.fixture
async def app_f03(tmp_path):
    """Controlled-mode application (same posture as P-10/F01/F02)."""
    application = Application(make_settings(tmp_path, mode="controlled"))
    await application.startup()
    yield application
    await application.shutdown()


@pytest.fixture
def client_f03(tmp_path):
    app = create_app(make_settings(tmp_path, mode="controlled"))
    with TestClient(app) as client:
        yield client


def owner_http_headers(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def service_http_headers() -> dict:
    return {"Authorization": "Bearer service-token-for-tests"}


def attach_fixture(application, transcript_text: str = "echo fixture",
                   available: bool = True):
    """Attach the labelled test double through the real service
    hook, as the owner. Returns the double for call inspection."""
    from app.voice.testing import FixtureSpeechProvider
    provider = FixtureSpeechProvider(
        transcript_text=transcript_text, available=available)
    application.voice.attach_provider(OWNER, provider)
    return provider


def make_session(application, **overrides) -> dict:
    data = {"title": "F03 test session", "language": "en"}
    data.update(overrides)
    return application.voice.create_session(OWNER, data)
