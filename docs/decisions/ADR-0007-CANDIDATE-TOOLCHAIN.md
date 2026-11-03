# ADR-0007: Compatible candidate toolchain, not blindly the latest releases

- **Decision ID:** ADR-0007
- **Status:** Proposed; installation, version lock and Windows validation pending
- **Date:** 2026-11-03

## Context
Official registry observations on 2026-11-03 show TypeScript 7.0.2 as latest, while typescript-eslint 8.72.1 advertises TypeScript >=4.8.4 <6.1.0. Sandbox Node 20 is past its published support end date.

## Problem
Select a realistic starting toolchain without replacing the owner's preferred technologies or assuming unrelated latest versions integrate.

## Options considered
1. Install every latest release and resolve failures later.
2. Keep unsupported Node 20.
3. Propose a supported Node LTS and compatible TypeScript line, then verify the complete graph on Windows.

## Selected decision
Propose option 3: Node 24.22.2 LTS, TypeScript 6.0.3, Python 3.13.17 and the observed FastAPI/React/Vite/Tauri candidates, subject to exact dependency resolution and smoke tests. Node 26 LTS is an alternative after compatibility verification.

## Reasons
Node 24 remains supported and satisfies the observed Vite/Vitest requirements. TypeScript 6.0.3 fits the current lint peer range. Retaining Python 3.13 avoids an unmeasured jump to the newest minor.

## Consequences
The frontend plugin peer graph must be resolved in full. Tauri core and CLI have separate version streams. Windows MSVC/Rust/WebView2 and native Python wheels remain unverified. Lockfiles and an SBOM are created only after a successful approved P-01 setup.

## Approval boundary
This is a candidate baseline, not an installed or owner-approved version lock. No package installation occurred in P-00.
