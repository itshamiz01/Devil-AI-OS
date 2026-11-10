# Expansion Feature 6 — Personal Knowledge & File Intelligence: Implementation Report

**Status: BUILT & VERIFIED IN STAGING (10 Nov 2026) — AWAITING OWNER GATE (Gate 3).**
Architecture: `F06_ARCHITECTURE.md` (same folder). Test report:
`F06_TEST_REPORT.md`. Regression evidence: `REGRESSION_EVIDENCE.txt`.
Smoke transcript: `docs/reports/F06_SMOKE_EVIDENCE.txt`.

## What was built

The owner's document library, as one new package
(`backend/app/knowledge/`) extending P-09 in place — no second
memory system, no second index, no second retrieval path.

- **Collections** (`knowledge_collections`): named libraries whose
  `slug` is the P-09 `project_ref`, so scoping is P-09's own
  project mechanism. Per-collection `excluded_patterns` (fnmatch)
  are honoured by folder indexing.
- **Documents** (`knowledge_documents`): full provenance per file —
  filename, source kind (`upload` / `folder`), format, size,
  SHA-256, extractor name, extraction detail, status, and
  byte-duplicate linkage (`duplicate_of_id`). Bytes are stored
  content-addressed under `<data_dir>/knowledge-files/<sha[:2]>/<sha>`
  (the F03 voice-audio pattern); identical bytes are stored once.
  Upload cap 25 MiB. Upload is a raw request body with a
  `filename` query parameter (F03 precedent — no multipart
  dependency added).
- **Real extraction, per format** (`app/knowledge/extractors.py`):
  text/markdown/code via stdlib UTF-8; CSV via stdlib (header row
  carried into every segment); PDF per page via `pypdf`; DOCX via
  `python-docx` (paragraphs and tables in body order); XLSX via
  `openpyxl` (per sheet, row ranges); PPTX via `python-pptx` (per
  slide, text frames and tables). Every extraction produces
  **located segments** (page / sheet+rows / slide / paragraph /
  line range) — the locators are what citations are made of.
  Format support is **probed at runtime** (library import), so the
  status surface reports what this environment can actually do.
- **Honest non-extraction**: images are read with Pillow for
  metadata only (dimensions, mode) and recorded
  `metadata_only` — **OCR is NOT IMPLEMENTED** (no OCR engine
  exists in this environment; status vocabulary says so:
  `metadata_only_ocr_not_implemented`, `ocr: not_implemented`).
  Unknown extensions are stored and recorded
  `unsupported_format` — bytes kept, no text invented. A parser
  refusal is `extraction_failed` with the detail recorded; a
  document with no extractable text is `empty`.
- **Chunking** (`app/knowledge/chunking.py`): located segments are
  packed toward 1200 characters (hard cap 2000) **without ever
  crossing a locator boundary**; char offsets are computed over
  the segment-joined document text.
- **Indexing through P-09's governed ingestion**
  (`memory.ingestion.ingest`), never around it: candidate title
  `"<filename> — <locator>"`, `source_type="document"`,
  `source_ref="knowledge_document:<id>"`, truth class
  `user_provided`, scope `OWNER_ONLY`, project = collection slug.
  P-09's screens therefore govern the library: secret-bearing
  chunks are refused by its sensitive screen (and their text is
  **not persisted in `knowledge_chunks` either** — hash only),
  duplicates dedupe on P-09's own content hash, low-value chunks
  are refused. Chunk rows (`knowledge_chunks`) record the locator,
  char span, text hash and the P-09 outcome
  (`stored` / `duplicate` / `rejected_sensitive` /
  `rejected_low_value`).
- **Cited search**: P-09 `retrieval.search` over exactly the
  memory ids F06 chunks point at (live documents only), each hit
  enriched with citations (document id, filename, chunk index,
  locator). Results additionally pass **P-09's own §9.5
  reliability bar** (task relevance > 0 or semantic similarity
  ≥ 0.35) — a filter, never a re-rank: P-09's order is returned
  unchanged. The response carries the embedder name and caveat.
  Project scoping is P-09's `project_ref` filter.
- **Deterministic intelligence, labelled as such**: keyphrases are
  token-frequency statistics (method named in the payload); the
  "excerpt" is verbatim highest-overlap sentences labelled
  *"deterministic extractive excerpt — verbatim sentences, not an
  AI summary"*; document comparison is a `difflib` diff labelled
  deterministic. Nothing fluent is generated; there is no LLM in
  this path.
- **Lifecycle**: deleting a document deletes its exclusively-owned
  P-09 memories through P-09's governed `store.delete`
  (embedding removed, absence verified, receipts returned in the
  API response); a memory another live document still cites is
  kept and reported (`shared_memories_kept`); stored bytes are
  removed when the last live document sharing the content address
  goes. Deleting a collection cascades through the same path.
  Folder indexing is confined to
  `<data_dir>/knowledge-import/<folder>` — traversal outside it is
  refused and the refusal is audited.
- **Command Center**: Knowledge view (status with probed format
  states + embedder caveat + not-implemented list, collections,
  upload, folder indexing, library with per-document states,
  cited search, document detail with extraction provenance +
  labelled intelligence + chunk table, delete) on real endpoints.

## Authorities and locks held

- **P-09 owns memory, the vector index, retrieval and governed
  deletion** — F06 calls its ingestion/retrieval/store APIs and
  adds no index of its own. **P-10** remains the security
  authority; **P-01** identity/audit: every data-bearing service
  method enforces the owner principal in the service layer, and
  routes additionally gate on the Permission enum
  (`READ_SYSTEM_DATA` reads, `WRITE_SYSTEM_DATA` writes) — the
  §4.2 two-depth pattern. Every act is audited
  (`knowledge.collection.*`, `knowledge.document.*`,
  `knowledge.folder.*` actions in the P-01 trail).
- **P-07 untouched; no money columns and no secret-value columns**
  in the three new tables — schema-guard tested.
- **Article 0 held**: no governance/safety/financial-authority
  code was modified. Document content is treated as **data,
  never instructions** — a document claiming governance authority
  is indexed as ordinary text and creates no task, plan or
  approval (security-tested).
- **No outbound network code** in the feature; all parsing is
  local. The four parser libraries make no network calls.

## Schema and version

- Additive migration **`af39baad9c40`** (revises `c41f7a9d03e6`):
  three tables (`knowledge_collections`, `knowledge_documents`,
  `knowledge_chunks`). Cycle-tested: 232 ⇄ 235 physical tables
  (231 ⇄ 234 metadata). Nothing else in the schema changed.
- API version **1.3.0 → 1.4.0** in `app/core/version.py` per the
  F02 versioning rule; the docstring now records that minors
  follow BUILD order (F06 is the fourth feature built; Features
  4–5 are deferred by owner decision, not built).

## Dependencies added (all pinned, all local, none phone home)

| Package | Pin | Used for |
|---|---|---|
| pypdf | 7.0.1 | PDF text extraction per page |
| python-docx | 1.2.0 | DOCX paragraphs + tables |
| openpyxl | 3.1.5 | XLSX sheets (+ `et-xmlfile==2.0.0` transitive) |
| python-pptx | 1.0.2 | PPTX slides (+ `lxml==6.1.3`, `Pillow==13.0.0`, `XlsxWriter==3.3.1` transitives) |

Pinned exactly in `backend/requirements.txt`; loose ranges in
`backend/pyproject.toml` (established convention). Pillow is
used directly only for image metadata.

## Permission matrix (routes)

| Route | Method | Permission | Service check |
|---|---|---|---|
| `/knowledge/status`, `/knowledge/formats` | GET | `read_system_data` | owner-only when principal passed |
| `/knowledge/collections` | GET/POST | read / `write_system_data` | owner-only |
| `/knowledge/collections/{id}` | DELETE | `write_system_data` | owner-only |
| `/knowledge/collections/{id}/documents` | GET/POST | read / `write_system_data` | owner-only |
| `/knowledge/collections/{id}/index-folder` | POST | `write_system_data` | owner-only |
| `/knowledge/documents/{id}` | GET/DELETE | read / `write_system_data` | owner-only |
| `/knowledge/documents/{id}/content` | GET | `read_system_data` | owner-only |
| `/knowledge/documents/{id}/compare/{other}` | GET | `read_system_data` | owner-only |
| `/knowledge/search`, `/knowledge/duplicates` | GET | `read_system_data` | owner-only |

## Rollback

1. (Optional, for a clean index) delete documents/collections via
   the API first — this removes their P-09 memories through the
   governed path.
2. `alembic downgrade c41f7a9d03e6` — drops the three knowledge
   tables (cycle-verified). Any F06 memories left behind remain
   ordinary P-09 records (source `knowledge_document:<id>`) and
   can be deleted through P-09's own surfaces.
3. Remove `<data_dir>/knowledge-files/` and
   `<data_dir>/knowledge-import/` if a full purge is wanted.
4. The four parser pins are additive — nothing else imports
   them; leaving them installed is harmless, removing them from
   `requirements.txt` is safe.

## Honest limitations (top of the gate, not the footnotes)

1. **Retrieval quality is capped by P-09's `local-hash-v1`
   embedder** — hashed token/trigram overlap, a lexical
   approximation, not neural semantics (readiness-review
   condition (b)). It is named and caveated on the status
   surface and on every search response. A real embedding model
   is an owner-machine configuration step (DEF-A2 family), not
   something staging can supply.
2. **OCR is NOT IMPLEMENTED.** Images are metadata-only. No text
   is ever invented for an image.
3. **Folder access is deliberately confined** to the
   `knowledge-import/` inbox under the data directory — the
   feature does not roam the owner's filesystem (that territory
   belongs to the deferred Windows/PC features).
4. Extraction quality is bounded by the parser libraries: no
   layout reconstruction, no scanned-PDF text (that is OCR), no
   embedded-image text, no macros/formulas evaluation (XLSX cell
   values as stored).
5. DEF-A1 (Windows unverified) and DEF-A2 (no real LLM) stand,
   unchanged by this feature. Classification remains **READY
   FOR CONTROLLED PILOT**.
