import React from "react";
import { OpportunityCard, type OpportunityRow } from "../components/cards";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import { navigate } from "../lib/router";

interface OppSummary {
  total: number;
  by_status: Record<string, number>;
  source: string;
}

export function OpportunitiesView(): React.ReactElement {
  const summary = useApi<OppSummary>("/dashboard/opportunities/summary", 30000);
  const list = useApi<OpportunityRow[]>("/opportunities?limit=100", 30000);
  return (
    <div className="view">
      <PageHeader
        title="Opportunity Intelligence"
        subtitle="P-03 discovery — evidence levels are facts; scores never override hard rejection rules"
        actions={<FreshnessBar updatedAt={list.updatedAt} />}
      />
      {summary.data ? (
        <Panel title="Opportunity overview" meta={summary.data.source}>
          <dl className="stat-row num">
            <div><dt>Total discovered</dt><dd>{summary.data.total}</dd></div>
            {Object.entries(summary.data.by_status).map(([s, c]) => (
              <div key={s}><dt>{s}</dt><dd>{c}</dd></div>
            ))}
          </dl>
        </Panel>
      ) : null}
      {list.loading && !list.data ? <LoadingState label="Loading opportunities…" /> : null}
      {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : null}
      {list.data && list.data.length === 0 ? (
        <EmptyState
          title="No opportunities discovered yet"
          detail="P-03 has not recorded any opportunities. Discovery runs from registered public sources and owner briefs — this console does not invent market ideas."
        />
      ) : null}
      <div className="card-grid">
        {(list.data ?? []).map((o) => (
          <OpportunityCard key={o.id} opportunity={o} />
        ))}
      </div>
    </div>
  );
}

interface OppDetail extends OpportunityRow {
  description?: string;
  proposed_solution?: string;
  geography?: string;
  discovery_method?: string;
  compliance?: Record<string, unknown>;
}

interface EvidenceRow {
  id: string;
  source?: string;
  kind?: string;
  summary?: string;
  created_at?: string;
  [key: string]: unknown;
}

export function OpportunityDetailView({ opportunityId }: { opportunityId: string }): React.ReactElement {
  const detail = useApi<OppDetail>(`/opportunities/${opportunityId}`);
  const evidence = useApi<EvidenceRow[]>(`/opportunities/${opportunityId}/evidence?limit=50`);
  const validation = useApi<Record<string, unknown>>(`/opportunities/${opportunityId}/validation`);
  if (detail.loading && !detail.data) return <LoadingState label="Loading opportunity…" />;
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const o = detail.data;
  if (!o) return <LoadingState />;
  return (
    <div className="view">
      <PageHeader
        title={o.name}
        subtitle={`Opportunity ${o.id}`}
        actions={
          <button type="button" className="btn" onClick={() => navigate("opportunities")}>
            Back to opportunities
          </button>
        }
      />
      <Panel title="Overview">
        <dl className="entity-fields wide">
          <div><dt>Status</dt><dd><StatusBadge value={o.status} /></dd></div>
          <div><dt>Category</dt><dd>{o.category}</dd></div>
          <div><dt>Target customer</dt><dd>{o.target_customer ?? "—"}</dd></div>
          <div><dt>Problem</dt><dd>{o.problem_statement ?? "—"}</dd></div>
          <div><dt>Proposed solution</dt><dd>{o.proposed_solution ?? "—"}</dd></div>
          <div><dt>Business model</dt><dd>{o.revenue_model ?? "—"}</dd></div>
          <div><dt>Geography</dt><dd>{o.geography ?? "—"}</dd></div>
          <div>
            <dt>Validation level</dt>
            <dd>Level {o.validation_level ?? 0} of 5 (P-03 evidence ladder)</dd>
          </div>
          <div><dt>Discovery method</dt><dd>{o.discovery_method ?? "—"}</dd></div>
          <div><dt>Last researched</dt><dd>{formatDateTime(o.last_researched_at)}</dd></div>
        </dl>
        <p className="muted">
          Estimates vs facts: validation level and compliance screening are evidence
          records. Revenue potential and startup cost, where P-03 records them, are
          estimates inside the research record — progression to business creation still
          requires P-06 eligibility (Level ≥ 3 + declaration + owner approval).
        </p>
      </Panel>
      <div className="two-col">
        <Panel title="Evidence">
          {evidence.data && evidence.data.length === 0 ? (
            <p className="muted">No evidence records attached yet.</p>
          ) : null}
          <DataTable
            columns={[
              { key: "kind", label: "Kind" },
              { key: "source", label: "Source" },
              { key: "summary", label: "Summary" },
              { key: "at", label: "Recorded" },
            ]}
            rows={(evidence.data ?? []).map((e) => ({
              kind: String(e.kind ?? e["evidence_type"] ?? "—"),
              source: String(e.source ?? e["source_name"] ?? "—"),
              summary: String(e.summary ?? e["title"] ?? "—"),
              at: formatDateTime(typeof e.created_at === "string" ? e.created_at : null),
            }))}
            emptyTitle="No evidence"
            emptyDetail="No evidence records for this opportunity."
          />
        </Panel>
        <Panel title="Validation & compliance">
          {validation.data ? (
            <pre className="params-json">{JSON.stringify(validation.data, null, 2)}</pre>
          ) : (
            <p className="muted">No validation record yet.</p>
          )}
          {o.compliance ? (
            <>
              <h3 className="subhead">Compliance screening</h3>
              <pre className="params-json">{JSON.stringify(o.compliance, null, 2)}</pre>
            </>
          ) : null}
        </Panel>
      </div>
    </div>
  );
}
