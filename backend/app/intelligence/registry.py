"""Model registry (P-02 §6.2).

The registry is the single source of truth about which models exist, what they
can do, and whether they are currently usable. It is deliberately separate from
the router: the registry records facts, the router makes choices.

Nothing here contacts a model. Health is *pushed in* by the router after it
probes a provider, which keeps this module deterministic and trivially testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from .schemas import ModelCapabilities, ModelHealth, ModelRecord


class UnknownModelError(KeyError):
    """Raised when a model identifier is not registered.

    A KeyError subclass so existing error handling still catches it, but with a
    message that names the problem instead of printing a bare string.
    """

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        super().__init__(f"model {model_id!r} is not registered")


class ModelRegistry:
    """In-memory registry of declared models and their observed health.

    Concurrency: registration and health updates are guarded by a lock because
    the router probes health from concurrent tasks. Reads return copies, so a
    caller can never mutate registry state by accident.
    """

    def __init__(self, records: list[ModelRecord] | None = None) -> None:
        self._records: dict[str, ModelRecord] = {}
        self._health: dict[str, ModelHealth] = {}
        self._lock = Lock()
        for record in records or []:
            self.register(record)

    # -- registration ------------------------------------------------------ #

    def register(self, record: ModelRecord, *, replace: bool = False) -> None:
        """Add a model. Re-registering without `replace` is an error.

        Silently overwriting a record could change a model's declared cost or
        privacy limits underneath the router, which §6.3 treats as a policy
        input rather than a detail.
        """
        with self._lock:
            if record.model_id in self._records and not replace:
                raise ValueError(
                    f"model {record.model_id!r} is already registered; "
                    "pass replace=True to update it deliberately"
                )
            self._records[record.model_id] = record

    def unregister(self, model_id: str) -> None:
        with self._lock:
            self._records.pop(model_id, None)
            self._health.pop(model_id, None)

    # -- reads ------------------------------------------------------------- #

    def get(self, model_id: str) -> ModelRecord:
        with self._lock:
            try:
                return self._records[model_id].model_copy(deep=True)
            except KeyError:
                raise UnknownModelError(model_id) from None

    def all(self) -> list[ModelRecord]:
        with self._lock:
            return [r.model_copy(deep=True) for r in self._records.values()]

    def local_models(self) -> list[ModelRecord]:
        return [r for r in self.all() if r.local]

    def cloud_models(self) -> list[ModelRecord]:
        return [r for r in self.all() if not r.local]

    def by_provider(self, provider: str) -> list[ModelRecord]:
        return [r for r in self.all() if r.provider == provider]

    def capabilities(self, model_id: str) -> ModelCapabilities | None:
        try:
            return self.get(model_id).capabilities
        except UnknownModelError:
            return None

    # -- health ------------------------------------------------------------ #

    def set_health(self, model_id: str, health: ModelHealth) -> None:
        with self._lock:
            if model_id not in self._records:
                raise UnknownModelError(model_id)
            self._health[model_id] = health

    def health(self, model_id: str) -> ModelHealth | None:
        with self._lock:
            health = self._health.get(model_id)
            return health.model_copy(deep=True) if health else None

    def is_healthy(self, model_id: str) -> bool:
        """True only when a probe has *confirmed* health.

        Unknown is treated as unhealthy for routing purposes: §6.4 requires the
        router to detect provider failure rather than optimistically assume a
        model works and discover otherwise mid-request.
        """
        health = self.health(model_id)
        return bool(health and health.healthy)

    def available_models(self, *, local_only: bool = False) -> list[ModelRecord]:
        """Models that are declared available and confirmed healthy."""
        return [
            r
            for r in self.all()
            if r.available and self.is_healthy(r.model_id) and (not local_only or r.local)
        ]

    def stale_health(self, max_age_seconds: float) -> list[str]:
        """Model ids whose health probe is older than the given age.

        The router uses this to decide when to re-probe instead of trusting a
        health result from before a model server went away.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
        with self._lock:
            items = list(self._health.items())
        return [
            model_id
            for model_id, health in items
            if _as_timestamp(health.checked_at) < cutoff
        ]


def _as_timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()
