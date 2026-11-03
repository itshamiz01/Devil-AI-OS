# ADR-0005: Modular local core and SQLite-first durable work

- **Decision ID:** ADR-0005
- **Status:** Proposed; owner review pending
- **Date:** 2026-11-03

## Context
The first product target is one owner-controlled Windows machine with constrained local resources. The long-term vision includes multiple businesses and machines.

## Problem
Provide durable, testable boundaries without premature distributed infrastructure or a monolithic unrestricted agent script.

## Options considered
1. One large agent process with direct access to all resources.
2. Microservices, distributed queues and PostgreSQL from the start.
3. A modular local application with explicit services, a durable bounded queue and SQLite-first persistence.

## Selected decision
Propose option 3. Keep the desktop shell thin; route all agent actions through application services and a tool gateway; share inference; extract services only after measured need.

## Reasons
Reduces initial operational burden while preserving testability, recovery and a future PostgreSQL/remote-node path. Logical agents do not require separate model servers.

## Consequences
Service boundaries and idempotency must be designed now. SQLite write concurrency and local-host storage limits must be measured. WAL is not a network database. Remote execution requires a later authenticated transport and authority design.

## Approval boundary
No backend, queue, database or worker is implemented in P-00. Acceptance belongs to the P-01 architecture gate.
