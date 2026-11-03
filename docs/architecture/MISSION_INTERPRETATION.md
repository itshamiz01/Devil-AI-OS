# Mission Interpretation and the Mission State Machine (P-02 §7)

## 1. Deterministic interpretation

`MissionInterpreter.interpret(text, principal_id=...)` is pure code. It never calls a model, so it is safe to run on untrusted text and its output is reproducible. It returns an `Interpretation` carrying category, classification, risk, constraints, missing information, assumptions, warnings, limitations and the authority-relevant fields (financial limit, currency, time constraint, approval required, override attempt, secret request).

Category precedence is most-restrictive-first: a request that is simultaneously conversational and financial is categorised as financial.

## 2. Request categories (§7.1) — 10

`general_conversation`, `information`, `analysis`, `research`, `planning`, `project_management`, `business_objective`, `system_management`, `financial_operation`, `prohibited_action`.

## 3. Mission fields (§7.2) — 17

`mission_id`, `owner_principal_id`, `title`, `original_request`, `intended_outcome`, `objective`, `success_criteria`, `constraints`, `available_resources`, `financial_limit`, `financial_limit_currency`, `time_constraint`, `required_capabilities`, `dependencies`, `risk`, `missing_information`, `assumptions` — plus `approval_required`, `expected_deliverables`, `category`, `classification`, `state` and `model_interpreted` for control and provenance.

`model_interpreted` is the attribution flag: when true, a model contributed to the interpretation, so the output is distinguishable from owner-stated fact.

## 4. Classifications (§7.3) — 9

`simple_request`, `information_task`, `analysis_task`, `short_execution_task`, `multi_step_mission`, `long_running_mission`, `high_risk_mission`, `financially_sensitive_mission`, `needs_clarification`.

## 5. Constraint extraction

Only what the owner actually stated is extracted. `_parse_money` recognises an explicit amount and currency; a budget of `$50` becomes `Constraint(kind="budget", value="50.00 USD", numeric_value=50.0, currency="USD", origin="owner_stated", required=True)`.

`Constraint.origin` is one of `owner_stated`, `system_default`, `inferred`, `assumed`, so the provenance of every constraint is visible. Policy constraints the system adds are marked `system_default` and are never presented as owner instructions.

**No default budget, deadline, risk tolerance or success criterion is ever synthesised.** `success_criteria` is always empty unless the owner supplied it. A missing value becomes a `ClarificationQuestion`, not an assumption (§7.4).

## 6. Risk assessment

Risk is classified from the shape of the request, not from its tone:

| Condition | Risk |
|---|---|
| Policy-override attempt or credential request | `CRITICAL` |
| A money-moving verb (`transfer`, `send`, `pay`, `withdraw`, `deposit`, `spend`, `invest`, `purchase`, `buy`, `refund`) **and** a money noun or amount | `CRITICAL` |
| Financially sensitive and an execution verb, with a stated amount | `CRITICAL` |
| Financially sensitive and an execution verb, no amount | `HIGH` |
| Financially sensitive only | `HIGH` |
| Execution verb only | `MODERATE` |
| Otherwise | `LOW` |

The money-verb rule does **not** require a numeric amount. An instruction to "transfer the available money" states no figure and is more dangerous for it, so requiring an amount to reach `CRITICAL` would have inverted the risk. Requiring both a verb and a money noun avoids flagging prose such as "research what customers buy", which describes a market rather than instructing a transfer.

## 7. Clarification

`_is_underspecified` treats a request as needing clarification when it is short, or when it names no concrete subject (product, service, niche, market, audience, software, ebook, course, template, tool, API) and states no budget.

`"Create a business."` produces `needs_clarification` with questions for `target_market`, `offering` and `time_constraint`, and the message *"I will not invent a budget, a market or success criteria."* The response status is `NEEDS_CLARIFICATION` and the category is `clarification_request`.

A mission in `NEEDS_CLARIFICATION`, or carrying any `missing_information`, cannot be planned: `Planner` raises with the missing items named.

## 8. Mission states (§7.5) — 12

`DRAFT`, `NEEDS_CLARIFICATION`, `READY_FOR_PLANNING`, `PLANNING`, `AWAITING_APPROVAL`, `APPROVED`, `EXECUTING`, `PAUSED`, `BLOCKED`, `COMPLETED`, `FAILED`, `CANCELLED`.

`MISSION_TRANSITIONS` defines the only legal moves. `COMPLETED`, `FAILED` and `CANCELLED` are terminal and have no exits; `TERMINAL_MISSION_STATES` is derived from that table rather than restated, so the two cannot disagree. `BLOCKED -> PLANNING` is the replanning path (§9.6).

`validate_mission_transition` raises `ValueError` naming the permitted targets. The API converts that into `409 Conflict` — an illegal transition is a client-visible condition and must not surface as an unhandled `500`.

Every transition is recorded in `mission_history` with `from_state`, `to_state`, `reason` and `actor_id`. A transition without a reason is refused: `transition_mission` requires a non-empty one.

## 9. Verification status

| Claim | Evidence |
|---|---|
| Categories, classification, constraint extraction, risk, clarification | `tests/test_mission_interpreter.py` — 48 tests |
| State machine legality, terminality, history, reason requirement | `tests/test_planning.py`, `tests/test_intelligence_api.py` |
| No invented budget / deadline / success criterion | Asserted directly; `success_criteria` is empty for every interpreted request |
| `$50` extraction with currency and `owner_stated` origin | `tests/test_intelligence_persistence.py` round trip |
