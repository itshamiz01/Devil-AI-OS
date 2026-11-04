# Reasoning, Evidence and Uncertainty (P-02 §8)

## 1. The nine-stage pipeline

`ReasoningPipeline.run(operation, question)` executes nine deterministic stages and returns a `ReasoningTrace`:

1. problem analysis — separate what is known from what is assumed
2. evidence collection — gather records, each with a reliability and a verification status
3. evidence assessment — find the weakest link, not the average
4. hypothesis generation — candidate explanations, each requiring evidence to advance
5. hypothesis ranking — supporting evidence outranks contradicting evidence
6. uncertainty assessment — decide whether a conclusion is warranted at all
7. conclusion or refusal — `refused=True` with a reason when evidence is insufficient
8. model calls — zero on the deterministic path
9. trace assembly — every stage's output retained for audit

`ReasoningTrace.model_calls == 0` on the deterministic path, and a test asserts it. A conclusion reached with no model installed is reached by code.

## 2. Evidence (§8.2)

`Evidence` carries `source`, `observation`, `collected_at`, `reliability`, `verification_status`, `stance`, `trust_domain`, `content_reference` and optional `mission_id`.

**Reliability** (5): `authoritative`, `trusted`, `unverified`, `model_generated`, `untrusted`.
**Verification status** (6, `UncertaintyLevel`): `verified`, `strongly_supported`, `tentative`, `assumed`, `unknown`, `insufficient`.
**Stance** (3): `supporting`, `contradicting`, `neutral`.
**Trust domain** (5): `owner`, `system`, `verified_external`, `model`, `external`.

### The central rule

A model-generated statement is **never** verified evidence. `Evidence._model_output_is_never_verified` is a model validator that makes `reliability=MODEL_GENERATED` incompatible with `verification_status=VERIFIED` at construction time. The rule cannot be bypassed by a caller, because it is enforced by the type rather than by convention.

Two further guards follow from it:

- `EvidenceManager.confirm(evidence_id, confirmed_by=...)` refuses to let model output confirm model output. Without this the system could bootstrap its own facts by having one model claim corroborate another.
- `add_model_claim(claim)` always enters evidence as `MODEL_GENERATED` / `TENTATIVE` / `MODEL` domain. Confirmation by an independent source (`owner`, `system`) promotes it to `VERIFIED`; confirmation `"by model"` raises.

`content_reference` stores a **reference** to an artefact, never the artefact. Retrieved external content is not copied into the database.

## 3. Weakest-link assessment

`weakest(levels)` returns the least trustworthy level in a set, and `UNKNOWN` for an empty set. Conclusions inherit the weakest evidence supporting them, so a single assumed fact prevents a verified conclusion. This is deliberate: averaging reliability would let many weak observations launder one strong claim.

## 4. Hypotheses (§8.3)

`HypothesisManager.propose(statement, confidence=...)` creates a `Hypothesis` in `PROPOSED` status. Statuses (5): `proposed`, `under_testing`, `supported`, `refuted`, `abandoned`.

`update_status` refuses `SUPPORTED` or `REFUTED` without corresponding evidence attached. A hypothesis cannot be declared supported by assertion.

Every hypothesis carries `confidence_basis`, which is **always** `"unvalidated_estimate"`. `HypothesisRecord` in the database defaults to the same string, so a persisted confidence can never be read back as a measured probability. `rank()` orders by attached evidence, with supporting evidence outranking contradicting.

## 5. Uncertainty (§8.4)

`UncertaintyManager.assess(question)` returns an `UncertaintyAssessment` with `level`, `sufficient`, `statement()` and the reasons. It **refuses** rather than forcing a conclusion:

| Situation | Outcome |
|---|---|
| No evidence at all | `level=UNKNOWN`, `sufficient=False`, statement contains *"do not have enough information"* |
| Contradictory strongly-supported evidence | `sufficient=False`, statement names the contradiction |
| Evidence below `min_observations` | `sufficient=False` |
| Consistent verified evidence | `sufficient=True` |

`require_sufficient(question)` raises `InsufficientEvidenceError` instead of guessing. The engine can say *"I do not have enough information"*, and §8.4 treats that as a correct answer rather than a failure.

## 6. Problem analysis

`ProblemAnalyzer.analyze(problem)` returns a `ProblemAnalysis` separating `known` from `unknown`. Evidence at `VERIFIED` reliability lands in `known`; `MODEL_GENERATED` or `ASSUMED` lands in `unknown`. The two lists are what a plan is allowed to build on, and the distinction survives into the response so the owner can see which parts of the reasoning rest on a model's say-so.

## 7. Deterministic work stays in code (§8.5)

Arithmetic, validation, state transitions, permission checks, transforms and rule application are performed by code, never delegated to a model. **Multi-agent debate is not implemented in P-02** and is deliberately excluded: it multiplies inference cost and produces disagreement that the system would then have to adjudicate with the same evidence rules it already applies.

## 8. Verification status

| Claim | Evidence |
|---|---|
| Model output can never be `VERIFIED` | Construction raises; tested |
| Model cannot confirm model | `confirm(..., confirmed_by="model")` raises; tested |
| Weakest-link rule | `weakest([VERIFIED, ASSUMED]) == ASSUMED`; tested |
| Refusal on no evidence and on contradiction | Tested, including the exact statement text |
| `confidence_basis` always `unvalidated_estimate` | Tested on the manager and on the persisted default |
| Zero model calls on the deterministic path | `trace.model_calls == 0`; tested |
| Known/unknown separation | Tested with mixed-reliability evidence |

All of the above are in `tests/test_decisions_context_security.py`.
