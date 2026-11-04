"""P-03 §26 governance: what the discovery engine may and may not do.

The permission list is short and the prohibition list is absolute.  AUTONOMOUS may
search authorised sources, generate candidates, estimate costs, analyse
competitors, report, rank and recommend.  It may **not** purchase domains, buy
subscriptions, pay for datasets, run advertisements, place orders, register
businesses, sign contracts, collect payments, launch campaigns, or create any
financial obligation of any kind.

Two implementation choices matter:

* **The prohibition is on the action class, not on a keyword.**  A verb list is
  used to *detect* intent in free text, but the authoritative gate is
  :class:`GovernanceAction`, a closed enumeration.  Anything not explicitly
  permitted is refused, so a new capability cannot become spendable by being
  added to the wrong list.
* **Refusals are recorded.**  A refused action is not quietly dropped; it is
  returned as a decision with a reason, so an audit can show that the boundary
  was reached and held.

This gate is deliberately independent of the autonomy level.  Even a fully
autonomous AUTONOMOUS may not spend money, because §26 is a phase-level
prohibition rather than a supervision setting.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "GOVERNANCE_VERB_PATTERNS",
    "GovernanceAction",
    "GovernanceDecision",
    "GovernanceGate",
    "GovernanceViolation",
    "OBLIGATION_PATTERNS",
    "PERMITTED_ACTIONS",
    "PROHIBITED_ACTIONS",
    "PROHIBITION_REASONS",
]


class GovernanceAction(str, Enum):
    """The closed set of actions this phase recognises.

    ``PERMITTED_*`` members are the §26 allowance list.  ``PROHIBITED_*`` members
    are named individually so that a refusal can state exactly which prohibition
    was reached instead of a generic "not allowed".
    """

    # -- permitted (§26) ---------------------------------------------------- #
    PERMITTED_SEARCH_AUTHORIZED_SOURCE = "search_authorized_source"
    PERMITTED_GENERATE_CANDIDATE = "generate_candidate"
    PERMITTED_ESTIMATE_COST = "estimate_cost"
    PERMITTED_ANALYSE_COMPETITOR = "analyze_competitor"
    PERMITTED_ANALYSE_MARKET = "analyze_market"
    PERMITTED_COLLECT_EVIDENCE = "collect_evidence"
    PERMITTED_SCORE_OPPORTUNITY = "score_opportunity"
    PERMITTED_VALIDATE_OPPORTUNITY = "validate_opportunity"
    PERMITTED_GENERATE_REPORT = "generate_report"
    PERMITTED_RANK_OPPORTUNITY = "rank_opportunity"
    PERMITTED_RECOMMEND_OPPORTUNITY = "recommend_opportunity"
    PERMITTED_SCHEDULE_RESEARCH = "schedule_research"

    # -- prohibited (§26) --------------------------------------------------- #
    PROHIBITED_PURCHASE_DOMAIN = "purchase_domain"
    PROHIBITED_BUY_SUBSCRIPTION = "buy_subscription"
    PROHIBITED_PAY_FOR_DATASET = "pay_for_dataset"
    PROHIBITED_RUN_ADVERTISEMENT = "run_advertisement"
    PROHIBITED_PLACE_ORDER = "place_order"
    PROHIBITED_REGISTER_BUSINESS = "register_business"
    PROHIBITED_SIGN_CONTRACT = "sign_contract"
    PROHIBITED_COLLECT_PAYMENT = "collect_payment"
    PROHIBITED_LAUNCH_CAMPAIGN = "launch_campaign"
    PROHIBITED_CREATE_FINANCIAL_OBLIGATION = "create_financial_obligation"
    PROHIBITED_TRANSFER_FUNDS = "transfer_funds"
    PROHIBITED_SHARE_CREDENTIAL_TO_MODEL = "share_credential_to_model"
    PROHIBITED_EXECUTE_RETRIEVED_CODE = "execute_retrieved_code"


# Classified by member NAME, not by value: the values are the wire form used in
# API payloads and audit records ("purchase_domain") and carry no prefix.  Keying
# the classification off the value produced two empty sets, which would have made
# authorize() refuse every action and then KeyError while looking up the reason.
PERMITTED_ACTIONS: frozenset[GovernanceAction] = frozenset(
    a for a in GovernanceAction if a.name.startswith("PERMITTED_")
)
PROHIBITED_ACTIONS: frozenset[GovernanceAction] = frozenset(
    a for a in GovernanceAction if a.name.startswith("PROHIBITED_")
)

# Import-time self-check.  A governance gate whose classification sets are empty
# is worse than no gate at all, because it fails closed on legitimate research and
# open on nothing - so the invariant is asserted where it cannot be missed.
_uncategorized = set(GovernanceAction) - (PERMITTED_ACTIONS | PROHIBITED_ACTIONS)
if _uncategorized:
    raise RuntimeError(
        "GovernanceAction members are not classified as permitted or prohibited: "
        + ", ".join(sorted(a.name for a in _uncategorized))
    )
if PERMITTED_ACTIONS & PROHIBITED_ACTIONS:
    raise RuntimeError("an action is classified as both permitted and prohibited")
if not PERMITTED_ACTIONS or not PROHIBITED_ACTIONS:
    raise RuntimeError("governance classification produced an empty set")

#: Why each prohibition exists, surfaced verbatim in refusals and reports.
PROHIBITION_REASONS: dict[GovernanceAction, str] = {
    GovernanceAction.PROHIBITED_PURCHASE_DOMAIN: (
        "purchasing a domain creates a financial obligation; §26 reserves all "
        "spend to the owner"
    ),
    GovernanceAction.PROHIBITED_BUY_SUBSCRIPTION: (
        "buying a subscription creates a recurring financial obligation"
    ),
    GovernanceAction.PROHIBITED_PAY_FOR_DATASET: (
        "paying for a dataset or API access is a purchase; research must use "
        "sources the owner has already authorized"
    ),
    GovernanceAction.PROHIBITED_RUN_ADVERTISEMENT: (
        "running advertisements spends money and makes public claims on the "
        "owner's behalf"
    ),
    GovernanceAction.PROHIBITED_PLACE_ORDER: (
        "placing an order commits the owner to a purchase"
    ),
    GovernanceAction.PROHIBITED_REGISTER_BUSINESS: (
        "registering a business creates legal obligations and a legal entity in "
        "the owner's name"
    ),
    GovernanceAction.PROHIBITED_SIGN_CONTRACT: (
        "signing a contract binds the owner legally"
    ),
    GovernanceAction.PROHIBITED_COLLECT_PAYMENT: (
        "collecting payment on the owner's behalf is a financial transaction "
        "requiring the owner's own accounts and tax handling"
    ),
    GovernanceAction.PROHIBITED_LAUNCH_CAMPAIGN: (
        "launching a campaign publishes content and may incur spend"
    ),
    GovernanceAction.PROHIBITED_CREATE_FINANCIAL_OBLIGATION: (
        "creating any financial obligation is prohibited outright"
    ),
    GovernanceAction.PROHIBITED_TRANSFER_FUNDS: (
        "transferring funds is prohibited outright and is not reachable at any "
        "autonomy level"
    ),
    GovernanceAction.PROHIBITED_SHARE_CREDENTIAL_TO_MODEL: (
        "credentials must never be exposed to a model (§27)"
    ),
    GovernanceAction.PROHIBITED_EXECUTE_RETRIEVED_CODE: (
        "code extracted from retrieved content must never be executed (§27)"
    ),
}

#: Patterns that indicate an intended financial obligation in free text.  Used to
#: screen owner-supplied or model-supplied instruction text, never as the
#: authoritative gate.
OBLIGATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.I))
    for label, pattern in (
        ("purchase", r"\b(buy|purchase|order|checkout|pay for|subscribe to)\b"),
        ("advertisement_spend", r"\b(run ads?|advertise|ad campaign|boost post|sponsor)\b"),
        ("contract", r"\b(sign|execute)\b[^.]{0,40}\b(contract|agreement|terms)\b"),
        ("business_registration", r"\b(register|incorporate|form)\b[^.]{0,40}\b(company|business|llc|ltd)\b"),
        ("fund_transfer", r"\b(transfer|wire|remit|send)\b[^.]{0,40}\b(funds?|money|payment)\b"),
        ("payment_collection", r"\b(collect|accept|process)\b[^.]{0,40}\b(payment|charge)\b"),
        ("domain_purchase", r"\b(register|buy|purchase)\b[^.]{0,40}\b(domain|hostname)\b"),
        ("campaign_launch", r"\b(launch|start)\b[^.]{0,40}\b(campaign|funnel ads)\b"),
    )
)

#: Patterns indicating an attempt to make the engine execute or exfiltrate.
GOVERNANCE_VERB_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.I))
    for label, pattern in (
        ("code_execution", r"\b(run|exec|execute|eval)\b[^.]{0,40}\b(code|script|snippet)\b"),
        ("credential_access", r"\b(reveal|share|send|print|expose)\b[^.]{0,60}\b(api[_ ]?key|password|token|secret|credential)\b"),
    )
)


class GovernanceViolation(BaseModel):
    """One detected breach or attempted breach."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    matched_text: str = Field(min_length=1, max_length=400)
    action: GovernanceAction
    reason: str = Field(min_length=1)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GovernanceDecision(BaseModel):
    """The gate's answer for one action."""

    model_config = ConfigDict(extra="forbid")

    action: GovernanceAction
    permitted: bool
    reason: str = Field(min_length=1)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str | None = None

    @model_validator(mode="after")
    def _permitted_matches_the_lists(self) -> "GovernanceDecision":
        expected = self.action in PERMITTED_ACTIONS
        if self.permitted != expected:
            raise ValueError(
                f"action '{self.action.value}' is "
                f"{'permitted' if expected else 'prohibited'} by §26 and the "
                f"decision said {'permitted' if self.permitted else 'prohibited'}"
            )
        return self


class GovernanceGate:
    """Authorises actions and records every refusal."""

    def __init__(self) -> None:
        self._decisions: list[GovernanceDecision] = []
        self._violations: list[GovernanceViolation] = []

    # ------------------------------------------------------------------ #
    def authorize(self, action: GovernanceAction, *, detail: str | None = None) -> GovernanceDecision:
        """Decide one action.  Refusals are recorded, never silently dropped."""
        if action in PERMITTED_ACTIONS:
            decision = GovernanceDecision(
                action=action,
                permitted=True,
                reason=f"'{action.value}' is within the §26 allowance list",
                detail=detail,
            )
        else:
            decision = GovernanceDecision(
                action=action,
                permitted=False,
                reason=PROHIBITION_REASONS.get(
                    action,
                    f"'{action.value}' is not on the §26 allowance list and is "
                    "therefore refused; anything not explicitly permitted is "
                    "prohibited",
                ),
                detail=detail,
            )
        self._decisions.append(decision)
        return decision

    def is_permitted(self, action: GovernanceAction) -> bool:
        return action in PERMITTED_ACTIONS

    def refuse_reason(self, action: GovernanceAction) -> str | None:
        if action in PERMITTED_ACTIONS:
            return None
        return PROHIBITION_REASONS.get(
            action, f"'{action.value}' is not on the §26 allowance list"
        )

    # ------------------------------------------------------------------ #
    def scan_text(self, text: str) -> tuple[GovernanceViolation, ...]:
        """Detect intended financial obligations or execution attempts in text.

        Used on owner-supplied briefs and on any retrieved or model-generated
        instruction before it can influence behaviour.  Detection is advisory: it
        produces violations for review, and the authoritative refusal still comes
        from :meth:`authorize`.
        """
        found: list[GovernanceViolation] = []
        obligation_to_action = {
            "purchase": GovernanceAction.PROHIBITED_CREATE_FINANCIAL_OBLIGATION,
            "advertisement_spend": GovernanceAction.PROHIBITED_RUN_ADVERTISEMENT,
            "contract": GovernanceAction.PROHIBITED_SIGN_CONTRACT,
            "business_registration": GovernanceAction.PROHIBITED_REGISTER_BUSINESS,
            "fund_transfer": GovernanceAction.PROHIBITED_TRANSFER_FUNDS,
            "payment_collection": GovernanceAction.PROHIBITED_COLLECT_PAYMENT,
            "domain_purchase": GovernanceAction.PROHIBITED_PURCHASE_DOMAIN,
            "campaign_launch": GovernanceAction.PROHIBITED_LAUNCH_CAMPAIGN,
            "code_execution": GovernanceAction.PROHIBITED_EXECUTE_RETRIEVED_CODE,
            "credential_access": GovernanceAction.PROHIBITED_SHARE_CREDENTIAL_TO_MODEL,
        }
        for label, pattern in OBLIGATION_PATTERNS + GOVERNANCE_VERB_PATTERNS:
            match = pattern.search(text)
            if match:
                action = obligation_to_action[label]
                found.append(
                    GovernanceViolation(
                        label=label,
                        matched_text=match.group(0)[:400],
                        action=action,
                        reason=PROHIBITION_REASONS[action],
                    )
                )
        self._violations.extend(found)
        return tuple(found)

    # ------------------------------------------------------------------ #
    def violations(self) -> tuple[GovernanceViolation, ...]:
        return tuple(self._violations)

    def refusals(self) -> tuple[GovernanceDecision, ...]:
        return tuple(d for d in self._decisions if not d.permitted)

    def clear(self) -> None:
        """Forget recorded decisions.  Never clears violations."""
        self._decisions.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "permitted_action_count": len(PERMITTED_ACTIONS),
            "prohibited_action_count": len(PROHIBITED_ACTIONS),
            "decisions_recorded": len(self._decisions),
            "refusals_recorded": len(self.refusals()),
            "violations_detected": len(self._violations),
            "prohibited_actions": sorted(a.value for a in PROHIBITED_ACTIONS),
            "permitted_actions": sorted(a.value for a in PERMITTED_ACTIONS),
        }
