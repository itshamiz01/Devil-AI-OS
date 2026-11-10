import React, { useState } from "react";
import {
  ConfirmationDialog,
  DataTable,
  ErrorState,
  FreshnessBar,
  LineChart,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { useApi } from "../lib/hooks";

interface HealthCheck {
  key: string;
  label: string;
  state: string;
  detail: string;
  source: string;
}

interface Sample {
  sampled_at: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  queue_depth: number | null;
}

interface Incident {
  id: string;
  severity: string;
  component: string;
  kind: string;
  title: string;
  status: string;
  detected_at: string;
}

interface Readiness {
  id: string | null;
  computed_at: string;
  overall_score: number;
  band: string;
  classification: string;
  critical_gate_ok: boolean;
  categories: Record<
    string,
    { weight: number; score: number; failed_checks: string[] }
  >;
  failed_checks: { category: string; check: string; detail: string }[];
  blockers: { key: string; scope: string; detail: string }[];
  recommendations: string[];
}

interface ReliabilityOverview {
  generated_at: string;
  health: {
    overall: string;
    checks: HealthCheck[];
    resources: { cpu_percent: number; memory_percent: number; disk_percent: number };
    event_dead_letters: number;
  };
  history: Sample[];
  ai: {
    probed?: boolean;
    detail?: string;
    providers?: Record<string, { available: boolean; detail: string; models: string[] }>;
  };
  agents: { total: number; by_status: Record<string, number> };
  businesses: { total?: number; by_status?: Record<string, number> };
  queue: {
    snapshot: { depth: number; running: number; capacity: number; by_status: Record<string, number> } | null;
    operations_dead_letters_open: number;
  };
  reliability: {
    incidents: {
      open_total: number;
      resolved: number;
      recovery_rate: number | null;
      open_by_severity: Record<string, number>;
    };
    circuit_breakers: { target: string; state: string; consecutive_failures: number }[];
    recent_incidents: Incident[];
  };
  data_protection: {
    backups: {
      count: number;
      latest_verified: boolean | null;
      stale: boolean;
      latest: { created_at: string; status: string } | null;
    };
    database: { healthy: boolean; latency_ms: number | null };
    migration: { database_revision: string | null; head: string | null; is_head: boolean };
  };
  readiness: Readiness | null;
  financial: {
    businesses_checked: number;
    integrity_ok: boolean | null;
    financial_suspended: boolean;
    trading: string;
  };
  controls: { security_mode: string; financial_suspended: boolean; source: string };
  resources: {
    admission_block_reason: string | null;
    backpressure: string;
    max_concurrency: number;
    note: string;
  };
  stability: {
    total_samples: number;
    windows: { target_hours: number; status: string; sample_span_hours: number }[];
    stuck_tasks: { id: string; name: string }[];
  };
}

/**
 * P-15 §14: System Performance & Reliability. Every value comes from
 * the P-15 read-model over the existing engines (P-01 monitor/queue,
 * P-12 breakers, P-10 backups/emergency, P-07 ledger integrity).
 * GPU and real-LLM latency are shown as unavailable when the backend
 * reports no measurement — never invented. Emergency controls call
 * the P-10 endpoints directly (delegation, not duplication) and
 * require confirmation.
 */
export function PerformanceView(): React.ReactElement {
  const overview = useApi<ReliabilityOverview>("/reliability/overview", 20000);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<null | "suspend" | "resume">(null);
  const d = overview.data;

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      setNotice(`${label} — confirmed by the backend.`);
      overview.reload();
    } catch (err) {
      setNotice(`${label} failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const setSuspension = async (suspended: boolean) => {
    setConfirm(null);
    await act(
      suspended ? "Suspend financial execution" : "Resume financial execution",
      () =>
        api("/security/emergency/financial-suspension", {
          method: "POST",
          body: { suspended, reason: "set from System Performance & Reliability" },
        }),
    );
  };

  return (
    <div className="view">
      <PageHeader
        title="System Performance & Reliability"
        subtitle="Measured operational health, incidents and production readiness — P-15"
        actions={<FreshnessBar updatedAt={overview.updatedAt} />}
      />
      {overview.loading && !d ? <LoadingState label="Loading reliability overview…" /> : null}
      {overview.error ? <ErrorState error={overview.error} onRetry={overview.reload} /> : null}
      {notice ? <p className="notice">{notice}</p> : null}
      {d ? (
        <>
          <Panel title="A · Live system health" meta={d.health.overall}>
            <dl className="stat-row num">
              <div><dt>Overall</dt><dd><StatusBadge value={d.health.overall} /></dd></div>
              <div><dt>CPU</dt><dd>{d.health.resources.cpu_percent}%</dd></div>
              <div><dt>RAM</dt><dd>{d.health.resources.memory_percent}%</dd></div>
              <div><dt>Disk</dt><dd>{d.health.resources.disk_percent}%</dd></div>
              <div><dt>Event dead letters</dt><dd>{formatNumber(d.health.event_dead_letters)}</dd></div>
            </dl>
            <DataTable
              columns={[
                { key: "label", label: "Component" },
                { key: "state", label: "State" },
                { key: "detail", label: "Detail" },
                { key: "source", label: "Source" },
              ]}
              rows={d.health.checks.map((c) => ({
                label: c.label,
                state: <StatusBadge value={c.state} />,
                detail: c.detail,
                source: c.source,
              }))}
              emptyTitle="No component checks"
              emptyDetail="The system-health aggregation returned no checks."
            />
            {d.history.length > 1 ? (
              <LineChart
                label="Memory % history (recorded samples)"
                points={d.history
                  .filter((s) => s.memory_percent !== null)
                  .map((s) => ({ x: s.sampled_at, y: s.memory_percent as number }))}
              />
            ) : (
              <p>No performance history yet — the sampler records while the system runs.</p>
            )}
          </Panel>

          <Panel title="B · AI infrastructure" meta="provider probe truth">
            {d.ai.providers ? (
              <DataTable
                columns={[
                  { key: "name", label: "Provider" },
                  { key: "available", label: "Available" },
                  { key: "detail", label: "Detail" },
                  { key: "models", label: "Models" },
                ]}
                rows={Object.entries(d.ai.providers).map(([name, p]) => ({
                  name,
                  available: p.available ? "available" : "unavailable",
                  detail: p.detail,
                  models: p.models.length ? p.models.join(", ") : "—",
                }))}
                emptyTitle="No providers"
                emptyDetail="No provider status was returned."
              />
            ) : (
              <p>No provider probe has run yet in this process. Model latency is never invented: no real LLM has been exercised in staging.</p>
            )}
          </Panel>

          <Panel title="C · Agent monitoring" meta="P-04 agent factory">
            <dl className="stat-row num">
              <div><dt>Total agents</dt><dd>{formatNumber(d.agents.total)}</dd></div>
              {Object.entries(d.agents.by_status).map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd>{formatNumber(v)}</dd></div>
              ))}
            </dl>
          </Panel>

          <Panel title="D · Business monitoring" meta="P-06 businesses">
            <dl className="stat-row num">
              <div><dt>Total businesses</dt><dd>{formatNumber(d.businesses.total ?? 0)}</dd></div>
              {Object.entries(d.businesses.by_status ?? {}).map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd>{formatNumber(v)}</dd></div>
              ))}
            </dl>
          </Panel>

          <Panel title="E · Queue monitoring" meta="P-01 task queue">
            {d.queue.snapshot ? (
              <dl className="stat-row num">
                <div><dt>Pending (depth)</dt><dd>{formatNumber(d.queue.snapshot.depth)}</dd></div>
                <div><dt>Running</dt><dd>{formatNumber(d.queue.snapshot.running)}</dd></div>
                <div><dt>Capacity</dt><dd>{formatNumber(d.queue.snapshot.capacity)}</dd></div>
                <div><dt>Completed</dt><dd>{formatNumber(d.queue.snapshot.by_status.completed ?? 0)}</dd></div>
                <div><dt>Failed</dt><dd>{formatNumber(d.queue.snapshot.by_status.failed ?? 0)}</dd></div>
                <div><dt>Dead-letter (operations)</dt><dd>{formatNumber(d.queue.operations_dead_letters_open)}</dd></div>
                <div><dt>Backpressure</dt><dd><StatusBadge value={d.resources.backpressure} /></dd></div>
              </dl>
            ) : (
              <p>Queue snapshot unavailable.</p>
            )}
            <p>{d.resources.note}</p>
          </Panel>

          <Panel title="F · Reliability dashboard" meta="incident register (P-15)">
            <dl className="stat-row num">
              <div><dt>Open incidents</dt><dd>{formatNumber(d.reliability.incidents.open_total)}</dd></div>
              <div><dt>Resolved</dt><dd>{formatNumber(d.reliability.incidents.resolved)}</dd></div>
              <div>
                <dt>Recovery rate</dt>
                <dd>{d.reliability.incidents.recovery_rate === null ? "—" : `${Math.round(d.reliability.incidents.recovery_rate * 100)}%`}</dd>
              </div>
              {Object.entries(d.reliability.incidents.open_by_severity).map(([k, v]) => (
                <div key={k}><dt>Open {k}</dt><dd>{formatNumber(v)}</dd></div>
              ))}
            </dl>
            <DataTable
              columns={[
                { key: "target", label: "Circuit breaker" },
                { key: "state", label: "State" },
                { key: "failures", label: "Consecutive failures", numeric: true },
              ]}
              rows={d.reliability.circuit_breakers.map((b) => ({
                target: b.target,
                state: <StatusBadge value={b.state} />,
                failures: String(b.consecutive_failures),
              }))}
              emptyTitle="No circuit breakers registered"
              emptyDetail="P-12 registers breakers per dependency target on first use."
            />
            <DataTable
              columns={[
                { key: "severity", label: "Severity" },
                { key: "component", label: "Component" },
                { key: "title", label: "Incident" },
                { key: "status", label: "Status" },
              ]}
              rows={d.reliability.recent_incidents.map((i) => ({
                severity: i.severity,
                component: i.component,
                title: i.title,
                status: <StatusBadge value={i.status} />,
              }))}
              emptyTitle="No incidents recorded"
              emptyDetail="The reliability incident register is empty."
            />
            <h3 className="subhead">Long-duration stability (§11.5)</h3>
            <DataTable
              columns={[
                { key: "window", label: "Window" },
                { key: "status", label: "Status" },
                { key: "coverage", label: "Recorded coverage" },
              ]}
              rows={d.stability.windows.map((w) => ({
                window: `${w.target_hours}h`,
                status: <StatusBadge value={w.status} />,
                coverage: `${w.sample_span_hours}h of samples`,
              }))}
              emptyTitle="No stability windows"
              emptyDetail="No long-duration targets are configured."
            />
            <p>
              Stuck tasks beyond threshold: {formatNumber(d.stability.stuck_tasks.length)}.
              Windows complete only when real sampler coverage spans them — never back-filled.
            </p>
          </Panel>

          <Panel title="G · Data protection" meta="P-10 backup service">
            <dl className="stat-row num">
              <div><dt>Backups</dt><dd>{formatNumber(d.data_protection.backups.count)}</dd></div>
              <div><dt>Latest verified</dt><dd>{d.data_protection.backups.latest_verified === null ? "—" : d.data_protection.backups.latest_verified ? "yes" : "no"}</dd></div>
              <div><dt>Latest stale</dt><dd>{d.data_protection.backups.stale ? "STALE" : "no"}</dd></div>
              <div><dt>Database</dt><dd>{d.data_protection.database.healthy ? "healthy" : "UNHEALTHY"}</dd></div>
              <div><dt>DB latency</dt><dd>{d.data_protection.database.latency_ms === null ? "—" : `${d.data_protection.database.latency_ms} ms`}</dd></div>
              <div><dt>Migration at head</dt><dd>{d.data_protection.migration.is_head ? "yes" : "no"}</dd></div>
            </dl>
            <div className="card-actions">
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void act("Create verified backup", () => api("/reliability/backups", { method: "POST", body: {} }))}
              >
                Create verified backup (P-10)
              </button>
            </div>
          </Panel>

          <Panel title="H · Production readiness" meta="§13 score from live evidence">
            {d.readiness ? (
              <>
                <dl className="stat-row num">
                  <div><dt>Overall score</dt><dd>{d.readiness.overall_score} / 100</dd></div>
                  <div><dt>Band</dt><dd>{d.readiness.band}</dd></div>
                  <div><dt>Critical gate</dt><dd>{d.readiness.critical_gate_ok ? "pass" : "FAILED"}</dd></div>
                  <div><dt>Computed</dt><dd>{d.readiness.computed_at}</dd></div>
                </dl>
                <p><strong>{d.readiness.classification}</strong></p>
                <DataTable
                  columns={[
                    { key: "category", label: "Category" },
                    { key: "weight", label: "Weight" },
                    { key: "score", label: "Score", numeric: true },
                    { key: "failed", label: "Failed checks" },
                  ]}
                  rows={Object.entries(d.readiness.categories).map(([key, cat]) => ({
                    category: key,
                    weight: `${cat.weight}%`,
                    score: String(cat.score),
                    failed: cat.failed_checks.length ? cat.failed_checks.join(", ") : "—",
                  }))}
                  emptyTitle="No categories"
                  emptyDetail="The readiness snapshot carries no categories."
                />
                {d.readiness.blockers.length ? (
                  <>
                    <h3 className="subhead">Blockers</h3>
                    <ul>
                      {d.readiness.blockers.map((b) => (
                        <li key={b.key}><strong>{b.scope}</strong>: {b.detail}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </>
            ) : (
              <p>No readiness snapshot computed yet.</p>
            )}
            <div className="card-actions">
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void act("Recompute readiness", () => api("/reliability/readiness/compute", { method: "POST", body: {} }))}
              >
                Recompute score
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void act("Run benchmark suite", () => api("/reliability/benchmarks", { method: "POST", body: { kind: "baseline" } }))}
              >
                Run benchmarks
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void act("Evaluate incidents", () => api("/reliability/evaluate", { method: "POST", body: {} }))}
              >
                Evaluate incidents
              </button>
            </div>
          </Panel>

          <Panel title="I · Emergency controls" meta={d.controls.source}>
            <dl className="stat-row">
              <div><dt>Security mode</dt><dd><StatusBadge value={d.controls.security_mode} /></dd></div>
              <div><dt>Financial execution</dt><dd>{d.controls.financial_suspended ? "SUSPENDED" : "active"}</dd></div>
              <div><dt>Ledger integrity (P-07)</dt><dd>{d.financial.integrity_ok === null ? "no businesses" : d.financial.integrity_ok ? "verified" : "FAILED"}</dd></div>
            </dl>
            <p>{d.financial.trading}</p>
            <div className="card-actions">
              {d.controls.financial_suspended ? (
                <button type="button" className="btn" disabled={busy} onClick={() => setConfirm("resume")}>
                  Resume financial execution
                </button>
              ) : (
                <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirm("suspend")}>
                  Suspend financial execution
                </button>
              )}
            </div>
            <p>
              Mode changes and shutdown stay in the Security view and the P-01 lifecycle —
              P-15 delegates to P-10 rather than duplicating its controls.
            </p>
          </Panel>

          <ConfirmationDialog
            open={confirm !== null}
            title={confirm === "suspend" ? "Suspend financial execution?" : "Resume financial execution?"}
            body={
              confirm === "suspend"
                ? "This asks the P-10 emergency service to suspend financial execution. Existing records are preserved; resumption is a separate confirmed action."
                : "This asks the P-10 emergency service to resume financial execution."
            }
            confirmLabel={confirm === "suspend" ? "Suspend" : "Resume"}
            danger={confirm === "suspend"}
            busy={busy}
            onCancel={() => setConfirm(null)}
            onConfirm={() => void setSuspension(confirm === "suspend")}
          />
        </>
      ) : null}
    </div>
  );
}
