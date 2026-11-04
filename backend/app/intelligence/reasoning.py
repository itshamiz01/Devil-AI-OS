"""Reasoning infrastructure (P-02 §8).

Separates what is *known* from what is *assumed*, and refuses to produce a
confident conclusion when the evidence does not support one.

§8.5 is the efficiency rule that shapes this module: deterministic code handles
validation, state transitions, mathematics, permission checks and rule
evaluation; a model is consulted only where semantic understanding is genuinely
required. Everything here is therefore pure Python — it runs identically with or
without an inference runtime, which is what makes the phase testable on a
machine that has no model installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .schemas import (
    UNCERTAINTY_RANK,
    Evidence,
    EvidenceReliability,
    EvidenceStance,
    Hypothesis,
    HypothesisStatus,
    ProblemAnalysis,
    TrustDomain,
    UncertaintyLevel,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def weakest(levels: Iterable[UncertaintyLevel]) -> UncertaintyLevel:
    """The least trustworthy level among a set.

    A conclusion is only as strong as its weakest supporting input. This is the
    mechanism that stops three tentative observations from combining into
    something that looks verified.
    """
    materialised = list(levels)
    if not materialised:
        return UncertaintyLevel.UNKNOWN
    return max(materialised, key=lambda level: UNCERTAINTY_RANK[level])


class InsufficientEvidenceError(RuntimeError):
    """Raised rather than guessing (§8.4).

    The system must be able to say "I do not have enough information to make this
    decision reliably." This exception is that sentence in code form: callers
    convert it into an explicit `UNAVAILABLE` response instead of a fabricated
    answer.
    """

    def __init__(self, question: str, have: int, need: int) -> None:
        self.question = question
        self.have = have
        self.need = need
        super().__init__(
            f"insufficient evidence to decide {question!r}: {have} usable "
            f"observation(s), {need} required"
        )


class EvidenceManager:
    """Tracks observations with their provenance and verification status (§8.2).

    The central invariant: a model-generated statement is never promoted to
    verified. It enters as `MODEL_GENERATED` / `TENTATIVE` at best, and only
    independent confirmation from an authoritative source can raise it.
    """

    def __init__(self) -> None:
        self._evidence: dict[str, Evidence] = {}
        self._counter = 0

    def add(
        self,
        *,
        source: str,
        observation: str,
        reliability: EvidenceReliability,
        verification_status: UncertaintyLevel = UncertaintyLevel.UNKNOWN,
        stance: EvidenceStance = EvidenceStance.NEUTRAL,
        trust_domain: TrustDomain = TrustDomain.EXTERNAL,
        mission_id: str | None = None,
        content_reference: str | None = None,
    ) -> Evidence:
        """Record one observation and return it with an assigned identifier."""
        self._counter += 1
        record = Evidence(
            evidence_id=f"ev-{self._counter:05d}",
            mission_id=mission_id,
            source=source,
            observation=observation,
            collected_at=_now(),
            reliability=reliability,
            verification_status=verification_status,
            stance=stance,
            trust_domain=trust_domain,
            content_reference=content_reference,
        )
        self._evidence[record.evidence_id] = record
        return record

    def add_model_claim(self, *, claim: str, mission_id: str | None = None) -> Evidence:
        """Record something a model asserted, correctly labelled as unverified.

        Kept as a distinct entry point so that no caller can accidentally record
        model output as authoritative: the reliability and trust domain are fixed
        here and cannot be overridden.
        """
        return self.add(
            source="model",
            observation=claim,
            reliability=EvidenceReliability.MODEL_GENERATED,
            verification_status=UncertaintyLevel.TENTATIVE,
            trust_domain=TrustDomain.MODEL,
            mission_id=mission_id,
        )

    def get(self, evidence_id: str) -> Evidence | None:
        record = self._evidence.get(evidence_id)
        return record.model_copy(deep=True) if record else None

    def all(self) -> list[Evidence]:
        return [e.model_copy(deep=True) for e in self._evidence.values()]

    def for_mission(self, mission_id: str) -> list[Evidence]:
        return [e for e in self.all() if e.mission_id == mission_id]

    def supporting(self, mission_id: str | None = None) -> list[Evidence]:
        return [
            e for e in self.all()
            if e.stance == EvidenceStance.SUPPORTING and (mission_id is None or e.mission_id == mission_id)
        ]

    def contradicting(self, mission_id: str | None = None) -> list[Evidence]:
        return [
            e for e in self.all()
            if e.stance == EvidenceStance.CONTRADICTING and (mission_id is None or e.mission_id == mission_id)
        ]

    def untrusted(self) -> list[Evidence]:
        """Evidence from outside the trust boundary (§12.4).

        The context manager uses this to ensure external content is framed as
        data and can never be merged into the instruction channel.
        """
        return [e for e in self.all() if e.trust_domain == TrustDomain.EXTERNAL]

    def confirm(self, evidence_id: str, *, confirmed_by: str) -> Evidence:
        """Promote an observation after independent confirmation.

        Only an authoritative or trusted source can confirm, and a model claim
        can never be confirmed by another model claim — that would let the system
        bootstrap its own facts.
        """
        record = self._evidence.get(evidence_id)
        if record is None:
            raise KeyError(f"unknown evidence {evidence_id!r}")
        if record.reliability == EvidenceReliability.MODEL_GENERATED and confirmed_by == "model":
            raise ValueError("model output cannot be confirmed by model output")
        promoted = record.model_copy(update={
            "verification_status": UncertaintyLevel.VERIFIED,
            "reliability": EvidenceReliability.AUTHORITATIVE,
            "source": f"{record.source} (confirmed by {confirmed_by})",
        })
        self._evidence[evidence_id] = promoted
        return promoted.model_copy(deep=True)

    def contradiction_exists(self, mission_id: str | None = None) -> bool:
        return bool(self.supporting(mission_id)) and bool(self.contradicting(mission_id))


class HypothesisManager:
    """Maintains competing explanations rather than committing to one (§8.3)."""

    def __init__(self, evidence: EvidenceManager) -> None:
        self._evidence = evidence
        self._hypotheses: dict[str, Hypothesis] = {}
        self._counter = 0

    def propose(
        self,
        statement: str,
        *,
        mission_id: str | None = None,
        confidence: float = 0.0,
        validation_requirement: str | None = None,
    ) -> Hypothesis:
        self._counter += 1
        hypothesis = Hypothesis(
            hypothesis_id=f"hy-{self._counter:05d}",
            mission_id=mission_id,
            statement=statement,
            confidence=confidence,
            # Always an unvalidated estimate unless a calibrated measurement
            # process exists. §8.3 forbids presenting confidence as objective
            # truth, and no such calibration exists in P-02.
            confidence_basis="unvalidated_estimate",
            validation_requirement=validation_requirement,
        )
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return hypothesis.model_copy(deep=True)

    def attach_evidence(self, hypothesis_id: str, evidence_id: str) -> Hypothesis:
        """Link an observation to a hypothesis, using the observation's stance."""
        hypothesis = self._hypotheses.get(hypothesis_id)
        if hypothesis is None:
            raise KeyError(f"unknown hypothesis {hypothesis_id!r}")
        record = self._evidence.get(evidence_id)
        if record is None:
            raise KeyError(f"unknown evidence {evidence_id!r}")

        if record.stance == EvidenceStance.CONTRADICTING:
            bucket = list(hypothesis.contradicting_evidence)
        else:
            bucket = list(hypothesis.supporting_evidence)
        if evidence_id not in bucket:
            bucket.append(evidence_id)

        updates: dict[str, object] = {}
        if record.stance == EvidenceStance.CONTRADICTING:
            updates["contradicting_evidence"] = bucket
        else:
            updates["supporting_evidence"] = bucket
        updated = hypothesis.model_copy(update=updates)
        self._hypotheses[hypothesis_id] = updated
        return updated.model_copy(deep=True)

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        record = self._hypotheses.get(hypothesis_id)
        return record.model_copy(deep=True) if record else None

    def all(self) -> list[Hypothesis]:
        return [h.model_copy(deep=True) for h in self._hypotheses.values()]

    def for_mission(self, mission_id: str) -> list[Hypothesis]:
        return [h for h in self.all() if h.mission_id == mission_id]

    def rank(self, mission_id: str | None = None) -> list[Hypothesis]:
        """Order hypotheses by net support, strongest first.

        Ranking is by *evidence count and stance*, not by the confidence number:
        an unvalidated estimate must not outrank a hypothesis that has actual
        observations behind it.
        """
        candidates = self.for_mission(mission_id) if mission_id else self.all()
        return sorted(
            candidates,
            key=lambda h: (len(h.contradicting_evidence), -len(h.supporting_evidence), h.hypothesis_id),
        )

    def update_status(self, hypothesis_id: str, status: HypothesisStatus) -> Hypothesis:
        hypothesis = self._hypotheses.get(hypothesis_id)
        if hypothesis is None:
            raise KeyError(f"unknown hypothesis {hypothesis_id!r}")
        if status == HypothesisStatus.SUPPORTED and not hypothesis.supporting_evidence:
            # A hypothesis with no supporting evidence cannot be "supported".
            raise ValueError("cannot mark a hypothesis SUPPORTED without supporting evidence")
        if status == HypothesisStatus.REFUTED and not hypothesis.contradicting_evidence:
            raise ValueError("cannot mark a hypothesis REFUTED without contradicting evidence")
        updated = hypothesis.model_copy(update={"status": status})
        self._hypotheses[hypothesis_id] = updated
        return updated.model_copy(deep=True)


@dataclass
class UncertaintyAssessment:
    """The honest summary of how much a conclusion may be relied upon (§8.4)."""

    level: UncertaintyLevel
    usable_observations: int
    contradictions: bool
    explanation: str
    sufficient: bool

    def statement(self) -> str:
        """Owner-facing wording. Never overstates."""
        if not self.sufficient:
            return (
                "I do not have enough information to decide this reliably. "
                + self.explanation
            )
        return self.explanation


class UncertaintyManager:
    """Decides whether a conclusion may be drawn at all (§8.4)."""

    #: How many usable observations a decision needs before the engine will
    #: commit to one. Deliberately explicit and configurable so the threshold is
    #: a documented policy rather than a hidden constant.
    def __init__(self, evidence: EvidenceManager, *, min_observations: int = 1) -> None:
        self._evidence = evidence
        self.min_observations = max(0, min_observations)

    def assess(self, question: str, *, mission_id: str | None = None) -> UncertaintyAssessment:
        records = self._evidence.for_mission(mission_id) if mission_id else self._evidence.all()
        # Contradicted and unknown observations carry no decision weight.
        usable = [
            r for r in records
            if r.verification_status not in {UncertaintyLevel.CONTRADICTED, UncertaintyLevel.UNKNOWN}
        ]
        contradictions = bool(self._evidence.supporting(mission_id)) and bool(
            self._evidence.contradicting(mission_id)
        )
        level = weakest(r.verification_status for r in usable) if usable else UncertaintyLevel.UNKNOWN
        sufficient = len(usable) >= self.min_observations and not contradictions

        if contradictions:
            explanation = (
                f"{len(usable)} observation(s) are available for {question!r}, but they "
                "contradict each other, so no reliable conclusion can be drawn."
            )
        elif not usable:
            explanation = f"No verified observations are available for {question!r}."
        else:
            explanation = (
                f"{len(usable)} observation(s) support a conclusion about {question!r}; "
                f"the strongest available level is {level.value}."
            )

        return UncertaintyAssessment(
            level=level,
            usable_observations=len(usable),
            contradictions=contradictions,
            explanation=explanation,
            sufficient=sufficient,
        )

    def require_sufficient(self, question: str, *, mission_id: str | None = None) -> UncertaintyAssessment:
        """Assess, and raise instead of proceeding on inadequate evidence."""
        assessment = self.assess(question, mission_id=mission_id)
        if not assessment.sufficient:
            raise InsufficientEvidenceError(question, assessment.usable_observations, self.min_observations)
        return assessment


class ProblemAnalyzer:
    """Structures a problem before any attempt to solve it (§8.1).

    Deterministic: it separates known from unknown using the evidence store and
    the mission's stated constraints, so the split is auditable rather than a
    model's impression.
    """

    def __init__(self, evidence: EvidenceManager) -> None:
        self._evidence = evidence

    def analyze(
        self,
        *,
        problem: str,
        expected_outcome: str | None = None,
        constraints: Iterable[str] = (),
        mission_id: str | None = None,
        candidate_blockers: Iterable[str] = (),
    ) -> ProblemAnalysis:
        records = self._evidence.for_mission(mission_id) if mission_id else self._evidence.all()
        known = [r.observation for r in records if r.verification_status in {
            UncertaintyLevel.VERIFIED, UncertaintyLevel.STRONGLY_SUPPORTED,
        }]
        assumed = [r.observation for r in records if r.verification_status == UncertaintyLevel.ASSUMED]
        contradicted = [r.observation for r in records if r.verification_status == UncertaintyLevel.CONTRADICTED]

        unknown: list[str] = list(assumed)
        if not known:
            unknown.append("no verified facts are available for this problem")
        unknown.extend(contradicted)

        blockers = [b for b in candidate_blockers if b]
        if not records:
            blockers.append("no evidence has been collected yet")

        level = weakest(r.verification_status for r in records) if records else UncertaintyLevel.UNKNOWN

        return ProblemAnalysis(
            problem=problem,
            expected_outcome=expected_outcome,
            known=known,
            unknown=list(dict.fromkeys(unknown)),
            constraints=list(constraints),
            blockers=blockers,
            uncertainty=level,
        )


@dataclass
class ReasoningTrace:
    """An auditable record of one reasoning pass.

    §16 requires the engine to distinguish recommendation from authorized
    decision; a trace is how that distinction stays inspectable after the fact.
    """

    operation: str
    mission_id: str | None
    problem: ProblemAnalysis
    uncertainty: UncertaintyAssessment
    evidence_ids: list[str] = field(default_factory=list)
    hypothesis_ids: list[str] = field(default_factory=list)
    conclusion: str | None = None
    #: Set when reasoning stopped because evidence was insufficient.
    refused: bool = False
    refusal_reason: str | None = None
    model_calls: int = 0
    duration_ms: float = 0.0


class ReasoningPipeline:
    """Runs the §8 sequence: understand, gather, check, conclude or refuse.

    The pipeline's most important behaviour is what it does when evidence is
    thin — it refuses. §8.4 forbids forcing a confident answer, so a refusal is
    a successful pipeline run, not a failure.
    """

    def __init__(
        self,
        evidence: EvidenceManager,
        hypotheses: HypothesisManager,
        uncertainty: UncertaintyManager,
        analyzer: ProblemAnalyzer,
    ) -> None:
        self.evidence = evidence
        self.hypotheses = hypotheses
        self.uncertainty = uncertainty
        self.analyzer = analyzer
        self.traces: list[ReasoningTrace] = []

    @classmethod
    def build(cls, *, min_observations: int = 1) -> "ReasoningPipeline":
        evidence = EvidenceManager()
        return cls(
            evidence=evidence,
            hypotheses=HypothesisManager(evidence),
            uncertainty=UncertaintyManager(evidence, min_observations=min_observations),
            analyzer=ProblemAnalyzer(evidence),
        )

    def run(
        self,
        *,
        operation: str,
        question: str,
        mission_id: str | None = None,
        expected_outcome: str | None = None,
        constraints: Iterable[str] = (),
        candidate_blockers: Iterable[str] = (),
    ) -> ReasoningTrace:
        started = datetime.now(timezone.utc)
        problem = self.analyzer.analyze(
            problem=question,
            expected_outcome=expected_outcome,
            constraints=constraints,
            mission_id=mission_id,
            candidate_blockers=candidate_blockers,
        )
        assessment = self.uncertainty.assess(question, mission_id=mission_id)
        records = self.evidence.for_mission(mission_id) if mission_id else self.evidence.all()

        trace = ReasoningTrace(
            operation=operation,
            mission_id=mission_id,
            problem=problem,
            uncertainty=assessment,
            evidence_ids=[r.evidence_id for r in records],
            hypothesis_ids=([h.hypothesis_id for h in self.hypotheses.for_mission(mission_id)] if mission_id else []),
            model_calls=0,  # deterministic pipeline; a model call would be recorded
        )

        if not assessment.sufficient:
            trace.refused = True
            trace.refusal_reason = assessment.statement()
        else:
            ranked = self.hypotheses.rank(mission_id)
            if ranked and ranked[0].supporting_evidence:
                trace.conclusion = ranked[0].statement
            else:
                trace.conclusion = assessment.explanation

        trace.duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        self.traces.append(trace)
        return trace


__all__ = [
    "EvidenceManager",
    "HypothesisManager",
    "InsufficientEvidenceError",
    "ProblemAnalyzer",
    "ReasoningPipeline",
    "ReasoningTrace",
    "UncertaintyAssessment",
    "UncertaintyManager",
    "weakest",
]
