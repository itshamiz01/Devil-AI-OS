"""Validation for the Universal Integration Framework (F02).

Two jobs, both fail-closed:

1. **Descriptor validation** — a connector declaration is accepted
   only if every capability names a real P-01 ``Permission`` and a
   risk action P-10 has actually classified (``ACTION_RISK``).
   Risk classification is P-10's authority: the framework refuses
   an unclassified action at registration instead of inventing a
   classification of its own.
2. **Payload validation** — a small, self-contained JSON-Schema
   subset validator (type / required / properties / items / enum /
   additionalProperties) used to check invocation payloads against
   a capability's declared input schema. No new dependency; the
   subset is deliberately the part connector contracts use.
"""
from __future__ import annotations

from ..core.exceptions import ValidationError
from ..permissions.models import ALL_PERMISSIONS
from ..security.constants import ACTION_RISK
from . import constants as C
from .interfaces.base import ConnectorDescriptor


def validate_descriptor(descriptor: ConnectorDescriptor) -> None:
    if not descriptor.key or not descriptor.key.replace("_", "").replace("-", "").isalnum():
        raise ValidationError(
            f"connector key '{descriptor.key}' must be alphanumeric/_/-")
    if not descriptor.name or not descriptor.provider:
        raise ValidationError("connector name and provider are required")
    if descriptor.kind not in C.KINDS:
        raise ValidationError(
            f"connector kind '{descriptor.kind}' is not a supported "
            f"integration type ({', '.join(C.KINDS)})")
    seen: set[str] = set()
    for cap in descriptor.capabilities:
        if not cap.name:
            raise ValidationError("every capability must declare a name")
        if cap.name in seen:
            raise ValidationError(
                f"capability '{cap.name}' is declared twice on "
                f"connector '{descriptor.key}'")
        seen.add(cap.name)
        if cap.permission not in ALL_PERMISSIONS:
            raise ValidationError(
                f"capability '{cap.name}' declares permission "
                f"'{cap.permission}', which is not a P-01 permission")
        if cap.risk_action not in ACTION_RISK:
            raise ValidationError(
                f"capability '{cap.name}' declares risk action "
                f"'{cap.risk_action}', which P-10 has not classified; "
                f"risk classification is P-10's authority and an "
                f"unclassified action is refused at registration")
        if cap.rate_limit_per_minute is not None and cap.rate_limit_per_minute < 1:
            raise ValidationError(
                f"capability '{cap.name}' rate_limit_per_minute must be >= 1")


_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate_payload(schema: dict, payload, path: str = "payload") -> list[str]:
    """Return a list of validation errors (empty = valid) for the
    supported JSON-Schema subset."""
    if not isinstance(schema, dict) or not schema:
        return []
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        check = _TYPE_CHECKS.get(expected)
        if check is None:
            return [f"{path}: unsupported schema type '{expected}'"]
        if not check(payload):
            return [f"{path}: expected type {expected}"]
    if "enum" in schema and payload not in schema["enum"]:
        errors.append(f"{path}: value is not one of the declared enum values")
    if isinstance(payload, dict):
        for key in schema.get("required", []):
            if key not in payload:
                errors.append(f"{path}.{key}: required property missing")
        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                errors.extend(validate_payload(properties[key], value, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: additional property not allowed")
    if isinstance(payload, list) and "items" in schema:
        for i, item in enumerate(payload):
            errors.extend(validate_payload(schema["items"], item, f"{path}[{i}]"))
    if isinstance(payload, str):
        if "minLength" in schema and len(payload) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(payload) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    return errors
