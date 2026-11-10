"""Model router (P-02).

Policy: task class -> enabled model profiles (smallest first) -> provider
availability probe -> resource check via the P-01 monitor -> pick the
smallest sufficient AVAILABLE local option. Cloud is considered only for
profiles whose provider is "cloud" AND the owner has enabled cloud AI;
the cloud stub honestly reports unavailable in P-02, so it is never
selected. When nothing qualifies, the router returns the deterministic
baseline path WITH REASONS — every selection (and every skip) is returned
so the caller can write it to decision_records.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..database.repositories.intelligence import ModelProfileRepository


@dataclass
class RouterDecision:
    kind: str  # "llm" | "baseline"
    provider_name: str | None = None
    profile_name: str | None = None
    model_id: str | None = None
    reasons: list[str] = field(default_factory=list)


class ModelRouter:
    def __init__(self, session_factory, providers: dict, monitor=None):
        self._session_factory = session_factory
        self._providers = providers
        self._monitor = monitor

    def _profiles_for(self, task_class: str):
        session = self._session_factory()
        try:
            profiles = ModelProfileRepository(session).list()
        finally:
            session.close()
        candidates = [
            p for p in profiles
            if p.enabled and p.model_id
            and (task_class in (p.task_classes or []) or "*" in (p.task_classes or []))
        ]
        candidates.sort(key=lambda p: (p.limits or {}).get("size_rank", 100))
        return candidates

    async def select(self, task_class: str) -> RouterDecision:
        reasons: list[str] = []
        candidates = self._profiles_for(task_class)
        if not candidates:
            reasons.append(
                f"no enabled model profile with a configured model_id covers "
                f"task class '{task_class}'; using the deterministic baseline planner")
            return RouterDecision(kind="baseline", reasons=reasons)

        violations = []
        if self._monitor is not None:
            try:
                violations = self._monitor.threshold_violations()
            except Exception:
                violations = []

        for profile in candidates:
            provider = self._providers.get(profile.provider)
            if provider is None:
                reasons.append(
                    f"profile '{profile.name}': provider '{profile.provider}' is not "
                    "registered in this build; skipped")
                continue
            if violations and (profile.limits or {}).get("requires_headroom"):
                reasons.append(
                    f"profile '{profile.name}' requires resource headroom but "
                    f"thresholds are violated ({[v['resource'] for v in violations]}); "
                    "deferred under resource pressure")
                continue
            available, detail = await provider.probe()
            if not available:
                reasons.append(f"profile '{profile.name}' ({profile.provider}): {detail}; skipped")
                continue
            reasons.append(
                f"selected profile '{profile.name}' ({profile.provider}:{profile.model_id}) "
                f"for task class '{task_class}': smallest available sufficient option")
            return RouterDecision(
                kind="llm", provider_name=profile.provider,
                profile_name=profile.name, model_id=profile.model_id, reasons=reasons)

        reasons.append("no candidate profile was available; using the deterministic baseline planner")
        return RouterDecision(kind="baseline", reasons=reasons)
