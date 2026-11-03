# ADR-0004: Conversation-sourced governance baseline

- **Decision ID:** ADR-0004
- **Status:** Accepted for P-00 by explicit owner selection on 2026-11-03
- **Date:** 2026-11-03

## Context
The initial repository contained only README.md and LICENSE. The Constitution and Prompt Pack required by P-00 were missing as files but had been supplied in the conversation.

## Problem
Establish authoritative documents without inventing requirements or silently treating an unavailable file as read.

## Options considered
1. Invent/reconstruct unspecified governance content.
2. Wait for canonical file uploads.
3. Use the owner-supplied conversation texts with explicit provenance.

## Selected decision
Option 3. The owner selected “Use the texts already supplied.” Save normalized transcriptions under the requested filenames and preserve the distinction between source requirements and derived recommendations.

## Reasons
Allows foundation work while retaining an auditable source and avoiding fabricated authority.

## Consequences
The files are not independently uploaded or signed originals. Their provenance is disclosed. The original README is archived and the license preserved. Contradictions are recorded in the open-decision register rather than silently amended.

## Approval boundary
This accepts the source for P-00 only. It does not approve D-02 phase mapping, D-03 early control slices, D-04 accounting changes or any later implementation.
