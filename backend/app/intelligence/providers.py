"""Model provider interface + adapters (P-02, ADR-001 hybrid AI).

Providers return RAW, UNTRUSTED plan output (a dict). They never execute
anything and their output is schema-validated by the planner before use.

- :class:`OllamaProvider` — local-first candidate. Honestly reports
  unavailable when no server responds or no models are installed. It is
  probe-tested in P-02 only against an absent server (see security/test
  reports); no real LLM has been exercised in this phase.
- :class:`FakeProvider` — deterministic test double with a preset raw
  output (valid plan / invalid plan / garbage / slow), used to verify the
  LLM path without a real model.
- :class:`CloudProviderStub` — the optional cloud path. Disabled by
  default (``AUTONOMUS_CLOUD_AI_ENABLED``); reports "not enabled" and
  never fabricates availability. No cloud vendor is configured in P-02.
"""
from __future__ import annotations

import abc
import asyncio
import copy
import json

import httpx

from ..integrations.interfaces.base import IntegrationAdapter, IntegrationHealth


class ProviderError(Exception):
    """The provider could not produce usable raw plan output."""


class ProviderUnavailable(ProviderError):
    """The provider is not available / not configured / not enabled."""


class ModelProvider(IntegrationAdapter):
    name = "unnamed"

    @abc.abstractmethod
    async def probe(self) -> tuple[bool, str]:
        """(available, human-readable detail). Must be honest."""

    @abc.abstractmethod
    async def list_models(self) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_plan_raw(self, mission_text: str, tools: list[dict],
                                model_id: str) -> dict:
        """Return raw untrusted plan output as a dict (PlanProposal shape)."""
        raise NotImplementedError

    async def health(self) -> IntegrationHealth:
        available, detail = await self.probe()
        return IntegrationHealth(name=self.name, available=available, detail=detail)

    async def close(self) -> None:
        return None


_PLAN_PROMPT = """You are the planning component of AUTONOMUS. Decompose the
mission into a plan using ONLY the tools listed. Reply with JSON only:
{{"steps": [{{"name": str, "tool_name": str, "payload": object,
"expectation": {{"kind": "result_fields", "require_ok": true, "fields": {{}}}}}}],
"rationale": str}}

Tools: {tools}

Mission: {mission}
"""


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(self, base_url: str, timeout_seconds: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self._models: list[str] = []
        self._detail = "not probed yet"

    def _client(self, timeout: float) -> httpx.AsyncClient:
        # trust_env=False: a LOCAL inference server must never be reached
        # through a system/environment proxy.
        return httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def probe(self) -> tuple[bool, str]:
        try:
            async with self._client(self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
            if resp.status_code != 200:
                self._models = []
                self._detail = f"ollama server responded HTTP {resp.status_code}"
                return False, self._detail
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            self._models = [m for m in models if m]
            if not self._models:
                self._detail = "ollama server reachable but no models installed"
                return False, self._detail
            self._detail = f"ollama available with {len(self._models)} model(s)"
            return True, self._detail
        except Exception as exc:
            self._models = []
            self._detail = f"ollama unavailable: {type(exc).__name__}: {exc}"
            return False, self._detail

    async def list_models(self) -> list[str]:
        if not self._models:
            await self.probe()
        return list(self._models)

    async def generate_plan_raw(self, mission_text: str, tools: list[dict],
                                model_id: str) -> dict:
        if not model_id:
            raise ProviderUnavailable(
                "no model_id configured in the model profile (owner has not "
                "selected a local model yet)")
        available, detail = await self.probe()
        if not available:
            raise ProviderUnavailable(detail)
        if model_id not in self._models:
            raise ProviderUnavailable(
                f"model '{model_id}' is not installed on the ollama server")
        prompt = _PLAN_PROMPT.format(
            tools=json.dumps(tools, default=str), mission=mission_text)
        try:
            async with self._client(60.0) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json={
                    "model": model_id, "stream": False, "format": "json",
                    "messages": [{"role": "user", "content": prompt}],
                })
        except Exception as exc:
            raise ProviderError(f"ollama chat request failed: {type(exc).__name__}: {exc}")
        if resp.status_code != 200:
            raise ProviderError(f"ollama chat responded HTTP {resp.status_code}")
        content = resp.json().get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except Exception as exc:
            raise ProviderError(f"model output is not valid JSON: {exc}")
        if not isinstance(parsed, dict):
            raise ProviderError("model output is not a JSON object")
        return parsed


class FakeProvider(ModelProvider):
    """Deterministic test double. ``raw_output`` is returned verbatim from
    generate_plan_raw so tests can feed valid, impermissible, or garbage
    model output through the real validation path."""

    name = "fake"

    def __init__(self, raw_output: dict | None = None, available: bool = True,
                 delay_seconds: float = 0.0):
        self.raw_output = raw_output
        self._available = available
        self.delay_seconds = delay_seconds
        self.calls: list[dict] = []

    async def probe(self) -> tuple[bool, str]:
        return self._available, "fake provider (test double)"

    async def list_models(self) -> list[str]:
        return ["fake-1"] if self._available else []

    async def generate_plan_raw(self, mission_text: str, tools: list[dict],
                                model_id: str) -> dict:
        self.calls.append({"mission_text": mission_text, "model_id": model_id})
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if not self._available:
            raise ProviderUnavailable("fake provider is unavailable")
        if self.raw_output is None:
            raise ProviderError("fake provider has no configured raw output")
        return copy.deepcopy(self.raw_output)


class CloudProviderStub(ModelProvider):
    """Optional cloud path (ADR-001): exists so the router has a real
    branch to refuse. No vendor is wired in P-02."""

    name = "cloud"

    def __init__(self, enabled: bool):
        self.enabled = enabled

    async def probe(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "cloud AI not enabled (AUTONOMUS_CLOUD_AI_ENABLED is off)"
        return False, "cloud AI enabled by owner but no cloud provider is configured in P-02"

    async def list_models(self) -> list[str]:
        return []

    async def generate_plan_raw(self, mission_text: str, tools: list[dict],
                                model_id: str) -> dict:
        _, detail = await self.probe()
        raise ProviderUnavailable(detail)
