"""Context management (P-02 §12).

Assembles what the reasoning layer is allowed to see, in priority order, within
a token budget — and defends the instruction channel from untrusted content.

The rule that shapes this module is §12.3: *never silently remove critical
financial or security constraints during context reduction*. So a protected item
is never dropped to fit a budget. If the protected items alone exceed the budget,
assembly fails loudly instead of quietly truncating the owner's financial limit
out of the prompt — losing a budget cap silently is precisely how a system
overspends.

P-09 will replace this with the full Memory and Continuous Learning Engine. This
module establishes the interface only; it does not implement persistent memory,
and nothing here claims to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum

from .missions import MissionInterpreter
from .prompts import fence_untrusted
from .router import estimate_tokens
from .schemas import Constraint, Mission, TrustDomain


class ContextPriority(IntEnum):
    """§12.2 — lower value means higher priority.

    The ordering is the policy: explicit current instructions outrank everything,
    so stale or contradictory context can never silently override what the owner
    just said.
    """

    OWNER_INSTRUCTION = 0
    MISSION_REQUIREMENT = 1
    APPROVED_CONSTRAINT = 2
    VERIFIED_EVIDENCE = 3
    PRIOR_DECISION = 4
    OPTIONAL = 5


@dataclass
class ContextItem:
    """One unit of context, with its provenance and protection status."""

    content: str
    source: str
    priority: ContextPriority
    trust_domain: TrustDomain = TrustDomain.SYSTEM
    #: Protected items survive any budget reduction (§12.3).
    protected: bool = False
    mission_id: str | None = None
    #: 0.0–1.0, used to order items within the same priority when trimming.
    relevance: float = 1.0
    tokens: int = 0

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = estimate_tokens(len(self.content))
        # External content is never protected: protection means "must reach the
        # model unchanged", and granting that to untrusted text would let a
        # retrieved document force itself into every prompt.
        if self.trust_domain == TrustDomain.EXTERNAL:
            self.protected = False


@dataclass
class InjectionFinding:
    """A detected attempt by external content to act as instructions."""

    kind: str
    matched_text: str
    source: str


@dataclass
class AssembledContext:
    """The result of assembly, including what was dropped and why."""

    items: list[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    token_budget: int = 0
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (source, reason)
    deduplicated: int = 0
    warnings: list[str] = field(default_factory=list)
    #: True when even protected items did not all fit.
    overflowed: bool = False

    @property
    def utilised(self) -> float:
        return (self.total_tokens / self.token_budget) if self.token_budget else 0.0

    def sources(self) -> list[str]:
        """Provenance list, in the order items will be rendered (§12.3)."""
        return [i.source for i in self.items]


class ContextOverflowError(RuntimeError):
    """Raised when protected context cannot fit the budget.

    Failing is correct: the alternative is silently dropping a financial or
    security constraint, which §12.3 forbids.
    """

    def __init__(self, needed: int, budget: int, protected_sources: list[str]) -> None:
        self.needed = needed
        self.budget = budget
        self.protected_sources = protected_sources
        super().__init__(
            f"protected context needs {needed} tokens but the budget is {budget}; "
            f"refusing to drop: {', '.join(protected_sources) or '<none>'}"
        )


class ContextManager:
    """Assembles, prioritises and budgets context."""

    #: Default budget for a small local model on a 3.85 GiB host. Deliberately
    #: modest: an oversized prompt on this hardware would time out rather than
    #: produce a better answer (§18).
    DEFAULT_TOKEN_BUDGET = 2048

    def __init__(
        self,
        *,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        interpreter: MissionInterpreter | None = None,
    ) -> None:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        self.token_budget = token_budget
        self._interpreter = interpreter or MissionInterpreter()

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #

    def from_owner_request(self, text: str, *, mission_id: str | None = None) -> ContextItem:
        return ContextItem(
            content=text,
            source="owner.current_request",
            priority=ContextPriority.OWNER_INSTRUCTION,
            trust_domain=TrustDomain.OWNER,
            protected=True,  # the current instruction is never trimmed away
            mission_id=mission_id,
        )

    def from_mission(self, mission: Mission) -> list[ContextItem]:
        """Mission facts, with hard constraints protected (§12.2, §12.3)."""
        items: list[ContextItem] = [
            ContextItem(
                content=f"Mission objective: {mission.objective or mission.title}",
                source=f"mission.{mission.mission_id}.objective",
                priority=ContextPriority.MISSION_REQUIREMENT,
                trust_domain=TrustDomain.OWNER,
                protected=True,
                mission_id=mission.mission_id,
            )
        ]
        for constraint in mission.constraints:
            items.append(self.from_constraint(constraint, mission_id=mission.mission_id))
        if mission.success_criteria:
            items.append(ContextItem(
                content="Success criteria: " + "; ".join(mission.success_criteria),
                source=f"mission.{mission.mission_id}.success_criteria",
                priority=ContextPriority.MISSION_REQUIREMENT,
                trust_domain=TrustDomain.OWNER,
                protected=True,
                mission_id=mission.mission_id,
            ))
        if mission.assumptions:
            items.append(ContextItem(
                content="Recorded assumptions: " + "; ".join(mission.assumptions),
                source=f"mission.{mission.mission_id}.assumptions",
                priority=ContextPriority.OPTIONAL,
                trust_domain=TrustDomain.SYSTEM,
                mission_id=mission.mission_id,
                relevance=0.5,
            ))
        return items

    def from_constraint(self, constraint: Constraint, *, mission_id: str | None = None) -> ContextItem:
        """A constraint as context. Budget and policy constraints are protected.

        This is the concrete mechanism behind §12.3: a financial limit is marked
        protected at the point it enters context, so no later trimming pass can
        remove it.
        """
        protected = constraint.kind in {"budget", "policy", "risk"} or constraint.required
        origin_note = {
            "owner_stated": "stated by the owner",
            "system_default": "system policy",
            "inferred": "inferred",
            "assumed": "assumed — not owner-authorized",
        }[constraint.origin]
        return ContextItem(
            content=f"Constraint ({constraint.kind}, {origin_note}): {constraint.value}",
            source=f"constraint.{constraint.kind}",
            priority=ContextPriority.APPROVED_CONSTRAINT,
            trust_domain=TrustDomain.OWNER if constraint.origin == "owner_stated" else TrustDomain.SYSTEM,
            protected=protected,
            mission_id=mission_id,
            relevance=1.0 if protected else 0.7,
        )

    def from_evidence(self, *, observation: str, source: str, verified: bool,
                      mission_id: str | None = None) -> ContextItem:
        """Evidence as context. Verified ranks above unverified (§12.2)."""
        return ContextItem(
            content=observation,
            source=source,
            priority=ContextPriority.VERIFIED_EVIDENCE if verified else ContextPriority.OPTIONAL,
            trust_domain=TrustDomain.VERIFIED if verified else TrustDomain.EXTERNAL,
            mission_id=mission_id,
            relevance=0.9 if verified else 0.4,
        )

    def from_decision(self, *, summary: str, decision_id: str, mission_id: str | None = None) -> ContextItem:
        return ContextItem(
            content=f"Prior decision {decision_id}: {summary}",
            source=f"decision.{decision_id}",
            priority=ContextPriority.PRIOR_DECISION,
            trust_domain=TrustDomain.SYSTEM,
            mission_id=mission_id,
            relevance=0.6,
        )

    def from_capability_registry(self, capability_ids: list[str]) -> ContextItem:
        return ContextItem(
            content="Available capabilities: " + ", ".join(sorted(capability_ids)),
            source="system.capability_registry",
            priority=ContextPriority.APPROVED_CONSTRAINT,
            trust_domain=TrustDomain.SYSTEM,
            protected=True,  # the model must not be allowed to forget what exists
            relevance=1.0,
        )

    def from_external(self, *, content: str, source: str, mission_id: str | None = None) -> ContextItem:
        """Untrusted retrieved content (§12.4).

        Marked EXTERNAL so it is fenced at render time and can never be treated
        as an instruction, a constraint, or a protected item.
        """
        return ContextItem(
            content=content,
            source=source,
            priority=ContextPriority.OPTIONAL,
            trust_domain=TrustDomain.EXTERNAL,
            protected=False,
            mission_id=mission_id,
            relevance=0.3,
        )

    # ------------------------------------------------------------------ #
    # Injection detection
    # ------------------------------------------------------------------ #

    def scan_untrusted(self, text: str, *, source: str) -> list[InjectionFinding]:
        """Detect instruction-shaped content inside untrusted text (§12.4).

        Detection is a *reporting* mechanism, not the defence. The defence is
        structural: untrusted text is fenced and is never parsed as an
        instruction by this codebase. Flagging matters because §20 Scenario G
        requires a security event to be recorded.
        """
        findings: list[InjectionFinding] = []
        if self._interpreter.detect_override_attempt(text):
            match = re.search(
                r"\b(?:ignore|disregard|bypass|override|disable|forget)\b[^.]{0,60}", text, re.IGNORECASE
            )
            findings.append(InjectionFinding(
                kind="policy_override_attempt",
                matched_text=(match.group(0) if match else text)[:120],
                source=source,
            ))
        if self._interpreter.detect_secret_request(text):
            match = re.search(
                r"\b(?:reveal|show|print|dump|expose|leak|give)\b[^.]{0,60}", text, re.IGNORECASE
            )
            findings.append(InjectionFinding(
                kind="secret_exfiltration_attempt",
                matched_text=(match.group(0) if match else text)[:120],
                source=source,
            ))
        # Fence markers inside external text are an escape attempt.
        if "<<<UNTRUSTED_EXTERNAL_DATA_END>>>" in text or "<<<UNTRUSTED_EXTERNAL_DATA_BEGIN>>>" in text:
            findings.append(InjectionFinding(
                kind="fence_escape_attempt",
                matched_text="<fence marker present in external content>",
                source=source,
            ))
        # Role-switching language is the classic injection shape.
        if re.search(r"\b(?:you\s+are\s+now|new\s+system\s+prompt|act\s+as\s+(?:the\s+)?(?:owner|admin|root))\b",
                     text, re.IGNORECASE):
            findings.append(InjectionFinding(
                kind="role_hijack_attempt",
                matched_text=text[:120],
                source=source,
            ))
        return findings

    # ------------------------------------------------------------------ #
    # Assembly
    # ------------------------------------------------------------------ #

    def assemble(self, items: list[ContextItem], *, strict: bool = True) -> AssembledContext:
        """Order, deduplicate and budget a set of context items.

        Protected items are always retained. When the remainder does not fit,
        the lowest-priority, least-relevant items are dropped first and each drop
        is recorded — nothing disappears without a trace.

        `strict=True` (the default) raises `ContextOverflowError` when protected
        items alone exceed the budget. Pass `strict=False` only when the caller
        intends to handle the overflow itself; the result is flagged either way.
        """
        # Deduplicate on normalised content: the same fact arriving from two
        # sources should cost the budget once (§12.3).
        seen: set[str] = set()
        unique: list[ContextItem] = []
        duplicates = 0
        for item in items:
            key = re.sub(r"\s+", " ", item.content.strip().lower())
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            unique.append(item)

        protected = [i for i in unique if i.protected]
        optional = [i for i in unique if not i.protected]

        protected_tokens = sum(i.tokens for i in protected)
        if protected_tokens > self.token_budget:
            sources = [i.source for i in protected]
            if strict:
                raise ContextOverflowError(protected_tokens, self.token_budget, sources)
            assembled = AssembledContext(
                items=protected,
                total_tokens=protected_tokens,
                token_budget=self.token_budget,
                deduplicated=duplicates,
                overflowed=True,
                warnings=[
                    f"protected context alone needs {protected_tokens} tokens "
                    f"against a budget of {self.token_budget}; nothing was dropped, "
                    "but the prompt exceeds budget"
                ],
            )
            return assembled

        # Priority first, then relevance, then source for determinism.
        optional.sort(key=lambda i: (i.priority.value, -i.relevance, i.source))
        protected.sort(key=lambda i: (i.priority.value, i.source))

        retained: list[ContextItem] = list(protected)
        total = protected_tokens
        dropped: list[tuple[str, str]] = []

        for item in optional:
            if total + item.tokens <= self.token_budget:
                retained.append(item)
                total += item.tokens
            else:
                dropped.append((item.source, f"exceeded token budget ({item.tokens} tokens)"))

        retained.sort(key=lambda i: (i.priority.value, -i.relevance, i.source))

        warnings: list[str] = []
        external = [i for i in retained if i.trust_domain == TrustDomain.EXTERNAL]
        if external:
            warnings.append(
                f"{len(external)} untrusted external item(s) are included and will be "
                "fenced as data, not instructions"
            )
        if dropped:
            warnings.append(f"{len(dropped)} lower-priority item(s) were trimmed to fit the budget")

        return AssembledContext(
            items=retained,
            total_tokens=total,
            token_budget=self.token_budget,
            dropped=dropped,
            deduplicated=duplicates,
            warnings=warnings,
        )

    def render(self, assembled: AssembledContext, *, system_prompt: str) -> str:
        """Render a prompt with untrusted content structurally separated.

        Trusted items go into the instruction/context section in priority order.
        External items go inside the data fence. The system prompt is emitted
        first and unmodified, so nothing in the assembled context can prepend to
        or overwrite it.
        """
        trusted = [i for i in assembled.items if i.trust_domain != TrustDomain.EXTERNAL]
        external = [i for i in assembled.items if i.trust_domain == TrustDomain.EXTERNAL]

        parts: list[str] = [system_prompt.rstrip(), "", "## Context", ""]
        for item in trusted:
            marker = " [protected]" if item.protected else ""
            parts.append(f"- ({item.source}{marker}) {item.content}")

        if external:
            parts.append("")
            parts.append("## External content")
            for item in external:
                parts.append(fence_untrusted(f"[source: {item.source}]\n{item.content}"))
                parts.append("")

        if assembled.dropped:
            parts.append("")
            parts.append("## Omitted for budget")
            for source, reason in assembled.dropped:
                parts.append(f"- {source}: {reason}")

        return "\n".join(parts)

    def summarize_for_owner(self, assembled: AssembledContext) -> dict[str, object]:
        """Provenance report (§12.3): what was used, what was dropped, why."""
        return {
            "token_budget": assembled.token_budget,
            "tokens_used": assembled.total_tokens,
            "utilisation": round(assembled.utilised, 3),
            "included_sources": assembled.sources(),
            "protected_sources": [i.source for i in assembled.items if i.protected],
            "untrusted_sources": [
                i.source for i in assembled.items if i.trust_domain == TrustDomain.EXTERNAL
            ],
            "dropped": [{"source": s, "reason": r} for s, r in assembled.dropped],
            "deduplicated": assembled.deduplicated,
            "warnings": assembled.warnings,
        }


__all__ = [
    "AssembledContext",
    "ContextItem",
    "ContextManager",
    "ContextOverflowError",
    "ContextPriority",
    "InjectionFinding",
]
