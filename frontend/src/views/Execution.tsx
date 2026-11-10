import React, { useState } from "react";
import { TaskCard, type TaskRow } from "../components/cards";
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

interface ExecutionSummary {
  requests_by_status: Record<string, number>;
  tasks_by_status: Record<string, number>;
  source: string;
}

interface ExecutionRequest {
  id: string;
  tool_name: string;
  action_name: string;
  status: string;
  agent_id: string;
  business_ref: string | null;
  risk_level: number;
  created_at: string;
  error?: Record<string, unknown> | null;
}

/**
 * §13 Execution Center + §17 Autonomous Operations: what the engines are
 * doing right now, with the transparency states kept distinct — planned,
 * requested, authorized, executing, completed, verified, failed are
 * different things and are never blurred (§17.4).
 */
export function ExecutionView(): React.ReactElement {
  const summary = useApi<ExecutionSummary>("/dashboard/execution/summary", 15000);
  const tasks = useApi<TaskRow[]>("/tasks?limit=100", 15000);
  const requests = useApi<ExecutionRequest[]>("/execution/requests?limit=100", 15000);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const taskControl = async (task: TaskRow, action: "pause" | "resume" | "cancel" | "retry") => {
    setActionError(null);
    setNotice(null);
    try {
      const result = await api<TaskRow>(`/tasks/${task.id}/${action}`, { method: "POST" });
      setNotice(`Task “${task.name}”: backend confirmed status ${result.data.status}.`);
      tasks.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    }
  };

  const failed = (tasks.data ?? []).filter((t) => t.status === "failed");
  const running = (tasks.data ?? []).filter((t) =>
    ["running", "in_progress"].includes(t.status.toLowerCase()),
  );

  return (
    <div className="view">
      <PageHeader
        title="Execution Center"
        subtitle="Tasks and tool executions across all businesses — status from the engines, never assumed"
        actions={<FreshnessBar updatedAt={tasks.updatedAt} />}
      />
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}

      {summary.data ? (
        <Panel title="Execution overview" meta={summary.data.source}>
          <h3 className="subhead">Execution requests by status (P-05)</h3>
          <dl className="stat-row num">
            {Object.entries(summary.data.requests_by_status).map(([s, c]) => (
              <div key={s}><dt>{s}</dt><dd>{c}</dd></div>
            ))}
          </dl>
          <h3 className="subhead">Tasks by status (P-01)</h3>
          <dl className="stat-row num">
            {Object.entries(summary.data.tasks_by_status).map(([s, c]) => (
              <div key={s}><dt>{s}</dt><dd>{c}</dd></div>
            ))}
          </dl>
        </Panel>
      ) : null}

      <Panel title="Live operations" meta="§17: executing work, with approval dependencies visible">
        {running.length === 0 ? (
          <p className="muted">
            No task is executing right now. A long-running task would stay listed here with
            its real status — it is never marked completed early (Scenario 14).
          </p>
        ) : (
          <div className="card-grid">
            {running.map((t) => (
              <TaskCard key={t.id} task={t} />
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Tasks" meta="controls call the real P-01 task endpoints">
        {tasks.loading && !tasks.data ? <LoadingState label="Loading tasks…" /> : null}
        {tasks.error ? <ErrorState error={tasks.error} onRetry={tasks.reload} /> : null}
        {tasks.data && tasks.data.length === 0 ? (
          <EmptyState
            title="No tasks yet"
            detail="No work has been submitted to the task manager. Tasks appear here when missions, research or executions create them."
          />
        ) : null}
        <ul className="plain-list">
          {(tasks.data ?? []).map((t) => (
            <li key={t.id} className="plain-item">
              <StatusBadge value={t.status} />
              <div className="plain-body">
                <strong>{t.name}</strong>
                <p className="muted">
                  {t.id} · created {formatDateTime(t.created_at)} · started{" "}
                  {formatDateTime(t.started_at)} · completed {formatDateTime(t.completed_at)}
                </p>
                {t.error ? (
                  <p className="error-text">
                    Failure: {String(t.error["message"] ?? "see task record")} — retry is
                    offered only where the backend accepts it; dangerous or non-idempotent
                    work is never auto-retried (§13.5).
                  </p>
                ) : null}
                <span className="card-actions">
                  {["queued", "created", "pending"].includes(t.status.toLowerCase()) ||
                  ["running", "in_progress"].includes(t.status.toLowerCase()) ? (
                    <button type="button" className="btn btn-small" onClick={() => void taskControl(t, "pause")}>
                      Pause
                    </button>
                  ) : null}
                  {t.status.toLowerCase() === "paused" ? (
                    <button type="button" className="btn btn-small" onClick={() => void taskControl(t, "resume")}>
                      Resume
                    </button>
                  ) : null}
                  {!["completed", "cancelled", "failed"].includes(t.status.toLowerCase()) ? (
                    <button type="button" className="btn btn-small" onClick={() => void taskControl(t, "cancel")}>
                      Cancel
                    </button>
                  ) : null}
                  {t.status.toLowerCase() === "failed" ? (
                    <button type="button" className="btn btn-small" onClick={() => void taskControl(t, "retry")}>
                      Retry
                    </button>
                  ) : null}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Execution requests" meta="P-05 tool executions with risk levels">
        {requests.data && requests.data.length === 0 ? (
          <EmptyState title="No execution requests" detail="No tool executions have been requested through P-05 yet." />
        ) : null}
        <ul className="plain-list">
          {(requests.data ?? []).map((r) => (
            <li key={r.id} className="plain-item">
              <StatusBadge value={r.status} />
              <div className="plain-body">
                <strong>
                  {r.tool_name} · {r.action_name}
                </strong>
                <p className="muted">
                  agent <span className="mono">{r.agent_id}</span>
                  {r.business_ref ? ` · business ${r.business_ref}` : ""} · risk level{" "}
                  {r.risk_level} (0–3, P-10 broker scale) · {formatDateTime(r.created_at)}
                </p>
              </div>
            </li>
          ))}
        </ul>
        {failed.length > 0 ? (
          <p className="muted">
            {failed.length} failed task(s) in the current list — failure stage, error and
            retry eligibility are on each task record above.
          </p>
        ) : null}
      </Panel>
    </div>
  );
}
