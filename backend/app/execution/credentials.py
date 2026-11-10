"""Credential broker (§13.3).

Agents hold credential *references*, never values. A reference has the
form ``env:NAME``; the broker resolves it internally at execution time
and hands the value ONLY to the adapter code path that injects it into
the outbound request. The value is never returned to the service layer's
result objects, never written to a table, never logged (the application
log scrubber is additionally seeded with configured secret values).

Two implementations:
- :class:`EnvCredentialBroker` — resolves from the process environment
  (on the owner's machine: the OS/user environment or a secret manager
  fronting the same interface in a later phase).
- :class:`DictCredentialBroker` — explicit mapping, used by tests.
"""
from __future__ import annotations

import os
from typing import Protocol

from .errors import ExecutionValidationError

REF_PREFIX = "env:"


def is_credential_ref(value) -> bool:
    return isinstance(value, str) and value.startswith(REF_PREFIX) and len(value) > len(REF_PREFIX)


class CredentialBroker(Protocol):
    def resolve(self, reference: str) -> str | None:
        """Return the secret value for a reference, or None if unknown.
        Implementations must not log the value."""
        ...


class EnvCredentialBroker:
    def resolve(self, reference: str) -> str | None:
        if not is_credential_ref(reference):
            raise ExecutionValidationError(
                f"credential reference '{reference}' is not of the form 'env:NAME'",
                details={"error_category": "CREDENTIAL_REF_INVALID"})
        return os.environ.get(reference[len(REF_PREFIX):])


class DictCredentialBroker:
    def __init__(self, values: dict[str, str]):
        self._values = dict(values)

    def resolve(self, reference: str) -> str | None:
        if not is_credential_ref(reference):
            raise ExecutionValidationError(
                f"credential reference '{reference}' is not of the form 'env:NAME'",
                details={"error_category": "CREDENTIAL_REF_INVALID"})
        return self._values.get(reference[len(REF_PREFIX):])
