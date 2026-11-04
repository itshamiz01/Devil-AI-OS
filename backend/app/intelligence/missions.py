"""Mission interpretation (P-02 §7).

Converts an owner's natural-language request into a structured mission — or
decides that no mission is warranted at all.

The governing constraint is §7.4: *never invent a budget, authorization or
success criterion*. That shapes the whole design. Everything that carries
authority — budgets, time limits, risk classification, approval requirements —
is extracted **deterministically** from what the owner actually wrote, and each
extracted constraint records its `origin` so a system default can never be
mistaken for an owner instruction.

A model may *enrich* an interpretation (suggesting an objective phrasing or
deliverables), but enrichment can never create a constraint, raise a risk level,
or grant an approval. When no model is available the interpreter still works; it
simply reports less, and says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schemas import (
    ClarificationQuestion,
    Constraint,
    Mission,
    MissionClassification,
    MissionState,
    RequestCategory,
    RiskLevel,
    validate_mission_transition,
)

# --------------------------------------------------------------------------- #
# Deterministic signal extraction
# --------------------------------------------------------------------------- #

#: Currency amounts: "$50", "50 USD", "€30", "1,000 dollars".
_MONEY = re.compile(
    r"""(?P<symbol>[$€£])\s*(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?)
        |(?P<amount2>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<code>USD|EUR|GBP|dollars?|euros?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SYMBOL_TO_CODE = {"$": "USD", "€": "EUR", "£": "GBP"}

#: Time windows: "in 30 days", "within 2 weeks", "by next month".
_TIME_WINDOW = re.compile(
    r"\b(?:in|within|over|by)\s+(?:the\s+)?(?:next\s+)?(\d+\s+)?(day|week|month|year|hour)s?\b",
    re.IGNORECASE,
)

#: Financial operations. Presence makes a request financially sensitive (§20 D).
_FINANCIAL = re.compile(
    r"\b(?:transfer|send|pay|payment|purchase|buy|spend|invest|withdraw|deposit|"
    r"invoice|refund|transaction|wallet|bank|credit\s*card|money|funds|capital|budget|revenue)\b",
    re.IGNORECASE,
)

#: Verbs that would cause an external, possibly irreversible effect.
_EXECUTION = re.compile(
    r"\b(?:launch|publish|deploy|execute|run|create|build|ship|release|register|sign\s*up|post|email|contact)\b",
    re.IGNORECASE,
)

#: Attempts to override system policy. §20 Scenario D and §12.4 both require
#: these to be recognised and refused rather than obeyed.
_OVERRIDE = re.compile(
    r"\b(?:ignore|disregard|bypass|override|disable|forget|turn\s*off)\b[^.]{0,40}"
    r"\b(?:all\s+)?(?:restrictions?|rules?|limits?|policies|policy|safeguards?|instructions?|"
    r"permissions?|approval[s]?|security|constraints?|guidelines?)\b",
    re.IGNORECASE,
)

#: Requests for credentials or secrets — always refused, never executed.
_SECRET_REQUEST = re.compile(
    r"\b(?:reveal|show|print|dump|expose|leak|give)\b[^.]{0,40}"
    r"\b(?:credentials?|passwords?|secrets?|api\s*keys?|private\s*keys?|tokens?)\b",
    re.IGNORECASE,
)

#: Verbs that move money. Combined with a money noun or an explicit amount these
#: make a request CRITICAL: an irreversible financial operation. Requiring both a
#: verb and a money noun avoids flagging prose such as "research what customers
#: buy", which describes a market rather than instructing a transfer.
_FINANCIAL_ACTION = re.compile(
    r"\b(?:transfer|send|pay|withdraw|deposit|spend|invest|purchase|buy|refund)\b",
    re.IGNORECASE,
)

_MONEY_NOUN = re.compile(
    r"\b(?:money|funds|capital|cash|balance|account|wallet|payment|budget)\b",
    re.IGNORECASE,
)

_PLANNING = re.compile(r"\b(?:roadmap|plan|planning|strategy|strategic|steps?\s+to|how\s+(?:do|can)\s+i)\b", re.IGNORECASE)
_RESEARCH = re.compile(r"\b(?:research|investigate|explore|market|demand|competitors?|validate|opportunity|opportunities)\b", re.IGNORECASE)
_ANALYSIS = re.compile(r"\b(?:analy[sz]e|analy[sz]is|compare|evaluate|assess|review|estimate|calculat\w+)\b", re.IGNORECASE)
_SYSTEM = re.compile(r"\b(?:status|health|restart|shutdown|backup|restore|configur\w+|logs?|database|queue|emergency)\b", re.IGNORECASE)
_BUSINESS = re.compile(r"\b(?:business|company|startup|product|service|customers?|sales?|revenue|profit|launch)\b", re.IGNORECASE)


def _parse_money(text: str) -> tuple[float | None, str | None]:
    """Extract the first explicit monetary amount, if the owner stated one."""
    match = _MONEY.search(text)
    if not match:
        return None, None
    if match.group("amount") is not None:
        amount = float(match.group("amount").replace(",", ""))
        return amount, _SYMBOL_TO_CODE.get(match.group("symbol"), "USD")
    if match.group("amount2") is not None:
        amount = float(match.group("amount2").replace(",", ""))
        code = (match.group("code") or "USD").upper()
        if code.startswith("DOLLAR"):
            code = "USD"
        elif code.startswith("EURO"):
            code = "EUR"
        return amount, code
    return None, None


# --------------------------------------------------------------------------- #
# Interpretation result
# --------------------------------------------------------------------------- #


@dataclass
class Interpretation:
    """Everything the deterministic interpreter concluded about a request."""

    category: RequestCategory
    classification: MissionClassification
    needs_mission: bool
    risk: RiskLevel
    constraints: list[Constraint] = field(default_factory=list)
    missing_information: list[ClarificationQuestion] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Non-empty when the interpreter could not do full semantic work because no
    #: model was available. Surfaced to the owner rather than hidden (§6.4).
    limitations: list[str] = field(default_factory=list)
    title: str | None = None
    objective: str | None = None
    intended_outcome: str | None = None
    required_capabilities: list[str] = field(default_factory=list)
    expected_deliverables: list[str] = field(default_factory=list)
    approval_required: bool = False
    override_attempt: bool = False
    secret_request: bool = False
    financial_limit: float | None = None
    financial_limit_currency: str | None = None
    time_constraint: str | None = None
    #: True only if a model contributed. Deterministic extraction leaves this
    #: False, which keeps model output attributable (§16).
    model_assisted: bool = False

    def hard_constraints(self) -> list[Constraint]:
        return [c for c in self.constraints if c.required or c.kind in {"budget", "policy", "risk"}]


class MissionInterpreter:
    """Deterministic request interpretation, with optional model enrichment.

    Every method that affects authority is pure and synchronous, so its behaviour
    is testable without a model and identical on every run.
    """

    #: Below this length a request is unlikely to carry a real mission, and
    #: §7.3 forbids turning an ordinary question into a complex mission.
    SHORT_REQUEST_CHARS = 120

    def detect_override_attempt(self, text: str) -> bool:
        return bool(_OVERRIDE.search(text))

    def detect_secret_request(self, text: str) -> bool:
        return bool(_SECRET_REQUEST.search(text))

    def detect_financial_sensitivity(self, text: str) -> bool:
        return bool(_FINANCIAL.search(text))

    def extract_constraints(self, text: str) -> list[Constraint]:
        """Pull out only what the owner actually stated.

        Note what is *absent*: no default budget, no assumed deadline, no
        inferred risk tolerance. §7.4 forbids inventing them, so if the owner did
        not say it, it is not here — it becomes a clarification question instead.
        """
        constraints: list[Constraint] = []

        amount, currency = _parse_money(text)
        if amount is not None:
            constraints.append(
                Constraint(
                    kind="budget",
                    value=f"{amount:.2f} {currency}",
                    numeric_value=amount,
                    currency=currency,
                    origin="owner_stated",
                    required=True,
                )
            )

        time_match = _TIME_WINDOW.search(text)
        if time_match:
            raw = time_match.group(0).strip()
            constraints.append(
                Constraint(kind="time", value=raw, origin="owner_stated", required=True)
            )

        if self.detect_financial_sensitivity(text):
            constraints.append(
                Constraint(
                    kind="policy",
                    value="financial operations require the authorized financial infrastructure and owner approval",
                    origin="system_default",
                    required=True,
                )
            )

        return constraints

    def assess_risk(self, text: str, constraints: list[Constraint]) -> RiskLevel:
        """Classify risk from the operation and its consequences (§10.3).

        Deterministic and conservative: an override attempt or a credential
        request is CRITICAL regardless of how politely it is phrased, because
        both are attempts to escape the permission boundary.
        """
        if self.detect_override_attempt(text) or self.detect_secret_request(text):
            return RiskLevel.CRITICAL

        has_money = any(c.kind == "budget" for c in constraints)
        financial = self.detect_financial_sensitivity(text)
        execution = bool(_EXECUTION.search(text))

        # An instruction that moves money is CRITICAL whether or not an amount was
        # stated. §20 Scenario D targets exactly this shape of request, and an
        # unbounded transfer is not safer than a bounded one.
        if _FINANCIAL_ACTION.search(text) and (has_money or _MONEY.search(text) or _MONEY_NOUN.search(text)):
            return RiskLevel.CRITICAL

        if financial and execution:
            return RiskLevel.CRITICAL if has_money else RiskLevel.HIGH
        if financial:
            return RiskLevel.HIGH
        if execution:
            return RiskLevel.MODERATE
        return RiskLevel.LOW

    def classify_category(self, text: str) -> RequestCategory:
        """Map a request onto exactly one category (§7.1).

        Ordering encodes precedence: a request that needs approval outranks one
        that merely needs execution, which outranks research, and so on. The most
        restrictive reading wins, so a request is never under-classified into a
        path with weaker controls.
        """
        if self.detect_override_attempt(text) or self.detect_secret_request(text):
            return RequestCategory.APPROVAL_REQUIRED
        if _SYSTEM.search(text) and not _BUSINESS.search(text):
            return RequestCategory.SYSTEM_MANAGEMENT
        if self.detect_financial_sensitivity(text) and _EXECUTION.search(text):
            return RequestCategory.TASK_EXECUTION
        if _RESEARCH.search(text):
            return RequestCategory.RESEARCH
        if _PLANNING.search(text):
            return RequestCategory.PLANNING
        if _BUSINESS.search(text):
            return RequestCategory.BUSINESS_OBJECTIVE
        if _ANALYSIS.search(text):
            return RequestCategory.ANALYSIS
        if text.strip().endswith("?"):
            return RequestCategory.INFORMATION
        return RequestCategory.GENERAL_CONVERSATION

    def classify_mission(self, text: str, category: RequestCategory, risk: RiskLevel,
                         constraints: list[Constraint]) -> MissionClassification:
        """Decide how much machinery the request deserves (§7.3)."""
        stripped = text.strip()

        if risk == RiskLevel.CRITICAL:
            return MissionClassification.HIGH_RISK_MISSION
        if any(c.kind == "budget" for c in constraints) and self.detect_financial_sensitivity(text):
            return MissionClassification.FINANCIALLY_SENSITIVE_MISSION

        if category == RequestCategory.GENERAL_CONVERSATION:
            return MissionClassification.SIMPLE_REQUEST
        if category == RequestCategory.INFORMATION:
            return MissionClassification.INFORMATION_TASK
        if category == RequestCategory.ANALYSIS:
            return MissionClassification.ANALYSIS_TASK

        # Business, research and planning requests are multi-step by nature, but
        # an underspecified one needs clarification before it can be planned.
        if category in {
            RequestCategory.BUSINESS_OBJECTIVE,
            RequestCategory.RESEARCH,
            RequestCategory.PLANNING,
            RequestCategory.TASK_EXECUTION,
        }:
            if self._is_underspecified(stripped, constraints):
                return MissionClassification.NEEDS_CLARIFICATION
            if len(stripped) > self.SHORT_REQUEST_CHARS or category == RequestCategory.RESEARCH:
                return MissionClassification.LONG_RUNNING_MISSION
            return MissionClassification.MULTI_STEP_MISSION

        if category == RequestCategory.SYSTEM_MANAGEMENT:
            return MissionClassification.SHORT_EXECUTION_TASK
        return MissionClassification.SIMPLE_REQUEST

    def _is_underspecified(self, text: str, constraints: list[Constraint]) -> bool:
        """True when planning would require inventing facts (§7.4).

        A business objective with no stated budget, market or product is not
        plannable: any plan would be built on invented constraints. Rather than
        fabricate them, the engine asks.
        """
        words = len(text.split())
        if words < 6:
            return True
        has_budget = any(c.kind == "budget" for c in constraints)
        has_concrete_subject = bool(re.search(r"\b(?:product|service|niche|market|audience|software|ebook|course|template|tool|api)\b", text, re.IGNORECASE))
        return not (has_budget or has_concrete_subject)

    def build_clarifications(self, text: str, classification: MissionClassification,
                             constraints: list[Constraint]) -> list[ClarificationQuestion]:
        """Ask only about what is genuinely required (§7.4).

        Required information and optional preferences are separated: a missing
        budget blocks planning, while a missing colour preference does not.
        """
        if classification != MissionClassification.NEEDS_CLARIFICATION:
            return []

        questions: list[ClarificationQuestion] = []
        kinds = {c.kind for c in constraints}

        if "budget" not in kinds and self.detect_financial_sensitivity(text):
            questions.append(ClarificationQuestion(
                question="What budget may this mission use? A budget is never assumed.",
                field="financial_limit", required=True,
            ))
        if not re.search(r"\b(?:market|audience|customers?|region|country)\b", text, re.IGNORECASE):
            questions.append(ClarificationQuestion(
                question="Which market or audience is this intended for?",
                field="target_market", required=True,
            ))
        if not re.search(r"\b(?:product|service|offering|deliverable)\b", text, re.IGNORECASE):
            questions.append(ClarificationQuestion(
                question="What kind of product or service should be considered?",
                field="offering", required=True,
            ))
        if "time" not in kinds:
            questions.append(ClarificationQuestion(
                question="Is there a timeframe you want this completed within?",
                field="time_constraint", required=False,
            ))
        return questions

    def interpret(self, text: str, *, principal_id: str | None = None) -> Interpretation:
        """Full deterministic interpretation of a request.

        This never calls a model, so it is safe to use on untrusted text: it
        cannot be talked into anything, and its output is reproducible.
        """
        if not text or not text.strip():
            raise ValueError("request text must not be empty")

        override = self.detect_override_attempt(text)
        secret_request = self.detect_secret_request(text)
        constraints = self.extract_constraints(text)
        risk = self.assess_risk(text, constraints)
        category = self.classify_category(text)
        classification = self.classify_mission(text, category, risk, constraints)

        amount, currency = _parse_money(text)
        time_match = _TIME_WINDOW.search(text)

        warnings: list[str] = []
        limitations: list[str] = []
        approval_required = False

        if override:
            warnings.append(
                "The request asked the system to ignore its restrictions. Restrictions "
                "are not optional and were not relaxed; the permission engine remains "
                "authoritative."
            )
            approval_required = True
        if secret_request:
            warnings.append(
                "The request asked for stored credentials. Credentials are never "
                "returned through the intelligence interface."
            )
            approval_required = True
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            approval_required = True
        if self.detect_financial_sensitivity(text):
            warnings.append(
                "Financial operations require the authorized financial infrastructure "
                "and explicit owner approval. P-02 can plan but cannot execute them."
            )

        # No model ran, so semantic enrichment is unavailable. Say so plainly
        # instead of leaving the owner to guess why the interpretation is thin.
        limitations.append(
            "Deterministic interpretation only: no local inference runtime is "
            "available, so semantic enrichment (objective phrasing, deliverables, "
            "capability inference) was not performed."
        )

        needs_mission = classification not in {
            MissionClassification.SIMPLE_REQUEST,
            MissionClassification.INFORMATION_TASK,
        }

        return Interpretation(
            category=category,
            classification=classification,
            needs_mission=needs_mission,
            risk=risk,
            constraints=constraints,
            missing_information=self.build_clarifications(text, classification, constraints),
            assumptions=[],  # never populated by deterministic extraction
            warnings=warnings,
            limitations=limitations,
            title=self._derive_title(text),
            financial_limit=amount,
            financial_limit_currency=currency if amount is not None else None,
            time_constraint=time_match.group(0).strip() if time_match else None,
            approval_required=approval_required,
            override_attempt=override,
            secret_request=secret_request,
            required_capabilities=self._infer_capabilities(text, category),
            model_assisted=False,
        )

    def _derive_title(self, text: str) -> str:
        """A short, faithful title taken from the owner's own words.

        Truncation only — no paraphrase, because a paraphrase is a model-style
        invention and the deterministic path must not invent.
        """
        cleaned = " ".join(text.split())
        return cleaned[:80] if len(cleaned) > 80 else cleaned

    def _infer_capabilities(self, text: str, category: RequestCategory) -> list[str]:
        """Map the request onto registered capability identifiers.

        Only capabilities that actually exist may be named (§11.2 forbids
        advertising capabilities without implementations), so this returns
        identifiers the capability registry is expected to hold.
        """
        capabilities: list[str] = []
        if category in {RequestCategory.ANALYSIS, RequestCategory.RESEARCH}:
            capabilities.append("analyze.text")
        if category == RequestCategory.PLANNING:
            capabilities.append("plan.generate")
        if _MONEY.search(text) or _ANALYSIS.search(text):
            capabilities.append("compute.deterministic")
        if category == RequestCategory.SYSTEM_MANAGEMENT:
            capabilities.append("system.read")
        return sorted(set(capabilities))

    def to_mission(self, text: str, interpretation: Interpretation, *,
                   owner_principal_id: str, mission_id: str) -> Mission:
        """Materialise a Mission from a deterministic interpretation."""
        state = (
            MissionState.NEEDS_CLARIFICATION
            if interpretation.classification == MissionClassification.NEEDS_CLARIFICATION
            or interpretation.missing_information
            else MissionState.DRAFT
        )
        return Mission(
            mission_id=mission_id,
            owner_principal_id=owner_principal_id,
            title=interpretation.title or self._derive_title(text),
            original_request=text,
            intended_outcome=interpretation.intended_outcome,
            objective=interpretation.objective,
            success_criteria=[],  # never invented (§7.4)
            constraints=interpretation.constraints,
            financial_limit=interpretation.financial_limit,
            financial_limit_currency=interpretation.financial_limit_currency,
            time_constraint=interpretation.time_constraint,
            required_capabilities=interpretation.required_capabilities,
            risk=interpretation.risk,
            missing_information=interpretation.missing_information,
            assumptions=interpretation.assumptions,
            approval_required=interpretation.approval_required,
            expected_deliverables=interpretation.expected_deliverables,
            category=interpretation.category,
            classification=interpretation.classification,
            state=state,
            model_interpreted=interpretation.model_assisted,
        )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "Interpretation",
    "MissionInterpreter",
    "utcnow",
    "validate_mission_transition",
]
