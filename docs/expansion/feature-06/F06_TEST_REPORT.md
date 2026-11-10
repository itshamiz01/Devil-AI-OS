# Expansion Feature 6 — Personal Knowledge & File Intelligence: Test Report

**Final code, 10 Nov 2026. All counts verified on disk / by run,
not asserted.**

## Feature suite (new): 56 tests, all passing

| File | Tests | Covers |
|---|---|---|
| `tests/test_f06_unit.py` | 17 | Extractors per format (real bytes built with the parser libraries; hand-built minimal PDF), runtime support probing, chunking (locator boundaries never crossed, caps), deterministic intelligence (keyphrase statistics, extractive excerpt, difflib compare), schema guards (no money / secret-value columns; migration cycle 232 ⇄ 235), metadata count 234 |
| `tests/test_f06_integration.py` | 28 | End-to-end over the real app: collection CRUD, uploads per format with real extraction evidence (PDF pages, XLSX sheets, DOCX, PPTX, CSV), byte-duplicate + P-09 duplicate outcomes, secret-screened chunk (text persisted nowhere — hash only), cited search (unscoped + project-scoped, reliability bar, P-09 order preserved), duplicates listing, compare, folder indexing incl. exclusions, deletion (bytes + index removed with verification receipts; shared memory kept while a duplicate lives; collection cascade), audit rows |
| `tests/test_f06_security.py` | 11 | Owner-only enforcement in the service layer for **every** data-bearing method (incl. `status()`/`formats()`), 401/403 discipline at the routes, governance-injection document indexed as inert data (no task/plan/approval created), folder traversal refused + audited, upload cap, secret-shaped content never persisted (document row, chunk rows, memory store), no-network source guard over `app/knowledge/` |

Test corpus (`tests/f06_support.py`) builds **real files**: a
hand-constructed minimal PDF with a correct xref table that
pypdf genuinely extracts, DOCX/XLSX/PPTX built with the same
libraries that parse them, a Pillow PNG. No mock parsers, no
fixture text presented as extraction.

## Full regression (final code)

- **Backend: 1113 passed / 0 failed / 0 errors** (1057 F03
  baseline + 56 F06), 22 chunks of 4 files over the
  C-locale-sorted list, per-chunk tmpfs basetemp + pruning.
  Evidence: `REGRESSION_EVIDENCE.txt` (same folder), including
  the honest first-pass record (26 pin failures + 21 tmpfs
  disk-full errors, all dispositioned: pins advanced with F06
  disclosure comments in 17 earlier files, erroring chunks
  re-run green, final full pass clean).
- **Frontend: 66 passed / 0 failed** (62 baseline + 4 new
  Knowledge view tests); strict TypeScript build clean
  (`tsc --noEmit && vite build`); dist rebuilt.
- **Live smoke: 31 passed / 0 failed** (`scripts/f06_smoke.py`,
  real uvicorn, throwaway auto-migrated DB; owner login attempt
  1 behind the `/health/ready` gate). Two smoke expectations
  were corrected during the run — both times the *product* was
  right and the smoke's assumption was wrong (shared-memory
  retention on first delete; the receipt field name
  `shared_memories_kept`). Transcript:
  `docs/reports/F06_SMOKE_EVIDENCE.txt`.

## Acceptance mapping (pack feature-6 section + Gate 3)

- Document ingestion with provenance + real extraction per
  supported format — integration tests + smoke, real bytes.
- Honest unsupported/not-configured states — unit + integration
  + smoke (image metadata-only, OCR not implemented, unknown
  extension `unsupported_format`).
- Indexing into P-09's existing store/ingestion (no second
  index) — integration (memory ids on chunk rows; P-09
  governance outcomes recorded) + source review.
- Retrieval with citations — integration + smoke (filename +
  locator on every hit; reliability bar; scoped isolation).
- Intelligence labelled deterministic — unit + frontend tests
  (excerpt label rendered verbatim).
- Deletion removes bytes AND index — integration + smoke
  (verification receipts; content address removed; shared
  memory kept until last holder deletes).
- Permission/audit discipline — security file (service-layer
  owner checks, route gates, audit assertions).

## Standing defects

DEF-A1 (Windows unverified) and DEF-A2 (no real LLM) stand.
No new defect was opened by this feature. The known
retrieval-quality cap is a property of P-09's embedder
(recorded in the implementation report's limitations), not a
defect introduced here.
