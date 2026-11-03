# ADR-0006: Separate financial authority and early protective foundations

- **Decision ID:** ADR-0006
- **Status:** Proposed implementation of constitutional requirements; D-03/D-04 pending
- **Date:** 2026-11-03

## Context
Business execution appears before the comprehensive financial phase in the prompt sequence. The Constitution nevertheless forbids unrestricted spending and unverified revenue.

## Problem
Prevent a sequencing gap in which agents can cause financial effects before deterministic financial controls exist.

## Options considered
1. Wait until P-07 for all financial controls.
2. Give the model temporary spending discretion.
3. Establish minimum control foundations early and keep live financial execution disabled until full verification.

## Selected decision
Propose option 3: early policy, bound approvals, audit, atomic budget reservations and ledger foundations; separate transaction execution and reconciliation; no live financial authority before P-07 gates.

## Reasons
Preserves the prompt order while enforcing the Constitution's non-negotiable capital and authority rules.

## Consequences
P-01/P-02 include small control slices rather than a complete financial product. Deposits/internal transfers are not sales; forecasts are not cash; corrections are append-only. Cash operating results and accrual profit need distinct definitions. ROI requires a defined denominator.

## Approval boundary
D-03 approves the cross-cutting interpretation; D-04 approves accounting terminology. Neither is assumed. No wallet, payment provider, trading account or real transaction is authorized.
