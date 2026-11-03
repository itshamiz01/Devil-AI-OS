import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_loopback_default():
    s = Settings(environment="test")
    assert s.host in {"127.0.0.1", "localhost", "::1"}


def test_remote_host_rejected():
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")


def test_remote_access_flag_rejected():
    with pytest.raises(ValidationError):
        Settings(allow_remote_access=True)


def test_phase_execution_flags_rejected():
    with pytest.raises(ValidationError):
        Settings(financial_execution_enabled=True)
    with pytest.raises(ValidationError):
        Settings(external_execution_enabled=True)
    with pytest.raises(ValidationError):
        Settings(cloud_ai_enabled=True)
