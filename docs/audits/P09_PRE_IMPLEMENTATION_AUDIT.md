# P-09 Pre-Implementation Audit (Stage 1, §2.1)

**Date:** 2026-11-09 · **Scope:** actual P-01–P-08 implementations in
staging, inspected before any P-09 code was written. Nothing was
assumed to exist because a prompt once requested it.

## 1. Memory/retrieval remnants in P-01–P-08

**None.** A full search of `backend/app` for vector stores,
embeddings, memory engines and retrieval found exactly three seams,
all in P-04:

- `app/agents/memory_interface.py` — `P04MemoryInterface` implementing
  the P-04 `AgentMemoryInterface` protocol. It serves two scopes from
  real P-04 tables (`agent_configuration_history` from
  `agent_configuration_versions`, `previous_task_references` from
  `agent_task_assignments` joined to `tasks`) and explicitly defers
  three scopes to P-09: `approved_contextual_memory`,
  `business_context`, `approved_lessons_or_evaluations` (returned as
  `unavailable` with the note "P-09 memory is not implemented yet").
  Scoped reads are hard-filtered: owner/system see all; an agent sees
  only its own records; service/system components are refused.
- `app/agents/constants.py` — the capability catalogue entry
  `memory_write`: `supported=False`, "catalogued, not grantable",
  `mapped_permission=None`.
- `app/execution/capabilities.py` — P-05's supported-capability table
  delegates to the P-04 catalogue, so the flip propagates.

No ChromaDB, no embedding code, no memory tables existed. P-09 was
built new, behind the P-04 protocol, not as a parallel store.

## 2. Vector-store decision (tracker note 2) — decided with evidence

- `chromadb` is **not importable** in the backend venv
  (`ModuleNotFoundError: No module named 'chromadb'`); `numpy` is
  also absent. Nothing in `pyproject.toml` declares either.
- Therefore ChromaDB is **not run and never claimed**. The P-00
  telemetry concern (Chroma telemetry recorded ON) is moot here:
  Chroma is not used at all.
- Delivered instead: a replaceable `VectorStore` interface
  (`app/memory/embeddings.py`) with a working **SQLite-backed local
  adapter** (`memory_embeddings` table) and a deterministic,
  fully-offline **local hash embedder** (`local-hash-v1`, 192-dim
  token + trigram hashing, no network, no paid API, no model files).
  Status is reported truthfully at runtime (`sqlite-local`, with the
  note that ChromaDB is not installed and not claimed). A future
  Chroma adapter can be dropped behind the same interface; if it is,
  telemetry must be disabled and proven before use.

## 3. P-04 `memory_write` reconciliation (tracker note 4)

Two grant paths existed and disagreed:

- P-04 creation evaluation rejects any requested capability whose
  catalogue entry is unsupported ("capability 'memory_write' is not
  backed by an implemented subsystem").
- P-05's capability-flip mechanism (`seed_capabilities` over
  `execution_capabilities`, keyed by `(name, version)`) is how
  earlier phases honestly flipped support once a subsystem landed.

P-09 reconciles both the P-05 way: at startup it flips the
`memory_write` catalogue entry to `supported=True` ("backed by the
P-09 governed memory write path") and mirrors the flip into P-05's
`execution_capabilities`. Granting still flows through P-04's normal
permission mapping; P-09 grants nothing itself. Three pre-existing
tests pinned the old unsupported state and were updated with
disclosure comments (see the implementation report).

## 4. Integration surfaces confirmed by inspection

- **P-01:** `Principal`/`PrincipalType` (OWNER/AGENT/SERVICE/SYSTEM),
  `Permission` enum (READ, MODIFY_BUSINESS_DATA, APPROVE_ACTIONS used
  by P-09 routes), hash-bound `approvals` (reused conceptually —
  P-09 needs no new approval flows and creates **no parallel
  approvals table**), `AuditEvent` + `AuditRepository` (P-09's audit
  trail), `system_config` (owner-governed settings, P-09 key
  `memory.settings`, same pattern as P-08's `survival.settings`),
  `Agent` rows carry `business_ref` (used to bind agent memory scope).
- **P-02:** provider interfaces exist, but P-09 has **no LLM
  dependency by construction** (Scenario 10): classification is
  deterministic keyword rules, embeddings are local hashing.
- **P-05:** execution history (`task_executions`) is referenceable as
  a memory source type; nothing copied.
- **P-06:** business records referenced by id (`business_id` on
  memory records); lifecycle untouched.
- **P-07 (tracker note 3):** financial records live in
  `revenue_records`, `expense_records`, `journal_entries`,
  `financial_forecasts`. P-09 stores **references only**;
  `financial_reference` checks existence across those tables and
  returns the source table name — never an amount. No P-09 table has
  a money column.
- **P-08:** `survival_experiments` and `survival_decisions` are real
  rows; `learning.from_experiment` / `from_decision` read them and
  refuse unknown ids. Health/scaling state is never copied.

## 5. House patterns followed

Models per phase in `app/database/models/<phase>.py` on the shared
`Base`/`TimestampMixin`; repositories per phase; API routers under
`/api/v1/<phase>` guarded by `require_permission`; a service facade
constructed in `app/core/application.py` after the previous phase;
scores as integers (basis points) or strings, never floats for money;
migrations additive on the single Alembic chain (P-08 head
`99902c03a197` → P-09 `7b13db7e9bfa`); audit append-only by API.

## 6. Baseline

P-08 head state: **450 tests**, migration head `99902c03a197`,
108 tables. (An early baseline run was discarded: it executed while
files were mid-edit and hit the known 512 MB /tmp exhaustion; the
regression proof for P-09 is the final full run on finished code.)
