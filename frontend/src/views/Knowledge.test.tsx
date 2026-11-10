import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { KnowledgeView } from "./Knowledge";

// Expansion Feature 6: the knowledge console renders the real
// endpoints and their honest states — probed format support
// (images metadata-only, OCR not implemented), the embedder
// caveat next to every search, citations on results, and the
// extractive-excerpt label that refuses to call verbatim
// sentences an AI summary.

const STATUS = {
  api_version: "1.4.0",
  counts: { collections: 1, documents: 1, chunks: 1, indexed_chunks: 1 },
  formats: {
    text: "supported",
    pdf: "supported",
    image: "metadata_only_ocr_not_implemented",
    ocr: "not_implemented",
  },
  embedder: "local-hash-v1",
  embedder_caveat:
    "retrieval runs over P-09's local-hash-v1 embedder: a lexical approximation (hashed token/trigram overlap), not a neural semantic model",
  retrieval_owner: "P-09",
  not_implemented: [
    "OCR — no OCR engine exists in this environment; images are metadata-only",
  ],
};

const COLLECTION = {
  id: "col-1",
  name: "Aurora Project",
  slug: "aurora-project",
  description: "the aurora files",
  excluded_patterns: [],
  document_count: 1,
  created_at: "2026-11-10T12:00:00Z",
};

const DOCUMENT = {
  id: "doc-1",
  collection_id: "col-1",
  filename: "report.pdf",
  source_kind: "upload",
  format: "pdf",
  size_bytes: 2048,
  sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  status: "indexed",
  extractor_name: "pypdf",
  extraction_detail: { pages: 2 },
  chunk_count: 1,
  indexed_chunk_count: 1,
  duplicate_of_id: null,
  error_detail: null,
  created_at: "2026-11-10T12:01:00Z",
};

const DETAIL = {
  ...DOCUMENT,
  chunks: [
    {
      id: "chunk-1",
      chunk_index: 0,
      locator: "page 1",
      text: "The budget review for Aurora happens every quarter.",
      memory_id: "mem-1",
      index_status: "stored",
    },
  ],
  intelligence: {
    keyphrases: [{ phrase: "budget review", count: 2 }],
    keyphrase_method: "token-frequency statistics (deterministic)",
    excerpt: {
      label:
        "deterministic extractive excerpt — verbatim sentences, not an AI summary",
      sentences: ["The budget review for Aurora happens every quarter."],
    },
  },
};

const SEARCH = {
  query: "budget review",
  count: 1,
  method: "P-09 hybrid retrieval with F06 citations",
  embedder: "local-hash-v1",
  embedder_caveat: STATUS.embedder_caveat,
  results: [
    {
      memory_id: "mem-1",
      score: 0.72,
      excerpt: "The budget review for Aurora happens every quarter.",
      citations: [
        {
          document_id: "doc-1",
          filename: "report.pdf",
          locator: "page 1",
          chunk_index: 0,
        },
      ],
    },
  ],
};

function stubKnowledge(
  extra: Record<string, (url: string, init: RequestInit) => unknown> = {},
) {
  return installFetchStub({
    "/knowledge/status": () => STATUS,
    "/knowledge/collections/col-1/documents": () => [DOCUMENT],
    "/knowledge/documents/doc-1": () => DETAIL,
    "/knowledge/search": () => SEARCH,
    ...extra,
    "/knowledge/collections": () => [COLLECTION],
  });
}

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("KnowledgeView (Expansion F-06)", () => {
  it("renders probed format states, the OCR limit and the embedder caveat", async () => {
    stubKnowledge();
    render(
      <AppProviders>
        <KnowledgeView />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getByText(/1 collections · 1 documents/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Metadata Only Ocr Not Implemented/)).toBeInTheDocument();
    expect(screen.getByText(/no OCR engine exists in this environment/)).toBeInTheDocument();
    expect(screen.getByText(/not a neural semantic model/)).toBeInTheDocument();
  });

  it("opens a collection and lists its documents with index counts", async () => {
    stubKnowledge();
    render(
      <AppProviders>
        <KnowledgeView />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getByText("Aurora Project")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() =>
      expect(screen.getByText("report.pdf")).toBeInTheDocument(),
    );
    expect(screen.getByText("1/1")).toBeInTheDocument();
  });

  it("search results carry their citations", async () => {
    stubKnowledge();
    render(
      <AppProviders>
        <KnowledgeView />
      </AppProviders>,
    );
    await userEvent.type(
      screen.getByLabelText("Search query"),
      "budget review",
    );
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(
        screen.getByText(/report\.pdf · page 1/),
      ).toBeInTheDocument(),
    );
  });

  it("document detail labels the excerpt as extractive, never a summary", async () => {
    stubKnowledge();
    render(
      <AppProviders>
        <KnowledgeView />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getByText("Aurora Project")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() =>
      expect(screen.getByText("report.pdf")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Inspect" }));
    await waitFor(() =>
      expect(screen.getByText(/not an AI summary/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/token-frequency statistics/)).toBeInTheDocument();
    expect(screen.getByText("page 1")).toBeInTheDocument();
  });
});
