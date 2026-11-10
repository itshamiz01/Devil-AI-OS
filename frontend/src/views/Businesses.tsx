import React, { useState } from "react";
import { BusinessCard, type BusinessRow } from "../components/cards";
import {
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { ApiError, api } from "../lib/api";
import { formatDateTime, formatMoney } from "../lib/format";
import { useApi } from "../lib/hooks";
import { navigate } from "../lib/router";

interface BusinessesSummary {
  total: number;
  by_status: Record<string, number>;
  businesses: BusinessRow[];
  source: string;
  note: string;
}

export function BusinessesView(): React.ReactElement {
  const summary = useApi<BusinessesSummary>("/dashboard/businesses/summary", 30000);
  return (
    <div className="view">
      <PageHeader
        title="Business Portfolio"
        subtitle="Every business AUTONOMUS operates — lifecycle from P-06, money only from P-07"
        actions={<FreshnessBar updatedAt={summary.updatedAt} />}
      />
      {summary.loading && !summary.data ? <LoadingState label="Loading businesses…" /> : null}
      {summary.error ? <ErrorState error={summary.error} onRetry={summary.reload} /> : null}
      {summary.data ? (
        <>
          <Panel title="Portfolio overview" meta={summary.data.source}>
            <dl className="stat-row num">
              <div><dt>Total</dt><dd>{summary.data.total}</dd></div>
              {Object.entries(summary.data.by_status).map(([s, c]) => (
                <div key={s}><dt>{s}</dt><dd>{c}</dd></div>
              ))}
            </dl>
            <p className="muted">{summary.data.note}</p>
          </Panel>
          {summary.data.businesses.length === 0 ? (
            <EmptyState
              title="No businesses exist yet"
              detail="Business creation follows P-06 eligibility: a validated opportunity at Level 3 or above, a pre-declared experiment, and owner approval. With no qualifying opportunity, the honest portfolio is empty."
            />
          ) : (
            <div className="card-grid">
              {summary.data.businesses.map((b) => (
                <BusinessCard key={b.id} business={b} />
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------- Business detail
interface BusinessDetail extends BusinessRow {
  opportunity_id: string;
  eligibility_decision: string;
  validation_level_at_creation: number;
  score_at_creation: number | null;
  launched_at: string | null;
  website_states: Record<string, unknown>;
  created_by: string;
  public_availability: boolean;
}

interface BizFinanceSummary {
  currency?: string;
  [key: string]: unknown;
}

interface LifecycleEvent {
  id: string;
  from_status?: string | null;
  to_status?: string | null;
  reason?: string;
  actor?: string;
  created_at?: string;
}

const TRANSITION_TARGETS = ["PAUSED", "OPERATIONAL", "BLOCKED", "ARCHIVED"];

export function BusinessDetailView({ businessId }: { businessId: string }): React.ReactElement {
  const detail = useApi<BusinessDetail>(`/business/businesses/${businessId}`);
  const lifecycle = useApi<LifecycleEvent[]>(`/business/businesses/${businessId}/lifecycle?limit=50`);
  const finance = useApi<BizFinanceSummary>(`/financial/businesses/${businessId}/summary`);
  const cash = useApi<{ available_cash_minor?: number; currency?: string }>(
    `/financial/businesses/${businessId}/available-cash`,
  );
  const [target, setTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const transition = async (to: string) => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await api<BusinessDetail>(`/business/businesses/${businessId}/transition`, {
        method: "POST",
        body: { target: to, reason: "Command Center owner action" },
      });
      setNotice(`Backend confirmed lifecycle status: ${result.data.status}`);
      setTarget(null);
      detail.reload();
      lifecycle.reload();
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden) setForbidden(true);
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      setTarget(null);
    } finally {
      setBusy(false);
    }
  };

  if (detail.loading && !detail.data) return <LoadingState label="Loading business…" />;
  if (detail.error) {
    return (
      <div className="view">
        <PageHeader title="Business" subtitle={businessId} />
        <ErrorState error={detail.error} onRetry={detail.reload} />
        {detail.error.isForbidden ? (
          <p className="muted">
            The backend denied access to this business for your principal (cross-business
            restriction, §13 Scenario 13). The denial comes from the backend — this page
            cannot override it.
          </p>
        ) : null}
      </div>
    );
  }
  const b = detail.data;
  if (!b) return <LoadingState />;

  return (
    <div className="view">
      <PageHeader
        title={b.name}
        subtitle={`Business ${b.id} · ${b.category}`}
        actions={
          <button type="button" className="btn" onClick={() => navigate("businesses")}>
            Back to portfolio
          </button>
        }
      />
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {forbidden ? (
        <p className="warn-text">A lifecycle action was denied by the backend for this business scope.</p>
      ) : null}

      <Panel title="Overview">
        <dl className="entity-fields wide">
          <div><dt>Lifecycle status</dt><dd><StatusBadge value={b.status} /></dd></div>
          <div><dt>Risk classification</dt><dd>{b.risk_classification ?? "—"}</dd></div>
          <div><dt>Eligibility decision</dt><dd>{b.eligibility_decision}</dd></div>
          <div><dt>Validation level at creation</dt><dd>Level {b.validation_level_at_creation}</dd></div>
          <div><dt>Score at creation</dt><dd>{b.score_at_creation ?? "—"}</dd></div>
          <div><dt>Deployment</dt><dd>{b.deployment_state} · public: {b.public_availability ? "yes" : "no"}</dd></div>
          <div><dt>Launched</dt><dd>{b.launched_at ?? "not launched"}</dd></div>
          <div><dt>Created by</dt><dd>{b.created_by}</dd></div>
          {b.is_fixture ? (
            <div><dt>Data kind</dt><dd><span className="fixture-tag">FIXTURE — labelled test data</span></dd></div>
          ) : null}
        </dl>
        <div className="card-actions">
          {TRANSITION_TARGETS.filter((t) => t !== b.status).map((t) => (
            <button key={t} type="button" className="btn" disabled={busy} onClick={() => setTarget(t)}>
              Transition to {t}
            </button>
          ))}
        </div>
        <p className="muted">
          Transitions execute on P-06's state machine (the only lifecycle authority, with
          P-08 overlays). Illegal transitions are refused by the backend; controlled
          shutdown is a P-08 governed decision, not a one-click action here.
        </p>
      </Panel>

      <div className="two-col">
        <Panel title="Finance (P-07)" meta="authoritative records only">
          {finance.error ? (
            <p className="muted">
              No P-07 financial summary is available for this business
              {finance.error.isForbidden ? " (access denied by the backend)" : ""}. Financial
              values are never estimated in this console.
            </p>
          ) : finance.data ? (
            <>
              <pre className="params-json">{JSON.stringify(finance.data, null, 2)}</pre>
              {cash.data && typeof cash.data.available_cash_minor === "number" ? (
                <p>
                  Available cash:{" "}
                  <strong className="num">
                    {formatMoney(cash.data.available_cash_minor, cash.data.currency ?? "INR")}
                  </strong>{" "}
                  (P-07 available-cash endpoint)
                </p>
              ) : null}
            </>
          ) : (
            <LoadingState />
          )}
        </Panel>

        <Panel title="Lifecycle history" meta="P-06 state machine events">
          {lifecycle.data && lifecycle.data.length === 0 ? (
            <p className="muted">No lifecycle events recorded.</p>
          ) : null}
          <DataTable
            columns={[
              { key: "at", label: "When" },
              { key: "change", label: "Change" },
              { key: "actor", label: "Actor" },
              { key: "reason", label: "Reason" },
            ]}
            rows={(lifecycle.data ?? []).map((e) => ({
              at: formatDateTime(e.created_at),
              change: `${e.from_status ?? "—"} → ${e.to_status ?? "—"}`,
              actor: e.actor ?? "—",
              reason: e.reason ?? "—",
            }))}
            emptyTitle="No history"
            emptyDetail="No lifecycle events for this business."
          />
        </Panel>
      </div>

      <ConfirmationDialog
        open={target !== null}
        title={`Transition business to ${target}?`}
        body={
          <p>
            This calls P-06's lifecycle transition for <strong>{b.name}</strong> (current
            status {b.status}). The backend validates the transition against the state
            machine; the new status shown afterwards comes from its response.
          </p>
        }
        confirmLabel={`Transition to ${target}`}
        busy={busy}
        danger={target === "ARCHIVED"}
        onConfirm={() => target && void transition(target)}
        onCancel={() => setTarget(null)}
      />
    </div>
  );
}
