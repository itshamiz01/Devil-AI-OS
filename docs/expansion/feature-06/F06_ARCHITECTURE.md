# Expansion Feature 6 — Personal Knowledge & File Intelligence: Architecture

Owner decision recorded: Features 4 (Windows Computer Control) and
5 (PC & System Management) are **DEFERRED by the owner** — they need
his Windows machine. Feature 6 was explicitly approved to proceed
ahead of them. The built sequence is therefore F01 → F02 → F03 →
F06; the app version takes the next built minor, **1.4.0**, per the
F02 versioning rule (minor per expansion feature *built*).

## 1. What exists already (the starting map)

From the Gate 2 readiness review (§7.6, rated READY with
conditions) and a fresh inspection:

- **P-09 is the retrieval owner, and its reuse is clean.**
  `MemoryService` exposes the governed ingestion pipeline
  (`memory.ingestion.ingest`: secret screen → usefulness filter →
  exact-duplicate detection → classify/entities → policy-gated
  store → vector index), hybrid retrieval
  (`memory.retrieval.search`: access filter BEFORE ranking, score
  breakdowns, `no_reliable_memory` honesty), and governed deletion
  (`memory.store.delete`: owner-only, removes the embedding and
  *verifies* its absence before issuing the receipt). The vector
  store is `SqliteVectorStore` fed by `LocalHashEmbedder`
  (`local-hash-v1`, 192-dim hashed token+trigram vectors).
- **P-05's documents adapter** reads text/markdown/CSV inside
  managed workspaces — and explicitly defers PDF and binary
  Office formats ("no existing project dependency supports them").
  It is an agent-execution adapter, not an owner library; F06 does
  not route owner files through the agent execution path.
- **F03 set the storage pattern**: content-addressed bytes under
  `<data_dir>/…`, metadata-only rows, record-level provenance,
  tombstone deletion that really removes bytes.
- **§4.2 inheritance contract** binds every new route: principal
  from `get_principal`, `Permission`-enum gates at the route,
  service-layer checks too, shared P-01 audit facade, secrets as
  metadata only, additive tables, money in P-07 (this feature has
  no money surface at all).

## 2. The two conditions, stated plainly

1. **Extraction beyond text/CSV does not exist.** PDF/DOCX/XLSX
   extraction and OCR are absent. Environment check for this
   build: `pypdf`, `python-docx`, `openpyxl`, `python-pptx` and
   `Pillow` are installable from the index as pinned, pure-local
   libraries (no telemetry, no network behaviour); **no OCR
   engine exists** (no `tesseract` binary), so OCR is recorded
   NOT IMPLEMENTED and images are metadata-only. The four parser
   libraries are added pinned to `requirements.txt` and recorded
   in the implementation report.
2. **Retrieval quality is capped by `local-hash-v1`.** It is a
   lexical approximation (hashed token/trigram overlap), NOT a
   neural semantic model. F06 search surfaces the embedder name
   and this caveat on every response; a real embedding model is
   DEF-A2 / owner-machine work.

## 3. Design: files *into* P-09, never beside it

The review's design question — "files into P-09 records with
source references" — is answered literally:

- A document is extracted into **located segments** (PDF pages,
  DOCX paragraphs/tables, XLSX sheets/row-ranges, PPTX slides,
  text lines). Segments are packed into chunks of ~1,200 chars
  (hard cap 2,000) that never cross a locator boundary, so every
  chunk carries exactly one citation locator.
- Each chunk is ingested through **P-09's own ingestion path**
  (`source_type="document"`, `truth_class="user_provided"`,
  `access_scope="OWNER_ONLY"`, `project_ref=<collection slug>`,
  `source_ref="knowledge_document:<id>"`). The secret screen,
  usefulness filter and duplicate detection therefore apply to
  document content exactly as to any memory — F06 adds no bypass.
- F06's own three tables are a **catalogue and citation map**,
  not an index: `knowledge_collections`,
  `knowledge_documents` (provenance + extraction record),
  `knowledge_chunks` (locator, char span, text hash, the P-09
  `memory_id` it resolved to, and the per-chunk ingestion
  outcome). Embeddings exist only in P-09's store.
- **Search is P-09 retrieval, enriched.** F06 calls
  `memory.retrieval.search`, keeps the hits whose memory ids are
  F06 chunks of live documents, and attaches citations
  (document, filename, chunk, locator). Ranking is P-09's,
  unchanged; F06 re-ranks nothing.
- **Deletion is total and proven.** Deleting a document deletes
  each exclusively-owned memory record through P-09's governed
  deletion (embedding removed, absence verified), removes the
  stored bytes, and drops the catalogue rows. A memory record
  shared with another live document (P-09 exact-duplicate
  linkage) survives until its last referencing document is
  deleted.

## 4. Honesty rules for "file intelligence"

- Anything summary-shaped is **extractive and labelled**: the
  document "excerpt" is the highest keyword-overlap sentences,
  verbatim, under the label *deterministic extractive excerpt —
  not an AI summary*. Keyphrases are token-frequency statistics,
  labelled as such. No fluent generated prose is produced
  anywhere in this feature; there is no LLM to produce it
  (DEF-A2).
- Per-format support states are reported from what the installed
  extractors can actually do, probed at runtime: supported
  formats extract for real; images report
  `metadata_only_ocr_not_implemented`; unknown extensions report
  `unsupported_format` and their text is never invented.
- Document comparison is a deterministic `difflib` text diff,
  labelled as such. Duplicate detection is exact (SHA-256 of
  bytes; P-09 content-hash at chunk level) — near-duplicate
  *similarity* claims are not made.
- **Documents are data, never instructions.** Content found in a
  document is stored as `user_provided` memory data with
  `document` source reliability; F06 contains no path by which
  document text can create a task, a plan, or any execution
  (pack §5 security rule). A security test pins this.

## 5. Boundaries

- **Upload** is the primary intake (raw body, F03 precedent; 25
  MiB cap). **Folder indexing** is confined to
  `<data_dir>/knowledge-import/` — the owner authorizes a folder
  by placing it there and naming it in an owner-only call;
  traversal outside the import root is refused. The owner's real
  folders live on his Windows machine (DEF-A1); nothing here
  pretends to reach them.
- Per-collection **exclusion patterns** (fnmatch) skip files at
  intake with the outcome recorded.
- Everything is owner-only in the service layer (routes also gate
  on the `Permission` enum — the two-depth §4.2 pattern), and
  every act lands in the P-01 audit trail. No outbound network
  code exists in this feature.

## 6. Rollback

Downgrade migration drops the three F06 tables; removing the
feature's chunks from P-09 is a data operation (delete documents
through the API first for a clean index), documented in the
implementation report. The parser libraries are additive pins;
removing them affects no earlier feature (nothing else imports
them).
