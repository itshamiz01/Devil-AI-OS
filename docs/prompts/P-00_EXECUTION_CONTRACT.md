# P-00 Execution Contract and Source Reconciliation

**Status:** Derived checklist from the owner's detailed P-00 request, not a verbatim archival copy.

## Authority and provenance

1. The owner supplied the Master Constitution, Prompt Pack and a later detailed P-00 initialization request in this conversation.
2. The named governance files were absent from the initial repository.
3. On 2026-11-03 the owner explicitly selected “Use the texts already supplied.”
4. The owner selected “Continue; mark Windows pending” for the inaccessible Windows hardware audit.
5. The Constitution remains the governing product specification. The Prompt Pack remains the implementation sequence. The detailed P-00 request governs this phase's inspection, deliverables and stop gate.

The transcribed governance documents preserve the supplied substantive requirements with normalized formatting. They are not represented as independently authenticated originals.

## Filename reconciliation

The earlier Prompt Pack used generic initialization filenames. The later P-00 request explicitly requires the following canonical deliverables:

| Required deliverable | Canonical repository path |
|---|---|
| Environment audit | `docs/reports/ENVIRONMENT_AUDIT.md` |
| AI feasibility | `docs/reports/AI_HARDWARE_FEASIBILITY.md` |
| Technology validation | `docs/reports/TECHNOLOGY_VALIDATION.md` |
| System architecture | `docs/architecture/SYSTEM_ARCHITECTURE.md` |
| Database architecture | `docs/architecture/DATABASE_ARCHITECTURE.md` |
| Agent governance | `docs/architecture/AGENT_GOVERNANCE.md` |
| Security foundation | `docs/architecture/SECURITY_FOUNDATION.md` |
| Roadmap | `docs/reports/DEVELOPMENT_ROADMAP.md` |
| Project README | `README.md` |
| Individual ADRs | `docs/decisions/` |

The governance files use the names explicitly requested in the detailed P-00 prompt: `docs/AUTONOMUS_MASTER_CONSTITUTION.md` and `docs/AUTONOMUS_DEVELOPMENT_PROMPT_PACK.md`. Older aliases are recorded in the Prompt Pack rather than duplicated as competing sources.

## Mandatory phase behavior

- Inspect before editing; preserve existing work.
- Validate the proposed stack against current official information and actual available resources.
- Distinguish sandbox evidence from owner-reported or unverified Windows information.
- Document all major components, data entities, agent controls and security boundaries.
- Do not implement P-01 or later, create application modules, connect financial accounts, execute transactions, download models or install unapproved dependencies.
- Do not create empty modules to imply progress.
- Prepare safe configuration examples and Git exclusions.
- Record recommendations separately from owner-locked decisions.
- Run structural checks and perform a separate critical audit pass.
- Report unresolved decisions and remaining limitations honestly.
- Stop at the P-00 gate; do not infer approval for P-01.

## Acceptance evidence map

| Requirement | Evidence location |
|---|---|
| Governance read and established | Transcribed governance files; provenance headers; baseline inspection |
| Workspace inspected | Environment audit; `P00_BASELINE.json` |
| Available hardware inspected | `ENVIRONMENT_EVIDENCE.json`; environment audit |
| Windows hardware inspected | **Pending**, owner-approved deferral; audit helper provided |
| Local AI feasibility | AI feasibility report; no benchmark claimed |
| Technology validation | Technology report and official-source evidence |
| Architecture/data/agents/security | Four architecture documents |
| Roadmap | P-00–P-16 roadmap and phase tracker |
| Safe initialization | README, archive, `.gitignore`, inert configuration examples |
| Audit | Structural verification output and critical review document |
| Independent external approval | **Pending**; same-assistant review is not independent human certification |
| Remaining risks | Known limitations, open decisions and completion report |

A documented design is not a working application. A structural check is not a Windows integration test. A simulated result is not collected revenue.
