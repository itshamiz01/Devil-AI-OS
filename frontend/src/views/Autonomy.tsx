import React, { useState } from "react";
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
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";

// ------------------------------------------------------------------ types

interface OperationsOverview {
  workflows: Record<string, number>;
  tasks: Record<string, number>;
  pending_approvals: number;
  open_dead_letters: number;
  engine: { running: boolean; tick_interval_seconds: number };
  generated_at: string;
}

interface WorkflowRow {
  id: string;
  name: string;
  business_id: string | null;
  origin: string;
  status: string;
  verified_outcome: string | null;
  autonomy_level: number;
  current_step: string | null;
  progress_percent: number | null;
  created_at: string;
}

interface WorkflowTaskRow {
  id: string;
  step_key: string;
  name: string;
  kind: string;
  action_class: string;
  status: string;
  verification_status: string;
  assigned_agent_id: string | null;
  attempts: number;
}

interface WorkflowDetail extends WorkflowRow {
  tasks: WorkflowTaskRow[];
  checkpoints: { completed_steps: { step_key: string }[] }[];
  history: { event_type: string; actor: string; created_at: string }[];
  learning_record_id: string | null;
}

interface AgentOpsRow {
  agent_id: string;
  business_ref: string | null;
  status: string;
  active_tasks: number;
  completed: number;
  failed: number;
  success_rate: number | null;
}

interface ApprovalLinkRow {
  id: string;
  workflow_id: string;
  purpose: string;
  status: string;
  approval_status: string | null;
  action: string | null;
  created_at: string;
}

interface TriggerRow {
  id: string;
  name: string;
  trigger_type: string;
  status: string;
  next_fire_at: string | null;
  last_fire_at: string | null;
  fire_count: number;
  missed_count: number;
}

interface RecoveryData {
  dead_letters: {
    id: string; workflow_id: string; failure_category: string;
    reason: string; status: string; created_at: string;
  }[];
  dead_letter_total: number;
  recovery_records: {
    id: string; failure_category: string; action: string;
    outcome: string; created_at: string;
  }[];
  circuit_breakers: {
    target: string; state: string; consecutive_failures: number;
  }[];
  checkpoints: number;
}

interface SafetyData {
  security_mode: string;
  constitution_mode: string;
  financial_suspended: boolean;
  paused_businesses: string[];
  active_workflows: number;
  autonomy_policies: { scope_type: string; level: number }[];
}

interface ReportRow {
  id: string;
  kind: string;
  title: string;
  created_at: string;
}

interface TemplateRow {
  name: string;
  description: string;
}

const TABS = [
  "Overview", "Workflows", "Agents", "Approvals", "Scheduler",
  "Recovery", "Safety", "Reports",
] as const;
type Tab = (typeof TABS)[number];

/**
 * §19 Autonomous Operations: the P-12 control surface. Every number
 * comes from the operations API; every control calls a real endpoint
 * and the UI updates only from the backend's response (reload after
 * the confirmed write). Nothing here can approve its own work —
 * approvals are decided in the P-01/P-11 approval surfaces; this
 * view links and processes them.
 */
export function AutonomyView(): React.ReactElement {
  const [tab, setTab] = useState<Tab>("Overview");
  const overview = useApi<OperationsOverview>("/operations/overview", 30000);

  return (
    <div className="view">
      <PageHeader
        title="Autonomous Operations"
        subtitle="P-12 operations engine — governed autonomy, verified outcomes"
        actions={<FreshnessBar updatedAt={overview.updatedAt} />}
      />
      <div className="filter-bar" role="tablist" aria-label="Autonomous operations sections">
        {TABS.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? "chip chip-active" : "chip"}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>
      {tab === "Overview" ? (
        <OverviewTab overview={overview} />
      ) : tab === "Workflows" ? (
        <WorkflowsTab />
      ) : tab === "Agents" ? (
        <AgentsTab />
      ) : tab === "Approvals" ? (
        <ApprovalsTab />
      ) : tab === "Scheduler" ? (
        <SchedulerTab />
      ) : tab === "Recovery" ? (
        <RecoveryTab />
      ) : tab === "Safety" ? (
        <SafetyTab />
      ) : (
        <ReportsTab />
      )}
    </div>
  );
}

// ------------------------------------------------------------------ tabs

function OverviewTab({
  overview,
}: {
  overview: ReturnType<typeof useApi<OperationsOverview>>;
}): React.ReactElement {
  if (overview.loading && !overview.data) {
    return <LoadingState label="Loading operations overview…" />;
  }
  if (overview.error) {
    return <ErrorState error={overview.error} onRetry={overview.reload} />;
  }
  const data = overview.data;
  if (!data) return <EmptyState title="No operations data" detail="" />;
  const totalWorkflows = Object.values(data.workflows).reduce((a, b) => a + b, 0);
  return (
    <>
      <Panel title="Operations overview" meta="P-12 operations engine">
        <dl className="stat-row num">
          <div><dt>Workflows total</dt><dd>{totalWorkflows}</dd></div>
          <div><dt>Running</dt><dd>{data.workflows.RUNNING ?? 0}</dd></div>
          <div><dt>Completed (verified)</dt><dd>{data.workflows.COMPLETED ?? 0}</dd></div>
          <div><dt>Waiting for approval</dt><dd>{data.workflows.WAITING_FOR_APPROVAL ?? 0}</dd></div>
          <div><dt>Failed</dt><dd>{data.workflows.FAILED ?? 0}</dd></div>
          <div><dt>Pending approvals</dt><dd>{data.pending_approvals}</dd></div>
          <div><dt>Dead letters</dt><dd>{data.open_dead_letters}</dd></div>
          <div>
            <dt>Scheduler engine</dt>
            <dd>{data.engine.running ? "running" : "stopped"}</dd>
          </div>
        </dl>
        <p className="muted">
          A completed workflow is a VERIFIED workflow: completion is only
          recorded after independent verification of every step. Workflow
          activity is not revenue — collected money is reported by P-07
          in Finance, never inferred here.
        </p>
      </Panel>
      <Panel title="Tasks by status">
        <dl className="stat-row num">
          {Object.entries(data.tasks).map(([status, count]) => (
            <div key={status}><dt>{status}</dt><dd>{count}</dd></div>
          ))}
        </dl>
      </Panel>
    </>
  );
}

function WorkflowsTab(): React.ReactElement {
  const list = useApi<{ items: WorkflowRow[]; total: number }>(
    "/operations/workflows?limit=50", 30000);
  const templates = useApi<{ items: TemplateRow[] }>("/operations/templates");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detail = useApi<WorkflowDetail>(
    selectedId ? `/operations/workflows/${selectedId}` : null, 15000);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("monitoring_report");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);

  const act = async (path: string, method = "POST") => {
    setBusy(true);
    setActionError(null);
    try {
      await api(path, { method });
      list.reload();
      detail.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setActionError(null);
    try {
      const created = await api<WorkflowRow>("/operations/workflows", {
        method: "POST",
        body: { name: name.trim(), template, autonomy_level: 2 },
      });
      await api(`/operations/workflows/${created.data.id}/validate`, {
        method: "POST",
      });
      setName("");
      list.reload();
      setSelectedId(created.data.id);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Panel title="Create workflow from template">
        <div className="filter-bar">
          <label className="field">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Weekly monitoring"
            />
          </label>
          <label className="field">
            Template
            <select value={template} onChange={(e) => setTemplate(e.target.value)}>
              {(templates.data?.items ?? []).map((t) => (
                <option key={t.name} value={t.name}>{t.name}</option>
              ))}
            </select>
          </label>
          <button className="btn" disabled={busy || !name.trim()} onClick={create}>
            Create + validate
          </button>
        </div>
        <p className="muted">
          Templates are the governed, deterministic definitions. The
          engine never executes free-form instructions.
        </p>
      </Panel>
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      <Panel title="Workflow Control Center">
        {list.loading && !list.data ? <LoadingState label="Loading workflows…" /> : null}
        {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : null}
        {list.data ? (
          <DataTable
            columns={[
              { key: "name", label: "Name" }, { key: "origin", label: "Origin" },
              { key: "status", label: "Status" }, { key: "verified", label: "Verified" },
              { key: "autonomy", label: "Autonomy" }, { key: "progress", label: "Progress" },
            ]}
            rows={list.data.items.map((w) => ({
              name: (
                <button key={w.id} className="link-button" onClick={() => setSelectedId(w.id)}>
                  {w.name}
                </button>
              ),
              origin: w.origin,
              status: <StatusBadge value={w.status} />,
              verified: w.verified_outcome ?? "—",
              autonomy: `L${w.autonomy_level}`,
              progress: w.progress_percent === null ? "—" : `${w.progress_percent}%`,
            }))}
            emptyTitle="No workflows yet"
            emptyDetail="Create one from a template above, or wait for a schedule or trigger to create one."
          />
        ) : null}
      </Panel>
      {selectedId && detail.data ? (
        <Panel title={`Workflow: ${detail.data.name}`} meta={detail.data.id}>
          <dl className="stat-row">
            <div><dt>Status</dt><dd>{detail.data.status}</dd></div>
            <div><dt>Verified outcome</dt><dd>{detail.data.verified_outcome ?? "—"}</dd></div>
            <div>
              <dt>Learning record</dt>
              <dd>{detail.data.learning_record_id ?? "none"}</dd>
            </div>
          </dl>
          <div className="card-actions">
            {detail.data.status === "READY" || detail.data.status === "SCHEDULED" ? (
              <button className="btn" disabled={busy}
                onClick={() => act(`/operations/workflows/${selectedId}/start`)}>
                Start
              </button>
            ) : null}
            {detail.data.status === "RUNNING" ? (
              <button className="btn" disabled={busy}
                onClick={() => act(`/operations/workflows/${selectedId}/pause`)}>
                Pause
              </button>
            ) : null}
            {["PAUSED", "BLOCKED", "RECOVERY_PENDING"].includes(detail.data.status) ? (
              <button className="btn" disabled={busy}
                onClick={() => act(`/operations/workflows/${selectedId}/resume`)}>
                Resume
              </button>
            ) : null}
            {!["COMPLETED", "FAILED", "CANCELLED"].includes(detail.data.status) ? (
              <button className="btn btn-danger" disabled={busy}
                onClick={() => setConfirmCancel(true)}>
                Cancel workflow
              </button>
            ) : null}
          </div>
          <DataTable
            columns={[
              { key: "name", label: "Step" }, { key: "kind", label: "Kind" },
              { key: "action", label: "Action" }, { key: "status", label: "Status" },
              { key: "verification", label: "Verification" },
              { key: "agent", label: "Agent" }, { key: "attempts", label: "Attempts" },
            ]}
            rows={detail.data.tasks.map((t) => ({
              name: t.name, kind: t.kind, action: t.action_class,
              status: <StatusBadge value={t.status} />,
              verification: t.verification_status,
              agent: t.assigned_agent_id ?? "—", attempts: String(t.attempts),
            }))}
            emptyTitle="No steps"
            emptyDetail="This workflow has no recorded steps."
          />
          {confirmCancel ? (
            <ConfirmationDialog
              open
              title="Cancel this workflow?"
              body="Running steps are not interrupted mid-flight; pending steps are cancelled. This is recorded in the workflow history."
              confirmLabel="Cancel workflow"
              danger
              onCancel={() => setConfirmCancel(false)}
              onConfirm={() => {
                setConfirmCancel(false);
                void act(`/operations/workflows/${selectedId}/cancel`);
              }}
            />
          ) : null}
        </Panel>
      ) : null}
    </>
  );
}

function AgentsTab(): React.ReactElement {
  const agents = useApi<{ items: AgentOpsRow[]; total: number }>(
    "/operations/agents", 30000);
  return (
    <Panel title="Agent Operations">
      {agents.loading && !agents.data ? <LoadingState label="Loading agent operations…" /> : null}
      {agents.error ? <ErrorState error={agents.error} onRetry={agents.reload} /> : null}
      {agents.data ? (
        <DataTable
          columns={[
            { key: "agent", label: "Agent" }, { key: "business", label: "Business" },
            { key: "status", label: "Status" }, { key: "active", label: "Active" },
            { key: "completed", label: "Completed" }, { key: "failed", label: "Failed" },
            { key: "rate", label: "Success rate" },
          ]}
          rows={agents.data.items.map((a) => ({
            agent: a.agent_id, business: a.business_ref ?? "—", status: a.status,
            active: String(a.active_tasks), completed: String(a.completed),
            failed: String(a.failed),
            rate: a.success_rate === null ? "—" : `${Math.round(a.success_rate * 100)}%`,
          }))}
          emptyTitle="No agent activity"
          emptyDetail="Agents appear here once workflows assign work to them."
        />
      ) : null}
    </Panel>
  );
}

function ApprovalsTab(): React.ReactElement {
  const approvals = useApi<{ items: ApprovalLinkRow[] }>(
    "/operations/approvals", 15000);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const check = async () => {
    setBusy(true);
    try {
      const result = await api<{ resolved: unknown[]; driven: string[] }>(
        "/operations/approvals/check", { method: "POST" });
      setNote(
        `Processed: ${result.data.resolved.length} resolved, ` +
        `${result.data.driven.length} workflow(s) driven.`);
      approvals.reload();
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Panel title="Approval Center — operations view">
        <p className="muted">
          These are references to the single P-01 approval store — the
          same approvals shown in the Command Center's Approvals view,
          where decisions are made. After a decision, process approvals
          here to release the waiting steps.
        </p>
        <button className="btn" disabled={busy} onClick={check}>
          Process approvals
        </button>
        {note ? <p role="status">{note}</p> : null}
      </Panel>
      <Panel title="Linked approvals">
        {approvals.loading && !approvals.data ? <LoadingState label="Loading approvals…" /> : null}
        {approvals.error ? <ErrorState error={approvals.error} onRetry={approvals.reload} /> : null}
        {approvals.data ? (
          <DataTable
            columns={[
              { key: "purpose", label: "Purpose" }, { key: "action", label: "Action" },
              { key: "link", label: "Link status" }, { key: "approval", label: "Approval" },
              { key: "created", label: "Created" },
            ]}
            rows={approvals.data.items.map((a) => ({
              purpose: a.purpose, action: a.action ?? "—", link: a.status,
              approval: a.approval_status ?? "—", created: formatDateTime(a.created_at),
            }))}
            emptyTitle="No linked approvals"
            emptyDetail="Restricted steps create approval links here when they park."
          />
        ) : null}
      </Panel>
    </>
  );
}

function SchedulerTab(): React.ReactElement {
  const triggers = useApi<{ items: TriggerRow[]; total: number }>(
    "/operations/triggers", 30000);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const tick = async () => {
    setBusy(true);
    try {
      const result = await api<{ fired: unknown[]; started: string[]; resumed: string[] }>(
        "/operations/scheduler/tick", { method: "POST" });
      setNote(
        `Tick complete: ${result.data.fired.length} trigger(s) fired, ` +
        `${result.data.started.length} started, ${result.data.resumed.length} resumed.`);
      triggers.reload();
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Panel title="Scheduler">
        <p className="muted">
          One engine, one tick: the same pass the background loop runs —
          approvals, due triggers, scheduled starts and recovery resumes.
          Running it manually never duplicates a fire (fire keys dedupe).
        </p>
        <button className="btn" disabled={busy} onClick={tick}>Run tick now</button>
        {note ? <p role="status">{note}</p> : null}
      </Panel>
      <Panel title="Triggers">
        {triggers.loading && !triggers.data ? <LoadingState label="Loading triggers…" /> : null}
        {triggers.error ? <ErrorState error={triggers.error} onRetry={triggers.reload} /> : null}
        {triggers.data ? (
          <DataTable
            columns={[
              { key: "name", label: "Name" }, { key: "type", label: "Type" },
              { key: "status", label: "Status" }, { key: "next", label: "Next fire" },
              { key: "fires", label: "Fires" }, { key: "missed", label: "Missed" },
            ]}
            rows={triggers.data.items.map((t) => ({
              name: t.name, type: t.trigger_type, status: t.status,
              next: t.next_fire_at ? formatDateTime(t.next_fire_at) : "—",
              fires: String(t.fire_count), missed: String(t.missed_count),
            }))}
            emptyTitle="No triggers"
            emptyDetail="Time, event and threshold triggers will be listed here."
          />
        ) : null}
      </Panel>
    </>
  );
}

function RecoveryTab(): React.ReactElement {
  const recovery = useApi<RecoveryData>("/operations/recovery", 30000);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const resolve = async (id: string) => {
    setBusy(true);
    setActionError(null);
    try {
      await api(`/operations/recovery/dead-letter/${id}/resolve`, {
        method: "POST", body: { resolution: "acknowledge" },
      });
      recovery.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      <Panel title="Recovery Center">
        {recovery.loading && !recovery.data ? <LoadingState label="Loading recovery data…" /> : null}
        {recovery.error ? <ErrorState error={recovery.error} onRetry={recovery.reload} /> : null}
        {recovery.data ? (
          <dl className="stat-row num">
            <div><dt>Dead letters</dt><dd>{recovery.data.dead_letter_total}</dd></div>
            <div><dt>Checkpoints</dt><dd>{recovery.data.checkpoints}</dd></div>
            <div>
              <dt>Open circuit breakers</dt>
              <dd>{recovery.data.circuit_breakers.filter((b) => b.state === "open").length}</dd>
            </div>
          </dl>
        ) : null}
      </Panel>
      {recovery.data && recovery.data.circuit_breakers.length > 0 ? (
        <Panel title="Circuit breakers">
          <DataTable
            columns={[
              { key: "target", label: "Target" }, { key: "state", label: "State" },
              { key: "failures", label: "Consecutive failures" },
            ]}
            rows={recovery.data.circuit_breakers.map((b) => ({
              target: b.target, state: b.state,
              failures: String(b.consecutive_failures),
            }))}
            emptyTitle="No circuit breakers"
            emptyDetail=""
          />
        </Panel>
      ) : null}
      <Panel title="Dead-letter queue">
        {recovery.data ? (
          <DataTable
            columns={[
              { key: "category", label: "Category" }, { key: "reason", label: "Reason" },
              { key: "status", label: "Status" }, { key: "created", label: "Created" },
              { key: "action", label: "Action" },
            ]}
            rows={recovery.data.dead_letters.map((d) => ({
              category: d.failure_category, reason: d.reason, status: d.status,
              created: formatDateTime(d.created_at),
              action: d.status === "open" ? (
                <button key={d.id} className="btn" disabled={busy} onClick={() => resolve(d.id)}>
                  Acknowledge
                </button>
              ) : "—",
            }))}
            emptyTitle="Dead-letter queue is empty"
            emptyDetail="Steps that exhaust retries land here for investigation instead of vanishing."
          />
        ) : null}
      </Panel>
      {recovery.data && recovery.data.recovery_records.length > 0 ? (
        <Panel title="Recent recovery actions">
          <DataTable
            columns={[
              { key: "category", label: "Category" }, { key: "action", label: "Action" },
              { key: "outcome", label: "Outcome" }, { key: "when", label: "When" },
            ]}
            rows={recovery.data.recovery_records.slice(0, 20).map((r) => ({
              category: r.failure_category, action: r.action, outcome: r.outcome,
              when: formatDateTime(r.created_at),
            }))}
            emptyTitle="No recovery actions"
            emptyDetail=""
          />
        </Panel>
      ) : null}
    </>
  );
}

function SafetyTab(): React.ReactElement {
  const safety = useApi<SafetyData>("/operations/safety", 15000);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"global" | "financial" | null>(null);

  const act = async (path: string, scope: string) => {
    setBusy(true);
    setActionError(null);
    try {
      await api(path, { method: "POST", body: { scope, scope_ref: null } });
      safety.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      <Panel title="System Safety Center">
        {safety.loading && !safety.data ? <LoadingState label="Loading safety state…" /> : null}
        {safety.error ? <ErrorState error={safety.error} onRetry={safety.reload} /> : null}
        {safety.data ? (
          <>
            <dl className="stat-row">
              <div><dt>Security mode (P-10)</dt><dd>{safety.data.security_mode}</dd></div>
              <div><dt>Constitution mode</dt><dd>{safety.data.constitution_mode}</dd></div>
              <div>
                <dt>Financial operations</dt>
                <dd>{safety.data.financial_suspended ? "SUSPENDED" : "active"}</dd>
              </div>
              <div><dt>Active workflows</dt><dd>{safety.data.active_workflows}</dd></div>
              <div>
                <dt>Paused businesses</dt>
                <dd>{safety.data.paused_businesses.length}</dd>
              </div>
            </dl>
            <div className="card-actions">
              {safety.data.security_mode !== "emergency_stop" ? (
                <button className="btn btn-danger" disabled={busy} onClick={() => setConfirm("global")}>
                  Global emergency stop
                </button>
              ) : (
                <button className="btn" disabled={busy}
                  onClick={() => act("/operations/emergency/resume", "global")}>
                  Resume from emergency stop (owner)
                </button>
              )}
              {!safety.data.financial_suspended ? (
                <button className="btn btn-danger" disabled={busy} onClick={() => setConfirm("financial")}>
                  Suspend financial operations
                </button>
              ) : (
                <button className="btn" disabled={busy}
                  onClick={() => act("/operations/emergency/resume", "financial")}>
                  Resume financial operations (owner)
                </button>
              )}
            </div>
            <p className="muted">
              Stops compose the existing machinery — P-10 security mode,
              P-08 business pauses, P-04/P-05 stops. Resuming is an
              explicit owner act; the system never restarts itself.
            </p>
          </>
        ) : null}
      </Panel>
      {confirm ? (
        <ConfirmationDialog
          open
          title={confirm === "global" ? "Trigger the global emergency stop?" : "Suspend financial operations?"}
          body={
            confirm === "global"
              ? "All autonomous execution halts via P-10's emergency mode. Running workflows pause; nothing new starts until the owner resumes."
              : "Financial execution suspends via P-10; non-financial work continues. The owner resumes explicitly."
          }
          confirmLabel={confirm === "global" ? "Emergency stop" : "Suspend financial"}
          danger
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            const scope = confirm;
            setConfirm(null);
            void act("/operations/emergency/stop", scope);
          }}
        />
      ) : null}
    </>
  );
}

function ReportsTab(): React.ReactElement {
  const reports = useApi<{ items: ReportRow[]; total: number }>(
    "/operations/reports", 30000);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const generate = async () => {
    setBusy(true);
    try {
      await api("/operations/reports", {
        method: "POST",
        body: { kind: "daily" },
      });
      setNote("Report generated from live operations data.");
      reports.reload();
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Panel title="Operational Reports">
        <button className="btn" disabled={busy} onClick={generate}>
          Generate daily operations report
        </button>
        {note ? <p role="status">{note}</p> : null}
        <p className="muted">
          Reports are computed from recorded operations data at
          generation time — figures are never projected or estimated.
        </p>
      </Panel>
      <Panel title="Generated reports">
        {reports.loading && !reports.data ? <LoadingState label="Loading reports…" /> : null}
        {reports.error ? <ErrorState error={reports.error} onRetry={reports.reload} /> : null}
        {reports.data ? (
          <DataTable
            columns={[
              { key: "title", label: "Title" }, { key: "type", label: "Type" },
              { key: "generated", label: "Generated" },
            ]}
            rows={reports.data.items.map((r) => ({
              title: r.title, type: r.kind,
              generated: formatDateTime(r.created_at),
            }))}
            emptyTitle="No reports yet"
            emptyDetail="Generate the first operations summary above."
          />
        ) : null}
      </Panel>
    </>
  );
}
