# ADR-0001: Hybrid AI with local-first operation

- **Decision ID:** ADR-0001
- **Status:** Owner-locked in supplied Constitution v1.0; transcribed for repository reference
- **Date:** 2026-11-03

## Context
AUTONOMUS needs reasoning, coding, research and content capabilities without a mandatory paid API or loss of owner control over data and cost.

## Problem
Select an infrastructure direction that supports local operation and useful optional acceleration without hiding cloud dependencies.

## Options considered
1. Local-only inference permanently.
2. Mandatory cloud inference.
3. Hybrid: local default, optional explicitly authorized cloud providers.

## Selected decision
Option 3, as already approved by the owner. Use replaceable provider adapters, capability-aware routing, shared local inference and explicit privacy/spending controls.

## Reasons
Preserves a no-mandatory-paid-API path while allowing optional quality/capacity improvements. Avoids coupling business logic to one model vendor.

## Consequences
The system must detect provider/model availability, record cloud usage, support local-only operation for supported workflows and pause/defer when local capacity is insufficient. Cloud fallback cannot be silent. Model quality and hardware capacity still require measurement.

## Approval boundary
This ADR records an existing decision; it does not approve a model download, provider account or cloud expenditure.
