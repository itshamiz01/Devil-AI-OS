"""Adapter interface (§5.1 F). Adapters perform ONE validated action and
return a structured result; they never decide policy (the policy engine
already ran) and never talk to the API layer. An adapter that cannot
perform an action in this environment raises
:class:`AdapterUnavailableError` — it never simulates success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AdapterResult:
    success: bool
    output: dict = field(default_factory=dict)
    summary: str = ""
    exit_code: int | None = None
    evidence: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_category: str | None = None
    resource_usage: dict = field(default_factory=dict)


@dataclass
class AdapterContext:
    agent_id: str
    request_id: str
    mode: str
    settings: dict


class ExecutionAdapter(Protocol):
    adapter_type: str

    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        ...

    def health(self) -> dict:
        """{status, health_status, details} for the registry/startup report."""
        ...
