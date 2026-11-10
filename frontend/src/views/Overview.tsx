import React from "react";
import { ActivityFeed } from "../components/cards";
import {
  ErrorState,
  FreshnessBar,
  LoadingState,
  MetricCard,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { humanize } from "../lib/format";
import { useApi } from "../lib/hooks";
import { navigate } from "../lib/router";
import { usePrefs } from "../lib/store";
import type {
  ActivityItem,
  AttentionItem,
  OverviewData,
  SystemHealthData,
} from "../lib/types";

export function OverviewView(): React.ReactElement {
  const { prefs } = usePrefs();
  const overview = useApi<OverviewData>(`/dashboard/overview?currency=${prefs.currency}`, 20000);
  const health = useApi<SystemHealthData>("/dashboard/system-health", 30000);
  const activity = useApi<{ items: ActivityItem[]; total: number; note: string }>("/dashboard/activity?limit=25", 20000);
  const attention = useApi<{ items: AttentionItem[]; total: number }>("/dashboard/attention", 20000);

  if (overview.loading && !overview.data) return <LoadingState label="Loading system overview…" />;
  if (overview.error && !overview.data) {
    return (
      <>
        <PageHeader title="Overview" subtitle="What AUTONOMUS is doing right now" />
        <ErrorState error={overview.error} onRetry={overview.reload} />
      </>
    );
  }
  const data = overview.data;
  if (!data) return <LoadingState />;
  const today = new Date().toLocaleDateString("en-GB", {
    timeZone: prefs.timezone,
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="view">
      <PageHeader
        title="Overview"
        subtitle={`${today} · mode: ${data.mode} · security: ${data.security_mode}`}
        actions={<FreshnessBar updatedAt={overview.updatedAt} />}
      />

      <section className="operating-banner" aria-label="Operating state">
        <div>
          <span className="operating-label">Operating state</span>
          <span className="operating-value">
            <StatusBadge value={data.operating_state} />
          </span>
        </div>
        <dl className="operating-counts num">
          <div><dt>Businesses</dt><dd>{data.counts.businesses_total}</dd></div>
          <div><dt>Agents</dt><dd>{data.counts.agents_total}</dd></div>
          <div><dt>Queue depth</dt><dd>{data.queue.depth}</dd></div>
          <div><dt>Running</dt><dd>{data.queue.running}</dd></div>
          <div><dt>Pending approvals</dt><dd>{data.counts.pending_approvals}</dd></div>
          <div><dt>Critical alerts</dt><dd>{data.counts.critical_alerts}</dd></div>
        </dl>
        {data.financial_suspension ? (
          <p className="error-text" role="alert">
            Financial execution is SUSPENDED by P-10 emergency control.
          </p>
        ) : null}
        {data.threshold_violations.length > 0 ? (
          <p className="warn-text">
            Resource thresholds exceeded:{" "}
            {data.threshold_violations.map((v) => `${v.resource} ${v.value} (limit ${v.threshold})`).join(", ")}
          </p>
        ) : null}
      </section>

      <section aria-label="Key performance indicators">
        <div className="metric-grid">
          {data.kpis.map((m) => (
            <MetricCard key={m.key} metric={m} />
          ))}
        </div>
        <p className="muted kpi-note">
          Financial KPIs are P-07 verified actuals in {data.finance.currency} (minor units,
          formatted). {data.finance.note} Internal transfers excluded:{" "}
          {data.finance.internal_transfers_excluded ? "yes" : "no"}.
        </p>
      </section>

      <div className="two-col">
        <Panel title="Attention required" meta="sorted by severity, then age">
          {attention.loading && !attention.data ? <LoadingState /> : null}
          {attention.error ? <p className="error-text">{attention.error.message}</p> : null}
          {attention.data && attention.data.items.length === 0 ? (
            <p className="muted">
              Nothing needs your attention: no pending approvals, no recently failed tasks,
              no survival warnings, no open financial or security alerts.
            </p>
          ) : null}
          <ul className="attention-list">
            {(attention.data?.items ?? []).map((item, i) => (
              <li key={`${item.kind}-${item.ref_id}-${i}`} className="attention-item">
                <StatusBadge value={item.severity} />
                <div>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => navigate(item.link.replace(/^#\//, ""))}
                  >
                    {item.title}
                  </button>
                  <p className="muted">{item.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="System health" meta="actual checks, not inferred">
          {health.loading && !health.data ? <LoadingState /> : null}
          {health.error ? <p className="error-text">{health.error.message}</p> : null}
          <ul className="health-list">
            {(health.data?.checks ?? []).map((check) => (
              <li key={check.key} className="health-item">
                <StatusBadge value={check.state} />
                <div>
                  <span className="health-label">{check.label}</span>
                  <p className="muted">{check.detail}</p>
                  <p className="health-source">{check.source}</p>
                </div>
              </li>
            ))}
          </ul>
          {health.data?.resources ? (
            <div className="health-resources">
              <p className="muted">
                Resource utilization ({health.data.resources.source}): CPU{" "}
                {health.data.resources.cpu_percent ?? "—"}% · Memory{" "}
                {health.data.resources.memory_percent ?? "—"}% · Disk{" "}
                {health.data.resources.disk_percent ?? "—"}%
                {health.data.resources.threshold_violations.length > 0
                  ? ` · ${health.data.resources.threshold_violations.length} threshold violation(s)`
                  : ""}
              </p>
            </div>
          ) : null}
          {(health.data?.modules ?? []).length > 0 ? (
            <ul className="health-list">
              {(health.data?.modules ?? []).map((mod) => (
                <li key={mod.module} className="health-item">
                  <StatusBadge value={mod.state} />
                  <div>
                    <span className="health-label">{mod.module} module health</span>
                    <p className="muted">from its own checks: {mod.checks.join(", ")}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
          {health.data && (health.data.event_dead_letters ?? 0) > 0 ? (
            <p className="error-text">
              {health.data.event_dead_letters} event deliver
              {health.data.event_dead_letters === 1 ? "y" : "ies"} dead-lettered —
              see the event dead-letter record.
            </p>
          ) : null}
        </Panel>
      </div>

      <Panel title="Operational activity" meta="persisted events, newest first">
        {activity.loading && !activity.data ? <LoadingState /> : null}
        {activity.error ? <p className="error-text">{activity.error.message}</p> : null}
        {activity.data ? <ActivityFeed items={activity.data.items} /> : null}
        {activity.data ? <p className="muted">{activity.data.note}</p> : null}
        <p className="muted">
          Lifecycle states in this console: {humanize("operational")},{" "}
          {humanize("operational_with_warnings")}, {humanize("restricted")},{" "}
          {humanize("safe_mode")}, {humanize("paused")}, {humanize("emergency")} — always
          read from the backend, never inferred from the page loading.
        </p>
      </Panel>
    </div>
  );
}
