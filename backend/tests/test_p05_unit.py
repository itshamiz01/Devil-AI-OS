"""P-05 unit tests: policy engine, path validation (platform-first),
code screen, standing-authorization matching, workflow definition
validation, secret hygiene, settings governance, registry views."""
from __future__ import annotations

import pytest

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.execution import constants as C
from app.execution.adapters.code import screen_code
from app.execution.errors import ExecutionValidationError
from app.execution.paths import PathValidationError, resolve_within_workspace
from app.execution.policy import match_standing_authorization
from app.execution.registry import ToolRegistry
from app.execution.schemas import ExecutionRequestIn, reject_secret_values
from app.execution.workflows import validate_definition
from app.permissions.models import Principal, PrincipalType
from tests.conftest import AGENT, OWNER
from tests.p05_support import app_rw, engine, grant, make_agent  # noqa: F401


# ------------------------------------------------------------ path validation
def test_path_validator_accepts_normal_relative_paths(tmp_path):
    validated = resolve_within_workspace(tmp_path, "reports/2026/summary.md")
    assert validated.relative == "reports/2026/summary.md"
    assert str(validated.absolute).startswith(str(tmp_path))


@pytest.mark.parametrize("raw", [
    "../escape.txt", "a/../../escape.txt", "..\\windows\\escape.txt",
    "/etc/passwd", "C:\\Windows\\system32\\x.dll", "c:/windows/x",
    "\\\\server\\share\\file.txt", "file.txt:alternate-stream",
    "CON.txt", "nul", "trailingdot.", "trailingspace ",
])
def test_path_validator_rejects_traversal_and_windows_constructs(tmp_path, raw):
    with pytest.raises(PathValidationError):
        resolve_within_workspace(tmp_path, raw)


def test_path_validator_symlink_escape_rejected(tmp_path):
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "ws"
    root.mkdir()
    (root / "link.txt").symlink_to(outside)
    with pytest.raises(PathValidationError):
        resolve_within_workspace(root, "link.txt")


# ---------------------------------------------------------------- code screen
def test_code_screen_hard_constructs():
    screen = screen_code("import os\nprint(os.environ['KEY'])")
    assert "environment_or_secret_access" in screen["hard"]
    assert screen_code("import subprocess; subprocess.run(['ls'])")["hard"]
    assert screen_code("eval('1+1')")["hard"]
    assert screen_code("import socket")["hard"]
    assert screen_code("import shutil; shutil.rmtree('/x')")["hard"]


def test_code_screen_soft_and_clean():
    assert "filesystem_access" in screen_code("open('x.txt').read()")["soft"]
    clean = screen_code("total = sum(range(10))\nprint(total)")
    assert clean == {"hard": [], "soft": []}


# ------------------------------------------------------- standing authorization
class _Row:
    def __init__(self, **kw):
        self.status = "active"
        self.revoked_at = None
        self.tool_name = "api_http"
        self.action_name = "post"
        self.scope_pattern = "api_http:post:api.example.com"
        self.agent_id = None
        self.role = None
        self.uses = 0
        self.max_uses = 5
        import datetime as dt
        self.expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
        self.id = "sa-1"
        for key, value in kw.items():
            setattr(self, key, value)


def _match(rows, **kw):
    args = dict(tool_name="api_http", action_name="post",
                scope="api_http:post:api.example.com", agent_id="a1", agent_role=None)
    args.update(kw)
    return match_standing_authorization(rows, **args)


def test_standing_authorization_matching_is_narrow():
    assert _match([_Row()]) is not None
    assert _match([_Row()], action_name="get") is None
    assert _match([_Row()], scope="api_http:post:other.example.com") is None
    assert _match([_Row(uses=5)]) is None                      # exhausted
    assert _match([_Row(status="revoked")]) is None
    import datetime as dt
    expired = _Row(expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
    assert _match([expired]) is None
    assert _match([_Row(agent_id="someone-else")]) is None
    assert _match([_Row(role="researcher")], agent_role="writer") is None
    # delete_permanent can never be covered, even by an exact row.
    assert _match([_Row(action_name="delete_permanent", tool_name="filesystem")],
                  tool_name="filesystem", action_name="delete_permanent",
                  scope="filesystem:delete_permanent:x") is None


# --------------------------------------------------------- workflow validation
def test_workflow_definition_validation():
    assert validate_definition({"steps": [{"id": "a", "tool": "filesystem",
                                            "action": "read"}]}) == []
    assert validate_definition({"steps": []})
    assert validate_definition({}) != []
    errors = validate_definition({"steps": [
        {"id": "a", "tool": "filesystem", "action": "read"},
        {"id": "a", "tool": "filesystem", "action": "read"}]})
    assert any("duplicate" in e for e in errors)
    errors = validate_definition({"steps": [
        {"id": "a", "tool": "filesystem", "action": "read", "on_failure": "explode"}]})
    assert any("on_failure" in e for e in errors)
    errors = validate_definition({"steps": [
        {"id": "a", "tool": "filesystem", "action": "read",
         "compensation": {"tool": "filesystem"}}]})
    assert any("compensation" in e for e in errors)
    errors = validate_definition({"steps": [
        {"id": f"s{i}", "tool": "t", "action": "a"} for i in range(51)]})
    assert any("ceiling" in e for e in errors)


# -------------------------------------------------------------- secret hygiene
def test_reject_secret_values():
    reject_secret_values({"url": "https://x", "credential_ref": "env:MY_KEY"})
    with pytest.raises(ExecutionValidationError):
        reject_secret_values({"api_key": "sk-live-raw-value"})
    with pytest.raises(ExecutionValidationError):
        reject_secret_values({"nested": {"password": "hunter2"}})
    with pytest.raises(ExecutionValidationError):
        reject_secret_values({"headers": {"Authorization": "Bearer abc"}})


async def test_submit_rejects_raw_secret_parameters(app_rw):
    agent_id = await make_agent(app_rw)
    service = engine(app_rw)
    with pytest.raises(ExecutionValidationError):
        service.submit(OWNER, ExecutionRequestIn(
            agent_id=agent_id, tool="api_http", action="get",
            parameters={"url": "https://api.example.com", "api_key": "raw-secret"}))


# ------------------------------------------------------------------- settings
async def test_execution_settings_owner_only(app_rw):
    service = engine(app_rw)
    with pytest.raises(PermissionDeniedError):
        service.update_settings(AGENT, {"max_concurrent_runs": 99})
    with pytest.raises(ValidationError):
        service.update_settings(OWNER, {"not_a_setting": 1})
    updated = service.update_settings(OWNER, {"max_concurrent_runs": 7})
    assert updated["values"]["max_concurrent_runs"] == 7
    assert service.settings_values()["max_concurrent_runs"] == 7


# -------------------------------------------------------------- registry views
async def test_registry_discovery_view_hides_internals(app_rw):
    service = engine(app_rw)
    rows, _ = service.registry.list_tools()
    by_name = {t.name: t for t in rows}
    discovery = ToolRegistry.discovery_view(by_name["filesystem"])
    assert "config_ref" not in discovery
    assert "health_details" not in discovery
    admin = ToolRegistry.admin_view(by_name["filesystem"])
    assert admin["config_ref"] == "execution.adapters.filesystem"
    # Truthful per-environment statuses after seeding.
    assert by_name["desktop"].status == "disabled"
    assert by_name["browser"].status == "degraded"
    assert by_name["filesystem"].status == "available"
    assert by_name["code_python"].status == "available"


async def test_startup_health_report_is_truthful(app_rw):
    service = engine(app_rw)
    report = service.startup_health_report()
    assert "process_controls_only" in report["code_isolation"]
    assert "NOT a strong sandbox" in report["code_isolation"]
    assert "unavailable" in report["browser_backend"]
    assert report["desktop_adapter"].startswith("disabled")
    assert report["emergency_stop"] is False


# ------------------------------------------------------- capability flip (P-05)
async def test_p05_capabilities_supported_but_memory_write_is_not(app_rw):
    caps = {c.name: c for c in app_rw.agents.capabilities.list_catalogue()}
    for name in C.P05_SUPPORTED_CAPABILITIES:
        assert caps[name].supported is True, name
    # P-09 DISCLOSURE: memory_write was the not-yet-backed capability
    # when this test was written; P-09 now genuinely backs it and
    # flips it at seed time (same mechanism as P-05's flip), so it is
    # supported. The still-unsupported assertions below are unchanged.
    assert caps["memory_write"].supported is True
    assert caps["code_generation"].supported is False
    assert caps["external_communication"].supported is False


# ------------------------------------------------------------- policy outcomes
async def test_policy_rejects_agent_without_capability(app_rw):
    agent_id = await make_agent(app_rw)
    service = engine(app_rw)
    request = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": "shared", "path": "x.txt"}))
    assert request.status == "REJECTED"
    assert "file_read" in request.result_summary


async def test_policy_records_all_checks(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    service = engine(app_rw)
    request = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": "shared", "path": "missing.txt"}))
    assert request.status == "QUEUED"
    audit = service.audit_for_request(request.id)
    submit_entries = [a for a in audit if a["action"] == "execution.submit"]
    assert submit_entries and submit_entries[0]["details"]["checks"]
    check_names = [c["check"] for c in submit_entries[0]["details"]["checks"]]
    assert check_names == ["agent_identity", "agent_status", "assigned_task",
                           "capabilities", "requested_scope", "tool_status",
                           "risk_category", "approval_status", "resource_limits",
                           "policy_restrictions"]


async def test_timeout_is_clamped_to_ceiling(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    service = engine(app_rw)
    request = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": "shared", "path": "x.txt"},
        timeout_seconds=999_999))
    assert request.timeout_seconds == service.settings_values()["max_timeout_seconds"]


async def test_idempotency_key_returns_original_request(app_rw):
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_read")
    service = engine(app_rw)
    payload = ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="read",
        parameters={"workspace": "shared", "path": "x.txt"},
        idempotency_key="unit-key-1")
    first = service.submit(OWNER, payload)
    second = service.submit(OWNER, payload)
    assert first.id == second.id
    rows, total = service.list_requests(agent_id=agent_id)
    assert total == 1


async def test_priority_never_overrides_risk(app_rw):
    """A Risk-2 action at maximum priority still requires approval."""
    agent_id = await make_agent(app_rw)
    await grant(app_rw, agent_id, "file_write")
    service = engine(app_rw)
    request = service.submit(OWNER, ExecutionRequestIn(
        agent_id=agent_id, tool="filesystem", action="delete_permanent",
        parameters={"workspace": "quarantine", "path": "old.txt"}, priority=10))
    assert request.status == "AWAITING_APPROVAL"
    assert request.risk_level == 2
