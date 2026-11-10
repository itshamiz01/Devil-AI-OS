import React, { useState } from "react";
import { AgentCard, type AgentRow } from "../components/cards";
import {
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
import { navigate } from "../lib/router";

interface AgentsSummary {
  total: number;
  by_status: Record<string, number>;
  creation_requests_by_status: Record<string, number>;
  source: string;
}

interface CreationRequest {
  id: string;
  requester_type: string;
  requester_id: string;
  requested_role: string;
  business_ref: string | null;
  justification: string | null;
  status: string;
  created_at: string;
}

export function AgentsView(): React.ReactElement {
  const summary = useApi<AgentsSummary>("/dashboard/agents/summary", 30000);
  const agents = useApi<AgentRow[]>("/agents?limit=200", 30000);
  const requests = useApi<CreationRequest[]>("/agent-factory/requests?limit=100");
  const [actionError, setActionError] = useState<string | null>(null);

  const decideRequest = async (id: string, decision: "approve" | "reject") => {
    setActionError(null);
    try {
      await api(`/agent-factory/requests/${id}/${decision}`, {
        method: "POST",
        body: { notes: `${decision}d from Command Center` },
      });
      requests.reload();
      summary.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    }
  };

  const byStatus = summary.data?.by_status ?? {};
  const pendingRequests = (requests.data ?? []).filter((r) => r.status === "pending");

  return (
    <div className="view">
      <PageHeader
        title="Agent Command Center"
        subtitle="Every agent AUTONOMUS operates — identity, assignment, permissions and lifecycle"
        actions={<FreshnessBar updatedAt={agents.updatedAt} />}
      />
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {summary.data ? (
        <Panel title="Agent overview" meta={summary.data.source}>
          <dl className="stat-row num">
            <div><dt>Total agents</dt><dd>{summary.data.total}</dd></div>
            {Object.entries(byStatus).map(([status, count]) => (
              <div key={status}><dt>{status}</dt><dd>{count}</dd></div>
            ))}
            <div><dt>Awaiting review</dt><dd>{pendingRequests.length}</dd></div>
          </dl>
        </Panel>
      ) : null}

      {agents.loading && !agents.data ? <LoadingState label="Loading agents…" /> : null}
      {agents.error ? <ErrorState error={agents.error} onRetry={agents.reload} /> : null}
      {agents.data && agents.data.length === 0 ? (
        <EmptyState
          title="No agents exist yet"
          detail="The Agent Factory has not created any agents. Agents are created through the governed P-04 factory (reuse-first, approval-gated) — none are invented for display."
        />
      ) : null}
      <div className="card-grid">
        {(agents.data ?? []).map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </div>

      {agents.data && agents.data.length > 0 ? (
        <Panel title="Agent hierarchy" meta="actual parent/child data only — nothing invented (§8.6)">
          <Hierarchy agents={agents.data} />
        </Panel>
      ) : null}

      <Panel title="Creation requests" meta="decided through P-04's governed endpoints">
        {requests.data && pendingRequests.length === 0 ? (
          <p className="muted">No creation requests are awaiting review.</p>
        ) : null}
        <ul className="plain-list">
          {pendingRequests.map((r) => (
            <li key={r.id} className="plain-item">
              <StatusBadge value={r.status} />
              <div className="plain-body">
                <strong>{r.requested_role}</strong>
                <p className="muted">
                  requested by {r.requester_type}:{r.requester_id}
                  {r.business_ref ? ` · business ${r.business_ref}` : ""} ·{" "}
                  {formatDateTime(r.created_at)}
                </p>
                {r.justification ? <p>{r.justification}</p> : null}
                <span className="card-actions">
                  <button type="button" className="btn btn-small btn-primary" onClick={() => void decideRequest(r.id, "approve")}>
                    Approve creation
                  </button>
                  <button type="button" className="btn btn-small btn-danger" onClick={() => void decideRequest(r.id, "reject")}>
                    Reject
                  </button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function Hierarchy({ agents }: { agents: AgentRow[] }): React.ReactElement {
  const byParent = new Map<string | null, AgentRow[]>();
  for (const a of agents) {
    const key = a.parent_agent_id ?? null;
    byParent.set(key, [...(byParent.get(key) ?? []), a]);
  }
  const renderLevel = (parent: string | null, depth: number): React.ReactNode => {
    const children = byParent.get(parent) ?? [];
    if (children.length === 0) return null;
    return (
      <ul className={depth === 0 ? "hierarchy" : undefined}>
        {children.map((a) => (
          <li key={a.id}>
            <button type="button" className="link-button" onClick={() => navigate("agents", a.id)}>
              {a.name}
            </button>{" "}
            <StatusBadge value={a.status} /> <span className="muted">{a.role}</span>
            {renderLevel(a.id, depth + 1)}
          </li>
        ))}
      </ul>
    );
  };
  return <>{renderLevel(null, 0)}</>;
}

// ------------------------------------------------------------ Agent detail
interface AgentDetail extends AgentRow {
  objective?: string | null;
  description?: string | null;
  created_at?: string;
  configuration_version?: number;
  security_classification?: string | null;
}

interface AgentPermissions {
  capabilities?: { capability?: string; name?: string; status?: string }[] | Record<string, unknown>;
  [key: string]: unknown;
}

export function AgentDetailView({ agentId }: { agentId: string }): React.ReactElement {
  const detail = useApi<AgentDetail>(`/agents/${agentId}`);
  const permissions = useApi<AgentPermissions>(`/agents/${agentId}/permissions`);
  const metrics = useApi<Record<string, unknown>>(`/agents/${agentId}/metrics`);
  const events = useApi<Record<string, unknown>[]>(`/agents/${agentId}/events?limit=25`);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const control = async (action: "suspend" | "resume" | "retire") => {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const result = await api<AgentDetail>(`/agents/${agentId}/${action}`, { method: "POST" });
      // Status shown comes from the backend's confirmed response (§28.3).
      setNotice(`Backend confirmed: agent status is now “${result.data.status}”.`);
      detail.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (detail.loading && !detail.data) return <LoadingState label="Loading agent…" />;
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const agent = detail.data;
  if (!agent) return <LoadingState />;

  return (
    <div className="view">
      <PageHeader
        title={agent.name}
        subtitle={`Agent ${agent.id}`}
        actions={
          <button type="button" className="btn" onClick={() => navigate("agents")}>
            Back to agents
          </button>
        }
      />
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}

      <Panel title="Identity">
        <dl className="entity-fields wide">
          <div><dt>Role</dt><dd>{agent.role}</dd></div>
          <div><dt>Status</dt><dd><StatusBadge value={agent.status} /></dd></div>
          <div><dt>Purpose / objective</dt><dd>{agent.objective ?? agent.description ?? "—"}</dd></div>
          <div><dt>Parent agent</dt><dd className="mono">{agent.parent_agent_id ?? "none (top-level)"}</dd></div>
          <div><dt>Assigned business</dt><dd className="mono">{agent.business_ref ?? "unassigned"}</dd></div>
          <div><dt>Model profile</dt><dd>{agent.model_profile ?? "default router profile"}</dd></div>
          <div><dt>Created</dt><dd>{formatDateTime(agent.created_at)}</dd></div>
          <div><dt>Last activity</dt><dd>{formatDateTime(agent.last_activity_at)}</dd></div>
          <div><dt>Configuration version</dt><dd>{agent.configuration_version ?? "—"}</dd></div>
          <div><dt>Security classification</dt><dd>{agent.security_classification ?? "—"}</dd></div>
        </dl>
        <div className="card-actions">
          {/* The backend's lifecycle calls suspend "pause" semantics: the UI
              labels controls with the backend's own state names. */}
          <button type="button" className="btn" onClick={() => void control("suspend")} disabled={busy}>
            Suspend agent
          </button>
          <button type="button" className="btn" onClick={() => void control("resume")} disabled={busy}>
            Resume agent
          </button>
          <button type="button" className="btn btn-danger" onClick={() => void control("retire")} disabled={busy}>
            Retire agent
          </button>
        </div>
        <p className="muted">
          Lifecycle changes execute through P-04 and are permission-checked by the backend;
          the status above updates only from the confirmed response.
        </p>
      </Panel>

      <div className="two-col">
        <Panel title="Permissions" meta="as granted by P-04/P-10 — changes go through approval">
          {permissions.loading ? <LoadingState /> : null}
          {permissions.error ? <p className="error-text">{permissions.error.message}</p> : null}
          {permissions.data ? (
            <pre className="params-json">{JSON.stringify(permissions.data, null, 2)}</pre>
          ) : null}
          <p className="muted">
            Permission changes are sensitive operations: they are requested and approved
            through the governed endpoints, never edited directly here.
          </p>
        </Panel>
        <Panel title="Performance & recent activity">
          {metrics.data ? (
            <pre className="params-json">{JSON.stringify(metrics.data, null, 2)}</pre>
          ) : (
            <p className="muted">No metrics recorded for this agent yet.</p>
          )}
          <h3 className="subhead">Recent events</h3>
          {events.data && events.data.length === 0 ? (
            <p className="muted">No events recorded.</p>
          ) : null}
          <ul className="plain-list">
            {(events.data ?? []).slice(0, 10).map((e, i) => (
              <li key={i} className="plain-item">
                <div className="plain-body">
                  <span className="mono">{String(e["event_type"] ?? e["type"] ?? "event")}</span>
                  <p className="muted">{formatDateTime(typeof e["created_at"] === "string" ? (e["created_at"] as string) : null)}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
