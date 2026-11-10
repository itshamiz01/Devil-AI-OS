import React, { useRef, useState } from "react";
import { ApiError, api, apiUpload } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import {
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";

/**
 * Expansion Feature 6 (Personal Knowledge & File Intelligence):
 * the owner's document library. Everything renders real
 * endpoints — the view holds no document state of its own.
 *
 * Honesty rules the layout: format support states are the
 * runtime-probed ones (images read metadata_only_ocr_not_
 * implemented — OCR does not exist here and no text is ever
 * invented); search results carry their citations (document +
 * chunk locator) and the embedder caveat is shown, because
 * retrieval runs on P-09's local-hash-v1 lexical embedder;
 * anything summary-shaped is labelled a deterministic
 * extractive excerpt — verbatim sentences, not an AI summary.
 */

export interface KnowledgeStatus {
  api_version: string;
  counts: {
    collections: number;
    documents: number;
    chunks: number;
    indexed_chunks: number;
  };
  formats: Record<string, string>;
  embedder: string;
  embedder_caveat: string;
  not_implemented: string[];
}

export interface CollectionRow {
  id: string;
  name: string;
  slug: string;
  description: string;
  excluded_patterns: string[];
  document_count?: number;
  created_at?: string | null;
}

export interface DocumentRow {
  id: string;
  collection_id: string;
  filename: string;
  source_kind: string;
  format: string;
  size_bytes: number;
  sha256: string;
  status: string;
  extractor_name?: string | null;
  extraction_detail: Record<string, unknown>;
  chunk_count: number;
  indexed_chunk_count: number;
  duplicate_of_id?: string | null;
  error_detail?: string | null;
  created_at?: string | null;
}

export interface ChunkRow {
  id: string;
  chunk_index: number;
  locator: string;
  text?: string | null;
  memory_id?: string | null;
  index_status: string;
}

export interface DocumentDetail extends DocumentRow {
  chunks: ChunkRow[];
  intelligence: {
    keyphrases: { phrase: string; count: number }[];
    keyphrase_method: string;
    excerpt: { label: string; sentences: string[] };
  };
}

export interface SearchHit {
  memory_id: string;
  score: number;
  excerpt: string;
  citations: {
    document_id: string;
    filename: string;
    locator: string;
    chunk_index: number;
  }[];
}

export interface SearchResult {
  query: string;
  count: number;
  results: SearchHit[];
  embedder: string;
  embedder_caveat: string;
  method: string;
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : "request failed";
}

export function KnowledgeView(): React.ReactElement {
  const status = useApi<KnowledgeStatus>("/knowledge/status");
  const collections = useApi<CollectionRow[]>("/knowledge/collections");
  const [selectedCollection, setSelectedCollection] = useState<string | null>(
    null,
  );
  const [selectedDocument, setSelectedDocument] = useState<string | null>(
    null,
  );
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [folder, setFolder] = useState("");
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const documents = useApi<DocumentRow[]>(
    selectedCollection
      ? `/knowledge/collections/${selectedCollection}/documents`
      : null,
  );
  const detail = useApi<DocumentDetail>(
    selectedDocument ? `/knowledge/documents/${selectedDocument}` : null,
  );

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      setNotice(label);
      status.reload();
      collections.reload();
      documents.reload();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const createCollection = () =>
    act("Collection created.", async () => {
      const created = await api<CollectionRow>("/knowledge/collections", {
        method: "POST",
        body: { name: newName, description: newDescription },
      });
      setNewName("");
      setNewDescription("");
      setSelectedCollection(created.data.id);
      setSelectedDocument(null);
    });

  const uploadFile = (file: File) => {
    if (!selectedCollection) return;
    void act(`Document added (${file.name}).`, () =>
      apiUpload(
        `/knowledge/collections/${selectedCollection}/documents?filename=${encodeURIComponent(file.name)}`,
        file,
      ),
    );
  };

  const indexFolder = () =>
    act("Folder indexed.", async () => {
      if (!selectedCollection) return;
      await api(`/knowledge/collections/${selectedCollection}/index-folder`, {
        method: "POST",
        body: { folder },
      });
      setFolder("");
    });

  const deleteDocument = (doc: DocumentRow) =>
    act(`Document deleted (${doc.filename}).`, async () => {
      await api(`/knowledge/documents/${doc.id}`, { method: "DELETE" });
      if (selectedDocument === doc.id) setSelectedDocument(null);
    });

  const deleteCollection = (col: CollectionRow) =>
    act(`Collection deleted (${col.name}).`, async () => {
      await api(`/knowledge/collections/${col.id}`, { method: "DELETE" });
      if (selectedCollection === col.id) {
        setSelectedCollection(null);
        setSelectedDocument(null);
      }
    });

  const runSearch = () =>
    act("Search complete.", async () => {
      const params = new URLSearchParams({ q: query });
      if (selectedCollection)
        params.set("collection_id", selectedCollection);
      const found = await api<SearchResult>(
        `/knowledge/search?${params.toString()}`,
      );
      setSearchResult(found.data);
    });

  const collectionRows: CollectionRow[] = Array.isArray(collections.data)
    ? collections.data
    : [];
  const documentRows: DocumentRow[] = Array.isArray(documents.data)
    ? documents.data
    : [];
  const statusData = status.data;

  return (
    <div className="view">
      <PageHeader
        title="Personal Knowledge"
        subtitle="Your documents, extracted for real and indexed into memory (P-09) — every answer traceable to its source."
      />
      {notice && <p className="notice">{notice}</p>}
      {actionError && <p className="error-text">{actionError}</p>}

      <Panel title="Library status" meta={statusData?.api_version}>
        {status.loading && <LoadingState />}
        {status.error && <ErrorState error={status.error} />}
        {statusData && (
          <>
            <p>
              {statusData.counts.collections} collections ·{" "}
              {statusData.counts.documents} documents ·{" "}
              {statusData.counts.indexed_chunks} of{" "}
              {statusData.counts.chunks} chunks indexed in P-09
            </p>
            <DataTable
              columns={[
                { key: "format", label: "Format" },
                { key: "state", label: "Support" },
              ]}
              rows={Object.entries(statusData.formats).map(
                ([format, state]) => ({
                  format,
                  state: <StatusBadge value={state} />,
                }),
              )}
              emptyTitle="No formats"
              emptyDetail="Format support could not be probed."
            />
            <p className="muted">
              Embedder: {statusData.embedder}. {statusData.embedder_caveat}
            </p>
            <ul className="muted">
              {statusData.not_implemented.map((item) => (
                <li key={item}>Not implemented: {item}</li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <Panel title="Collections">
        <div className="form-row">
          <input
            aria-label="New collection name"
            placeholder="New collection name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <input
            aria-label="New collection description"
            placeholder="Description"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
          <button disabled={busy || !newName.trim()} onClick={createCollection}>
            Create collection
          </button>
        </div>
        <DataTable
          columns={[
            { key: "name", label: "Name" },
            { key: "slug", label: "Project ref" },
            { key: "documents", label: "Documents", numeric: true },
            { key: "actions", label: "" },
          ]}
          rows={collectionRows.map((col) => ({
            name: col.name,
            slug: col.slug,
            documents: col.document_count ?? 0,
            actions: (
              <>
                <button
                  disabled={busy}
                  onClick={() => {
                    setSelectedCollection(col.id);
                    setSelectedDocument(null);
                  }}
                >
                  Open
                </button>{" "}
                <button disabled={busy} onClick={() => deleteCollection(col)}>
                  Delete
                </button>
              </>
            ),
          }))}
          emptyTitle="No collections yet"
          emptyDetail="Create a collection to start building your library."
        />
      </Panel>

      {selectedCollection && (
        <Panel title="Documents">
          <div className="form-row">
            <input
              ref={fileRef}
              type="file"
              aria-label="Upload a document"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadFile(file);
                e.target.value = "";
              }}
            />
            <input
              aria-label="Folder under the import directory"
              placeholder="Folder under knowledge-import/"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
            />
            <button disabled={busy || !folder.trim()} onClick={indexFolder}>
              Index folder
            </button>
          </div>
          {documents.loading && <LoadingState />}
          {documents.error && <ErrorState error={documents.error} />}
          <DataTable
            columns={[
              { key: "filename", label: "File" },
              { key: "format", label: "Format" },
              { key: "status", label: "Status" },
              { key: "chunks", label: "Chunks indexed", numeric: true },
              { key: "created", label: "Added" },
              { key: "actions", label: "" },
            ]}
            rows={documentRows.map((doc) => ({
              filename: doc.filename,
              format: doc.format,
              status: <StatusBadge value={doc.status} />,
              chunks: `${doc.indexed_chunk_count}/${doc.chunk_count}`,
              created: formatDateTime(doc.created_at),
              actions: (
                <>
                  <button
                    disabled={busy}
                    onClick={() => setSelectedDocument(doc.id)}
                  >
                    Inspect
                  </button>{" "}
                  <button disabled={busy} onClick={() => deleteDocument(doc)}>
                    Delete
                  </button>
                </>
              ),
            }))}
            emptyTitle="No documents in this collection"
            emptyDetail="Upload a file or index a folder from the import directory."
          />
        </Panel>
      )}

      <Panel title="Search your documents">
        <div className="form-row">
          <input
            aria-label="Search query"
            placeholder="Ask your documents…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button disabled={busy || !query.trim()} onClick={runSearch}>
            Search
          </button>
        </div>
        {searchResult && (
          <>
            <p className="muted">
              {searchResult.count} cited results · {searchResult.method}
            </p>
            {searchResult.results.map((hit) => (
              <article key={hit.memory_id} className="search-hit">
                <p>{hit.excerpt}</p>
                <p className="muted">
                  {hit.citations.map((cite, i) => (
                    <span key={i}>
                      {cite.filename} · {cite.locator}
                      {i < hit.citations.length - 1 ? "; " : ""}
                    </span>
                  ))}
                </p>
              </article>
            ))}
            {searchResult.count === 0 && (
              <EmptyState
                title="No cited results"
                detail="Nothing in the library clears the reliability bar for that query — absence is reported, never filled by invention."
              />
            )}
          </>
        )}
      </Panel>

      {selectedDocument && (
        <Panel title="Document detail">
          {detail.loading && <LoadingState />}
          {detail.error && <ErrorState error={detail.error} />}
          {detail.data && (
            <>
              <p>
                <strong>{detail.data.filename}</strong> ·{" "}
                <StatusBadge value={detail.data.status} /> · extractor:{" "}
                {detail.data.extractor_name ?? "none"} · SHA-256{" "}
                {detail.data.sha256.slice(0, 12)}…
              </p>
              {detail.data.error_detail && (
                <p className="muted">{detail.data.error_detail}</p>
              )}
              <p className="muted">
                Keyphrases ({detail.data.intelligence.keyphrase_method}):{" "}
                {detail.data.intelligence.keyphrases
                  .map((k) => `${k.phrase} (${k.count})`)
                  .join(", ") || "none"}
              </p>
              <p className="muted">
                {detail.data.intelligence.excerpt.label}
              </p>
              <blockquote>
                {detail.data.intelligence.excerpt.sentences.join(" ")}
              </blockquote>
              <DataTable
                columns={[
                  { key: "index", label: "#", numeric: true },
                  { key: "locator", label: "Locator" },
                  { key: "index_status", label: "Index" },
                  { key: "text", label: "Text" },
                ]}
                rows={detail.data.chunks.map((chunk) => ({
                  index: chunk.chunk_index,
                  locator: chunk.locator,
                  index_status: <StatusBadge value={chunk.index_status} />,
                  text: chunk.text ?? "(not persisted — see index status)",
                }))}
                emptyTitle="No chunks"
                emptyDetail="This document produced no chunks."
              />
            </>
          )}
        </Panel>
      )}
    </div>
  );
}
