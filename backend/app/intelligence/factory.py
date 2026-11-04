"""Composition root for the intelligence subsystem.

Kept separate from `core/application.py` so the intelligence package owns its own
construction rules, and so a test can build an engine without a database, a task
manager or an HTTP app.

The important behaviour here is honesty about the local runtime. When
`model_provider` is `"none"` — the default, and the truth on this hardware — the
router is built with `NoRuntimeProvider`, so any generation attempt returns a
clear limitation instead of a fabricated answer. Registering an Ollama adapter
does **not** download weights: it points at a server the owner must already be
running.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psutil

from ..core.config import Settings
from ..database.connection import Database
from ..tasks.manager import TaskManager
from .autonomy import AutonomyController
from .capabilities import CapabilityRegistry, default_capabilities
from .context import ContextManager
from .decisions import DecisionEngine
from .engine import IntelligenceEngine
from .missions import MissionInterpreter
from .orchestrator import DispatchPolicy, Orchestrator
from .output import StructuredOutputParser
from .planning import Planner, PlanValidator, ValidationPolicy
from .providers import ModelProvider, NoRuntimeProvider, OllamaProvider
from .reasoning import ReasoningPipeline
from .registry import ModelRegistry
from .repository import IntelligenceRepository
from .router import InferencePolicy, ModelRouter, ResourceSnapshot, UsageRecord
from .schemas import AutonomyLevel, ModelCapabilities, ModelRecord


def probe_host_resources() -> ResourceSnapshot:
    """Read real host capacity for admission control (§6.5, §18).

    Uses `psutil`, already a P-01 dependency for monitoring. `percent=False`
    avoids psutil's blocking sampling interval, so this stays cheap enough to
    call on every routing decision without adding latency to a request.
    """
    memory = psutil.virtual_memory()
    return ResourceSnapshot(
        available_ram_gb=memory.available / (1024 ** 3),
        cpu_percent=psutil.cpu_percent(interval=None),
        gpu_available=False,  # no GPU detection is claimed; see ADR-0015
        logical_cpus=psutil.cpu_count(logical=True) or 1,
    )


@dataclass
class IntelligenceServices:
    """Everything the API layer needs, bundled for wiring."""

    engine: IntelligenceEngine
    router: ModelRouter
    registry: ModelRegistry
    capabilities: CapabilityRegistry
    autonomy: AutonomyController
    orchestrator: Orchestrator | None
    planner: Planner
    decisions: DecisionEngine
    reasoning: ReasoningPipeline
    repository: IntelligenceRepository


def build_providers(settings: Settings) -> tuple[dict[str, ModelProvider], ModelRegistry, list[str]]:
    """Construct the provider adapters and registry the settings justify.

    Returns `(providers, registry, notes)` where `notes` records what was *not*
    configured, so the status endpoint can explain an empty registry instead of
    leaving the owner to guess.
    """
    providers: dict[str, ModelProvider] = {}
    registry = ModelRegistry()
    notes: list[str] = []

    if settings.model_provider == "ollama":
        providers["ollama"] = OllamaProvider(settings.ollama_base_url)
        if settings.registered_model_id:
            registry.register(ModelRecord(
                model_id=settings.registered_model_id,
                provider="ollama",
                local=True,
                capabilities=ModelCapabilities(
                    context_window=settings.registered_model_context_window,
                    min_ram_gb=settings.registered_model_min_ram_gb,
                    # Declared, not measured: a local GGUF model served by Ollama
                    # can return JSON, but whether it does so reliably depends on
                    # the specific weights, so this is a configuration claim the
                    # owner makes.
                    supports_structured_output=True,
                    supports_tool_calling=False,
                ),
                limitations=[
                    "declared capabilities are configuration, not measurement",
                    "no model weights are downloaded by AUTONOMUS",
                ],
            ))
        else:
            notes.append(
                "model_provider is 'ollama' but no model id is registered; set "
                "AUTONOMUS_REGISTERED_MODEL_ID to a model already pulled locally"
            )
    else:
        providers["none"] = NoRuntimeProvider("AUTONOMUS_MODEL_PROVIDER is 'none'")
        notes.append(
            "no inference runtime is configured: the engine runs deterministically "
            "and reports model-dependent work as unavailable"
        )

    if not settings.cloud_ai_enabled:
        notes.append(
            "cloud inference is disabled by the phase-flag control; no cloud model "
            "can be selected regardless of router policy"
        )
    return providers, registry, notes


def build_inference_policy(settings: Settings) -> InferencePolicy:
    return InferencePolicy(
        cloud_enabled=settings.cloud_ai_enabled,
        max_concurrent_requests=settings.inference_max_concurrent,
        ram_safety_fraction=settings.inference_ram_safety_fraction,
        max_cost_per_1k_tokens=settings.inference_max_cost_per_1k_tokens,
        default_timeout_seconds=settings.inference_timeout_seconds,
        health_max_age_seconds=settings.model_health_ttl_seconds,
        cloud_data_egress_permitted=settings.inference_cloud_egress_permitted,
    )


def build_intelligence(
    settings: Settings,
    db: Database,
    tasks: TaskManager,
) -> IntelligenceServices:
    """Assemble the intelligence subsystem from validated settings."""
    providers, registry, notes = build_providers(settings)
    repository = IntelligenceRepository(db)

    async def _record_usage(usage: UsageRecord) -> None:
        """Persist inference accounting (§17).

        Passed to the router as its usage listener, which the router already
        treats as best-effort: an accounting failure can never abort a
        generation. These rows are operational cost tracking and are never
        summed into business revenue or expenses.
        """
        await repository.record_usage(
            request_id=usage.request_id, provider=usage.provider, model_id=usage.model_id,
            local=usage.local, duration_ms=usage.duration_ms,
            prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
            estimated_cost=usage.estimated_cost, success=usage.success, error=usage.error,
            purpose=usage.purpose, correlation_id=usage.correlation_id,
        )

    router = ModelRouter(
        registry,
        providers,
        policy=build_inference_policy(settings),
        resource_probe=probe_host_resources,
        usage_listener=_record_usage,
    )

    capabilities = default_capabilities()
    autonomy = AutonomyController(initial=AutonomyLevel(settings.autonomy_level))
    planner = Planner(
        capabilities,
        validator=PlanValidator(capabilities, policy=ValidationPolicy(max_steps=settings.plan_max_steps)),
    )
    orchestrator = Orchestrator(
        db, tasks, capabilities, autonomy=autonomy, planner=planner,
        policy=DispatchPolicy(max_concurrent_per_mission=settings.mission_max_concurrent_tasks),
    )
    reasoning = ReasoningPipeline.build()
    parser = StructuredOutputParser(router)
    engine = IntelligenceEngine(
        router=router,
        capabilities=capabilities,
        autonomy=autonomy,
        orchestrator=orchestrator,
        interpreter=MissionInterpreter(),
        planner=planner,
        decisions=DecisionEngine(),
        context=ContextManager(token_budget=settings.context_token_budget),
        reasoning=reasoning,
        parser=parser,
        repository=repository,
    )
    # Configuration notes are surfaced through the status endpoint rather than
    # logged, so an operator can see why no model is registered.
    engine.configuration_notes = list(notes)
    return IntelligenceServices(
        engine=engine, router=router, registry=registry, capabilities=capabilities,
        autonomy=autonomy, orchestrator=orchestrator, planner=planner,
        decisions=engine.decisions, reasoning=reasoning, repository=repository,
    )


async def initialize(services: IntelligenceServices) -> dict[str, int]:
    """Async startup work that `build_intelligence` cannot do synchronously.

    Persists the configured model registrations and reloads any missions that
    were stored before the last shutdown. Recovery restores *visibility* only:
    nothing is re-planned, re-dispatched or re-authorized, because §15 requires
    execution authority to be granted explicitly each time. Tasks a mission had
    already dispatched remain the P-01 task manager's responsibility, which
    performs its own interrupted-task recovery.
    """
    for record in services.registry.all():
        await services.repository.upsert_model(record)
    recovered = await services.engine.recover()
    return {"models_persisted": len(services.registry.all()), "missions_recovered": recovered}


__all__ = [
    "IntelligenceServices",
    "build_intelligence",
    "initialize",
    "build_inference_policy",
    "build_providers",
    "probe_host_resources",
]
