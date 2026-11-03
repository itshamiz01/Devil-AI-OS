"""Model router (P-02 §6.3–§6.5).

The router answers one question: which permitted model should serve this
request? It is the enforcement point for the phase's cost and privacy rules, and
it is deliberately *explainable* — every selection carries the reason each
candidate was accepted or rejected, because a routing decision that cannot be
audited cannot be trusted.

The three rules this module exists to guarantee:

1. **Local-first** (§6.3). A local model that can do the job is always preferred
   over a cloud model that could do it better.
2. **Never silently switch to paid** (§6.4, §16). Cloud candidates are excluded
   during *selection*, not checked during *fallback*. That ordering matters: if
   exclusion happened in the fallback loop, a policy bug could still spend the
   owner's money. Here an unpermitted cloud model is never in the candidate list
   at all, so no code path can reach it.
3. **Memory-aware admission** (§6.5, §18). A model that will not fit in available
   RAM is rejected before it is loaded, not after the host starts thrashing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .providers import ModelOutputError, ModelProvider, ModelTimeoutError, ModelUnavailableError
from .registry import ModelRegistry
from .schemas import GenerationRequest, GenerationResult, ModelRecord

#: Conservative characters-per-token estimate used for context validation. It is
#: an approximation, and is documented as one: §10.2 forbids claiming precision
#: that was never measured. Four is deliberately pessimistic for English prose so
#: that a prompt near the limit is rejected rather than silently truncated.
CHARS_PER_TOKEN_ESTIMATE = 4.0

UsageListener = Callable[["UsageRecord"], Awaitable[None]]


@dataclass(frozen=True)
class ResourceSnapshot:
    """Host capacity at the moment of a routing decision."""

    available_ram_gb: float
    cpu_percent: float
    gpu_available: bool = False
    logical_cpus: int = 1


@dataclass(frozen=True)
class InferencePolicy:
    """Owner-configured limits the router must respect.

    Every field maps to a validated `Settings` value; the router never reads
    configuration itself, so policy stays injectable and tests stay honest.
    """

    cloud_enabled: bool = False
    max_concurrent_requests: int = 1
    #: Fraction of *available* RAM a single model may be assumed to need.
    #: 0.8 leaves headroom so inference cannot starve the Core OS (§18).
    ram_safety_fraction: float = 0.8
    max_cost_per_1k_tokens: float = 0.0
    default_timeout_seconds: float = 60.0
    health_max_age_seconds: float = 60.0
    #: Set when the owner has authorized data to leave the machine. Absent this,
    #: sensitive prompts are pinned to local models (§6.3).
    cloud_data_egress_permitted: bool = False


@dataclass(frozen=True)
class RouteRequirements:
    """What the caller needs, independent of which model provides it."""

    min_context_window: int = 0
    require_structured_output: bool = False
    require_tool_calling: bool = False
    require_reasoning: bool = False
    #: Estimated prompt size in characters; used for context validation.
    prompt_chars: int = 0
    contains_sensitive_data: bool = False
    max_cost_per_1k_tokens: float | None = None
    max_latency_ms: float | None = None


@dataclass(frozen=True)
class Rejection:
    model_id: str
    reason: str


@dataclass(frozen=True)
class RouteDecision:
    """An ordered candidate list plus the reasoning behind it."""

    candidates: list[ModelRecord] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def viable(self) -> bool:
        return bool(self.candidates)

    def explain(self) -> str:
        if not self.candidates:
            detail = "; ".join(f"{r.model_id}: {r.reason}" for r in self.rejections) or "no models registered"
            return f"no permitted model available ({detail})"
        chosen = self.candidates[0].model_id
        why = ", ".join(
            f"{r.model_id} ({r.reason})" for r in self.rejections
        ) or "all registered models were eligible"
        return f"selected {chosen}; rejected: {why}"


@dataclass(frozen=True)
class UsageRecord:
    """One inference attempt, for accounting (§17).

    Kept separate from business revenue and expenses, as §17 requires: model
    usage is an operational cost record, not a financial ledger entry.
    """

    request_id: str
    provider: str
    model_id: str
    local: bool
    duration_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    estimated_cost: float
    success: bool
    error: str | None = None
    purpose: str = "unspecified"
    correlation_id: str | None = None


def estimate_tokens(chars: int) -> int:
    """Approximate token count from character count."""
    if chars <= 0:
        return 0
    return int(chars / CHARS_PER_TOKEN_ESTIMATE) + 1


class ModelRouter:
    """Selects and invokes models under owner-imposed limits."""

    def __init__(
        self,
        registry: ModelRegistry,
        providers: dict[str, ModelProvider],
        *,
        policy: InferencePolicy,
        resource_probe: Callable[[], ResourceSnapshot],
        usage_listener: UsageListener | None = None,
    ) -> None:
        self.registry = registry
        self.providers = providers
        self.policy = policy
        self._resource_probe = resource_probe
        self._usage_listener = usage_listener
        # Bounded concurrency (§6.5). One semaphore for the whole router, so N
        # callers cannot start N inferences and freeze the Core OS (§18).
        self._semaphore = asyncio.Semaphore(max(1, policy.max_concurrent_requests))
        self._request_counter = 0
        self._usage: list[UsageRecord] = []

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    async def probe_health(self, *, force: bool = False) -> dict[str, Any]:
        """Probe every registered provider and record the results.

        Without `force`, a recent probe is reused. Re-probing on every request
        would add latency to each generation for no safety benefit; §6.5 asks for
        health checks, not for a health check per token.
        """
        results: dict[str, Any] = {}
        stale = set(self.registry.stale_health(self.policy.health_max_age_seconds))
        for record in self.registry.all():
            provider = self.providers.get(record.provider)
            if provider is None:
                results[record.model_id] = {
                    "healthy": False,
                    "detail": f"no provider adapter registered for {record.provider!r}",
                }
                continue
            if not force and record.model_id not in stale:
                existing = self.registry.health(record.model_id)
                if existing is not None:
                    results[record.model_id] = {
                        "healthy": existing.healthy,
                        "detail": existing.detail,
                        "cached": True,
                    }
                    continue
            health = await provider.check_health()
            self.registry.set_health(record.model_id, health)
            results[record.model_id] = {
                "healthy": health.healthy,
                "detail": health.detail,
                "latency_ms": health.latency_ms,
            }
        return results

    # ------------------------------------------------------------------ #
    # Selection
    # ------------------------------------------------------------------ #

    def select(self, requirements: RouteRequirements) -> RouteDecision:
        """Return permitted candidates, best first.

        Ordering: local before cloud, then smaller RAM requirement first, then
        larger context window first. Smaller-first is intentional — on a 3.85 GiB
        host the model most likely to fit should be tried first, and trying the
        largest model first would waste the timeout budget on a predictable
        failure.
        """
        snapshot = self._resource_probe()
        ram_budget_gb = snapshot.available_ram_gb * self.policy.ram_safety_fraction
        cost_ceiling = self.policy.max_cost_per_1k_tokens
        if requirements.max_cost_per_1k_tokens is not None:
            cost_ceiling = min(cost_ceiling, requirements.max_cost_per_1k_tokens)

        needed_tokens = estimate_tokens(requirements.prompt_chars)
        accepted: list[ModelRecord] = []
        rejections: list[Rejection] = []

        for record in self.registry.all():
            reason = self._reject_reason(
                record,
                requirements,
                snapshot=snapshot,
                ram_budget_gb=ram_budget_gb,
                cost_ceiling=cost_ceiling,
                needed_tokens=needed_tokens,
            )
            if reason is None:
                accepted.append(record)
            else:
                rejections.append(Rejection(record.model_id, reason))

        accepted.sort(key=lambda r: (not r.local, r.capabilities.min_ram_gb, -r.capabilities.context_window))
        return RouteDecision(candidates=accepted, rejections=rejections)

    def _reject_reason(
        self,
        record: ModelRecord,
        requirements: RouteRequirements,
        *,
        snapshot: ResourceSnapshot,
        ram_budget_gb: float,
        cost_ceiling: float,
        needed_tokens: int,
    ) -> str | None:
        """Explain why a model cannot serve this request, or None if it can."""
        if not record.available:
            return "declared unavailable"
        # The adapter check precedes the health check deliberately: a model with
        # no adapter can never be probed healthy, and reporting "not healthy"
        # would mask the real cause and send an operator to debug the wrong
        # thing.
        if record.provider not in self.providers:
            return f"no provider adapter for {record.provider!r}"
        if not self.registry.is_healthy(record.model_id):
            return "not healthy (no successful probe)"

        caps = record.capabilities
        if caps.context_window < max(requirements.min_context_window, needed_tokens):
            return (
                f"context window {caps.context_window} is below the "
                f"{max(requirements.min_context_window, needed_tokens)} tokens required"
            )
        if requirements.require_structured_output and not caps.supports_structured_output:
            return "does not support structured output"
        if requirements.require_tool_calling and not caps.supports_tool_calling:
            return "does not support tool calling"
        if requirements.require_reasoning and not caps.supports_reasoning:
            return "does not declare reasoning capability"

        if record.local:
            # Memory-aware admission (§6.5): refuse before loading, not after
            # the host is already swapping. A GPU relaxes the host-RAM check
            # because weights would live in VRAM.
            if not snapshot.gpu_available and caps.min_ram_gb > ram_budget_gb:
                return (
                    f"needs ~{caps.min_ram_gb:.1f} GiB but only {ram_budget_gb:.1f} GiB "
                    f"is permitted of {snapshot.available_ram_gb:.1f} GiB available"
                )
            return None

        # ---- cloud gating (§6.3): every condition must hold ----
        if not self.policy.cloud_enabled:
            return "cloud inference is disabled by configuration"
        if record.cost_per_1k_tokens > cost_ceiling:
            return (
                f"cost {record.cost_per_1k_tokens}/1k exceeds the permitted "
                f"ceiling {cost_ceiling}/1k"
            )
        if requirements.contains_sensitive_data and not self.policy.cloud_data_egress_permitted:
            # §6.3: never send sensitive information to a cloud provider without
            # the applicable data-sharing authorization. This is a hard refusal,
            # not a preference.
            return "prompt contains sensitive data and cloud egress is not authorized"
        return None

    # ------------------------------------------------------------------ #
    # Generation with controlled fallback
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        request: GenerationRequest,
        requirements: RouteRequirements | None = None,
    ) -> GenerationResult:
        """Run a generation, falling back only among *permitted* candidates.

        Cancellation propagates: `asyncio.CancelledError` is never caught here,
        because swallowing it would break the cooperative cancellation that the
        P-01 task engine and the owner's emergency stop both depend on.
        """
        reqs = requirements or RouteRequirements(prompt_chars=len(request.prompt))
        decision = self.select(reqs)
        if not decision.viable:
            raise ModelUnavailableError(decision.explain())

        if request.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        async with self._semaphore:
            errors: list[str] = []
            for record in decision.candidates:
                provider = self.providers[record.provider]
                started = time.perf_counter()
                try:
                    result = await provider.generate(request, record.model_id)
                except (ModelTimeoutError, ModelUnavailableError, ModelOutputError) as exc:
                    duration_ms = (time.perf_counter() - started) * 1000.0
                    errors.append(f"{record.model_id}: {exc}")
                    await self._record_usage(
                        record=record,
                        duration_ms=duration_ms,
                        success=False,
                        error=str(exc),
                        request=request,
                    )
                    # §6.4 controlled fallback: try the next *permitted* model.
                    # The candidate list was already filtered by policy, so this
                    # loop cannot reach an unpermitted paid provider.
                    continue
                await self._record_usage(
                    record=record,
                    duration_ms=result.duration_ms,
                    success=True,
                    error=None,
                    request=request,
                    tokens=(result.usage.prompt_tokens, result.usage.completion_tokens),
                )
                return result

            raise ModelUnavailableError(
                f"every permitted model failed: {'; '.join(errors)}",
                tried=[c.model_id for c in decision.candidates],
            )

    async def _record_usage(
        self,
        *,
        record: ModelRecord,
        duration_ms: float,
        success: bool,
        error: str | None,
        request: GenerationRequest,
        tokens: tuple[int | None, int | None] | None = None,
    ) -> None:
        self._request_counter += 1
        prompt_tokens, completion_tokens = tokens or (None, None)
        total = (prompt_tokens or 0) + (completion_tokens or 0)
        usage = UsageRecord(
            request_id=f"req-{self._request_counter}",
            provider=record.provider,
            model_id=record.model_id,
            local=record.local,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            # Local inference has no per-token price; cost stays 0.0 rather than
            # being estimated, because §25 forbids inventing measurements.
            estimated_cost=round(total / 1000.0 * record.cost_per_1k_tokens, 6),
            success=success,
            error=error,
            purpose=request.purpose,
            correlation_id=request.correlation_id,
        )
        self._usage.append(usage)
        if self._usage_listener is not None:
            # A listener failure must not abort the generation; the caller's
            # result matters more than the accounting row.
            try:
                await self._usage_listener(usage)
            except Exception:  # noqa: BLE001 - accounting is best-effort
                pass

    @property
    def usage_history(self) -> list[UsageRecord]:
        return list(self._usage)

    @property
    def pending_capacity(self) -> int:
        """How many more concurrent inferences could start right now."""
        return self._semaphore._value  # noqa: SLF001 - intentional introspection
