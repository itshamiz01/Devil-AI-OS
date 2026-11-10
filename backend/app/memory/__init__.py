"""Memory and Continuous Learning Engine (P-09).

Persistent, provenance-carrying institutional memory over P-01–P-08:
classified records with truth classes distinct from facts (§3.1),
governed ingestion (§7), a local hybrid store — relational metadata
authoritative, SQLite vector adapter for similarity (§8) — hybrid
retrieval with hard access filters (§9), context assembly (§10),
evidence-based learning with enforced confidence ceilings (§11),
contradiction/version preservation (§12), and owner controls (§17).

Memory is DATA, never authority (Article 0): nothing here can write
owner instructions, permissions, approvals or spending limits.
"""
from .service import MemoryService

__all__ = ["MemoryService"]
