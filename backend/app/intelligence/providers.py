"""Model provider abstraction (P-02 §6.1).

The intelligence engine never talks to Ollama, llama.cpp or any cloud API
directly. It talks to a `ModelProvider`, and concrete adapters translate. That
indirection is what makes the system provider-independent (§6) and what allows
the whole phase to be tested deterministically without a model installed (§19.1).

Honesty note that governs this file: `NoRuntimeProvider` is *not* a fake model.
It is the truthful adapter for a host that has no inference runtime, and it fails
loudly. Nothing in this package fabricates a model response.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

import httpx

from .schemas import GenerationRequest, GenerationResult, ModelCapabilities, ModelHealth, TokenUsage


class ModelUnavailableError(RuntimeError):
    """No permitted model could serve the request (§6.4).

    Raised instead of silently switching to a paid provider. The router reports
    the limitation to the owner rather than spending their money.
    """

    def __init__(self, detail: str, *, tried: list[str] | None = None) -> None:
        self.detail = detail
        self.tried = list(tried or [])
        super().__init__(detail)


class ModelTimeoutError(ModelUnavailableError):
    """The model did not answer within its budget (§6.5)."""


class ModelOutputError(ModelUnavailableError):
    """The model answered, but the answer is unusable (§6.4).

    Distinct from unavailability because the correct response differs: an
    unusable answer may justify one bounded repair attempt (§13), whereas an
    unavailable provider should trigger fallback.
    """


@runtime_checkable
class ModelProvider(Protocol):
    """The provider contract from §6.1."""

    name: str

    async def generate(self, request: GenerationRequest, model_id: str) -> GenerationResult:
        """Run one generation. Must respect `request.timeout_seconds`."""

    async def check_health(self) -> ModelHealth:
        """Report whether the provider can serve requests right now."""

    async def list_models(self) -> list[str]:
        """Model identifiers this provider can serve."""

    async def get_capabilities(self, model_id: str) -> ModelCapabilities | None:
        """Declared capabilities, or None if the model is unknown."""


class NoRuntimeProvider:
    """Adapter for a host with no local inference runtime installed.

    This is the actual state of the P-02 development workspace: no `ollama`, no
    `llama-server`, no GPU, and the model-download hosts are unreachable. Rather
    than pretending otherwise, this provider reports itself permanently
    unhealthy and raises on generation, so the router takes its documented
    "no permitted model available" path (§6.4) and the owner sees a truthful
    resource limitation instead of an invented answer.
    """

    name = "none"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def generate(self, request: GenerationRequest, model_id: str) -> GenerationResult:
        raise ModelUnavailableError(
            f"no local inference runtime is installed ({self.reason})", tried=[model_id]
        )

    async def check_health(self) -> ModelHealth:
        return ModelHealth(
            healthy=False,
            checked_at=_now(),
            detail=f"no inference runtime available: {self.reason}",
        )

    async def list_models(self) -> list[str]:
        return []

    async def get_capabilities(self, model_id: str) -> ModelCapabilities | None:
        return None


class OllamaProvider:
    """Adapter for a local Ollama server (§6.1).

    Talks to Ollama's documented HTTP API over loopback. It is written against
    the real endpoints, but **it has not been verified against a live server in
    this workspace**, because no Ollama binary exists here and the download host
    is unreachable. That is recorded as a known limitation rather than claimed as
    working.

    Deliberate omissions:
      * No `keep_alive` tuning or model pulling. Loading and unloading models is
        a host-capacity decision the owner must make (§18), and silently
        downloading multi-gigabyte weights would exceed the machine's 3.85 GiB.
      * No streaming. Bounded, timeout-enforced single responses keep inference
        from blocking the Core OS (§6.5, §18).
    """

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        *,
        connect_timeout: float = 5.0,
        capabilities: dict[str, ModelCapabilities] | None = None,
    ) -> None:
        # Loopback by default: §13 requires local binding, and an inference
        # endpoint on a public interface would leak prompts off the machine.
        self.base_url = base_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self._capabilities = dict(capabilities or {})

    async def generate(self, request: GenerationRequest, model_id: str) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.system:
            payload["system"] = request.system
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(request.timeout_seconds, connect=self.connect_timeout)
            ) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(
                f"model {model_id} exceeded its {request.timeout_seconds:.1f}s budget",
                tried=[model_id],
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailableError(
                f"ollama request failed for {model_id}: {exc.__class__.__name__}", tried=[model_id]
            ) from exc

        duration_ms = (time.perf_counter() - started) * 1000.0
        text = body.get("response")
        if not isinstance(text, str) or not text.strip():
            # An empty or malformed body is an unusable answer, not an outage:
            # §13 permits one bounded repair attempt for this case.
            raise ModelOutputError(f"model {model_id} returned no usable text", tried=[model_id])

        eval_count = body.get("eval_count")
        prompt_count = body.get("prompt_eval_count")
        return GenerationResult(
            text=text,
            model_id=model_id,
            provider=self.name,
            local=True,
            duration_ms=duration_ms,
            usage=TokenUsage(
                prompt_tokens=int(prompt_count) if isinstance(prompt_count, int) else None,
                completion_tokens=int(eval_count) if isinstance(eval_count, int) else None,
            ),
            truncated=bool(body.get("done_reason") == "length"),
            correlation_id=request.correlation_id,
        )

    async def check_health(self) -> ModelHealth:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.connect_timeout, connect=self.connect_timeout)
            ) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
        except httpx.TimeoutException:
            return ModelHealth(healthy=False, checked_at=_now(), detail="ollama health check timed out")
        except httpx.HTTPError as exc:
            return ModelHealth(
                healthy=False, checked_at=_now(), detail=f"ollama unreachable: {exc.__class__.__name__}"
            )
        return ModelHealth(
            healthy=True,
            checked_at=_now(),
            detail="ollama responded",
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.connect_timeout, connect=self.connect_timeout)
            ) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError:
            return []
        models = body.get("models") or []
        return [m["name"] for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)]

    async def get_capabilities(self, model_id: str) -> ModelCapabilities | None:
        return self._capabilities.get(model_id)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
