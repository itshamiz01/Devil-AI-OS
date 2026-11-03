# ADR-0002: Controlled autonomy and deterministic authority

- **Decision ID:** ADR-0002
- **Status:** Owner-locked in supplied Constitution v1.0
- **Date:** 2026-11-03

## Context
The system may eventually browse, communicate, publish, write code, create agents and handle money.

## Problem
Operational independence must not become independent ownership, self-granted privilege or unrestricted financial authority.

## Options considered
1. Unrestricted autonomous execution.
2. Approval for every individual task.
3. Controlled autonomy within explicit, deterministic policy and owner authority.

## Selected decision
Option 3. Intelligence proposes actions; application governance authorizes them. The owner retains administrative authority, policy control and emergency shutdown.

## Reasons
Supports useful automation while preserving capital, security, legal boundaries and accountability. A model cannot be the authority that validates its own permissions.

## Consequences
All external actions require scoped tool authorization. Critical actions require bound owner approval. Agents cannot alter their own grants, create unrestricted descendants or disable audit/security. Simulation, supervised and controlled-autonomous modes must not self-elevate.

## Approval boundary
The exact early-phase control implementation is proposed in ADR-0006 and D-03. This ADR does not enable live external execution.
