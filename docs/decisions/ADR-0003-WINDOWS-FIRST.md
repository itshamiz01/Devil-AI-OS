# ADR-0003: Windows-first product direction

- **Decision ID:** ADR-0003
- **Status:** Owner-locked direction; minimum Windows release and hardware pending
- **Date:** 2026-11-03

## Context
The intended product needs a local desktop interface, local models/data, browser automation and Windows computer control.

## Problem
Choose the initial production experience without prematurely optimizing for every platform.

## Options considered
1. Cloud-only application.
2. Cross-platform-first desktop product.
3. Windows-first local desktop with future remote/multi-machine interfaces.

## Selected decision
Option 3, as supplied by the owner. Tauri remains the preferred desktop candidate.

## Reasons
Aligns with local-first operation and required Windows capabilities while leaving explicit expansion boundaries.

## Consequences
Windows startup, shutdown, WebView2, MSVC/Rust, filesystem, automation and recovery must be tested on the target PC. Linux development evidence cannot certify Windows readiness. Remote nodes require authenticated interfaces rather than shared SQLite files.

## Unresolved
D-01: minimum Windows release/architecture and owner PC directory. Windows 11 x64 is recommended because current Playwright documentation lists Windows 11+; this recommendation is not yet an owner-locked minimum.

## Approval boundary
No Windows installation, directory change or desktop implementation occurred in P-00.
