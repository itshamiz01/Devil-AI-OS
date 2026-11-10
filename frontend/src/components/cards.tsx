import React, { useState } from "react";
import { ApiError, api } from "../lib/api";
import { formatDateTime, formatMoney, humanize } from "../lib/format";
import { navigate } from "../lib/router";
import { usePrefs } from "../lib/store";
import type { ActivityItem, Approval } from "../lib/types";
import { ConfirmationDialog, StatusBadge } from "./ui";

// -------------------------------------------------------------- AgentCard
export interface AgentRow {
  id: string;
  name: string;
  role: string;
  status: string;
  parent_agent_id?: string | null;
  business_ref?: string | null;
  model_profile?: string | null;
  last_activity_at?: string | null;
  agent_type?: string | null;
}

export function AgentCard({ agent }: { agent: AgentRow }): React.ReactElement {
  return (
    <article className="entity-card">
      <header>
        <h3>{agent.name}</h3>
        <StatusBadge value={agent.status} />
      </header>
      <dl className="entity-fields">
        <div><dt>Role</dt><dd>{agent.role}</dd></div>
        <div><dt>ID</dt><dd className="mono">{agent.id}</dd></div>
        {agent.business_ref ? <div><dt>Business</dt><dd className="mono">{agent.business_ref}</dd></div> : null}
        {agent.model_profile ? <div><dt>Model profile</dt><dd>{agent.model_profile}</dd></div> : null}
        <div><dt>Last activity</dt><dd>{formatDateTime(agent.last_activity_at)}</dd></div>
      </dl>
      <button type="button" className="btn btn-small" onClick={() => navigate("agents", agent.id)}>
        Inspect agent
      </button>
    </article>
  );
}

// ----------------------------------------------------------- BusinessCard
export interface BusinessRow {
  id: string;
  name: string;
  category: string;
  status: string;
  risk_classification?: string | null;
  is_fixture?: boolean;
  deployment_state?: string;
  created_at?: string;
}

export function BusinessCard({ business }: { business: BusinessRow }): React.ReactElement {
  return (
    <article className="entity-card">
      <header>
        <h3>{business.name}</h3>
        <StatusBadge value={business.status} />
      </header>
      <dl className="entity-fields">
        <div><dt>Category</dt><dd>{business.category}</dd></div>
        <div><dt>ID</dt><dd className="mono">{business.id}</dd></div>
        {business.risk_classification ? (
          <div><dt>Risk</dt><dd>{humanize(business.risk_classification)}</dd></div>
        ) : null}
        {business.is_fixture ? (
          <div><dt>Data kind</dt><dd><span className="fixture-tag">FIXTURE — labelled test data</span></dd></div>
        ) : null}
        <div><dt>Deployment</dt><dd>{humanize(business.deployment_state)}</dd></div>
      </dl>
      <button type="button" className="btn btn-small" onClick={() => navigate("businesses", business.id)}>
        Open business
      </button>
    </article>
  );
}

// -------------------------------------------------------- OpportunityCard
export interface OpportunityRow {
  id: string;
  name: string;
  category: string;
  target_customer?: string;
  problem_statement?: string;
  revenue_model?: string;
  status: string;
  validation_level?: number;
  last_researched_at?: string | null;
}

export function OpportunityCard({ opportunity }: { opportunity: OpportunityRow }): React.ReactElement {
  return (
    <article className="entity-card">
      <header>
        <h3>{opportunity.name}</h3>
        <StatusBadge value={opportunity.status} />
      </header>
      <dl className="entity-fields">
        <div><dt>Category</dt><dd>{opportunity.category}</dd></div>
        {opportunity.target_customer ? <div><dt>Target customer</dt><dd>{opportunity.target_customer}</dd></div> : null}
        {opportunity.revenue_model ? <div><dt>Revenue model</dt><dd>{opportunity.revenue_model}</dd></div> : null}
        <div>
          <dt>Validation level</dt>
          <dd>Level {opportunity.validation_level ?? 0} of 5 — evidence-based, not an estimate</dd>
        </div>
        <div><dt>Last researched</dt><dd>{formatDateTime(opportunity.last_researched_at)}</dd></div>
      </dl>
      <button type="button" className="btn btn-small" onClick={() => navigate("opportunities", opportunity.id)}>
        Open opportunity
      </button>
    </article>
  );
}

// --------------------------------------------------------------- TaskCard
export interface TaskRow {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  category?: string;
  priority?: number;
  assigned_agent_id?: string | null;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  progress?: Record<string, unknown>;
  error?: Record<string, unknown> | null;
}

export function TaskCard({ task }: { task: TaskRow }): React.ReactElement {
  const progressNote =
    task.progress && typeof task.progress["note"] === "string"
      ? (task.progress["note"] as string)
      : null;
  return (
    <article className="entity-card">
      <header>
        <h3>{task.name}</h3>
        <StatusBadge value={task.status} />
      </header>
      <dl className="entity-fields">
        <div><dt>Task ID</dt><dd className="mono">{task.id}</dd></div>
        {task.assigned_agent_id ? <div><dt>Agent</dt><dd className="mono">{task.assigned_agent_id}</dd></div> : null}
        <div><dt>Started</dt><dd>{formatDateTime(task.started_at)}</dd></div>
        <div>
          <dt>Completed</dt>
          <dd>{task.completed_at ? formatDateTime(task.completed_at) : "Not completed"}</dd>
        </div>
        {progressNote ? <div><dt>Latest progress</dt><dd>{progressNote}</dd></div> : null}
        {task.error ? (
          <div><dt>Error</dt><dd className="error-text">{String(task.error["message"] ?? "see task detail")}</dd></div>
        ) : null}
      </dl>
    </article>
  );
}

// ----------------------------------------------------------- ApprovalCard
/**
 * §18.2/§18.4: the card shows the EXACT parameters and their hash. The
 * decision is sent to the backend's governed endpoint; the card reports
 * success only after the backend confirms (its response carries the new
 * status), and a parameter/hash mismatch in the response is surfaced.
 */
export function ApprovalCard({
  approval,
  onDecided,
}: {
  approval: Approval;
  onDecided: () => void;
}): React.ReactElement {
  const { prefs } = usePrefs();
  const [confirming, setConfirming] = useState<"approve" | "reject" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const decide = async (approve: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api<Approval>(`/approvals/${approval.id}/decision`, {
        method: "POST",
        body: { approve, notes: approve ? "Approved from Command Center" : "Rejected from Command Center" },
      });
      // Success is claimed ONLY from the backend's confirmed response,
      // and only if it still binds the exact parameters shown (§18.4).
      if (result.data.parameters_hash !== approval.parameters_hash) {
        setError(
          "The backend's decision response carries different parameters than shown. " +
            "Treat this decision as NOT confirmed and re-open the request.",
        );
        setDone(null);
      } else {
        setDone(result.data.status);
      }
      setConfirming(null);
      onDecided();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      setConfirming(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="entity-card approval-card">
      <header>
        <h3>{approval.action}</h3>
        <StatusBadge value={approval.status} />
      </header>
      <dl className="entity-fields">
        <div><dt>Request ID</dt><dd className="mono">{approval.id}</dd></div>
        <div>
          <dt>Requested by</dt>
          <dd>{approval.requesting_principal_type}:{approval.requesting_principal_id}</dd>
        </div>
        {approval.resource ? <div><dt>Resource</dt><dd className="mono">{approval.resource}</dd></div> : null}
        <div><dt>Risk</dt><dd><StatusBadge value={approval.risk_classification} /></dd></div>
        {approval.reason ? <div><dt>Reason</dt><dd>{approval.reason}</dd></div> : null}
        {approval.requested_permissions.length > 0 ? (
          <div><dt>Permissions</dt><dd>{approval.requested_permissions.join(", ")}</dd></div>
        ) : null}
        <div><dt>Requested</dt><dd>{formatDateTime(approval.created_at, prefs.timezone)}</dd></div>
        <div>
          <dt>Expires</dt>
          <dd>{approval.expires_at ? formatDateTime(approval.expires_at, prefs.timezone) : "No expiry set"}</dd>
        </div>
        <div>
          <dt>Parameters hash</dt>
          <dd className="mono hash">{approval.parameters_hash}</dd>
        </div>
      </dl>
      <div className="params-block">
        <h4>Exact parameters</h4>
        <pre className="params-json">{JSON.stringify(approval.parameters, null, 2)}</pre>
      </div>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      {done ? (
        <p className="ok-text" role="status">
          Backend confirmed: status is now {humanize(done)}.
        </p>
      ) : approval.status === "pending" ? (
        <div className="card-actions">
          <button type="button" className="btn btn-primary" onClick={() => setConfirming("approve")} disabled={busy}>
            Approve once
          </button>
          <button type="button" className="btn btn-danger" onClick={() => setConfirming("reject")} disabled={busy}>
            Reject
          </button>
        </div>
      ) : null}
      <ConfirmationDialog
        open={confirming !== null}
        title={confirming === "approve" ? "Approve this request?" : "Reject this request?"}
        body={
          <div>
            <p>
              Action <strong>{approval.action}</strong> requested by{" "}
              {approval.requesting_principal_type}:{approval.requesting_principal_id}.
            </p>
            <p>
              The decision binds parameters with hash{" "}
              <span className="mono">{approval.parameters_hash.slice(0, 16)}…</span>. If the
              parameters changed since the request, the backend will refuse the decision.
            </p>
          </div>
        }
        confirmLabel={confirming === "approve" ? "Approve once" : "Reject"}
        danger={confirming === "reject"}
        busy={busy}
        onConfirm={() => void decide(confirming === "approve")}
        onCancel={() => setConfirming(null)}
      />
    </article>
  );
}

// ----------------------------------------------------------- ActivityFeed
export function ActivityFeed({ items }: { items: ActivityItem[] }): React.ReactElement {
  if (items.length === 0) {
    return (
      <p className="muted">
        No persisted events yet. The feed shows real system events only — an empty feed
        means nothing has happened, not that data is missing.
      </p>
    );
  }
  return (
    <ol className="activity-feed">
      {items.map((item) => (
        <li key={item.event_id} className="activity-item">
          <StatusBadge value={item.severity} />
          <div className="activity-body">
            <span className="activity-title">{humanize(item.event_type)}</span>
            <span className="activity-meta">
              {item.source} · {formatDateTime(item.created_at)}
              {item.task_id ? ` · task ${item.task_id}` : ""}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

export { formatMoney };
