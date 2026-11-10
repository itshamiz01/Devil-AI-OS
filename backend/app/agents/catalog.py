"""The capability catalog (P-04 Stage 5).

Data, not authority. What exists, what risk it carries, what level of authority
it needs, and — for the prohibited ones — why. The enforcement of all of it
lives in :mod:`app.agents.capabilities`, which is the only place a capability is
granted, denied or checked.

The catalog is split from the service for one reason: it is the part that will
grow. P-05 adds execution and adapter capabilities, P-06 adds distribution and
asset capabilities, and each addition is a data change that should leave the
grant/deny logic — the part a reviewer must be able to hold in their head at
once — untouched.

**The catalog is code, not data in the database.** `BUILTIN_CATALOG` is
reconciled into `agent_capabilities` on every startup, and there is deliberately
no endpoint that creates or edits an entry. A capability that could be added over
HTTP could be added at level 0 by whoever holds the grant permission, and then
the level of a capability would depend on who asked. Editing the catalog is a
code change, which means it is reviewed, versioned and attributable.

**Level 3 cannot be lifted from the database.** `PROHIBITED_CAPABILITIES` is a
literal set here and is consulted independently of the catalog row, so deleting
or disabling the row for `spending.authorize` does not make spending
authorizable. The rows exist so an owner can *read* the prohibition and its
reason; enforcement does not depend on them.
"""

from __future__ import annotations

from .lifecycle import AgentStatus
from .schemas import ApprovalLevel, CapabilityDefinition

__all__ = [
    "AUTHORITYLESS_AGENT_STATES",
    "BUILTIN_CATALOG",
    "PROHIBITED_CAPABILITIES",
    "UNGRANTABLE_AGENT_STATES",
]

# --------------------------------------------------------------------------- #
# The catalog
# --------------------------------------------------------------------------- #
#: Level-3 keys, as a literal set. Consulted independently of any catalog row:
#: no database edit can lift one of these.
PROHIBITED_CAPABILITIES: frozenset[str] = frozenset({
    "secrets.store_raw",
    "spending.authorize",
    "financial.execute",
    "approval.self_grant",
    "governance.bypass",
    "identity.impersonate_owner",
    "distribution.publish_unauthorized",
    "evidence.fabricate",
})


def _cap(key: str, name: str, category: str, level: ApprovalLevel,
         access_class: str, description: str, *, enabled: bool = True,
         requires_scope: bool = False, risk: str | None = None,
         prohibited_reason: str = "") -> CapabilityDefinition:
    """Build a catalog entry, deriving the risk from the level unless told.

    Risk describes harm and level describes the authority needed to hold the
    capability. They are separate columns, but in this catalog they move
    together, and deriving one from the other keeps an entry from claiming to be
    low-risk while needing an owner's signature.
    """
    default_risk = {
        ApprovalLevel.AUTONOMOUS: "low",
        ApprovalLevel.CONDITIONAL: "medium",
        ApprovalLevel.OWNER_APPROVAL: "high",
        ApprovalLevel.PROHIBITED: "critical",
    }[level]
    # A prohibited capability is never enabled, and that is derived here rather
    # than typed per entry, for the same reason risk is derived: `enabled` answers
    # "may this be granted at all, today?", and for level 3 the answer is never.
    # Leaving it to each entry would allow one to claim to be both prohibited and
    # available, and would inflate the enabled count a status endpoint reports as
    # though it were authority the system can hand out. "Not yet" and "never" stay
    # distinguishable because approval_level and prohibited_reason say which.
    available = False if level is ApprovalLevel.PROHIBITED else enabled
    return CapabilityDefinition(
        capability_key=key, name=name, category=category, risk_level=risk or default_risk,
        approval_level=level, access_class=access_class, description=description,
        enabled=available, requires_scope=requires_scope,
        prohibited_reason=prohibited_reason)


_L0 = ApprovalLevel.AUTONOMOUS
_L1 = ApprovalLevel.CONDITIONAL
_L2 = ApprovalLevel.OWNER_APPROVAL
_L3 = ApprovalLevel.PROHIBITED

BUILTIN_CATALOG: tuple[CapabilityDefinition, ...] = (
    # ---- L0: read-only authority over records that already exist ------------
    _cap("research.read", "Read research", "research", _L0, "read",
         "Read opportunities, assessments and the evidence recorded against them (P-03)."),
    _cap("tasks.read", "Read tasks", "tasks", _L0, "read",
         "Read tasks, their executions and their history (P-01)."),
    _cap("events.read", "Read system events", "observability", _L0, "read",
         "Read the event log (P-01)."),
    _cap("audit.read", "Read audit records", "observability", _L0, "read",
         "Read audit events, including permission denials (P-01)."),
    _cap("agents.read", "Read the agent registry", "agents", _L0, "read",
         "Read agent rows, their lifecycle state and their provenance (P-04)."),
    _cap("templates.read", "Read agent templates", "agents", _L0, "read",
         "Read templates, their versions and their validation verdicts (P-04 Stage 3)."),
    _cap("monitoring.read", "Read resource state", "observability", _L0, "read",
         "Read resource pressure and system metrics. Labelled per-agent metrics "
         "arrive in P-04 Stage 8."),

    # ---- L1: writes, allowed only while the conditions hold ----------------
    _cap("research.write", "Record research findings", "research", _L1, "write",
         "Open, rank and assess opportunities (P-03). Scope is the opportunity or "
         "sweep the finding belongs to, so a grant cannot be a general licence.",
         requires_scope=True),
    _cap("evidence.write", "Record evidence", "research", _L1, "write",
         "Attach evidence to an opportunity. Scope is the opportunity id: evidence "
         "recorded against something else is not evidence about it.",
         requires_scope=True),
    _cap("tasks.write", "Create and update tasks", "tasks", _L1, "write",
         "Create and update tasks for this agent to execute (P-01)."),
    _cap("memory.write", "Write to agent memory", "memory", _L1, "write",
         "Write to long-term agent memory. Disabled: no memory subsystem exists "
         "yet (deferred by ADR-0008, planned P-09).", enabled=False),

    # ---- L2: an owner must decide ------------------------------------------
    _cap("templates.write", "Author agent templates", "agents", _L2, "write",
         "Create or revise the templates that govern what agents may be. An agent "
         "authoring its own governing definition needs the owner's decision."),
    _cap("agents.create_request", "Request another agent", "agents", _L2, "write",
         "Ask the creation engine for another agent. Delegation depth is bounded "
         "separately by AUTONOMUS_AGENT_MAX_DELEGATION_DEPTH (P-04 Stage 4)."),
    _cap("capabilities.request", "Request a capability", "agents", _L2, "write",
         "Ask for an additional capability for itself or another agent. The request "
         "goes to the owner; this capability does not grant anything by itself."),
    _cap("external.network", "Contact an external host", "execution", _L2, "execute",
         "Reach a host outside loopback. Disabled: the adapters that would use it "
         "are P-05, and egress stays deny-by-default behind "
         "AUTONOMUS_RESEARCH_PERMITTED_HOSTS.", enabled=False),
    _cap("execution.tool", "Invoke an execution tool", "execution", _L2, "execute",
         "Invoke a registered execution tool. Disabled: the tool registry is P-05.",
         enabled=False),
    _cap("filesystem.read", "Read workspace files", "execution", _L2, "read",
         "Read files inside an authorized workspace. The adapter (Stage 3) "
         "enforces containment against the resolved workspace root; scope is "
         "the workspace name.", requires_scope=True),
    _cap("filesystem.write", "Write workspace files", "execution", _L2, "write",
         "Write files inside an authorized workspace. Scope is the workspace path, "
         "so a grant cannot reach outside it. The adapter (Stage 3) writes "
         "atomically and quarantines deletes; scope is the workspace name.",
         requires_scope=True),
    _cap("code.execute", "Execute code", "execution", _L2, "execute",
         "Run generated code in the allow-listed interpreter inside the agent's "
         "workspace, under a wall-clock timeout with capped output. Isolation is "
         "self-labelled weak (subprocess-with-timeout), so every run is Risk 2 and "
         "held for owner approval (§30 rule 22).", requires_scope=True),
    _cap("browser.control", "Drive a browser", "execution", _L2, "execute",
         "Drive a browser session. Disabled: the browser adapter ships "
         "interface-only in P-05.", enabled=False),
    _cap("distribution.publish", "Publish externally", "distribution", _L2, "execute",
         "Publish content to an external channel with the owner's authorization. "
         "Disabled: channel adapters are P-06, and publishing without authorization "
         "is prohibited outright below.", enabled=False),

    # ---- L3: refused unconditionally, with no approval path ----------------
    _cap("secrets.store_raw", "Store a raw secret", "security", _L3, "write",
         "Hold a raw credential, token or password in agent state, a prompt or an "
         "output.",
         prohibited_reason="The Constitution forbids raw credentials in agent "
                           "instructions or persisted agent state. No secret store "
                           "is implemented (ADR-0012), so there is nowhere safe to "
                           "put one and no reason to hold one."),
    _cap("spending.authorize", "Authorize spending", "financial", _L3, "execute",
         "Authorize a purchase, subscription, order or any financial obligation.",
         prohibited_reason="§26 prohibits purchases and spending at every autonomy "
                           "level. There is no configuration key that enables it, "
                           "because a setting would imply the capability exists and "
                           "is merely switched off."),
    _cap("financial.execute", "Execute a financial transaction", "financial", _L3,
         "execute", "Execute a transfer, payment or accounting entry.",
         prohibited_reason="Financial execution is P-07 and "
                           "AUTONOMUS_FINANCIAL_EXECUTION_ENABLED is refused at "
                           "startup by validate_phase_flags. P-06 must prepare an "
                           "interface to it, never implement it."),
    _cap("approval.self_grant", "Decide its own approval", "governance", _L3,
         "execute", "Approve or reject an approval this agent itself requested.",
         prohibited_reason="Self-approval of a critical action is forbidden. The "
                           "central ApprovalService already refuses a requester "
                           "deciding its own high or critical risk approval; this "
                           "entry makes the prohibition explicit in the capability "
                           "vocabulary so it cannot be granted as though it were "
                           "an ordinary authority."),
    _cap("governance.bypass", "Bypass governance", "governance", _L3, "execute",
         "Disable or weaken the permission engine, a phase flag, a validation gate "
         "or the emergency stop.",
         prohibited_reason="An agent that could switch off the thing that constrains "
                           "it would make every other control advisory. The "
                           "emergency stop is owner-only by ADR-0013 and is never "
                           "clearable by an automatic path."),
    _cap("identity.impersonate_owner", "Act as the owner", "governance", _L3,
         "execute", "Act as, speak for, or claim the authority of the owner.",
         prohibited_reason="Owner authority comes from an owner credential and an "
                           "owner session. A capability that conferred it would "
                           "make the distinction between the owner and an agent "
                           "unauditable."),
    _cap("distribution.publish_unauthorized", "Publish without authorization",
         "distribution", _L3, "execute",
         "Publish, post or transmit content externally without the owner's "
         "authorization.",
         prohibited_reason="External publishing requires explicit authorization, and "
                           "no agent may bypass a platform's verification, "
                           "registration or identity checks to achieve it."),
    _cap("evidence.fabricate", "Record unverified data as verified", "research",
         _L3, "write",
         "Record a model-generated, simulated or unverified figure as verified "
         "evidence.",
         prohibited_reason="§19 forbids inventing statistics, prices, market sizes "
                           "or publication dates, and forbids claiming a source was "
                           "queried when it was not. Assumptions are not market "
                           "evidence."),
)

#: Agent states that may not receive a new grant.
UNGRANTABLE_AGENT_STATES = frozenset({
    AgentStatus.SUSPENDED.value, AgentStatus.FAILED.value,
    AgentStatus.RETIRING.value, AgentStatus.RETIRED.value,
})

#: Agent states in which an existing grant confers no authority.
AUTHORITYLESS_AGENT_STATES = UNGRANTABLE_AGENT_STATES


