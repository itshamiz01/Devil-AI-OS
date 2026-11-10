import React from "react";
import {
  BarChart,
  ChartPanel,
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { formatDateTime, formatMoney } from "../lib/format";
import { useApi } from "../lib/hooks";
import { usePrefs } from "../lib/store";

interface FinSummary {
  currency: string;
  businesses: {
    business_id: string;
    net_collected_minor: number;
    expenses_minor: number;
    net_profit_minor: number;
    is_fixture: boolean;
  }[];
  totals: { net_collected_minor: number; expenses_minor: number; net_profit_minor: number };
  internal_transfers_excluded: boolean;
  note: string;
  open_alerts: number;
  source: string;
}

interface FinDashboard {
  businesses: {
    business_id: string;
    currency: string;
    is_fixture: boolean;
    health: string;
    verified_net_collected_minor: number;
    projected_minor: number;
    available_cash_minor: number;
    protected_reserves_minor: number;
  }[];
  open_alerts: number;
  note: string;
}

interface Forecast {
  id: string;
  business_id: string;
  forecast_type: string;
  method: string;
  currency: string;
  status?: string;
  created_at?: string;
}

interface FinAlert {
  id: string;
  business_id: string | null;
  alert_type: string;
  severity: string;
  title: string;
  recommended_action: string;
  status: string;
  created_at: string;
}

/**
 * §11 Financial Command Center. P-07 is the only source. Forecast,
 * projected, collected and reserves are separate columns — never merged
 * into a single "earnings" figure (§11.2). This view executes nothing:
 * financial operations go through P-07 + P-10 controlled authorization.
 */
export function FinanceView(): React.ReactElement {
  const { prefs } = usePrefs();
  const summary = useApi<FinSummary>(`/dashboard/finance/summary?currency=${prefs.currency}`, 30000);
  const dashboard = useApi<FinDashboard>("/financial/dashboard", 30000);
  const forecasts = useApi<Forecast[]>("/financial/forecasts?limit=50");
  const alerts = useApi<FinAlert[]>("/financial/alerts?limit=50", 30000);
  const currency = summary.data?.currency ?? prefs.currency;

  return (
    <div className="view">
      <PageHeader
        title="Finance"
        subtitle="Financial truth from P-07 — actuals and forecasts are never mixed"
        actions={<FreshnessBar updatedAt={summary.updatedAt} />}
      />
      {summary.loading && !summary.data ? <LoadingState label="Loading financial position…" /> : null}
      {summary.error ? <ErrorState error={summary.error} onRetry={summary.reload} /> : null}

      {summary.data ? (
        <Panel title={`Verified actuals — consolidated (${currency})`} meta={summary.data.source}>
          <dl className="stat-row num">
            <div>
              <dt>Collected revenue (verified)</dt>
              <dd>{formatMoney(summary.data.totals.net_collected_minor, currency)}</dd>
            </div>
            <div>
              <dt>Actual expenses (paid)</dt>
              <dd>{formatMoney(summary.data.totals.expenses_minor, currency)}</dd>
            </div>
            <div>
              <dt>Net profit / loss (actual)</dt>
              <dd>{formatMoney(summary.data.totals.net_profit_minor, currency)}</dd>
            </div>
            <div>
              <dt>Open financial alerts</dt>
              <dd>{summary.data.open_alerts}</dd>
            </div>
          </dl>
          <p className="muted">
            {summary.data.note} Internal transfers excluded:{" "}
            {summary.data.internal_transfers_excluded ? "yes" : "no"}. Businesses in other
            currencies are consolidated separately by P-07 — never summed without a
            documented exchange rate.
          </p>
          {summary.data.businesses.length === 0 ? (
            <EmptyState
              title="No financial records yet"
              detail="No business has a P-07 financial profile with activity. Collected revenue is shown only when a verified payment record exists — a fresh system honestly shows no money."
            />
          ) : (
            <DataTable
              columns={[
                { key: "business", label: "Business" },
                { key: "collected", label: "Collected (verified)", numeric: true },
                { key: "expenses", label: "Expenses (paid)", numeric: true },
                { key: "profit", label: "Net profit (actual)", numeric: true },
                { key: "fixture", label: "Data kind" },
              ]}
              rows={summary.data.businesses.map((b) => ({
                business: <span className="mono">{b.business_id}</span>,
                collected: formatMoney(b.net_collected_minor, currency),
                expenses: formatMoney(b.expenses_minor, currency),
                profit: formatMoney(b.net_profit_minor, currency),
                fixture: b.is_fixture ? "FIXTURE" : "real",
              }))}
              emptyTitle="No businesses"
              emptyDetail="No per-business financial rows."
            />
          )}
        </Panel>
      ) : null}

      {dashboard.data ? (
        <ChartPanel
          title="Per-business position — projected vs collected kept separate"
          meta={`P-07 dashboard · ${dashboard.data.note}`}
        >
          {dashboard.data.businesses.length === 0 ? (
            <EmptyState
              title="No business financial profiles"
              detail="P-07 has no business profiles yet, so there is nothing to compare. Projected figures, when they exist, are estimates — collected figures are verified actuals."
            />
          ) : (
            <DataTable
              columns={[
                { key: "business", label: "Business" },
                { key: "health", label: "Health" },
                { key: "projected", label: "Projected (estimate)", numeric: true },
                { key: "collected", label: "Collected (verified)", numeric: true },
                { key: "cash", label: "Available cash", numeric: true },
                { key: "reserves", label: "Protected reserves", numeric: true },
              ]}
              rows={dashboard.data.businesses.map((b) => ({
                business: <span className="mono">{b.business_id}{b.is_fixture ? " (fixture)" : ""}</span>,
                health: <StatusBadge value={b.health} />,
                projected: formatMoney(b.projected_minor, b.currency),
                collected: formatMoney(b.verified_net_collected_minor, b.currency),
                cash: formatMoney(b.available_cash_minor, b.currency),
                reserves: formatMoney(b.protected_reserves_minor, b.currency),
              }))}
              emptyTitle="No rows"
              emptyDetail="No business rows."
            />
          )}
          {dashboard.data.businesses.length > 0 ? (
            <BarChart
              label="Verified collected revenue by business (actuals only)"
              bars={dashboard.data.businesses.map((b) => ({
                label: b.business_id.slice(0, 8),
                value: b.verified_net_collected_minor,
                tone: "ok" as const,
              }))}
              format={(v) => formatMoney(v, dashboard.data?.businesses[0]?.currency ?? currency)}
            />
          ) : null}
        </ChartPanel>
      ) : null}

      <div className="two-col">
        <Panel title="Forecasts" meta="FORECAST — not financial events (§11.7)">
          {forecasts.data && forecasts.data.length === 0 ? (
            <EmptyState title="No forecasts" detail="No forecasts have been generated in P-07. Forecasts are projections and are always labelled as such — never presented as collected money." />
          ) : null}
          <ul className="plain-list">
            {(forecasts.data ?? []).map((f) => (
              <li key={f.id} className="plain-item">
                <StatusBadge value="pending" />
                <div className="plain-body">
                  <strong>{f.forecast_type}</strong>
                  <p className="muted">
                    method: {f.method} · currency {f.currency} · business{" "}
                    <span className="mono">{f.business_id}</span> · {formatDateTime(f.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Financial warnings" meta="P-07 analytics alerts">
          {alerts.data && alerts.data.length === 0 ? (
            <EmptyState title="No financial alerts" detail="No budget overruns, unverified-payment warnings or duplicate-transaction alerts are open." />
          ) : null}
          <ul className="plain-list">
            {(alerts.data ?? []).map((a) => (
              <li key={a.id} className="plain-item">
                <StatusBadge value={a.severity} />
                <div className="plain-body">
                  <strong>{a.title}</strong>
                  <p className="muted">
                    {a.alert_type} · {a.status} · {a.recommended_action}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Transactions & approvals" meta="how money decisions work here">
        <p className="muted">
          The transaction ledger (journal entries, revenue and expense records) is browsable
          per business in Businesses → Finance, served by P-07's own endpoints. This console
          never executes transfers: spending requests are approved in the owning business
          view with a P-01 approval id, under P-07 budgets and P-10 authorization (§11.5).
        </p>
      </Panel>
    </div>
  );
}
