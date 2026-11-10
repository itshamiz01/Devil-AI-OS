import React from "react";
import {
  DataTable,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { formatNumber } from "../lib/format";
import { useApi } from "../lib/hooks";

interface SystemStatus {
  lifecycle_state: string;
  database_healthy: boolean;
  resources: {
    cpu_percent: number;
    memory_percent: number;
    memory_available_mb: number;
    memory_total_mb: number;
    disk_percent: number;
    disk_free_gb: number;
    process_count: number;
  };
  threshold_violations: { resource: string; value: number; threshold: number }[];
  queue: { capacity: number; depth: number; running: number; by_status: Record<string, number> };
}

interface SecretsData {
  secrets?: { name: string; backend?: string; status?: string }[];
  [key: string]: unknown;
}

/**
 * §16 System Operations Center. Telemetry shown is what the platform
 * actually measures (P-01 monitor via psutil). GPU telemetry does not
 * exist in the backend and is shown as unavailable — never invented
 * (§16.2). Logs are the persisted event/audit views, access-controlled
 * by P-10; secret values never appear (P-10 metadata-only broker).
 */
export function OperationsView(): React.ReactElement {
  const status = useApi<SystemStatus>("/system/status", 15000);
  const execHealth = useApi<Record<string, unknown>>("/execution/health-report", 30000);
  const secrets = useApi<SecretsData>("/security/secrets", 60000);
  const audit = useApi<Record<string, unknown>[]>("/security/audit?limit=50", 30000);
  const backups = useApi<Record<string, unknown>[]>("/security/backups", 60000);

  const r = status.data?.resources;
  return (
    <div className="view">
      <PageHeader
        title="System Operations"
        subtitle="Infrastructure health and resources — measured, not inferred"
        actions={<FreshnessBar updatedAt={status.updatedAt} />}
      />
      {status.loading && !status.data ? <LoadingState label="Loading system status…" /> : null}
      {status.error ? <ErrorState error={status.error} onRetry={status.reload} /> : null}
      {status.data && r ? (
        <Panel title="System status" meta="P-01 system monitor">
          <dl className="stat-row">
            <div><dt>Lifecycle</dt><dd><StatusBadge value={status.data.lifecycle_state} /></dd></div>
            <div><dt>Database</dt><dd>{status.data.database_healthy ? "healthy" : "UNHEALTHY"}</dd></div>
            <div><dt>Queue depth</dt><dd className="num">{status.data.queue.depth}</dd></div>
            <div><dt>Queue running</dt><dd className="num">{status.data.queue.running}</dd></div>
            <div><dt>Queue capacity</dt><dd className="num">{status.data.queue.capacity}</dd></div>
          </dl>
          <h3 className="subhead">Resources (this host, measured by psutil)</h3>
          <dl className="stat-row num">
            <div><dt>CPU</dt><dd>{r.cpu_percent}%</dd></div>
            <div><dt>Memory</dt><dd>{r.memory_percent}% used</dd></div>
            <div><dt>Memory available</dt><dd>{formatNumber(Math.round(r.memory_available_mb))} MB</dd></div>
            <div><dt>Disk</dt><dd>{r.disk_percent}% used · {r.disk_free_gb} GB free</dd></div>
            <div><dt>Processes</dt><dd>{r.process_count}</dd></div>
            <div>
              <dt>GPU usage</dt>
              <dd>Unavailable — the backend exposes no GPU telemetry; the target machine's GPU cannot run inference (P-00 verdict), and no figure is invented here.</dd>
            </div>
          </dl>
          {status.data.threshold_violations.length > 0 ? (
            <p className="warn-text" role="alert">
              Threshold violations:{" "}
              {status.data.threshold_violations.map((v) => `${v.resource} ${v.value} > ${v.threshold}`).join(", ")}
            </p>
          ) : (
            <p className="muted">No resource threshold violations.</p>
          )}
        </Panel>
      ) : null}

      <div className="two-col">
        <Panel title="Execution health" meta="P-05 health report">
          {execHealth.data ? (
            <pre className="params-json">{JSON.stringify(execHealth.data, null, 2)}</pre>
          ) : (
            <p className="muted">Execution health report unavailable.</p>
          )}
          <p className="muted">
            Scheduler: AUTONOMUS runs an in-process task queue (shown above) and P-05
            workflow runs (Execution view). There is no separate cron-style scheduler API;
            recurring-workflow controls are therefore not offered here rather than faked.
          </p>
        </Panel>

        <Panel title="Secret vault status" meta="metadata only — values never leave P-10's broker">
          {secrets.error ? (
            <p className="muted">Secret metadata unavailable: {secrets.error.message}</p>
          ) : null}
          {secrets.data ? (
            <pre className="params-json">{JSON.stringify(secrets.data, null, 2)}</pre>
          ) : null}
          <h3 className="subhead">Backups</h3>
          {backups.data && backups.data.length === 0 ? (
            <p className="muted">No backup records. P-10 backups are owner-triggered from the Security tooling; none exist in this environment yet.</p>
          ) : null}
          <ul className="plain-list">
            {(backups.data ?? []).map((b, i) => (
              <li key={i} className="plain-item">
                <div className="plain-body">
                  <span className="mono">{String(b["id"] ?? `backup-${i}`)}</span>
                  <p className="muted">{String(b["status"] ?? "")} · {String(b["created_at"] ?? "")}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Audit & event log" meta="P-10 audit (hash-chained) — access-controlled">
        <DataTable
          columns={[
            { key: "at", label: "When" },
            { key: "actor", label: "Actor" },
            { key: "action", label: "Action" },
            { key: "target", label: "Target" },
            { key: "decision", label: "Decision" },
          ]}
          rows={(audit.data ?? []).map((e) => ({
            at: String(e["created_at"] ?? "—"),
            actor: `${String(e["actor_type"] ?? "")}:${String(e["actor_id"] ?? "")}`,
            action: String(e["action"] ?? "—"),
            target: `${String(e["target_type"] ?? "")}:${String(e["target_id"] ?? "")}`,
            decision: String(e["decision"] ?? "—"),
          }))}
          emptyTitle="No audit events visible"
          emptyDetail="Either no auditable actions have occurred, or your principal cannot see them (P-10 access restrictions apply)."
        />
        <p className="muted">
          The full activity feed is on Overview; security event exploration with filters is
          served by P-10's audit endpoints. Log views never contain secret values.
        </p>
      </Panel>
    </div>
  );
}
