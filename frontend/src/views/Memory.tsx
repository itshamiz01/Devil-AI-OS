import React, { useState } from "react";
import {
  ConfirmationDialog,
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { ApiError, api } from "../lib/api";
import { formatBps, formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";

interface MemoryStatus {
  engine: string;
  total_memories: number;
  by_layer: Record<string, number>;
  learning_records: number;
  vector_store: { store: string; status: string; indexed: number; embedder: string; note: string };
  authority_boundary: string;
  llm_dependency: string;
}

interface MemoryRecordRow {
  id: string;
  layer: string;
  category: string;
  title: string;
  content: string;
  status: string;
  truth_class: string;
  confidence: string;
  confidence_bps: number;
  source_type: string;
  source_ref: string;
  business_id: string | null;
  created_at: string;
}

interface LearningRow {
  id: string;
  subject?: string;
  status?: string;
  confidence?: string;
  observation_count?: number;
  expected_outcome?: string;
  actual_outcome?: string;
  [key: string]: unknown;
}

const LAYERS = ["", "working", "episodic", "semantic", "procedural"];

/**
 * §14 Memory & Learning Center. Memory is data, never authority
 * (Article 0): owner controls here call P-09's governed endpoints, and
 * nothing in this view can turn a memory into an instruction.
 */
export function MemoryView(): React.ReactElement {
  const status = useApi<MemoryStatus>("/memory/status", 30000);
  const [layer, setLayer] = useState("");
  const records = useApi<MemoryRecordRow[]>(
    `/memory?limit=100${layer ? `&layer=${layer}` : ""}`,
    30000,
  );
  const learning = useApi<LearningRow[]>("/memory/learning?limit=50");
  const contradictions = useApi<Record<string, unknown>[]>("/memory/contradictions/list?limit=50");
  const [selected, setSelected] = useState<MemoryRecordRow | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<MemoryRecordRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const act = async (fn: () => Promise<unknown>, okMessage: string) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      setNotice(okMessage);
      records.reload();
      status.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="view">
      <PageHeader
        title="Memory & Learning"
        subtitle="What AUTONOMUS knows, how it learned it, and what is still unverified"
        actions={<FreshnessBar updatedAt={status.updatedAt} />}
      />
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {status.data ? (
        <Panel title="Memory overview" meta={status.data.engine}>
          <dl className="stat-row num">
            <div><dt>Total records</dt><dd>{status.data.total_memories}</dd></div>
            {Object.entries(status.data.by_layer).map(([l, c]) => (
              <div key={l}><dt>{l}</dt><dd>{c}</dd></div>
            ))}
            <div><dt>Learning records</dt><dd>{status.data.learning_records}</dd></div>
            <div>
              <dt>Vector store</dt>
              <dd>
                {status.data.vector_store.store} · {status.data.vector_store.indexed} indexed
              </dd>
            </div>
          </dl>
          <p className="muted">{status.data.vector_store.note}</p>
          <p className="muted">{status.data.authority_boundary}</p>
          <p className="muted">{status.data.llm_dependency}</p>
        </Panel>
      ) : null}

      <div className="filter-bar" role="group" aria-label="Memory layer filter">
        {LAYERS.map((l) => (
          <button
            key={l || "all"}
            type="button"
            className={`chip ${layer === l ? "chip-active" : ""}`}
            onClick={() => setLayer(l)}
          >
            {l === "" ? "all layers" : l}
          </button>
        ))}
      </div>

      {records.loading && !records.data ? <LoadingState label="Loading memory records…" /> : null}
      {records.error ? <ErrorState error={records.error} onRetry={records.reload} /> : null}
      {records.data && records.data.length === 0 ? (
        <EmptyState
          title="No memory records"
          detail="The memory engine holds no records in this scope yet. Records are created by ingestion, agent work and owner input — never fabricated for display."
        />
      ) : null}
      <ul className="plain-list">
        {(records.data ?? []).map((r) => (
          <li key={r.id} className="plain-item">
            <StatusBadge value={r.status} />
            <div className="plain-body">
              <button type="button" className="link-button" onClick={() => setSelected(r)}>
                <strong>{r.title}</strong>
              </button>
              <p className="muted">
                {r.layer} · {r.category} · truth: {r.truth_class} · confidence{" "}
                {formatBps(r.confidence_bps)} ({r.confidence}) · source {r.source_type}
                {r.business_id ? ` · business ${r.business_id}` : ""} ·{" "}
                {formatDateTime(r.created_at)}
              </p>
              {selected?.id === r.id ? (
                <div className="record-detail">
                  <p>{r.content}</p>
                  <p className="muted mono">id {r.id} · source ref {r.source_ref || "—"}</p>
                  <span className="card-actions">
                    <button
                      type="button"
                      className="btn btn-small"
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () => api(`/memory/${r.id}/verify`, { method: "POST", body: { evidence_refs: [] } }),
                          "Backend response received for verification request — see the record status after reload.",
                        )
                      }
                    >
                      Request verification
                    </button>
                    <button
                      type="button"
                      className="btn btn-small"
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () =>
                            api(`/memory/${r.id}`, {
                              method: "PATCH",
                              body: { status: "ARCHIVED", reason: "archived from Command Center" },
                            }),
                          "Record archived (backend confirmed).",
                        )
                      }
                    >
                      Archive
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      disabled={busy}
                      onClick={() => setConfirmDelete(r)}
                    >
                      Request deletion
                    </button>
                  </span>
                  <p className="muted">
                    Corrections preserve history: P-09 versions every change and never
                    silently rewrites a record. Deletion completes only after the search
                    index is verified clean (P-09 receipt).
                  </p>
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      <div className="two-col">
        <Panel title="Learning records" meta="confidence is mechanical (P-09 §11.4)">
          {learning.data && learning.data.length === 0 ? (
            <p className="muted">
              No learning records yet. A lesson needs at least 3 observations plus owner
              review to become VERIFIED — nothing here is “learned” from a single anecdote.
            </p>
          ) : null}
          <ul className="plain-list">
            {(learning.data ?? []).slice(0, 15).map((l) => (
              <li key={l.id} className="plain-item">
                <StatusBadge value={String(l.status ?? "unknown")} />
                <div className="plain-body">
                  <strong>{String(l.subject ?? l.id)}</strong>
                  <p className="muted">
                    observations: {String(l.observation_count ?? "—")} · confidence{" "}
                    {String(l.confidence ?? "—")}
                  </p>
                  {l.expected_outcome ? <p className="muted">expected: {String(l.expected_outcome)}</p> : null}
                  {l.actual_outcome ? <p className="muted">actual: {String(l.actual_outcome)}</p> : null}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Contradictions" meta="both records preserved (P-09)">
          {contradictions.data && contradictions.data.length === 0 ? (
            <p className="muted">No contradictions recorded. When records conflict, both are preserved and the verified newer one is prioritised — never silently merged.</p>
          ) : null}
          <ul className="plain-list">
            {(contradictions.data ?? []).slice(0, 15).map((c, i) => (
              <li key={i} className="plain-item">
                <div className="plain-body">
                  <span className="mono">{String(c["id"] ?? `contradiction-${i}`)}</span>
                  <p className="muted">{String(c["detail"] ?? c["status"] ?? "")}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <ConfirmationDialog
        open={confirmDelete !== null}
        title="Request deletion of this memory record?"
        body={
          <p>
            Deletion goes through P-09's governed endpoint and completes only after the
            vector index is verified clean; the receipt state — not this dialog — is the
            proof. Record: <strong>{confirmDelete?.title}</strong>
          </p>
        }
        confirmLabel="Request deletion"
        danger
        busy={busy}
        onConfirm={() => {
          const target = confirmDelete;
          setConfirmDelete(null);
          if (target) {
            void act(
              () => api(`/memory/${target.id}`, { method: "DELETE" }),
              "Deletion request completed by the backend (index sync verified by P-09).",
            );
          }
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
