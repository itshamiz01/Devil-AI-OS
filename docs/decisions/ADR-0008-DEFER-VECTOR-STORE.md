# ADR-0008: Replaceable retrieval boundary; defer vector-store selection

- **Decision ID:** ADR-0008
- **Status:** Proposed; P-09 selection pending
- **Date:** 2026-11-03

## Context
ChromaDB is a preferred candidate, but the core OS does not yet have retrieval requirements, a corpus or target-hardware benchmarks. The available sandbox has about 1.94 GiB total RAM.

## Problem
Support future semantic memory without making an unbenchmarked vector service a mandatory dependency for basic operation.

## Options considered
1. Install ChromaDB and an embedding model during foundation work.
2. Remove vector retrieval from the long-term architecture.
3. Define a replaceable retrieval interface and defer the concrete store/model until measured need.

## Selected decision
Propose option 3. Preserve ChromaDB as a candidate and retain the owner's required memory capabilities.

## Reasons
Avoids premature memory/dependency cost while keeping the architecture compatible with local embeddings and semantic retrieval.

## Consequences
Early evidence and working state can use structured persistence. P-09 must benchmark retrieval quality, latency, resource use, Windows compatibility, isolation and migration before selecting a store. Retrieval content remains untrusted and scoped.

## Approval boundary
No vector database, embedding model or memory engine is installed or implemented in P-00.
