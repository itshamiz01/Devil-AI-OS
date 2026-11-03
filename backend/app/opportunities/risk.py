"""P-03 §15 legal, platform and ethical risk.

This module exists to stop the engine recommending something the owner should
never build.  Two properties matter more than coverage:

* **A prohibited match is terminal.**  It produces a BLOCKING finding, and a
  BLOCKING finding forces ``verdict='blocked'`` at the schema level - so no
  amount of attractive economics can rescue it.
* **Ignorance is reported as ignorance.**  Legal risk cannot be assessed
  without a jurisdiction.  When none is supplied the verdict is
  ``cannot_determine`` with an explicit data gap, never ``acceptable``.

The matcher is deliberately conservative in *both* directions: it uses
word-boundary matching on a curated term list rather than substring matching,
so "assassination" does not fire on "seasoning", and it records the term that
matched so a false positive can be inspected and overridden by the owner rather
than silently ignored.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from app.opportunities.schemas import (
    BusinessCategory,
    RiskAssessment,
    RiskFinding,
    RiskSeverity,
)

__all__ = [
    "CONTEXT_WINDOW",
    "DEFENCE_ELIGIBLE_TERMS",
    "DEFENSIVE_MARKERS",
    "OFFENSIVE_MARKERS",
    "PROHIBITED_CATEGORIES",
    "PLATFORM_POLICY_RULES",
    "REGULATED_CATEGORIES",
    "ComplianceScreen",
    "RiskEngine",
]


#: §15 prohibited-category rejection list.  A match on any term produces a
#: BLOCKING finding and ends the evaluation.  Keys are the human-readable
#: prohibition; values are the trigger terms.
PROHIBITED_CATEGORIES: dict[str, tuple[str, ...]] = {
    "illegal goods or services": (
        "stolen goods", "stolen data", "counterfeit", "fake id", "fake passport",
        "forged documents", "black market", "smuggling",
    ),
    "weapons and explosives": (
        "firearm sale", "gun sales", "ammunition", "explosives", "bomb making",
        "weapon manufacture", "3d printed firearm",
    ),
    "controlled substances": (
        "illegal drugs", "narcotics", "cocaine", "heroin", "methamphetamine",
        "drug synthesis", "prescription without license",
    ),
    "adult and pornographic content": (
        "pornography", "pornographic", "adult content", "escort services",
        "sexually explicit",
    ),
    "fraud, deception and astroturfing": (
        "fake reviews", "buy reviews", "review manipulation", "astroturfing",
        "click fraud", "ad fraud", "phishing", "scam", "ponzi",
        "pyramid scheme", "get rich quick", "money mule",
        "credit card fraud", "identity theft",
    ),
    "unauthorised intrusion and abuse tooling": (
        "hacking service", "cracking service", "malware", "ransomware",
        "keylogger", "spyware", "ddos for hire", "account takeover",
        "credential stuffing", "exploit kit",
    ),
    "academic dishonesty": (
        "essay mill", "exam cheating", "contract cheating", "take my exam",
        "ghostwritten dissertation", "answer key leak",
    ),
    "unlicensed financial or medical practice": (
        "unlicensed lending", "payday loan operation", "insider trading",
        "market manipulation", "diagnose patients without license",
        "prescribe medication", "unlicensed medical advice",
        "unregistered securities", "unlicensed insurance",
    ),
    "sanctions and tax evasion": (
        "sanctions evasion", "tax evasion", "money laundering",
        "offshore shell company for hiding", "shell company to evade",
    ),
    "gambling without a licence": (
        "unlicensed gambling", "unlicensed casino", "illegal betting",
        "sports betting without license",
    ),
    "exploitation of minors": (
        "minors gambling", "underage alcohol sales", "underage vaping",
        "child data harvesting", "marketing to children with data",
    ),
    "plagiarism and content theft": (
        "plagiarized content", "scraped content resale", "pirated software",
        "cracked software", "nulled scripts", "copyright infringement service",
    ),
    "deceptive dropshipping and misrepresentation": (
        "bait and switch", "fake scarcity generator", "misleading health claims",
        "fake celebrity endorsement", "counterfeit supplements",
    ),
}

#: Prohibited terms for which a legitimate **defensive or educational** industry
#: exists.  "Malware detection", "anti-phishing training" and "ransomware
#: recovery" are lawful businesses that merely contain a prohibited noun;
#: blocking them would cost the owner real opportunities.  Terms outside this set
#: (weapons, stolen data, pornography, and so on) have no defensive reading and
#: always block.
DEFENCE_ELIGIBLE_TERMS: frozenset[str] = frozenset({
    "malware", "ransomware", "spyware", "keylogger", "phishing",
    "credential stuffing", "account takeover", "exploit kit", "ddos for hire",
    "scam", "ponzi", "identity theft", "money laundering", "tax evasion",
    "counterfeit", "credit card fraud", "hacking service", "cracking service",
})

#: Markers that, near a defence-eligible term, indicate the offering *defends
#: against* the thing rather than supplying it.
DEFENSIVE_MARKERS: tuple[str, ...] = (
    "detection", "detect", "prevention", "prevent", "anti", "protection",
    "protect", "awareness", "education", "educational", "training", "recovery",
    "remediation", "response", "analysis", "mitigation", "removal", "remove",
    "scanner", "scanning", "monitoring", "audit", "compliance", "free",
    "against", "stop", "reporting", "victim",
)

#: Markers that indicate the offering *supplies* the prohibited thing.  These
#: win over defensive markers, so "sell malware" blocks even if the same
#: sentence also happens to contain the word "protection".
OFFENSIVE_MARKERS: tuple[str, ...] = (
    "for hire", "sell", "selling", "sale of", "buy", "purchase", "hire",
    "order", "download", "crack", "supply", "provide access", "kit for",
    "service to attack", "targeting", "victim list",
)

#: How far either side of a matched term the engine looks for context.  A whole
#: document containing "education" somewhere must not launder a "sell malware"
#: sentence elsewhere in it.
CONTEXT_WINDOW = 80


#: Product categories that are *lawful* but regulated: they require a licence,
#: registration or professional standing.  These produce a HIGH finding with a
#: mitigation, not an automatic block.
REGULATED_CATEGORIES: dict[str, tuple[str, ...]] = {
    "financial services": (
        "investment advice", "financial planning", "trading signals",
        "cryptocurrency exchange", "payment processing", "lending",
    ),
    "health and medical": (
        "medical device", "health supplement", "therapy service",
        "clinical advice", "diagnostics", "telehealth",
    ),
    "food and consumables": (
        "food sale", "dietary supplement", "alcohol sale", "cosmetics",
    ),
    "data handling": (
        "personal data", "customer data resale", "data broker",
        "health records", "credit reporting",
    ),
    "education and certification": (
        "accredited course", "certification exam", "professional qualification",
    ),
    "gambling and gaming": ("gambling", "betting", "lottery", "casino"),
}

#: Platform policy rules: business categories that specific platforms restrict.
PLATFORM_POLICY_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "apple_app_store": {
        "restricted": ("adult content", "gambling", "cryptocurrency mining"),
        "requires_review": ("health", "financial"),
    },
    "google_play": {
        "restricted": ("gambling", "weapons", "tobacco"),
        "requires_review": ("financial", "health"),
    },
    "stripe": {
        "restricted": ("adult content", "gambling", "firearms", "cryptocurrency"),
        "requires_review": ("subscription boxes", "travel"),
    },
    "paypal": {
        "restricted": ("adult content", "gambling", "pharmacy"),
        "requires_review": ("preorders", "high risk"),
    },
    "amazon_marketplace": {
        "restricted": ("weapons", "tobacco", "alcohol", "medical devices"),
        "requires_review": ("supplements", "baby products"),
    },
    "etsy": {
        "restricted": ("resale of mass produced", "alcohol", "weapons", "medical claims"),
        "requires_review": ("handmade claims", "vintage"),
    },
    "youtube_monetization": {
        "restricted": ("adult content", "hate content", "dangerous acts"),
        "requires_review": ("medical", "financial advice"),
    },
    "gumroad": {
        "restricted": ("adult content without flag", "gambling"),
        "requires_review": ("financial products",),
    },
}


def _term_patterns(terms: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Compile each term into a word-boundary pattern.

    Word boundaries are the point: substring matching would flag "seasoning"
    for "ass", or "scamper" for "scam".  False positives cost the owner real
    opportunities, so the matcher is built to avoid them.
    """
    out = []
    for term in terms:
        # Allow internal spaces/hyphens but require boundaries at both ends.
        body = r"[\s\-_]*".join(re.escape(part) for part in term.split())
        out.append((term, re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.I)))
    return out


_PROHIBITED_PATTERNS = {
    prohibition: _term_patterns(terms)
    for prohibition, terms in PROHIBITED_CATEGORIES.items()
}
_REGULATED_PATTERNS = {
    area: _term_patterns(terms) for area, terms in REGULATED_CATEGORIES.items()
}


class ComplianceScreen:
    """The cheapest possible rejection: scan text before spending any research.

    Used at INITIAL_SCREENING (§17) so that a prohibited idea is discarded
    before a single source is contacted.
    """

    @staticmethod
    def _context_verdict(term: str, haystack: str, start: int, end: int) -> str:
        """Decide whether a matched term is offensive, defensive or unclear.

        Returns ``"offensive"``, ``"defensive"`` or ``"unclear"``.  Offensive
        markers take precedence, and the default is ``"unclear"`` - which blocks,
        because the screen is meant to be conservative.
        """
        if term not in DEFENCE_ELIGIBLE_TERMS:
            return "offensive"
        window = haystack[max(0, start - CONTEXT_WINDOW): end + CONTEXT_WINDOW]
        if any(m in window for m in OFFENSIVE_MARKERS):
            return "offensive"
        if any(m in window for m in DEFENSIVE_MARKERS):
            return "defensive"
        return "unclear"

    def scan_text(self, text: str) -> tuple[RiskFinding, ...]:
        findings: list[RiskFinding] = []
        haystack = text.lower()
        for prohibition, patterns in _PROHIBITED_PATTERNS.items():
            for term, pattern in patterns:
                match = pattern.search(haystack)
                if not match:
                    continue
                verdict = self._context_verdict(
                    term.lower(), haystack, match.start(), match.end()
                )
                if verdict == "defensive":
                    # A lawful defensive/educational offering.  Not blocked, but
                    # not silently cleared either: it is escalated for owner
                    # confirmation because the text is genuinely ambiguous.
                    findings.append(
                        RiskFinding(
                            category="ethical",
                            severity=RiskSeverity.HIGH,
                            description=(
                                f"the term '{term}' (prohibition: '{prohibition}') "
                                "appears in what looks like a defensive or "
                                "educational context; the offering must be "
                                "confirmed as defending against this rather than "
                                "supplying it"
                            ),
                            mitigation=(
                                "owner confirmation required that the product "
                                "defends against or educates about the subject "
                                "rather than providing it"
                            ),
                        )
                    )
                else:
                    findings.append(
                        RiskFinding(
                            category="prohibited_category",
                            severity=RiskSeverity.BLOCKING,
                            description=(
                                f"prohibited category '{prohibition}' matched on "
                                f"the term '{term}'"
                                + (
                                    ""
                                    if verdict == "offensive"
                                    else " with no defensive context present"
                                )
                            ),
                            mitigation=None,
                            blocks_recommendation=True,
                        )
                    )
                break  # one match per prohibition is enough
        return tuple(findings)

    def scan_candidate(self, candidate: Any) -> tuple[RiskFinding, ...]:
        """Screen an :class:`OpportunityCandidate` (or an Opportunity)."""
        parts = []
        for attr in ("title", "description", "problem_addressed", "proposed_offering", "target_customer"):
            value = getattr(candidate, attr, None)
            if value:
                parts.append(str(value))
        inner = getattr(candidate, "candidate", None)
        if inner is not None:
            for attr in ("title", "description", "problem_addressed", "proposed_offering"):
                value = getattr(inner, attr, None)
                if value:
                    parts.append(str(value))
        return self.scan_text(" \n ".join(parts))


class RiskEngine:
    """Full §15 assessment: prohibited categories, regulated areas, platform
    policy and the jurisdiction gap."""

    def __init__(self, *, screen: ComplianceScreen | None = None):
        self.screen = screen or ComplianceScreen()

    def platform_findings(
        self, platforms: Iterable[str], category: BusinessCategory | None = None
    ) -> tuple[RiskFinding, ...]:
        findings: list[RiskFinding] = []
        for raw in platforms:
            key = raw.strip().lower().replace(" ", "_")
            rules = PLATFORM_POLICY_RULES.get(key)
            if rules is None:
                findings.append(
                    RiskFinding(
                        category="platform_policy",
                        severity=RiskSeverity.LOW,
                        description=(
                            f"platform '{raw}' has no policy rules modelled; its "
                            "restrictions were not checked"
                        ),
                        platform=raw,
                        mitigation="verify the platform's acceptable-use policy manually",
                    )
                )
                continue
            if rules.get("restricted"):
                findings.append(
                    RiskFinding(
                        category="platform_policy",
                        severity=RiskSeverity.MEDIUM,
                        description=(
                            f"platform '{raw}' restricts: "
                            f"{', '.join(rules['restricted'])}; confirm the offering "
                            "falls outside these"
                        ),
                        platform=raw,
                        mitigation="check the listing against the platform's restricted list before committing",
                    )
                )
            if rules.get("requires_review"):
                findings.append(
                    RiskFinding(
                        category="platform_policy",
                        severity=RiskSeverity.LOW,
                        description=(
                            f"platform '{raw}' applies extra review to: "
                            f"{', '.join(rules['requires_review'])}"
                        ),
                        platform=raw,
                    )
                )
        return tuple(findings)

    def regulated_findings(self, text: str) -> tuple[RiskFinding, ...]:
        findings: list[RiskFinding] = []
        haystack = text.lower()
        for area, patterns in _REGULATED_PATTERNS.items():
            matched = [term for term, pattern in patterns if pattern.search(haystack)]
            if matched:
                findings.append(
                    RiskFinding(
                        category="regulatory",
                        severity=RiskSeverity.HIGH,
                        description=(
                            f"the offering touches the regulated area '{area}' "
                            f"(matched: {', '.join(matched[:4])}); licensing, "
                            "registration or professional standing may be required"
                        ),
                        mitigation=(
                            "confirm the specific licence or registration required "
                            "in the target jurisdiction before any spend"
                        ),
                    )
                )
        return tuple(findings)

    def assess(
        self,
        *,
        text: str,
        category: BusinessCategory | None = None,
        jurisdictions: Iterable[str] = (),
        platforms: Iterable[str] = (),
        extra_findings: Iterable[RiskFinding] = (),
    ) -> RiskAssessment:
        """Produce the §15 assessment.

        ``jurisdictions`` empty is a data gap, not a clean bill of health.
        """
        findings: list[RiskFinding] = []
        findings.extend(self.screen.scan_text(text))
        findings.extend(self.regulated_findings(text))
        findings.extend(self.platform_findings(platforms, category))
        findings.extend(extra_findings)

        jurisdictions = tuple(j for j in jurisdictions if j and j.strip())
        gaps: list[str] = []
        if not jurisdictions:
            gaps.append(
                "no jurisdiction supplied; legal, tax and consumer-protection "
                "obligations could not be assessed"
            )
        if not platforms:
            gaps.append("no distribution platform supplied; platform policy was not checked")

        prohibited = [f for f in findings if f.category == "prohibited_category"]
        if prohibited:
            return RiskAssessment(
                findings=tuple(findings),
                blocked=True,
                jurisdictions_considered=jurisdictions,
                data_gaps=tuple(gaps),
                verdict="blocked",
                reasons=tuple(
                    f"prohibited category: {p.description}" for p in prohibited
                ),
            )

        blocking = [f for f in findings if f.blocks_recommendation]
        if blocking:
            return RiskAssessment(
                findings=tuple(findings),
                blocked=True,
                jurisdictions_considered=jurisdictions,
                data_gaps=tuple(gaps),
                verdict="blocked",
                reasons=tuple(f.description for f in blocking),
            )

        if not jurisdictions:
            # Lawful-looking, but unassessable.  This is the honest answer.
            return RiskAssessment(
                findings=tuple(findings),
                jurisdictions_considered=jurisdictions,
                data_gaps=tuple(gaps),
                verdict="cannot_determine",
                reasons=(
                    "compliance could not be determined without a target "
                    "jurisdiction; the opportunity is neither cleared nor blocked",
                ),
            )

        high = [f for f in findings if f.severity is RiskSeverity.HIGH]
        medium = [f for f in findings if f.severity is RiskSeverity.MEDIUM]
        if high:
            verdict = "high_risk"
            reasons = tuple(f.description for f in high)
        elif medium:
            verdict = "acceptable_with_mitigation"
            reasons = tuple(f.description for f in medium)
        else:
            verdict = "acceptable"
            reasons = (
                "no prohibited category, regulated area or platform restriction "
                f"matched for {', '.join(jurisdictions)}",
            )
        return RiskAssessment(
            findings=tuple(findings),
            jurisdictions_considered=jurisdictions,
            data_gaps=tuple(gaps),
            verdict=verdict,
            reasons=reasons,
        )
