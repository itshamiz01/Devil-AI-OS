"""P-03 §8 research sources and §27 the security boundary around them.

Three rules govern this module, and they are the reason it looks more
defensive than a typical HTTP wrapper:

1. **Deny by default.**  :class:`NetworkPolicy` starts with an empty permitted
   host set.  A source is reachable only if the owner has explicitly authorised
   its host.  Nothing is assumed available because it "usually is".
2. **Refusal is a first-class result.**  An adapter that cannot reach its
   source returns a :class:`SourceRefusal` naming the reason.  It never returns
   empty content that a caller might mistake for "the market is quiet", and it
   never invents a plausible response.
3. **Retrieved content stays untrusted.**  Credentials never enter a
   :class:`~app.opportunities.schemas.RetrievedContent`, response bodies are
   size-capped, and the payload is data - not instructions - for every layer
   above this one.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.exceptions import AppError
from app.intelligence.schemas import EvidenceReliability, TrustDomain
from app.opportunities.schemas import (
    AcquisitionMethod,
    RetrievedContent,
    SourceDescriptor,
    SourceStatus,
    SourceType,
)

__all__ = [
    "FetchResult",
    "MAX_RESPONSE_CHARS",
    "HttpSourceAdapter",
    "MockSourceAdapter",
    "NetworkPolicy",
    "RefusalCategory",
    "SourceAdapter",
    "SourceAuthorisationError",
    "SourceNotFoundError",
    "SourceRefusal",
    "RefusalCategory",
    "SourceRegistry",
    "UnreachableSourceAdapter",
]

#: Hard cap on retained response text.  A research payload has no business
#: being megabytes, and an unbounded read is both a memory risk (§30) and a
#: prompt-injection surface (§27).
MAX_RESPONSE_CHARS = 200_000

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|password|passwd|authorization)\b"),
)


class RefusalCategory(str, Enum):
    """Why an acquisition did not happen.

    These are reported verbatim in research output.  ``NETWORK_UNREACHABLE`` is
    expected to be the dominant category in a sandboxed deployment, and saying
    so is correct behaviour - not a defect to be worked around.
    """

    NOT_CONFIGURED = "not_configured"
    NOT_AUTHORIZED = "not_authorized"
    HOST_NOT_PERMITTED = "host_not_permitted"
    NETWORK_UNREACHABLE = "network_unreachable"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_FAILED = "authentication_failed"
    POLICY_FORBIDDEN = "policy_forbidden"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    RESPONSE_TOO_LARGE = "response_too_large"
    MALFORMED_RESPONSE = "malformed_response"


class SourceNotFoundError(AppError):
    """Raised when a source_id is not registered."""

    status_code = 404
    code = "source_not_found"


class SourceAuthorisationError(AppError):
    """Raised when an operation is attempted on an unauthorised source."""

    status_code = 403
    code = "source_not_authorized"


class NetworkPolicy(BaseModel):
    """The allowlist that decides what this deployment may contact at all.

    ``permitted_hosts`` defaults to empty: **deny everything**.  Hosts are added
    only from explicit owner configuration, which keeps §26 (no unauthorised
    external contact) and §27 (network access restricted to approved adapters)
    true by construction rather than by convention.
    """

    model_config = ConfigDict(extra="forbid")

    permitted_hosts: frozenset[str] = frozenset()
    allow_any_https: bool = False
    request_timeout_seconds: float = Field(default=15.0, gt=0, le=300)
    max_response_chars: int = Field(default=MAX_RESPONSE_CHARS, gt=0, le=2_000_000)
    max_requests_per_minute_per_source: int = Field(default=10, ge=0, le=1000)
    user_agent: str = Field(
        default="AUTONOMUS-P03/1.0 (research; owner-authorized)", max_length=200
    )
    follow_redirects: bool = False

    @field_validator("permitted_hosts")
    @classmethod
    def _normalise_hosts(cls, value: Iterable[str]) -> frozenset[str]:
        out = set()
        for raw in value:
            host = raw.strip().lower()
            if not host:
                continue
            parsed = urlparse(host if "//" in host else f"//{host}")
            candidate = (parsed.hostname or host).lower().rstrip(".")
            if not re.fullmatch(r"[a-z0-9.\-]{1,253}", candidate):
                raise ValueError(f"'{raw}' is not a valid hostname")
            out.add(candidate)
        return frozenset(out)

    @model_validator(mode="after")
    def _redirects_need_allowlist(self) -> "NetworkPolicy":
        """Following redirects can leave the allowlist, so it is refused unless
        the allowlist is explicitly wide open."""
        if self.follow_redirects and not self.allow_any_https and not self.permitted_hosts:
            raise ValueError(
                "follow_redirects=True with an empty allowlist is refused: a "
                "redirect could leave the permitted host set"
            )
        return self

    def host_permitted(self, url: str) -> bool:
        if self.allow_any_https:
            return True
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return False
        if host in self.permitted_hosts:
            return True
        # A subdomain of a permitted registrable host is permitted
        # (api.example.com when example.com is allowed), never the reverse.
        return any(host.endswith(f".{allowed}") for allowed in self.permitted_hosts)


class SourceRefusal(BaseModel):
    """An honest failure to acquire data."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    operation: str
    category: RefusalCategory
    detail: str = Field(min_length=1)
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    url: str | None = Field(default=None, max_length=2048)
    http_status: int | None = Field(default=None, ge=100, le=599)
    retryable: bool = False

    @field_validator("detail")
    @classmethod
    def _no_secrets_in_detail(cls, value: str) -> str:
        """A refusal message is surfaced in reports and logs; it must never
        carry a credential (§27)."""
        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                raise ValueError(
                    "refusal detail appears to contain a credential and was rejected"
                )
        return value


class FetchResult(BaseModel):
    """Exactly one of ``content`` or ``refusal`` is set."""

    model_config = ConfigDict(extra="forbid")

    content: RetrievedContent | None = None
    refusal: SourceRefusal | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "FetchResult":
        if (self.content is None) == (self.refusal is None):
            raise ValueError("FetchResult must carry exactly one of content/refusal")
        return self

    @property
    def ok(self) -> bool:
        return self.content is not None

    @classmethod
    def refused(cls, refusal: SourceRefusal) -> "FetchResult":
        return cls(refusal=refusal)

    @classmethod
    def fetched(cls, content: RetrievedContent) -> "FetchResult":
        return cls(content=content)


class SourceAdapter(Protocol):
    """What every source implementation must provide (§8).

    Provider-independent by design: the registry, the research workflow and the
    scoring layer only ever see this interface, so adding a provider cannot
    change how evidence is classified.
    """

    descriptor: SourceDescriptor

    def fetch(self, operation: str, params: dict[str, Any]) -> FetchResult:
        ...


class UnreachableSourceAdapter:
    """The adapter used for any source this deployment cannot actually contact.

    It performs no I/O and always refuses.  This is what every real market
    research source resolves to in a sandbox without outbound network access -
    and reporting that truthfully is the whole point of the class.
    """

    def __init__(self, descriptor: SourceDescriptor, *, reason: str | None = None):
        self.descriptor = descriptor
        self._reason = reason or (
            f"source '{descriptor.name}' could not be contacted from this "
            "deployment; no outbound network route is available to it"
        )

    def fetch(self, operation: str, params: dict[str, Any]) -> FetchResult:
        return FetchResult.refused(
            SourceRefusal(
                source_id=self.descriptor.source_id,
                operation=operation,
                category=RefusalCategory.NETWORK_UNREACHABLE,
                detail=self._reason,
                url=self.descriptor.endpoint_template,
                retryable=False,
            )
        )


class HttpSourceAdapter:
    """Real HTTP acquisition, gated by :class:`NetworkPolicy`.

    The transport is injected so tests can exercise every branch - allowlist
    refusal, timeout, oversized body, non-200 - without touching a network.
    """

    def __init__(
        self,
        descriptor: SourceDescriptor,
        policy: NetworkPolicy,
        *,
        transport: Any = None,
        credentials: dict[str, str] | None = None,
    ):
        self.descriptor = descriptor
        self.policy = policy
        self._transport = transport
        # Held here and never copied into RetrievedContent (§27).
        self._credentials = dict(credentials or {})

    def _build_url(self, operation: str, params: dict[str, Any]) -> str | None:
        template = self.descriptor.endpoint_template
        if not template:
            return None
        url = template
        for key, value in params.items():
            url = url.replace(f"{{{key}}}", str(value))
        return url

    def fetch(self, operation: str, params: dict[str, Any]) -> FetchResult:
        sid = self.descriptor.source_id
        if self.descriptor.status is not SourceStatus.AUTHORIZED:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.NOT_AUTHORIZED,
                    detail=f"source status is {self.descriptor.status.value}, not authorized",
                )
            )
        if operation not in self.descriptor.supported_operations:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.UNSUPPORTED_OPERATION,
                    detail=(
                        f"source '{self.descriptor.name}' does not support "
                        f"'{operation}'; supported: "
                        f"{', '.join(self.descriptor.supported_operations) or 'none'}"
                    ),
                )
            )
        url = self._build_url(operation, params)
        if url is None:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.INVALID_REQUEST,
                    detail="source has no endpoint_template configured",
                )
            )
        if not self.policy.host_permitted(url):
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.HOST_NOT_PERMITTED,
                    detail=(
                        f"host for '{url}' is not in the owner-authorized "
                        "network allowlist; refusing to contact it"
                    ),
                    url=url,
                )
            )
        if self._transport is None:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.NETWORK_UNREACHABLE,
                    detail="no HTTP transport is configured for this deployment",
                    url=url,
                )
            )
        try:
            response = self._transport.get(
                url,
                timeout=self.policy.request_timeout_seconds,
                headers={"User-Agent": self.policy.user_agent},
                follow_redirects=self.policy.follow_redirects,
            )
        except Exception as exc:  # noqa: BLE001 - converted into a refusal
            category = (
                RefusalCategory.TIMEOUT
                if "timeout" in type(exc).__name__.lower()
                or "timed out" in str(exc).lower()
                else RefusalCategory.NETWORK_UNREACHABLE
            )
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=category,
                    detail=f"{type(exc).__name__}: {exc}"[:400],
                    url=url,
                    retryable=category is RefusalCategory.TIMEOUT,
                )
            )

        status = int(getattr(response, "status_code", 0) or 0)
        if status == 429:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.RATE_LIMITED,
                    detail="source returned HTTP 429 (rate limited)",
                    url=url,
                    http_status=status,
                    retryable=True,
                )
            )
        if status in {401, 403}:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.AUTHENTICATION_FAILED,
                    detail=f"source returned HTTP {status}; credentials absent or rejected",
                    url=url,
                    http_status=status,
                    retryable=False,
                )
            )
        if not 200 <= status < 300:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.MALFORMED_RESPONSE,
                    detail=f"source returned unexpected HTTP {status}",
                    url=url,
                    http_status=status,
                    retryable=500 <= status < 600,
                )
            )

        body = str(getattr(response, "text", "") or "")
        raw_bytes = len(body.encode("utf-8", errors="replace"))
        if len(body) > self.policy.max_response_chars:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.RESPONSE_TOO_LARGE,
                    detail=(
                        f"response of {len(body)} characters exceeds the "
                        f"{self.policy.max_response_chars} character cap"
                    ),
                    url=url,
                    http_status=status,
                )
            )
        return FetchResult.fetched(
            RetrievedContent(
                source_id=sid,
                retrieved_at=datetime.now(timezone.utc),
                url=url,
                http_status=status,
                body_text=body,
                trust_domain=TrustDomain.EXTERNAL,
                bytes_received=raw_bytes,
            )
        )


class MockSourceAdapter:
    """Deterministic fixture adapter used for tests and for the sample report.

    Everything it returns is stamped ``MOCK`` and its descriptor reliability is
    ``UNTRUSTED``, so mock data can never be mistaken for acquired market
    evidence downstream.  §31 requires the sample opportunity report to use
    clearly labelled test data; this is the mechanism that enforces the label.
    """

    def __init__(
        self,
        descriptor: SourceDescriptor,
        fixtures: dict[str, list[dict[str, Any]]],
    ):
        if descriptor.source_type is not SourceType.MOCK:
            raise ValueError(
                "MockSourceAdapter requires a descriptor with source_type=MOCK; "
                "mock data must never masquerade as a real source"
            )
        if descriptor.reliability is not EvidenceReliability.UNTRUSTED:
            raise ValueError(
                "a mock source must declare reliability=UNTRUSTED"
            )
        self.descriptor = descriptor
        self._fixtures = {k: list(v) for k, v in fixtures.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def fetch(self, operation: str, params: dict[str, Any]) -> FetchResult:
        self.calls.append((operation, dict(params)))
        sid = self.descriptor.source_id
        if operation not in self._fixtures:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=sid,
                    operation=operation,
                    category=RefusalCategory.UNSUPPORTED_OPERATION,
                    detail=(
                        f"mock source has no fixture for '{operation}'; "
                        f"available: {', '.join(sorted(self._fixtures)) or 'none'}"
                    ),
                )
            )
        rows = self._fixtures[operation]
        query = str(params.get("query", "")).lower()
        if query:
            rows = [r for r in rows if query in str(r).lower()] or rows
        return FetchResult.fetched(
            RetrievedContent(
                source_id=sid,
                retrieved_at=datetime.now(timezone.utc),
                url=f"mock://{sid}/{operation}",
                http_status=200,
                body_text=json.dumps({"mock": True, "rows": rows}),
                structured={"mock": True, "rows": rows},
                bytes_received=len(json.dumps(rows)),
            )
        )


class SourceRegistry:
    """The single gate between the discovery engine and the outside world.

    All acquisition goes through :meth:`fetch`, which enforces authorisation
    before delegating to an adapter.  An adapter can therefore never be reached
    for a source the owner has not authorised.
    """

    def __init__(self, policy: NetworkPolicy | None = None):
        self.policy = policy or NetworkPolicy()
        self._descriptors: dict[str, SourceDescriptor] = {}
        self._adapters: dict[str, SourceAdapter] = {}

    def register(
        self, descriptor: SourceDescriptor, adapter: SourceAdapter | None = None
    ) -> SourceDescriptor:
        if descriptor.source_id in self._descriptors:
            raise ValueError(f"source '{descriptor.source_id}' is already registered")
        chosen: SourceAdapter
        if adapter is not None:
            if adapter.descriptor.source_id != descriptor.source_id:
                raise ValueError(
                    "adapter descriptor does not match the descriptor being registered"
                )
            chosen = adapter
        elif descriptor.access_method is AcquisitionMethod.MOCK_ADAPTER:
            raise ValueError(
                "a MOCK_ADAPTER source must be registered with an explicit "
                "MockSourceAdapter; the registry will not invent fixture data"
            )
        elif descriptor.access_method is AcquisitionMethod.UNAVAILABLE or (
            descriptor.status is not SourceStatus.AUTHORIZED
        ):
            chosen = UnreachableSourceAdapter(descriptor)
        else:
            chosen = HttpSourceAdapter(descriptor, self.policy)
        self._descriptors[descriptor.source_id] = descriptor
        self._adapters[descriptor.source_id] = chosen
        return descriptor

    def get(self, source_id: str) -> SourceDescriptor:
        try:
            return self._descriptors[source_id]
        except KeyError:
            raise SourceNotFoundError(
                f"source '{source_id}' is not registered"
            ) from None

    def adapter(self, source_id: str) -> SourceAdapter:
        self.get(source_id)
        return self._adapters[source_id]

    def set_status(self, source_id: str, status: SourceStatus) -> SourceDescriptor:
        descriptor = self.get(source_id)
        updated = descriptor.model_copy(update={"status": status})
        self._descriptors[source_id] = updated
        # Swap the adapter so an authorisation change takes effect immediately.
        current = self._adapters[source_id]
        if isinstance(current, (UnreachableSourceAdapter, HttpSourceAdapter)):
            self._adapters[source_id] = (
                HttpSourceAdapter(updated, self.policy)
                if status is SourceStatus.AUTHORIZED
                and updated.access_method is not AcquisitionMethod.UNAVAILABLE
                and updated.access_method is not AcquisitionMethod.MOCK_ADAPTER
                else UnreachableSourceAdapter(updated)
            )
        else:
            # A MockSourceAdapter keeps its fixtures; only its descriptor changes.
            current.descriptor = updated
        return updated

    def list_sources(self, *, status: SourceStatus | None = None) -> list[SourceDescriptor]:
        items = sorted(self._descriptors.values(), key=lambda d: d.source_id)
        return [d for d in items if status is None or d.status is status]

    def by_type(self, source_type: SourceType) -> list[SourceDescriptor]:
        return [d for d in self.list_sources() if d.source_type is source_type]

    def authorized_operations(self, source_id: str) -> tuple[str, ...]:
        descriptor = self.get(source_id)
        if descriptor.status is not SourceStatus.AUTHORIZED:
            return ()
        return descriptor.supported_operations

    def fetch(
        self, source_id: str, operation: str, params: dict[str, Any] | None = None
    ) -> FetchResult:
        """Acquire from one source, or return an honest refusal."""
        descriptor = self.get(source_id)
        params = dict(params or {})
        if descriptor.status is SourceStatus.FORBIDDEN_BY_POLICY:
            return FetchResult.refused(
                SourceRefusal(
                    source_id=source_id,
                    operation=operation,
                    category=RefusalCategory.POLICY_FORBIDDEN,
                    detail=f"source '{descriptor.name}' is forbidden by policy",
                )
            )
        return self._adapters[source_id].fetch(operation, params)

    def fetch_many(
        self,
        source_ids: Iterable[str],
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, FetchResult]:
        """Acquire the same operation from several sources.

        Returns one result per requested source, **always** - including
        refusals - so a partially failed sweep stays visible instead of being
        silently truncated.

        An unregistered id does not abort the sweep: it is reported as a
        ``NOT_CONFIGURED`` refusal against that id, which is deliberately a
        different category from ``NETWORK_UNREACHABLE``.  A misconfigured source
        list must be distinguishable from a source that exists but could not be
        contacted, otherwise a typo looks like an outage.

        :meth:`fetch` (single source) still raises ``SourceNotFoundError``,
        because a direct call naming an unknown source is a programming error
        that should fail loudly at the call site.
        """
        results: dict[str, FetchResult] = {}
        for sid in source_ids:
            if sid in results:
                continue
            try:
                results[sid] = self.fetch(sid, operation, params)
            except SourceNotFoundError:
                results[sid] = FetchResult.refused(
                    SourceRefusal(
                        source_id=sid,
                        operation=operation,
                        category=RefusalCategory.NOT_CONFIGURED,
                        detail=(
                            f"source '{sid}' is not registered in this deployment; "
                            "it was requested as part of a sweep"
                        ),
                        retryable=False,
                    )
                )
        return results

    def snapshot(self) -> dict[str, Any]:
        """Status summary for the API and reports.  Carries no credentials."""
        return {
            "registered": len(self._descriptors),
            "authorized": len(self.list_sources(status=SourceStatus.AUTHORIZED)),
            "permitted_hosts": sorted(self.policy.permitted_hosts),
            "allow_any_https": self.policy.allow_any_https,
            "by_status": {
                s.value: len(self.list_sources(status=s)) for s in SourceStatus
            },
            "sources": [
                {
                    "source_id": d.source_id,
                    "name": d.name,
                    "type": d.source_type.value,
                    "status": d.status.value,
                    "access_method": d.access_method.value,
                    "operations": list(d.supported_operations),
                    "reliability": d.reliability.value,
                    "licensing": d.licensing,
                }
                for d in self.list_sources()
            ],
        }
