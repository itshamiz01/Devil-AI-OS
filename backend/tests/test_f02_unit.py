"""Expansion Feature 2 unit tests: descriptor validation (the
capability contract), the payload schema validator, the schema
guards (no money columns, no secret-value columns), the API
catalogue + OpenAPI permission metadata (review §2 fixes 1/3), the
literal-binding guard (fix 2 disposition), and the single-source
API version (fix 4).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.integrations.interfaces.base import Capability, ConnectorDescriptor
from app.integrations.validation import validate_descriptor, validate_payload

BACKEND = Path(__file__).resolve().parents[1]


def _descriptor(**overrides) -> ConnectorDescriptor:
    base = dict(key="unit_connector", name="Unit", provider="Tests",
                kind="rest_api", capabilities=(
                    Capability(name="do", permission="execute_tools",
                               risk_action="network.fetch"),))
    base.update(overrides)
    return ConnectorDescriptor(**base)


# ------------------------------------------------------- descriptors
def test_descriptor_accepts_classified_action_and_real_permission():
    validate_descriptor(_descriptor())  # no raise


def test_descriptor_refuses_unknown_permission():
    bad = _descriptor(capabilities=(
        Capability(name="do", permission="not_a_permission",
                   risk_action="network.fetch"),))
    with pytest.raises(ValidationError, match="not a P-01 permission"):
        validate_descriptor(bad)


def test_descriptor_refuses_unclassified_risk_action():
    # Risk classification is P-10's authority: an action P-10 has
    # not classified is refused at registration, never reclassified
    # by the framework.
    bad = _descriptor(capabilities=(
        Capability(name="do", permission="execute_tools",
                   risk_action="integration.unclassified_thing"),))
    with pytest.raises(ValidationError, match="has not classified"):
        validate_descriptor(bad)


def test_descriptor_refuses_duplicate_capability_and_bad_kind():
    dup = _descriptor(capabilities=(
        Capability(name="do", risk_action="read"),
        Capability(name="do", risk_action="read")))
    with pytest.raises(ValidationError, match="declared twice"):
        validate_descriptor(dup)
    with pytest.raises(ValidationError, match="not a supported"):
        validate_descriptor(_descriptor(kind="carrier_pigeon"))


# ------------------------------------------------------------ payloads
def test_payload_validator_subset():
    schema = {"type": "object",
              "properties": {"message": {"type": "string", "minLength": 1},
                             "count": {"type": "integer"},
                             "mode": {"enum": ["a", "b"]}},
              "required": ["message"], "additionalProperties": False}
    assert validate_payload(schema, {"message": "hi"}) == []
    assert validate_payload(schema, {}) != []                       # required
    assert validate_payload(schema, {"message": 5}) != []           # type
    assert validate_payload(schema, {"message": ""}) != []          # minLength
    assert validate_payload(schema, {"message": "x", "mode": "z"}) != []  # enum
    assert validate_payload(schema, {"message": "x", "nope": 1}) != []    # extra
    assert validate_payload(schema, {"message": "x", "count": True}) != []  # bool != int


# --------------------------------------------------------- schema guards
def test_integration_tables_have_no_money_or_secret_value_columns():
    from app.database.models.integrations import (
        IntegrationConnector, IntegrationInvocation,
    )
    money_tokens = ("amount", "minor", "currency", "price", "balance",
                    "revenue", "profit", "collected", "journal", "ledger",
                    "charge", "fee")
    # Columns that would store a secret VALUE. credential_secret_name
    # is a registry NAME (a metadata reference, the P-10 pattern) and
    # is the single whitelisted exception.
    value_tokens = ("secret_value", "api_key", "password", "token_value",
                    "credential_value", "private_key")
    for model in (IntegrationConnector, IntegrationInvocation):
        for column in model.__table__.columns:
            for token in money_tokens:
                assert token not in column.name, (model.__tablename__, column.name)
            for token in value_tokens:
                assert token not in column.name, (model.__tablename__, column.name)
    names = {c.name for c in IntegrationConnector.__table__.columns}
    assert "credential_secret_name" in names  # reference NAME only


def test_framework_never_decides_approvals_or_writes_finance():
    # Article 0 structural guard: the framework consumes approvals
    # through the broker's verify path only, and contains no
    # financial write surface.
    sources = "\n".join(
        p.read_text() for p in (BACKEND / "app" / "integrations").rglob("*.py"))
    assert ".decide(" not in sources
    assert "FinancialService" not in sources
    assert "JournalEntry" not in sources


# ------------------------------------------- API catalogue / OpenAPI (§2)
def test_catalogue_labels_permissions_and_depths(tmp_path):
    from app.main import create_app
    from app.integrations.catalogue import build_catalogue
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path))
    catalogue = build_catalogue(app)
    by = {(op["path"], op["method"]): op for op in catalogue["operations"]}

    invoke = by[("/api/v1/integrations/{key}/invoke", "POST")]
    assert invoke["required_permission"] == "execute_tools"
    assert invoke["authorization_depth"] == "route"

    login = by[("/api/v1/auth/login", "POST")]
    assert login["required_permission"] is None
    assert login["authorization_depth"] == "public"

    # A P-01-era service-layer surface: authenticated, no route
    # permission declared — labelled honestly, not assumed.
    tasks = by[("/api/v1/tasks", "POST")]
    assert tasks["authorization_depth"] in ("authenticated", "route")
    assert catalogue["count"] > 600


def test_openapi_carries_permission_extensions(tmp_path):
    from app.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path))
    schema = app.openapi()
    op = schema["paths"]["/api/v1/integrations/{key}/invoke"]["post"]
    assert op["x-required-permission"] == "execute_tools"
    assert op["x-authorization-depth"] == "route"
    # Expansion F03 disclosure: API version advanced to 1.3.0 per the
    # recorded versioning rule (minor per expansion feature).
    # Expansion F06 disclosure: advanced to 1.4.0 by the same rule.
    assert schema["info"]["version"] == "1.4.0"


def test_literal_permission_bindings_agree_with_enum():
    # Gate 2 review §2 finding 2, dispositioned: literal bindings in
    # existing route modules are NOT churned, but any literal that
    # is not a Permission enum value now fails this test — the
    # silent-typo dead-route failure mode is test-detectable.
    from app.permissions.models import ALL_PERMISSIONS
    routes_dir = BACKEND / "app" / "api" / "routes"
    literal = re.compile(r"""require_permission\(\s*["']([a-z_]+)["']\s*\)""")
    offenders = []
    for path in routes_dir.glob("*.py"):
        for match in literal.finditer(path.read_text()):
            if match.group(1) not in ALL_PERMISSIONS:
                offenders.append((path.name, match.group(1)))
    assert offenders == []


def test_framework_routes_bind_permissions_from_the_enum():
    source = (BACKEND / "app" / "api" / "routes" / "integrations.py").read_text()
    assert "require_permission(Permission." in source


def test_api_version_single_source():
    from app.core.version import APP_VERSION
    # Expansion F03 disclosure: advanced to 1.3.0 (see above).
    # Expansion F06 disclosure: advanced to 1.4.0 (see above).
    assert APP_VERSION == "1.4.0"
    main_source = (BACKEND / "app" / "main.py").read_text()
    assert 'version="0.1.0"' not in main_source
    assert "APP_VERSION" in main_source
