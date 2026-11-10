"""Unit tests: config, lifecycle, redaction, state machine, retry policy."""
from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.core.lifecycle import AppState, LifecycleManager
from app.core.logging import redact_text
from app.tasks.models import (
    ErrorKind, TaskStatus, validate_transition,
)
from app.tasks.scheduler import backoff_delay, classify_exception, is_retryable
from app.tasks.models import TaskExecutionError


def test_config_defaults_and_derived_url(tmp_path):
    s = Settings(data_dir=tmp_path)
    assert s.host == "127.0.0.1"  # loopback by default
    assert s.effective_database_url.endswith("autonomus.db")
    assert s.mode == "simulation"


def test_config_rejects_concurrency_above_capacity():
    with pytest.raises(PydanticValidationError):
        Settings(queue_capacity=2, max_concurrency=5)


def test_config_rejects_bad_port_and_mode():
    with pytest.raises(PydanticValidationError):
        Settings(port=70000)
    with pytest.raises(PydanticValidationError):
        Settings(mode="unrestricted")


def test_config_production_requires_credential():
    with pytest.raises(PydanticValidationError):
        Settings(environment="production", admin_password=None, dev_token=None)


def test_config_secrets_redacted_in_dump():
    s = Settings(admin_password="super-secret-value", dev_token="tok123456")
    dumped = s.redacted_dict()
    assert dumped["admin_password"] == "***REDACTED***"
    assert "super-secret-value" not in str(dumped)


def test_lifecycle_valid_and_invalid_transitions():
    lm = LifecycleManager()
    assert lm.state == AppState.STOPPED
    lm.transition(AppState.STARTING)
    lm.transition(AppState.READY)
    assert lm.is_ready
    with pytest.raises(ValueError):
        lm.transition(AppState.STARTING)  # ready -> starting is invalid
    lm.transition(AppState.STOPPING)
    lm.transition(AppState.STOPPED)


def test_redaction_masks_secrets_and_patterns():
    assert "hunter2" not in redact_text("login with password=hunter2 ok")
    assert "abc123456" not in redact_text("Authorization: Bearer abc123456")
    assert "my-real-secret" not in redact_text("value is my-real-secret here",
                                                secret_values=("my-real-secret",))
    assert redact_text("nothing sensitive") == "nothing sensitive"


def test_valid_task_transitions():
    assert validate_transition(TaskStatus.CREATED, TaskStatus.VALIDATING)
    assert validate_transition(TaskStatus.QUEUED, TaskStatus.RUNNING)
    assert validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
    assert validate_transition(TaskStatus.FAILED, TaskStatus.RETRY_PENDING)
    assert validate_transition(TaskStatus.WAITING_FOR_APPROVAL, TaskStatus.QUEUED)


@pytest.mark.parametrize("current,target", [
    (TaskStatus.COMPLETED, TaskStatus.RUNNING),
    (TaskStatus.CANCELLED, TaskStatus.COMPLETED),
    (TaskStatus.FAILED, TaskStatus.COMPLETED),
    (TaskStatus.RUNNING, TaskStatus.RUNNING),
    (TaskStatus.COMPLETED, TaskStatus.QUEUED),
])
def test_invalid_task_transitions(current, target):
    assert not validate_transition(current, target)


def test_backoff_is_exponential_and_capped():
    assert backoff_delay(1, 0.5, 30) == 0.5
    assert backoff_delay(2, 0.5, 30) == 1.0
    assert backoff_delay(3, 0.5, 30) == 2.0
    assert backoff_delay(20, 0.5, 30) == 30


def test_retry_eligibility_rules():
    assert not is_retryable(ErrorKind.INVALID_INPUT)
    assert not is_retryable(ErrorKind.PERMISSION_DENIED)
    assert not is_retryable(ErrorKind.SECURITY)
    assert is_retryable(ErrorKind.TIMEOUT)
    assert is_retryable(ErrorKind.TRANSIENT)
    assert classify_exception(TaskExecutionError("x", ErrorKind.SECURITY)) == ErrorKind.SECURITY
    assert classify_exception(TimeoutError()) == ErrorKind.TIMEOUT
    assert classify_exception(ValueError("bad")) == ErrorKind.INVALID_INPUT
