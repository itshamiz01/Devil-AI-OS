"""Memory policy: secret detection (§7.4/§18.2), governance-write
prevention (Article 0, §14.5/§18.5) and access control (§14.4/§18.1).

These are pure functions over records and principals so the security
suite can test the boundaries directly, and so every write path in
the engine passes through exactly one gate.
"""
from __future__ import annotations

import re

from ..core.exceptions import PermissionDeniedError
from ..permissions.models import Principal, PrincipalType
from . import constants as C

# ---------------------------------------------------------------------------
# Secret detection. Patterns target credential SHAPES, not values from
# any real system. A match blocks ordinary AND vector storage; the
# recorded security event contains only the pattern name (§18.2).
# ---------------------------------------------------------------------------
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b")),
    ("labelled_secret", re.compile(
        r"(?i)\b(?:password|passwd|api[_-]?key|secret[_-]?key|access[_-]?token|"
        r"auth[_-]?token|private[_-]?key|wallet[_-]?seed|recovery[_-]?code)\s*[:=]\s*\S{6,}")),
    ("session_cookie", re.compile(r"(?i)\bsessionid\s*=\s*[A-Za-z0-9._\-]{12,}")),
    ("long_hex_secret", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
]


def detect_secrets(*texts: str) -> list[str]:
    """Return the NAMES of matched secret patterns (never the values)."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text) and name not in found:
                found.append(name)
    return found


# Instruction-shaped content aimed at governance. Such content may be
# STORED as data (e.g. an episodic record that an attack happened) but
# it can never become an owner instruction or a permission change —
# there is simply no code path from memory to governance. Attempts by
# an AGENT to originate governance categories are refused outright.
GOVERNANCE_CLAIM_RE = re.compile(
    r"(?i)\b(ignore|override|bypass|disable|remove)\b.{0,60}"
    r"\b(owner|approval|permission|security|governance|spending limit|audit)\b"
    r"|\bnew (owner )?instruction\s*:"
    r"|\bgrant (yourself|agent|me)\b.{0,40}\bpermission\b")


def looks_like_governance_claim(text: str) -> bool:
    return bool(text and GOVERNANCE_CLAIM_RE.search(text))


def assert_write_allowed(principal: Principal, *, category: str,
                         access_scope: str, truth_class: str,
                         title: str = "", content: str = "") -> None:
    """The single write gate for memory records (Article 0).

    - Agents may not originate OWNER_INSTRUCTION records, OWNER_ONLY
      scope, or verified_fact truth claims (§14.5/§30 rules 8/17).
    - Instruction-shaped content claiming governance authority is
      refused for agent principals (memory poisoning, Scenario 5);
      for the owner it is stored only as ordinary data — the memory
      engine has no path to permissions, approvals, system_config or
      spending limits regardless of who writes.
    """
    if principal.type is PrincipalType.AGENT:
        if category in C.AGENT_FORBIDDEN_CATEGORIES:
            raise PermissionDeniedError(
                "agents cannot write owner instructions through memory "
                "(Article 0 / §14.5): memory is data, never authority",
                details={"error_category": "MEMORY_GOVERNANCE_WRITE"})
        if access_scope in C.AGENT_FORBIDDEN_SCOPES:
            raise PermissionDeniedError(
                "agents cannot create OWNER_ONLY memory",
                details={"error_category": "MEMORY_GOVERNANCE_WRITE"})
        if truth_class in C.AGENT_FORBIDDEN_TRUTH_CLASSES:
            raise PermissionDeniedError(
                "agents cannot assert verified_fact; verification is an "
                "owner action on evidence (§3.1)",
                details={"error_category": "MEMORY_TRUTH_ESCALATION"})
        if looks_like_governance_claim(f"{title}\n{content}"):
            raise PermissionDeniedError(
                "instruction-shaped content claiming governance authority "
                "is refused as memory poisoning (§18.5, Scenario 5)",
                details={"error_category": "MEMORY_POISONING"})


def can_read(principal: Principal, record) -> bool:
    """§14.4/§18.1 access decision for one record. Hard filter: ranking
    can never widen this (§9.3)."""
    if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
        return True
    if principal.type is PrincipalType.SERVICE:
        return record.access_scope != "OWNER_ONLY"
    if principal.type is not PrincipalType.AGENT:
        return False
    # Agent principals from here.
    scope = record.access_scope
    if scope == "OWNER_ONLY":
        return False
    if scope in ("PRIVATE_AGENT", "TASK_ONLY"):
        return record.agent_id == principal.id
    if scope == "ORGANIZATION_SHARED":
        return True
    # PROJECT_SHARED / BUSINESS_SHARED: the agent's registered
    # business must match the record's business; unscoped records
    # (no business) in PROJECT_SHARED are readable (project context
    # is shared by design), BUSINESS_SHARED requires a business match.
    agent_business = getattr(principal, "business_ref", None)
    if record.business_id:
        return agent_business == record.business_id
    return scope == "PROJECT_SHARED"


def can_read_learning(principal: Principal, record) -> bool:
    """Learning records carry business scope only (plus provenance)."""
    if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM,
                          PrincipalType.SERVICE):
        return True
    if principal.type is not PrincipalType.AGENT:
        return False
    if not record.business_id:
        return True
    return getattr(principal, "business_ref", None) == record.business_id


def agent_business_ref(session_factory, principal: Principal) -> str | None:
    """Resolve an agent principal's registered business (P-01 Agent
    row), mirroring P-07/P-08's business access checks."""
    if principal.type is not PrincipalType.AGENT:
        return None
    from ..database.models.core import Agent as AgentRow
    session = session_factory()
    try:
        row = session.get(AgentRow, principal.id)
        return row.business_ref if row is not None else None
    finally:
        session.close()


class ScopedPrincipal:
    """A principal view carrying the resolved business_ref for the
    pure policy functions (the P-01 Principal model has no such
    field; services resolve it once per request)."""

    def __init__(self, principal: Principal, business_ref: str | None):
        self._principal = principal
        self.type = principal.type
        self.id = principal.id
        self.business_ref = business_ref

    @property
    def raw(self) -> Principal:
        return self._principal
