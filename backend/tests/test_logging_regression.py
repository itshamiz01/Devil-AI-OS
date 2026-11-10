"""Regression test: programmatic Alembic migrations must not clobber the
application logging pipeline (found in the P-01 smoke run: alembic.ini's
fileConfig re-leveled the root logger to WARN and post-migration INFO logs
vanished)."""
from __future__ import annotations

import pytest

from app.core.application import Application
from app.core.logging import get_logger
from tests.conftest import make_settings


async def test_logging_survives_auto_migrate(tmp_path):
    settings = make_settings(tmp_path, auto_migrate=True)
    app = Application(settings)
    await app.startup()
    try:
        get_logger("test.regression").info("post-migration-log-marker-12345")
        log_text = settings.effective_log_file.read_text(errors="ignore")
        assert "application ready" in log_text
        assert "post-migration-log-marker-12345" in log_text
        # Secrets configured for this app must never appear in the file.
        assert "test-owner-password-123" not in log_text
    finally:
        await app.shutdown()
    log_text = settings.effective_log_file.read_text(errors="ignore")
    assert "graceful shutdown initiated" in log_text
    assert "application stopped" in log_text
