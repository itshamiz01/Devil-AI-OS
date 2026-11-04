"""P-02 §19.1 — model router tests.

These use mock providers, as §19.1 explicitly directs, because no inference
runtime exists in this workspace. What they verify is the router's *policy*
logic: selection, local-first ordering, cloud gating, admission control,
fallback and accounting. They do not and cannot verify that a real model
produces useful text.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.intelligence.providers import (
    ModelOutputError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from app.intelligence.registry import ModelRegistry, UnknownModelError
from app.intelligence.router import (
    InferencePolicy,
    ModelRouter,
    ResourceSnapshot,
    RouteRequirements,
    estimate_tokens,
)
from app.intelligence.schemas import (
    GenerationRequest,
    GenerationResult,
    ModelCapabilities,
    ModelHealth,
    ModelRecord,
    TokenUsage,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class MockProvider:
    """A provider whose behaviour is set per test.

    `behavior` selects the failure mode so that timeout, unusable-output and
    outage paths are each exercised deterministically.
    """

    def __init__(self, name: str = "mock", *, healthy: bool = True, behavior: str = "ok", delay: float = 0.0):
        self.name = name
        self.healthy = healthy
        self.behavior = behavior
        self.delay = delay
        self.calls: list[tuple[str, str]] = []
        self.health_checks = 0
        self._concurrent = 0
        self.max_concurrent_observed = 0
        self._gate: asyncio.Event | None = None

    async def generate(self, request: GenerationRequest, model_id: str) -> GenerationResult:
        self.calls.append((request.purpose, model_id))
        self._concurrent += 1
        self.max_concurrent_observed = max(self.max_concurrent_observed, self._concurrent)
        try:
            if self._gate is not None:
                await self._gate.wait()
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.behavior == "timeout":
                raise ModelTimeoutError(f"{model_id} timed out", tried=[model_id])
            if self.behavior == "garbage":
                raise ModelOutputError(f"{model_id} returned no usable text", tried=[model_id])
            if self.behavior == "down":
                raise ModelUnavailableError(f"{model_id} is unreachable", tried=[model_id])
            return GenerationResult(
                text=f"response from {model_id}",
                model_id=model_id,
                provider=self.name,
                local=True,
                duration_ms=1.0,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
                correlation_id=request.correlation_id,
            )
        finally:
            self._concurrent -= 1

    async def check_health(self) -> ModelHealth:
        self.health_checks += 1
        return ModelHealth(
            healthy=self.healthy,
            checked_at=datetime.now(timezone.utc),
            detail="mock healthy" if self.healthy else "mock unhealthy",
            latency_ms=0.5,
        )

    async def list_models(self) -> list[str]:
        return ["mock-small"] if self.healthy else []

    async def get_capabilities(self, model_id: str) -> ModelCapabilities | None:
        return ModelCapabilities(context_window=4096)

    def block_until_released(self) -> None:
        """Make generation wait, so concurrency can be observed."""
        self._gate = asyncio.Event()

    def release(self) -> None:
        if self._gate is not None:
            self._gate.set()


def make_record(
    model_id: str,
    *,
    provider: str = "mock",
    local: bool = True,
    context_window: int = 4096,
    min_ram_gb: float = 1.0,
    structured: bool = False,
    tool_calling: bool = False,
    reasoning: bool = False,
    cost: float = 0.0,
    available: bool = True,
) -> ModelRecord:
    return ModelRecord(
        model_id=model_id,
        provider=provider,
        local=local,
        capabilities=ModelCapabilities(
            context_window=context_window,
            supports_structured_output=structured,
            supports_tool_calling=tool_calling,
            min_ram_gb=min_ram_gb,
            supports_reasoning=reasoning,
        ),
        available=available,
        cost_per_1k_tokens=cost,
        limitations=[] if local else ["data leaves the machine"],
    )


def make_router(
    records: list[ModelRecord],
    providers: dict | None = None,
    *,
    policy: InferencePolicy | None = None,
    ram_available: float = 3.0,
    gpu: bool = False,
) -> tuple[ModelRouter, ModelRegistry, dict]:
    registry = ModelRegistry(records)
    provs = providers if providers is not None else {"mock": MockProvider()}
    router = ModelRouter(
        registry,
        provs,
        policy=policy or InferencePolicy(),
        resource_probe=lambda: ResourceSnapshot(available_ram_gb=ram_available, cpu_percent=10.0, gpu_available=gpu),
    )
    return router, registry, provs


def healthy_registry(records: list[ModelRecord], providers: dict, policy: InferencePolicy | None = None,
                     ram_available: float = 3.0, gpu: bool = False) -> ModelRouter:
    """Build a router whose models have all been probed healthy."""
    router, _, _ = make_router(records, providers, policy=policy, ram_available=ram_available, gpu=gpu)
    asyncio.run(router.probe_health(force=True))
    return router


# --------------------------------------------------------------------------- #
# Provider availability
# --------------------------------------------------------------------------- #


def test_health_probe_records_results_and_reuses_recent_ones():
    provider = MockProvider(healthy=True)
    router, registry, _ = make_router([make_record("mock-small")], {"mock": provider})

    results = asyncio.run(router.probe_health(force=True))
    assert results["mock-small"]["healthy"] is True
    assert provider.health_checks == 1
    assert registry.is_healthy("mock-small") is True

    # A second probe within the health TTL must not re-contact the provider.
    asyncio.run(router.probe_health())
    assert provider.health_checks == 1, "recent health should be reused, not re-probed"


def test_unhealthy_provider_makes_models_unroutable():
    provider = MockProvider(healthy=False)
    router, registry, _ = make_router([make_record("mock-small")], {"mock": provider})
    asyncio.run(router.probe_health(force=True))

    assert registry.is_healthy("mock-small") is False
    decision = router.select(RouteRequirements())
    assert not decision.viable
    assert any("not healthy" in r.reason for r in decision.rejections)


def test_model_without_a_provider_adapter_is_rejected():
    router, registry, _ = make_router([make_record("orphan", provider="nonexistent")])
    asyncio.run(router.probe_health(force=True))
    decision = router.select(RouteRequirements())
    assert not decision.viable
    assert any("no provider adapter" in r.reason for r in decision.rejections)


def test_unregistered_model_raises_a_named_error():
    registry = ModelRegistry([make_record("mock-small")])
    with pytest.raises(UnknownModelError) as exc:
        registry.get("does-not-exist")
    assert "does-not-exist" in str(exc.value)


def test_duplicate_registration_requires_explicit_replace():
    registry = ModelRegistry()
    registry.register(make_record("mock-small"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(make_record("mock-small", cost=99.0))
    registry.register(make_record("mock-small", cost=99.0), replace=True)
    assert registry.get("mock-small").cost_per_1k_tokens == 99.0


# --------------------------------------------------------------------------- #
# Selection and local-first behaviour
# --------------------------------------------------------------------------- #


def test_local_model_is_preferred_over_a_capable_cloud_model():
    """§6.3: use local models whenever they can reasonably perform the task."""
    provider = MockProvider()
    router = healthy_registry(
        [
            make_record("cloud-big", provider="mock", local=False, context_window=128_000, cost=0.01),
            make_record("local-small", provider="mock", local=True, context_window=4096),
        ],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=True, cloud_data_egress_permitted=True, max_cost_per_1k_tokens=1.0),
    )
    decision = router.select(RouteRequirements())
    assert decision.viable
    assert decision.candidates[0].model_id == "local-small"


def test_smaller_local_model_is_tried_before_larger_one():
    """On a small host the model most likely to fit should be attempted first."""
    provider = MockProvider()
    router = healthy_registry(
        [
            make_record("local-huge", min_ram_gb=2.5),
            make_record("local-tiny", min_ram_gb=0.5),
        ],
        {"mock": provider},
        # 4.0 GiB available x 0.8 safety fraction = 3.2 GiB budget, so both the
        # 0.5 GiB and the 2.5 GiB model fit and ordering is what is under test.
        ram_available=4.0,
    )
    decision = router.select(RouteRequirements())
    assert [c.model_id for c in decision.candidates] == ["local-tiny", "local-huge"]


def test_unavailable_model_is_excluded():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("ok"), make_record("disabled", available=False)], {"mock": provider}
    )
    decision = router.select(RouteRequirements())
    assert [c.model_id for c in decision.candidates] == ["ok"]
    assert any(r.model_id == "disabled" and "unavailable" in r.reason for r in decision.rejections)


def test_select_with_no_registered_models_explains_itself():
    router, _, _ = make_router([])
    decision = router.select(RouteRequirements())
    assert not decision.viable
    assert "no models registered" in decision.explain()


# --------------------------------------------------------------------------- #
# Cloud fallback restrictions
# --------------------------------------------------------------------------- #


def test_cloud_model_is_excluded_when_cloud_inference_is_disabled():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("cloud-x", local=False, cost=0.01)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=False),
    )
    decision = router.select(RouteRequirements())
    assert not decision.viable
    assert any("cloud inference is disabled" in r.reason for r in decision.rejections)


def test_sensitive_data_never_routes_to_cloud_without_egress_authorization():
    """§6.3: never send sensitive information to a cloud provider unauthorized."""
    provider = MockProvider()
    router = healthy_registry(
        [make_record("cloud-x", local=False, cost=0.0)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=True, cloud_data_egress_permitted=False),
    )
    decision = router.select(RouteRequirements(contains_sensitive_data=True))
    assert not decision.viable
    assert any("sensitive data" in r.reason for r in decision.rejections)


def test_sensitive_data_may_use_cloud_once_egress_is_authorized():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("cloud-x", local=False, cost=0.0)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=True, cloud_data_egress_permitted=True),
    )
    assert router.select(RouteRequirements(contains_sensitive_data=True)).viable


def test_cost_ceiling_rejects_an_expensive_model():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("pricey", local=False, cost=0.50)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=True, max_cost_per_1k_tokens=0.05),
    )
    decision = router.select(RouteRequirements())
    assert not decision.viable
    assert any("exceeds the permitted ceiling" in r.reason for r in decision.rejections)


def test_request_level_cost_ceiling_tightens_the_policy_ceiling():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("mid", local=False, cost=0.10)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=True, max_cost_per_1k_tokens=1.00),
    )
    assert router.select(RouteRequirements(max_cost_per_1k_tokens=0.50)).viable
    assert not router.select(RouteRequirements(max_cost_per_1k_tokens=0.01)).viable


def test_no_automatic_paid_fallback_when_the_local_model_fails():
    """§6.4/§16: a local failure must not silently become a paid request.

    The cloud model is excluded at selection time, so it is not in the candidate
    list the fallback loop iterates — no code path can reach it.
    """
    local = MockProvider("mock", behavior="down")
    router = healthy_registry(
        [
            make_record("local-small", provider="mock"),
            make_record("cloud-paid", provider="cloud", local=False, cost=0.20),
        ],
        {"mock": local, "cloud": MockProvider("cloud")},
        policy=InferencePolicy(cloud_enabled=False),
    )
    with pytest.raises(ModelUnavailableError) as exc:
        asyncio.run(router.generate(GenerationRequest(prompt="hello", purpose="test")))
    assert exc.value.tried == ["local-small"], "only the permitted local model may be attempted"
    assert "cloud-paid" not in str(exc.value)


# --------------------------------------------------------------------------- #
# Resource limits
# --------------------------------------------------------------------------- #


def test_model_needing_more_ram_than_available_is_rejected():
    """§6.5: memory-aware admission refuses before loading, not after thrashing."""
    provider = MockProvider()
    router = healthy_registry(
        [make_record("too-big", min_ram_gb=6.0)], {"mock": provider}, ram_available=3.85
    )
    decision = router.select(RouteRequirements())
    assert not decision.viable
    assert any("GiB" in r.reason for r in decision.rejections)


def test_ram_safety_fraction_leaves_headroom_for_the_core_os():
    """A model fitting in raw free RAM must still be refused if it leaves nothing."""
    provider = MockProvider()
    # 3.0 GiB available, 0.8 safety fraction -> 2.4 GiB budget; a 2.6 GiB model
    # would fit in raw RAM but must be rejected to protect the Core OS (§18).
    router = healthy_registry(
        [make_record("tight", min_ram_gb=2.6)], {"mock": provider}, ram_available=3.0
    )
    assert not router.select(RouteRequirements()).viable


def test_gpu_presence_relaxes_the_host_ram_check():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("big", min_ram_gb=8.0)], {"mock": provider}, ram_available=3.0, gpu=True
    )
    assert router.select(RouteRequirements()).viable


def test_context_window_is_validated_against_the_prompt_size():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("small-ctx", context_window=512)], {"mock": provider}
    )
    # 8000 chars ~= 2001 tokens, far beyond a 512-token window.
    decision = router.select(RouteRequirements(prompt_chars=8000))
    assert not decision.viable
    assert any("context window" in r.reason for r in decision.rejections)


def test_explicit_minimum_context_window_is_honoured():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("small-ctx", context_window=1024), make_record("big-ctx", context_window=32_768)],
        {"mock": provider},
    )
    decision = router.select(RouteRequirements(min_context_window=8192))
    assert [c.model_id for c in decision.candidates] == ["big-ctx"]


def test_token_estimate_is_conservative():
    assert estimate_tokens(0) == 0
    assert estimate_tokens(4000) == 1001
    assert estimate_tokens(1) == 1


# --------------------------------------------------------------------------- #
# Capability filtering
# --------------------------------------------------------------------------- #


def test_structured_output_requirement_filters_models():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("plain"), make_record("structured", structured=True)], {"mock": provider}
    )
    decision = router.select(RouteRequirements(require_structured_output=True))
    assert [c.model_id for c in decision.candidates] == ["structured"]


def test_tool_calling_requirement_filters_models():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("plain"), make_record("tools", tool_calling=True)], {"mock": provider}
    )
    assert [c.model_id for c in router.select(RouteRequirements(require_tool_calling=True)).candidates] == ["tools"]


def test_reasoning_requirement_filters_models():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("plain"), make_record("thinker", reasoning=True)], {"mock": provider}
    )
    assert [c.model_id for c in router.select(RouteRequirements(require_reasoning=True)).candidates] == ["thinker"]


# --------------------------------------------------------------------------- #
# Timeout, invalid output and fallback
# --------------------------------------------------------------------------- #


def test_timeout_falls_back_to_the_next_permitted_model():
    slow = MockProvider("slow", behavior="timeout")
    good = MockProvider("good")
    router = healthy_registry(
        [
            make_record("first", provider="slow", min_ram_gb=0.1),
            make_record("second", provider="good", min_ram_gb=0.2),
        ],
        {"slow": slow, "good": good},
    )
    result = asyncio.run(router.generate(GenerationRequest(prompt="hi", purpose="fallback")))
    assert result.model_id == "second"
    assert slow.calls and good.calls


def test_unusable_model_output_falls_back():
    garbage = MockProvider("garbage", behavior="garbage")
    good = MockProvider("good")
    router = healthy_registry(
        [
            make_record("broken", provider="garbage", min_ram_gb=0.1),
            make_record("working", provider="good", min_ram_gb=0.2),
        ],
        {"garbage": garbage, "good": good},
    )
    result = asyncio.run(router.generate(GenerationRequest(prompt="hi")))
    assert result.model_id == "working"


def test_all_candidates_failing_reports_every_attempt():
    a = MockProvider("a", behavior="down")
    b = MockProvider("b", behavior="timeout")
    router = healthy_registry(
        [
            make_record("m1", provider="a", min_ram_gb=0.1),
            make_record("m2", provider="b", min_ram_gb=0.2),
        ],
        {"a": a, "b": b},
    )
    with pytest.raises(ModelUnavailableError) as exc:
        asyncio.run(router.generate(GenerationRequest(prompt="hi")))
    assert set(exc.value.tried) == {"m1", "m2"}
    assert "every permitted model failed" in str(exc.value)


def test_generation_with_no_viable_model_raises_before_calling_anything():
    provider = MockProvider()
    router, _, _ = make_router([make_record("m1")], {"mock": provider})  # never probed
    with pytest.raises(ModelUnavailableError):
        asyncio.run(router.generate(GenerationRequest(prompt="hi")))
    assert provider.calls == [], "no provider should be invoked when selection fails"


# --------------------------------------------------------------------------- #
# Bounded concurrency and cancellation
# --------------------------------------------------------------------------- #


def test_concurrent_requests_are_bounded_by_policy():
    """§6.5/§18: inference must not spawn unbounded parallel work."""
    provider = MockProvider()
    router, _, _ = make_router(
        [make_record("m1")], {"mock": provider}, policy=InferencePolicy(max_concurrent_requests=1)
    )

    async def scenario() -> int:
        await router.probe_health(force=True)
        provider.block_until_released()

        async def one() -> None:
            await router.generate(GenerationRequest(prompt="hi"))

        tasks = [asyncio.create_task(one()) for _ in range(3)]
        await asyncio.sleep(0.05)
        provider.release()
        await asyncio.gather(*tasks)
        return provider.max_concurrent_observed

    assert asyncio.run(scenario()) == 1


def test_cancellation_propagates_and_is_not_swallowed():
    """The fallback loop must never catch CancelledError.

    Swallowing it would break the cooperative cancellation the P-01 task engine
    and the owner's emergency stop both rely on.
    """
    provider = MockProvider()
    router, _, _ = make_router([make_record("m1")], {"mock": provider})

    async def scenario() -> bool:
        await router.probe_health(force=True)
        provider.block_until_released()
        task = asyncio.create_task(router.generate(GenerationRequest(prompt="hi")))
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False

    assert asyncio.run(scenario()) is True


# --------------------------------------------------------------------------- #
# Usage accounting
# --------------------------------------------------------------------------- #


def test_local_inference_is_recorded_at_zero_cost():
    """§17/§25: local usage is accounted, but no cost is invented."""
    provider = MockProvider()
    router = healthy_registry([make_record("m1")], {"mock": provider})
    asyncio.run(router.generate(GenerationRequest(prompt="hi", purpose="planning")))

    history = router.usage_history
    assert len(history) == 1
    record = history[0]
    assert record.success is True
    assert record.local is True
    assert record.estimated_cost == 0.0
    assert record.prompt_tokens == 10 and record.completion_tokens == 20
    assert record.purpose == "planning"


def test_failed_attempts_are_recorded_too():
    provider = MockProvider("mock", behavior="down")
    router = healthy_registry([make_record("m1")], {"mock": provider})
    with pytest.raises(ModelUnavailableError):
        asyncio.run(router.generate(GenerationRequest(prompt="hi")))
    history = router.usage_history
    assert len(history) == 1
    assert history[0].success is False
    assert history[0].error


def test_cloud_cost_is_computed_from_declared_price():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("cloud-x", local=False, cost=2.0)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=True, max_cost_per_1k_tokens=10.0),
    )
    asyncio.run(router.generate(GenerationRequest(prompt="hi")))
    record = router.usage_history[0]
    assert record.local is False
    # 30 tokens at 2.0 per 1k = 0.06
    assert record.estimated_cost == pytest.approx(0.06)


def test_usage_listener_failure_does_not_abort_generation():
    provider = MockProvider()

    async def bad_listener(_record) -> None:
        raise RuntimeError("accounting backend unavailable")

    registry = ModelRegistry([make_record("m1")])
    router = ModelRouter(
        registry,
        {"mock": provider},
        policy=InferencePolicy(),
        resource_probe=lambda: ResourceSnapshot(available_ram_gb=3.0, cpu_percent=5.0),
        usage_listener=bad_listener,
    )
    asyncio.run(router.probe_health(force=True))
    result = asyncio.run(router.generate(GenerationRequest(prompt="hi")))
    assert result.text


def test_explain_describes_the_decision():
    provider = MockProvider()
    router = healthy_registry(
        [make_record("local-ok"), make_record("cloud-no", local=False, cost=1.0)],
        {"mock": provider},
        policy=InferencePolicy(cloud_enabled=False),
    )
    explanation = router.select(RouteRequirements()).explain()
    assert "selected local-ok" in explanation
    assert "cloud-no" in explanation
