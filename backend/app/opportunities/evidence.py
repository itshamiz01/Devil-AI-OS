"""P-03 §9 evidence management.

This module does **not** replace P-02's :class:`~app.intelligence.reasoning.EvidenceManager`;
it stores the market-research-specific record type and bridges to P-02 when the
reasoning engine needs to consume it (§25 integration boundary).  The P-02
epistemic rule - model output can never be VERIFIED - is enforced in the schema
and re-checked here on the way in, because evidence is the one place where a
silent promotion would corrupt every downstream number.

Three behaviours matter:

* **Corroboration is earned, not assumed.**  A record is promoted to
  CORROBORATED only when a second record with a *different* independence group
  supports the same claim key.  Two records from the same source, or the same
  record counted twice, never corroborate anything.
* **Promotion to VERIFIED requires an authoritative source and an explicit
  confirmation.**  Nothing in this module can promote on volume alone.
* **Contradiction is preserved, not resolved.**  Conflicting records are both
  kept and both surfaced.  The engine reports the disagreement rather than
  picking a winner.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.intelligence.reasoning import EvidenceManager
from app.intelligence.schemas import (
    Evidence,
    EvidenceReliability,
    EvidenceStance,
    TrustDomain,
    UncertaintyLevel,
)
from app.opportunities.schemas import (
    ADMISSIBLE_CLASSIFICATIONS,
    CLASSIFICATION_TO_UNCERTAINTY,
    EvidenceClassification,
    SourceEvidence,
)

__all__ = ["EvidenceStore", "EvidenceQualityStats", "claim_key", "metric_key"]


def metric_key(evidence: SourceEvidence) -> str:
    """The identity of the thing being measured, **excluding** the value.

    This is the counterpart to :func:`claim_key` and the two must not be
    conflated.  Corroboration asks "do these records *agree*?", so its key
    includes the value.  Contradiction asks "do these records disagree about the
    *same metric*?", so its key must exclude the value - otherwise two sources
    quoting $19 and $29 for the same product land in different groups and the
    disagreement is never seen.
    """
    base = evidence.evidence_type.value
    if evidence.numeric_value is not None:
        return f"{base}|{evidence.unit or ''}"
    normalised = " ".join((evidence.claim or "").lower().split())[:80]
    return f"{base}|{normalised}"


def claim_key(evidence: SourceEvidence) -> str:
    """A stable key identifying what an observation is *about*.

    Two records corroborate each other only when they share a claim key.  The key
    is deliberately coarse - evidence type plus the numeric value and unit when
    present, otherwise the type plus a normalised claim prefix - so that two
    sources reporting the same price agree while two sources reporting different
    prices do not.
    """
    base = evidence.evidence_type.value
    if evidence.numeric_value is not None:
        return f"{base}|{evidence.numeric_value}|{evidence.unit or ''}"
    normalised = " ".join((evidence.claim or "").lower().split())[:80]
    return f"{base}|{normalised}"


class EvidenceQualityStats:
    """A flat, JSON-safe summary of an evidence body."""

    def __init__(self, evidence: Sequence[SourceEvidence]):
        self.total = len(evidence)
        self.by_classification: dict[str, int] = defaultdict(int)
        self.by_reliability: dict[str, int] = defaultdict(int)
        self.by_type: dict[str, int] = defaultdict(int)
        for item in evidence:
            self.by_classification[item.classification.value] += 1
            self.by_reliability[item.reliability.value] += 1
            self.by_type[item.evidence_type.value] += 1
        self.admissible = sum(1 for e in evidence if e.is_admissible())
        self.contradicted = sum(
            1 for e in evidence if e.classification is EvidenceClassification.CONTRADICTED
        )
        self.outdated = sum(
            1 for e in evidence if e.classification is EvidenceClassification.OUTDATED
        )
        self.unverified = sum(
            1 for e in evidence if e.classification is EvidenceClassification.UNVERIFIED
        )
        self.verified = sum(
            1 for e in evidence if e.classification is EvidenceClassification.VERIFIED
        )
        self.corroborated = sum(
            1 for e in evidence if e.classification is EvidenceClassification.CORROBORATED
        )
        self.model_generated = sum(
            1 for e in evidence
            if e.reliability is EvidenceReliability.MODEL_GENERATED
        )
        self.source_count = len({e.source_id for e in evidence if e.source_id})

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "admissible": self.admissible,
            "verified": self.verified,
            "corroborated": self.corroborated,
            "unverified": self.unverified,
            "contradicted": self.contradicted,
            "outdated": self.outdated,
            "model_generated": self.model_generated,
            "distinct_sources": self.source_count,
            "by_classification": dict(sorted(self.by_classification.items())),
            "by_reliability": dict(sorted(self.by_reliability.items())),
            "by_type": dict(sorted(self.by_type.items())),
        }


class EvidenceStore:
    """Append-only evidence storage scoped per opportunity."""

    def __init__(self) -> None:
        self._by_id: dict[str, SourceEvidence] = {}
        self._by_opportunity: dict[str, list[str]] = defaultdict(list)
        self._confirmations: dict[str, str] = {}
        self._last_load_refusals = 0

    # ------------------------------------------------------------------ #
    def add(self, evidence: SourceEvidence) -> SourceEvidence:
        """Store one record.  Idempotent on ``evidence_id``."""
        # Defence in depth: the schema already refuses this, but the store is the
        # last gate before persistence and reporting.
        if evidence.reliability is EvidenceReliability.MODEL_GENERATED and (
            evidence.classification
            in {EvidenceClassification.VERIFIED, EvidenceClassification.CORROBORATED}
        ):
            raise ValueError(
                "refusing to store model-generated evidence as VERIFIED or CORROBORATED"
            )
        existing = self._by_id.get(evidence.evidence_id)
        if existing is not None:
            if existing != evidence:
                raise ValueError(
                    f"evidence_id '{evidence.evidence_id}' is already stored with "
                    "different content; ids must be unique per observation"
                )
            return existing
        self._by_id[evidence.evidence_id] = evidence
        if evidence.opportunity_id:
            if evidence.evidence_id not in self._by_opportunity[evidence.opportunity_id]:
                self._by_opportunity[evidence.opportunity_id].append(evidence.evidence_id)
        return evidence

    def add_all(self, evidence: Iterable[SourceEvidence]) -> list[SourceEvidence]:
        return [self.add(e) for e in evidence]

    def get(self, evidence_id: str) -> SourceEvidence | None:
        return self._by_id.get(evidence_id)

    def all(self) -> list[SourceEvidence]:
        return list(self._by_id.values())

    def for_opportunity(self, opportunity_id: str) -> list[SourceEvidence]:
        return [self._by_id[i] for i in self._by_opportunity.get(opportunity_id, ())]

    def stats(self, opportunity_id: str | None = None) -> EvidenceQualityStats:
        evidence = (
            self.for_opportunity(opportunity_id)
            if opportunity_id
            else self.all()
        )
        return EvidenceQualityStats(evidence)

    # ------------------------------------------------------------------ #
    def corroborate(self, opportunity_id: str) -> list[SourceEvidence]:
        """Promote records that a second, independent source supports.

        Returns the newly promoted records.  Promotion is only ever
        SUPPORTING/TENTATIVE -> CORROBORATED.  Nothing is promoted to VERIFIED
        here, and nothing already CONTRADICTED or OUTDATED is touched.
        """
        groups: dict[str, list[SourceEvidence]] = defaultdict(list)
        for item in self.for_opportunity(opportunity_id):
            if item.classification in {
                EvidenceClassification.SUPPORTING,
                EvidenceClassification.TENTATIVE,
            }:
                groups[claim_key(item)].append(item)

        promoted: list[SourceEvidence] = []
        for key, items in groups.items():
            # Independence: different independence_group when declared, otherwise
            # a different source_id.  Records with neither cannot corroborate.
            seen: dict[str, SourceEvidence] = {}
            for item in items:
                identity = item.independence_group or item.source_id
                if identity is None:
                    continue
                seen.setdefault(identity, item)
            if len(seen) < 2:
                continue
            representative = next(iter(seen.values()))
            updated = representative.model_copy(
                update={
                    "classification": EvidenceClassification.CORROBORATED,
                    "independence_group": representative.independence_group
                    or representative.source_id,
                }
            )
            # model_copy bypasses validation; re-validate explicitly so the
            # CORROBORATED-requires-independence-group rule still applies.
            updated = SourceEvidence.model_validate(updated.model_dump())
            self._by_id[updated.evidence_id] = updated
            promoted.append(updated)
            for other in seen.values():
                if other.evidence_id != updated.evidence_id:
                    self._by_id[other.evidence_id] = other.model_copy(
                        update={"supersedes": other.supersedes}
                    )
        return promoted

    def confirm(
        self, evidence_id: str, *, confirmed_by: str, authoritative_only: bool = True
    ) -> SourceEvidence:
        """Explicitly confirm one record, promoting it to VERIFIED.

        Confirmation is an act by a named confirmer, recorded against the
        evidence.  When ``authoritative_only`` is set (the default) a source that
        is not AUTHORITATIVE or TRUSTED cannot be confirmed - volume of agreement
        is not a substitute for source quality.
        """
        item = self._by_id.get(evidence_id)
        if item is None:
            raise KeyError(f"evidence '{evidence_id}' is not stored")
        if confirmed_by == "model" or item.reliability is EvidenceReliability.MODEL_GENERATED:
            raise ValueError(
                "model-generated evidence cannot be confirmed to VERIFIED; it "
                "requires an independent external source"
            )
        if authoritative_only and item.reliability not in {
            EvidenceReliability.AUTHORITATIVE,
            EvidenceReliability.TRUSTED,
        }:
            raise ValueError(
                f"evidence from a '{item.reliability.value}' source cannot be "
                "confirmed to VERIFIED; only authoritative or trusted sources qualify"
            )
        if item.classification is EvidenceClassification.CONTRADICTED:
            raise ValueError(
                "contradicted evidence cannot be confirmed; resolve the "
                "contradiction first"
            )
        updated = item.model_copy(
            update={"classification": EvidenceClassification.VERIFIED}
        )
        updated = SourceEvidence.model_validate(updated.model_dump())
        self._by_id[evidence_id] = updated
        self._confirmations[evidence_id] = confirmed_by
        return updated

    def confirmed_by(self, evidence_id: str) -> str | None:
        return self._confirmations.get(evidence_id)

    @property
    def last_load_refusals(self) -> int:
        """How many records P-02 refused on epistemic grounds in the last load."""
        return self._last_load_refusals

    # ------------------------------------------------------------------ #
    def contradictions(self, opportunity_id: str | None = None) -> list[tuple[SourceEvidence, ...]]:
        """Records that disagree about the same metric.

        Grouped by :func:`metric_key`, which excludes the measured value, so a
        $19 observation and a $29 observation about the same thing are compared
        rather than filed separately.  Both sides are always returned: the store
        reports a disagreement, it does not adjudicate one.
        """
        items = self.for_opportunity(opportunity_id) if opportunity_id else self.all()
        groups: dict[str, list[SourceEvidence]] = defaultdict(list)
        for item in items:
            groups[metric_key(item)].append(item)

        out: list[tuple[SourceEvidence, ...]] = []
        for group in groups.values():
            explicit = [g for g in group if g.classification is EvidenceClassification.CONTRADICTED]
            if explicit:
                others = [g for g in group if g not in explicit]
                out.append(tuple([*explicit, *others]))
                continue
            values = {g.numeric_value for g in group if g.numeric_value is not None}
            sources = {g.source_id for g in group if g.source_id}
            if len(values) > 1 and len(sources) > 1:
                out.append(tuple(sorted(group, key=lambda g: g.evidence_id)))
        return out

    def mark_stale(self, *, now: datetime | None = None) -> list[SourceEvidence]:
        """Flag records whose useful life has expired.

        Staleness is a property of the collection date, so it must be re-evaluated
        over time; an analysis run last month on data with a 7-day life is not
        still valid today.
        """
        now = now or datetime.now(timezone.utc)
        updated = []
        for item in list(self._by_id.values()):
            if item.classification is EvidenceClassification.OUTDATED:
                continue
            if item.is_stale(now=now):
                fresh = item.model_copy(
                    update={
                        "classification": EvidenceClassification.OUTDATED,
                        "notes": (item.notes + "; " if item.notes else "")
                        + f"marked outdated at {now.isoformat()}",
                    }
                )
                fresh = SourceEvidence.model_validate(fresh.model_dump())
                self._by_id[item.evidence_id] = fresh
                updated.append(fresh)
        return updated

    def evidence_ids(self, opportunity_id: str) -> tuple[str, ...]:
        return tuple(self._by_opportunity.get(opportunity_id, ()))

    # ------------------------------------------------------------------ #
    # §25 - bridge into the P-02 reasoning engine
    # ------------------------------------------------------------------ #
    def to_p02(self, evidence: SourceEvidence) -> Evidence:
        """Convert one P-03 record into a P-02 :class:`Evidence`.

        The mapping is lossy in exactly one direction - P-02's coarser
        uncertainty scale - and that is intentional: P-02 reasons about certainty,
        P-03 reasons about market provenance.  The trust domain and reliability
        carry across unchanged, so nothing becomes *more* trusted in translation.
        """
        return Evidence(
            evidence_id=evidence.evidence_id,
            mission_id=None,
            source=evidence.source_id or "unattributed",
            observation=evidence.claim,
            collected_at=evidence.collected_at or datetime.now(timezone.utc),
            reliability=evidence.reliability,
            verification_status=CLASSIFICATION_TO_UNCERTAINTY[evidence.classification],
            stance=(
                EvidenceStance.CONTRADICTING
                if evidence.classification is EvidenceClassification.CONTRADICTED
                else EvidenceStance.SUPPORTING
                if evidence.classification in ADMISSIBLE_CLASSIFICATIONS
                else EvidenceStance.NEUTRAL
            ),
            trust_domain=evidence.trust_domain,
            content_reference=evidence.source_url or evidence.evidence_id,
        )

    def load_into(self, manager: EvidenceManager, opportunity_id: str) -> int:
        """Push an opportunity's evidence into a P-02 EvidenceManager.

        Returns the number of records accepted.  A record that P-02 *refuses on
        epistemic grounds* (a pydantic ValidationError, for example model output
        presented as verified) is skipped and counted in
        :attr:`last_load_refusals`.  Any other exception - a TypeError from a
        signature mismatch, say - propagates, because that is a bug in this
        bridge and silently swallowing it would report success while transferring
        nothing.
        """
        accepted = 0
        refused = 0
        for item in self.for_opportunity(opportunity_id):
            converted = self.to_p02(item)
            # P-02's EvidenceManager.add() assigns its own evidence_id and stamps
            # its own collected_at, so both are excluded here.  That means the
            # P-03 collection timestamp is NOT carried into P-02: the bridge is
            # deliberately one-way and lossy on time, and callers that need the
            # original timestamp must read it from this store.
            payload = converted.model_dump(
                exclude={"evidence_id", "mission_id", "collected_at"}
            )
            try:
                manager.add(mission_id=None, **payload)
                accepted += 1
            except ValidationError:
                # A genuine epistemic refusal by P-02 (for example model output
                # presented as verified).  Counted and reported, never forced.
                refused += 1
        self._last_load_refusals = refused
        return accepted

    def snapshot(self, opportunity_id: str | None = None) -> dict[str, Any]:
        stats = self.stats(opportunity_id)
        return {
            "quality": stats.as_dict(),
            "contradictions": len(self.contradictions(opportunity_id)),
            "confirmed": len(self._confirmations),
            "records": [
                {
                    "evidence_id": e.evidence_id,
                    "type": e.evidence_type.value,
                    "classification": e.classification.value,
                    "reliability": e.reliability.value,
                    "source_id": e.source_id,
                    "claim": e.claim[:200],
                    "numeric_value": str(e.numeric_value) if e.numeric_value is not None else None,
                    "unit": e.unit,
                    "collected_at": e.collected_at.isoformat() if e.collected_at else None,
                }
                for e in (self.for_opportunity(opportunity_id) if opportunity_id else self.all())
            ],
        }
