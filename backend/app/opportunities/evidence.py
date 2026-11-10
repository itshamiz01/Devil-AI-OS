"""Evidence discipline (P-03 §9, §19).

Rules implemented here, all deterministic:

- A claim's classification can only be *raised* by corroboration: two or
  more INDEPENDENT sources (different independence groups — syndicated
  copies of one claim do not count twice, §9.3) supporting the same topic,
  at least one of them from a primary-official / government source or the
  pair both at SUPPORTING or better.
- Numeric claims on the same topic that disagree materially (>10%)
  cluster by stated figure: the cluster backed by the most independent
  sources stands, minority outliers are flagged CONTRADICTED, and a tie
  flags both sides. The conflict is always reported, never silently
  resolved.
- Evidence older than the freshness window (by source publication date,
  when the source itself states one) is OUTDATED. When no publication
  date exists, freshness is honestly "unknown", never assumed fresh.
- Evidence quality is a standalone 0–5 computation (§16.3), reported
  separately from commercial attractiveness.
"""
from __future__ import annotations

import datetime as dt
import re

from .constants import CLASSIFICATION_STRENGTH, CORE_EVIDENCE_CATEGORIES

STRONG_SOURCES = {"primary_official", "government_regulatory"}
FRESHNESS_WINDOW_DAYS = 540  # ~18 months

_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)?")


def freshness_for(publication_date: str | None, now: dt.datetime | None = None) -> str:
    """fresh | stale | unknown. Only a source-stated publication date can
    make evidence stale; absence of a date is 'unknown', not 'fresh'."""
    if not publication_date:
        return "unknown"
    now = now or dt.datetime.now(dt.timezone.utc)
    parsed = None
    for fmt in ("%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = dt.datetime.strptime(publication_date.strip(), fmt)
            break
        except (ValueError, TypeError):
            continue
    if parsed is None:
        # A year alone is still usable evidence of age.
        year = re.search(r"(19|20)\d{2}", publication_date)
        if year:
            parsed = dt.datetime(int(year.group(0)), 1, 1, tzinfo=dt.timezone.utc)
        else:
            return "unknown"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return "stale" if (now - parsed).days > FRESHNESS_WINDOW_DAYS else "fresh"


def _amounts(claim: str) -> list[float]:
    return [float(m.group(1)) for m in _AMOUNT_RE.finditer(claim)]


def apply_corroboration(records: list, reliability_by_source_id: dict) -> list[dict]:
    """Mutates classifications on the given EvidenceRecord rows (in the
    caller's session) and returns a list of change descriptions. The
    caller persists a history event describing every change, so the
    original classification is never silently lost (§21)."""
    changes: list[dict] = []
    by_topic: dict[str, list] = {}
    for record in records:
        if record.evidence_kind != "source_claim" or not record.topic_key:
            continue
        if record.classification in ("CONTRADICTED", "OUTDATED"):
            continue
        by_topic.setdefault(record.topic_key, []).append(record)

    for topic, group in by_topic.items():
        # --- contradiction: same topic, materially different numbers.
        # Records cluster by their stated figure (within 10%). The cluster
        # backed by the most independent groups stands; minority outliers
        # are flagged CONTRADICTED. A tie flags BOTH sides — the system
        # reports the conflict, it never picks a winner on a coin flip.
        numeric = [(r, _amounts(r.claim)) for r in group]
        numeric = [(r, a[0]) for r, a in numeric if a]
        if len(numeric) >= 2:
            clusters: list[list] = []
            for record, value in numeric:
                placed = False
                for cluster in clusters:
                    anchor = cluster[0][1]
                    if anchor and value and abs(value - anchor) / max(value, anchor) <= 0.10:
                        cluster.append((record, value))
                        placed = True
                        break
                if not placed:
                    clusters.append([(record, value)])
            if len(clusters) > 1:
                def _groups(cluster) -> int:
                    return len({r.independence_group for r, _ in cluster})
                clusters.sort(key=_groups, reverse=True)
                tied = _groups(clusters[0]) == _groups(clusters[1])
                winners = set() if tied else {r.id for r, _ in clusters[0]}
                for record, _value in numeric:
                    if record.id not in winners and record.classification != "CONTRADICTED":
                        changes.append({
                            "evidence_id": record.id, "topic": topic,
                            "from": record.classification, "to": "CONTRADICTED",
                            "reason": "independent sources state materially different figures "
                                      "for this topic and this record is in the minority "
                                      "(or the sources tie); the conflict is reported, not resolved silently"})
                        record.classification = "CONTRADICTED"
        live = [r for r in group if r.classification != "CONTRADICTED"]
        # --- corroboration: >=2 independent groups, decent base strength
        groups = {r.independence_group for r in live if r.independence_group}
        if len(groups) >= 2:
            has_strong_source = any(
                reliability_by_source_id.get(r.source_id) in STRONG_SOURCES for r in live)
            decent = [r for r in live
                      if CLASSIFICATION_STRENGTH.get(r.classification, 0) >= CLASSIFICATION_STRENGTH["SUPPORTING"]]
            if has_strong_source or len(decent) >= 2:
                for record in live:
                    if record.classification in ("SUPPORTING", "TENTATIVE"):
                        changes.append({"evidence_id": record.id, "topic": topic,
                                        "from": record.classification, "to": "CORROBORATED",
                                        "reason": "supported by independent sources (§9.3)"})
                        record.classification = "CORROBORATED"
    return changes


def evidence_quality(records: list) -> tuple[float, dict]:
    """Standalone evidence-quality score, 0–5 (§16.3).

    Components: mean classification strength (45%), provenance completeness
    (25%), source independence (15%), core-category coverage (15%).
    No evidence at all scores 0 — never a default mid value.
    """
    if not records:
        return 0.0, {"records": 0, "note": "no evidence records exist"}
    strengths = [CLASSIFICATION_STRENGTH.get(r.classification, 0.0) for r in records]
    mean_strength = sum(strengths) / len(strengths)
    complete = sum(1 for r in records
                   if r.retrieval_timestamp is not None
                   and (r.source_id or r.source_url or r.recorded_by not in ("", "system")))
    provenance = complete / len(records)
    groups = {r.independence_group for r in records if r.independence_group}
    independence = min(1.0, len(groups) / 3.0)
    categories = {r.category for r in records}
    coverage = len(categories & set(CORE_EVIDENCE_CATEGORIES)) / len(CORE_EVIDENCE_CATEGORIES)
    score = 5.0 * (0.45 * mean_strength + 0.25 * provenance
                   + 0.15 * independence + 0.15 * coverage)
    breakdown = {
        "records": len(records),
        "mean_strength": round(mean_strength, 3),
        "provenance_completeness": round(provenance, 3),
        "independent_groups": len(groups),
        "core_category_coverage": round(coverage, 3),
        "by_classification": {c: sum(1 for r in records if r.classification == c)
                              for c in sorted({r.classification for r in records})},
    }
    return round(score, 2), breakdown


def evidence_gaps(records: list, *, has_commercial: bool, competitor_count: int) -> list[str]:
    """The honest gap list (§9.4): what is missing, stated plainly."""
    gaps: list[str] = []
    by_category: dict[str, list] = {}
    for record in records:
        by_category.setdefault(record.category, []).append(record)

    def strong(category: str) -> bool:
        return any(CLASSIFICATION_STRENGTH.get(r.classification, 0) >= CLASSIFICATION_STRENGTH["SUPPORTING"]
                   for r in by_category.get(category, []))

    if not records:
        gaps.append("No evidence has been collected at all.")
    if not strong("demand"):
        gaps.append("No reliable customer demand evidence (nothing at SUPPORTING or better).")
    if not by_category.get("purchasing_intent"):
        gaps.append("No evidence of actual purchases or purchasing intent.")
    if not strong("pricing"):
        gaps.append("No verified pricing information.")
    if competitor_count == 0:
        gaps.append("No competitor evidence has been recorded.")
    if not strong("cost"):
        gaps.append("No confirmed platform fee / cost structure evidence.")
    if not has_commercial:
        gaps.append("No commercial analysis has been performed.")
    if not by_category.get("market_size"):
        gaps.append("No reliable market-size evidence; market size cannot be established.")
    if any(r.classification == "CONTRADICTED" for r in records):
        gaps.append("Some evidence is CONTRADICTED by independent sources and must be resolved.")
    return gaps
