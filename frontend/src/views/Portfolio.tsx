import React, { useState } from "react";
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
import { ApiError, api } from "../lib/api";
import { formatMoney } from "../lib/format";
import { useApi } from "../lib/hooks";

// ------------------------------------------------------------------ types
// Shapes mirror the P-13 API exactly (app/api/routes/portfolio.py).
// The UI formats values; it never recomputes a total the API did
// not provide, and cash is shown per business — never combined.

interface PortfolioRow {
  id: string;
  name: string;
  mission: string;
  status: string;
  survival_mode: boolean;
}

interface MemberBusiness {
  business_id: string;
  name: string;
  category: string;
  portfolio_stage: string;
  p06_state: string;
  p08_overlay_state: string | null;
  is_fixture: boolean;
}

interface MemberRow {
  business_id: string;
  status: string;
  strategic_priority: number;
  group_labels: string[];
  business: MemberBusiness;
}

interface OverviewData {
  portfolio: PortfolioRow;
  total_businesses: number;
  active_businesses: number;
  businesses_at_risk: number;
  stage_counts: Record<string, number>;
  members: MemberRow[];
  survival_mode: boolean;
}

interface CompareRow {
  business_id: string;
  name: string;
  portfolio_stage: string;
  net_collected_minor?: number | null;
  projected_minor?: number | null;
}

interface RelationshipRow {
  id: string;
  source_business_id: string;
  target_business_id: string;
  relationship_type: string;
  status: string;
  sharing_policy: string;
}

interface FinanceRow {
  business_id: string;
  name: string;
  net_collected_minor?: number | null;
  collected_minor?: number;
  projected_minor?: number;
  available_cash?: unknown;
  financial_profile?: null;
  note?: string;
}

interface FinanceData {
  businesses: FinanceRow[];
  totals: {
    net_collected_minor: number;
    collected_minor: number;
    projected_minor: number;
    basis: string;
  };
  combined_available_cash: null;
  combined_cash_note: string;
  internal_allocations: AllocationRow[];
}

interface AllocationRow {
  id: string;
  business_id: string;
  amount_minor: number;
  kind: string;
  is_external_payment: boolean;
  presentation: string;
  method: string | null;
  status: string;
}

interface OpportunityRow {
  id: string;
  category: string;
  title: string;
  evidence_status: string;
  confidence: string;
  status: string;
  involved_business_ids: string[];
}

interface RecommendationRow {
  id: string;
  kind: string;
  title: string;
  rationale: string;
  evidence_status: string;
  status: string;
}

interface ResourceKind {
  capacity_units: number;
  allocated_units: number;
  available_units: number;
  per_business: Record<string, number>;
}

interface ServiceRow {
  id: string;
  name: string;
  kind: string;
  status: string;
  capacity_units: number;
}

interface RiskData {
  risk_level: string | null;
  per_business?: {
    business_id: string;
    name: string;
    risk_level: string;
    signals: string[];
  }[];
  findings?: { kind: string; detail?: string }[];
  note?: string;
}

interface ReportRow {
  id: string;
  report_type: string;
  title: string;
  generated_by: string;
  created_at: string | null;
}

const TABS = [
  "Overview",
  "Map",
  "Comparison",
  "Intelligence",
  "Resources",
  "Finance",
  "Services",
  "Risk",
  "Strategy",
  "Reports",
] as const;

type Tab = (typeof TABS)[number];

function nameOf(members: MemberRow[], businessId: string): string {
  const found = members.find((m) => m.business_id === businessId);
  return found ? found.business.name : businessId;
}

// ------------------------------------------------------------------- tabs

function OverviewTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const state = useApi<OverviewData>(`/portfolio/portfolios/${portfolioId}/overview`);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  if (state.loading) return <LoadingState label="Loading portfolio overview…" />;
  if (state.error || !state.data)
    return <ErrorState error={state.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={state.reload} />;
  const data = state.data;

  async function toggleSurvival(): Promise<void> {
    setBusy(true);
    setActionError(null);
    try {
      await api(`/portfolio/portfolios/${portfolioId}/survival-mode`, {
        method: "POST",
        body: { enabled: !data.survival_mode },
      });
      state.reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <FreshnessBar updatedAt={state.updatedAt} />
      <div className="metric-grid">
        <Panel title="Businesses">
          <p className="metric-value">{data.total_businesses}</p>
          <p className="metric-note">{data.active_businesses} active memberships</p>
        </Panel>
        <Panel title="At risk">
          <p className="metric-value">{data.businesses_at_risk}</p>
          <p className="metric-note">P-08 overlay reads AT_RISK</p>
        </Panel>
        <Panel title="Survival mode">
          <p className="metric-value">{data.survival_mode ? "ON" : "OFF"}</p>
          <p className="metric-note">
            Advisory only — pauses nothing and moves no money (§12).
          </p>
          <button type="button" disabled={busy} onClick={toggleSurvival}>
            {data.survival_mode ? "Clear survival mode" : "Activate survival mode"}
          </button>
          {actionError ? <p className="form-error">{actionError}</p> : null}
        </Panel>
      </div>
      <Panel title="Lifecycle stages (derived from P-06 + P-08)">
        <DataTable
          columns={[
            { key: "stage", label: "Portfolio stage" },
            { key: "count", label: "Businesses", numeric: true },
          ]}
          rows={Object.entries(data.stage_counts).map(([stage, count]) => ({
            stage,
            count: String(count),
          }))}
          emptyTitle="No businesses yet"
          emptyDetail="Register businesses in this portfolio to see their stages."
        />
      </Panel>
      <Panel title="Businesses">
        <DataTable
          columns={[
            { key: "name", label: "Business" },
            { key: "category", label: "Category" },
            { key: "stage", label: "Stage" },
            { key: "p06", label: "P-06 state" },
            { key: "membership", label: "Membership" },
          ]}
          rows={data.members.map((m) => ({
            name: m.business.name,
            category: m.business.category,
            stage: <StatusBadge value={m.business.portfolio_stage} />,
            p06: m.business.p06_state,
            membership: <StatusBadge value={m.status} />,
          }))}
          emptyTitle="No member businesses"
          emptyDetail="This portfolio has no registered businesses."
        />
      </Panel>
    </div>
  );
}

function MapTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const overview = useApi<OverviewData>(`/portfolio/portfolios/${portfolioId}/overview`);
  const rels = useApi<{ items: RelationshipRow[] }>(
    `/portfolio/relationships?portfolio_id=${portfolioId}`,
  );
  if (overview.loading || rels.loading) return <LoadingState label="Loading portfolio map…" />;
  if (overview.error || !overview.data)
    return <ErrorState error={overview.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={overview.reload} />;
  const members = overview.data.members;
  return (
    <div>
      <Panel title="Business relationships">
        <p className="metric-note">
          A relationship is a governed declaration — it grants no access by itself (§7).
        </p>
        <DataTable
          columns={[
            { key: "source", label: "From" },
            { key: "type", label: "Relationship" },
            { key: "target", label: "To" },
            { key: "policy", label: "Sharing policy" },
            { key: "status", label: "Status" },
          ]}
          rows={(rels.data?.items ?? []).map((r) => ({
            source: nameOf(members, r.source_business_id),
            type: r.relationship_type,
            target: nameOf(members, r.target_business_id),
            policy: r.sharing_policy,
            status: <StatusBadge value={r.status} />,
          }))}
          emptyTitle="No relationships recorded"
          emptyDetail="Relationships are created and approved by the owner."
        />
      </Panel>
      <Panel title="Groups">
        <DataTable
          columns={[
            { key: "name", label: "Business" },
            { key: "groups", label: "Group labels" },
            { key: "priority", label: "Strategic priority", numeric: true },
          ]}
          rows={members.map((m) => ({
            name: m.business.name,
            groups: m.group_labels.join(", ") || "—",
            priority: String(m.strategic_priority),
          }))}
          emptyTitle="No member businesses"
          emptyDetail="Grouping is analytical only — businesses are never duplicated."
        />
      </Panel>
    </div>
  );
}

function ComparisonTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const overview = useApi<OverviewData>(`/portfolio/portfolios/${portfolioId}/overview`);
  const ids = (overview.data?.members ?? [])
    .filter((m) => m.status !== "REMOVED")
    .map((m) => m.business_id)
    .slice(0, 6);
  const comparison = useApi<{ businesses: CompareRow[] }>(
    ids.length >= 2 ? `/portfolio/compare?ids=${ids.join(",")}` : null,
  );
  if (overview.loading) return <LoadingState label="Loading comparison…" />;
  if (ids.length < 2)
    return (
      <EmptyState
        title="Two businesses needed"
        detail="Comparison needs at least two member businesses."
      />
    );
  if (comparison.loading) return <LoadingState label="Loading comparison…" />;
  if (comparison.error || !comparison.data)
    return (
      <ErrorState
        error={comparison.error ?? new ApiError(0, { code: "no_data", message: "No data" })}
        onRetry={comparison.reload}
      />
    );
  return (
    <Panel title="Business comparison (each business's own P-07 figures)">
      <DataTable
        columns={[
          { key: "name", label: "Business" },
          { key: "stage", label: "Stage" },
          { key: "collected", label: "Collected (verified)", numeric: true },
          { key: "projected", label: "Projected (separate)", numeric: true },
        ]}
        rows={comparison.data.businesses.map((b) => ({
          name: b.name,
          stage: <StatusBadge value={b.portfolio_stage} />,
          collected:
            b.net_collected_minor === null || b.net_collected_minor === undefined
              ? "no P-07 profile"
              : formatMoney(b.net_collected_minor),
          projected:
            b.projected_minor === null || b.projected_minor === undefined
              ? "—"
              : formatMoney(b.projected_minor),
        }))}
        emptyTitle="Nothing to compare"
        emptyDetail="No comparison data returned."
      />
      <p className="metric-note">
        Collected and projected are never blended; cash balances are never combined (§11).
      </p>
    </Panel>
  );
}

function IntelligenceTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const opps = useApi<{ items: OpportunityRow[] }>(
    `/portfolio/portfolios/${portfolioId}/opportunities`,
  );
  const recs = useApi<{ items: RecommendationRow[] }>(
    `/portfolio/portfolios/${portfolioId}/recommendations`,
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      opps.reload();
      recs.reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (opps.loading || recs.loading) return <LoadingState label="Loading intelligence…" />;
  return (
    <div>
      <Panel title="Cross-business intelligence">
        <p className="metric-note">
          Deterministic detectors over system evidence only. Speculative items are labelled
          and cannot be accepted as verified (§6).
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(() => api(`/portfolio/portfolios/${portfolioId}/analyze`, { method: "POST" }))
          }
        >
          Run analysis
        </button>
        {actionError ? <p className="form-error">{actionError}</p> : null}
      </Panel>
      <Panel title="Opportunities">
        <DataTable
          columns={[
            { key: "title", label: "Opportunity" },
            { key: "category", label: "Category" },
            { key: "evidence", label: "Evidence" },
            { key: "status", label: "Status" },
            { key: "actions", label: "Decision" },
          ]}
          rows={(opps.data?.items ?? []).map((o) => ({
            title: o.title,
            category: o.category,
            evidence: <StatusBadge value={o.evidence_status} />,
            status: <StatusBadge value={o.status} />,
            actions:
              o.status === "PROPOSED" ? (
                <span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api(`/portfolio/opportunities/${o.id}/decision`, {
                          method: "POST",
                          body: { decision: "ACCEPTED", rationale: "owner via Command Center" },
                        }),
                      )
                    }
                  >
                    Accept
                  </button>{" "}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api(`/portfolio/opportunities/${o.id}/decision`, {
                          method: "POST",
                          body: { decision: "REJECTED", rationale: "owner via Command Center" },
                        }),
                      )
                    }
                  >
                    Reject
                  </button>
                </span>
              ) : (
                "—"
              ),
          }))}
          emptyTitle="No opportunities"
          emptyDetail="Run analysis to detect evidence-based opportunities."
        />
      </Panel>
      <Panel title="Recommendations">
        <DataTable
          columns={[
            { key: "title", label: "Recommendation" },
            { key: "kind", label: "Kind" },
            { key: "evidence", label: "Evidence" },
            { key: "status", label: "Status" },
          ]}
          rows={(recs.data?.items ?? []).map((r) => ({
            title: r.title,
            kind: r.kind,
            evidence: <StatusBadge value={r.evidence_status} />,
            status: <StatusBadge value={r.status} />,
          }))}
          emptyTitle="No recommendations"
          emptyDetail="Recommendations appear after analysis finds evidence."
        />
      </Panel>
    </div>
  );
}

function ResourcesTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const state = useApi<{ kinds: Record<string, ResourceKind> }>(
    `/portfolio/portfolios/${portfolioId}/resources`,
  );
  if (state.loading) return <LoadingState label="Loading resources…" />;
  if (state.error || !state.data)
    return <ErrorState error={state.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={state.reload} />;
  return (
    <Panel title="Shared resources (owner-configured capacities)">
      <DataTable
        columns={[
          { key: "kind", label: "Resource" },
          { key: "capacity", label: "Capacity", numeric: true },
          { key: "allocated", label: "Allocated", numeric: true },
          { key: "available", label: "Available", numeric: true },
        ]}
        rows={Object.entries(state.data.kinds).map(([kind, v]) => ({
          kind,
          capacity: String(v.capacity_units),
          allocated: String(v.allocated_units),
          available: String(v.available_units),
        }))}
        emptyTitle="No resource kinds configured"
        emptyDetail="Capacities are owner-configured in portfolio settings."
      />
      <p className="metric-note">
        One business may hold at most the configured share of any kind (anti-monopolization, §10).
      </p>
    </Panel>
  );
}

function FinanceTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const state = useApi<FinanceData>(`/portfolio/portfolios/${portfolioId}/finance`);
  if (state.loading) return <LoadingState label="Loading portfolio finance…" />;
  if (state.error || !state.data)
    return <ErrorState error={state.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={state.reload} />;
  const data = state.data;
  return (
    <div>
      <div className="metric-grid">
        <Panel title="Verified collected (flows)">
          <p className="metric-value">{formatMoney(data.totals.net_collected_minor)}</p>
          <p className="metric-note">{data.totals.basis}</p>
        </Panel>
        <Panel title="Projected (kept separate)">
          <p className="metric-value">{formatMoney(data.totals.projected_minor)}</p>
          <p className="metric-note">Projected is never blended into collected.</p>
        </Panel>
        <Panel title="Combined cash">
          <p className="metric-value">Not combined</p>
          <p className="metric-note">{data.combined_cash_note}</p>
        </Panel>
      </div>
      <Panel title="Per-business finance (from P-07)">
        <DataTable
          columns={[
            { key: "name", label: "Business" },
            { key: "collected", label: "Collected (verified)", numeric: true },
            { key: "projected", label: "Projected", numeric: true },
          ]}
          rows={data.businesses.map((b) => ({
            name: b.name,
            collected:
              b.financial_profile === null
                ? "no P-07 profile"
                : formatMoney(b.net_collected_minor),
            projected:
              b.financial_profile === null ? "—" : formatMoney(b.projected_minor),
          }))}
          emptyTitle="No member businesses"
          emptyDetail="Finance appears once businesses are registered."
        />
      </Panel>
      <Panel title="Internal cost allocations">
        <DataTable
          columns={[
            { key: "business", label: "Charged business" },
            { key: "amount", label: "Internal share", numeric: true },
            { key: "method", label: "Method" },
            { key: "kind", label: "Kind" },
          ]}
          rows={data.internal_allocations.map((a) => ({
            business: a.business_id,
            amount: formatMoney(a.amount_minor),
            method: a.method ?? "—",
            kind: a.kind,
          }))}
          emptyTitle="No internal allocations"
          emptyDetail="Internal allocations are management accounting — never external payments."
        />
      </Panel>
    </div>
  );
}

function ServicesTab(): React.ReactElement {
  const state = useApi<{ items: ServiceRow[] }>("/portfolio/services");
  if (state.loading) return <LoadingState label="Loading shared services…" />;
  if (state.error || !state.data)
    return <ErrorState error={state.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={state.reload} />;
  return (
    <Panel title="Shared services">
      <DataTable
        columns={[
          { key: "name", label: "Service" },
          { key: "kind", label: "Kind" },
          { key: "capacity", label: "Capacity units", numeric: true },
          { key: "status", label: "Status" },
        ]}
        rows={state.data.items.map((s) => ({
          name: s.name,
          kind: s.kind,
          capacity: String(s.capacity_units),
          status: <StatusBadge value={s.status} />,
        }))}
        emptyTitle="No shared services"
        emptyDetail="Shared services are registered by the owner; access is per business and revocable."
      />
    </Panel>
  );
}

function RiskTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const risk = useApi<RiskData>(`/portfolio/portfolios/${portfolioId}/risk`);
  const conc = useApi<{
    businesses: { business_id: string; name: string; share_bps: number }[];
    threshold_bps: number;
  }>(`/portfolio/portfolios/${portfolioId}/concentration`);
  const [busy, setBusy] = useState(false);
  if (risk.loading || conc.loading) return <LoadingState label="Loading risk…" />;
  if (risk.error || !risk.data)
    return <ErrorState error={risk.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={risk.reload} />;
  return (
    <div>
      <Panel title="Portfolio risk">
        <p className="metric-value">{risk.data.risk_level ?? "Not assessed"}</p>
        <p className="metric-note">
          {risk.data.note ?? "From P-08 lifecycle readings and P-07 concentration."}
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api(`/portfolio/portfolios/${portfolioId}/risk/assess`, {
                method: "POST",
              });
              risk.reload();
            } finally {
              setBusy(false);
            }
          }}
        >
          Run risk assessment
        </button>
        <DataTable
          columns={[
            { key: "name", label: "Business" },
            { key: "level", label: "Risk level" },
            { key: "signals", label: "Signals" },
          ]}
          rows={(risk.data.per_business ?? []).map((b) => ({
            name: b.name,
            level: <StatusBadge value={b.risk_level} />,
            signals: b.signals.join("; ") || "—",
          }))}
          emptyTitle="No assessment yet"
          emptyDetail="Run a risk assessment to compute per-business levels."
        />
      </Panel>
      <Panel title="Revenue concentration (verified collected)">
        <DataTable
          columns={[
            { key: "name", label: "Business" },
            { key: "share", label: "Share of collected", numeric: true },
          ]}
          rows={(conc.data?.businesses ?? []).map((b) => ({
            name: b.name,
            share: `${(b.share_bps / 100).toFixed(1)}%`,
          }))}
          emptyTitle="No collected revenue yet"
          emptyDetail="Concentration is computed from verified collected revenue only."
        />
        <p className="metric-note">
          Threshold: {conc.data ? `${(conc.data.threshold_bps / 100).toFixed(0)}%` : "—"} of
          verified collected revenue.
        </p>
      </Panel>
    </div>
  );
}

function StrategyTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const state = useApi<{
    areas: Record<string, { status: string; detail: string }>;
    objectives: { id: string; title: string; horizon: string }[];
  }>(`/portfolio/portfolios/${portfolioId}/strategy`);
  if (state.loading) return <LoadingState label="Loading strategy…" />;
  if (state.error || !state.data)
    return <ErrorState error={state.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={state.reload} />;
  return (
    <div>
      <Panel title="Strategic assessment areas">
        <DataTable
          columns={[
            { key: "area", label: "Area" },
            { key: "status", label: "Status" },
            { key: "detail", label: "Basis" },
          ]}
          rows={Object.entries(state.data.areas).map(([area, v]) => ({
            area: area.replaceAll("_", " "),
            status: <StatusBadge value={v.status} />,
            detail: v.detail,
          }))}
          emptyTitle="No strategy data"
          emptyDetail="Strategy is computed from live portfolio evidence."
        />
        <p className="metric-note">
          Areas without evidence are labelled INSUFFICIENT_DATA — never estimated (§16).
        </p>
      </Panel>
      <Panel title="Objectives">
        <DataTable
          columns={[
            { key: "title", label: "Objective" },
            { key: "horizon", label: "Horizon" },
          ]}
          rows={state.data.objectives.map((o) => ({
            title: o.title,
            horizon: o.horizon,
          }))}
          emptyTitle="No objectives set"
          emptyDetail="Portfolio objectives are set by the owner."
        />
      </Panel>
    </div>
  );
}

function ReportsTab({ portfolioId }: { portfolioId: string }): React.ReactElement {
  const state = useApi<{ items: ReportRow[] }>(
    `/portfolio/portfolios/${portfolioId}/reports`,
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  if (state.loading) return <LoadingState label="Loading reports…" />;
  if (state.error || !state.data)
    return <ErrorState error={state.error ?? new ApiError(0, { code: "no_data", message: "No data" })} onRetry={state.reload} />;
  return (
    <Panel title="Portfolio reports">
      <p className="metric-note">
        Reports snapshot live P-06/P-07/P-08/P-13 views with sources named. PDF export is not
        implemented.
      </p>
      {(["SNAPSHOT", "FINANCIAL", "RISK", "STRATEGIC"] as const).map((type) => (
        <button
          key={type}
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setActionError(null);
            try {
              await api(`/portfolio/portfolios/${portfolioId}/reports`, {
                method: "POST",
                body: { report_type: type },
              });
              state.reload();
            } catch (err) {
              setActionError(err instanceof Error ? err.message : "Action failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Generate {type.toLowerCase()}
        </button>
      ))}
      {actionError ? <p className="form-error">{actionError}</p> : null}
      <DataTable
        columns={[
          { key: "title", label: "Report" },
          { key: "type", label: "Type" },
          { key: "by", label: "Generated by" },
        ]}
        rows={state.data.items.map((r) => ({
          title: r.title,
          type: r.report_type,
          by: r.generated_by,
        }))}
        emptyTitle="No reports yet"
        emptyDetail="Generate a report to snapshot the current portfolio state."
      />
    </Panel>
  );
}

// -------------------------------------------------------------------- view

export function PortfolioView(): React.ReactElement {
  const portfolios = useApi<{ items: PortfolioRow[] }>("/portfolio/portfolios");
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const portfolioId =
    selected ?? portfolios.data?.items[0]?.id ?? null;

  return (
    <div>
      <PageHeader
        title="Business Portfolio"
        subtitle="Multi-business coordination (P-13) — isolation-first, evidence-based, P-07 remains the only financial authority."
      />
      {portfolios.loading ? (
        <LoadingState label="Loading portfolios…" />
      ) : portfolios.error ? (
        <ErrorState error={portfolios.error} onRetry={portfolios.reload} />
      ) : (portfolios.data?.items.length ?? 0) === 0 ? (
        <EmptyState
          title="No portfolios yet"
          detail="Create a portfolio through the API to coordinate multiple businesses."
        />
      ) : (
        <div>
          <div className="toolbar">
            <label>
              Portfolio{" "}
              <select
                value={portfolioId ?? ""}
                onChange={(e) => setSelected(e.target.value)}
              >
                {(portfolios.data?.items ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="toolbar" role="tablist" aria-label="Portfolio sections">
            {TABS.map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={tab === name}
                className={tab === name ? "tab active" : "tab"}
                onClick={() => setTab(name)}
              >
                {name}
              </button>
            ))}
          </div>
          {portfolioId ? (
            <div>
              {tab === "Overview" ? <OverviewTab portfolioId={portfolioId} /> : null}
              {tab === "Map" ? <MapTab portfolioId={portfolioId} /> : null}
              {tab === "Comparison" ? <ComparisonTab portfolioId={portfolioId} /> : null}
              {tab === "Intelligence" ? (
                <IntelligenceTab portfolioId={portfolioId} />
              ) : null}
              {tab === "Resources" ? <ResourcesTab portfolioId={portfolioId} /> : null}
              {tab === "Finance" ? <FinanceTab portfolioId={portfolioId} /> : null}
              {tab === "Services" ? <ServicesTab /> : null}
              {tab === "Risk" ? <RiskTab portfolioId={portfolioId} /> : null}
              {tab === "Strategy" ? <StrategyTab portfolioId={portfolioId} /> : null}
              {tab === "Reports" ? <ReportsTab portfolioId={portfolioId} /> : null}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
