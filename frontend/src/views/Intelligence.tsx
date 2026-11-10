import React, { useState } from "react";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { ApiError, api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";

interface Mission {
  id: string;
  text: string;
  creator_type: string;
  creator_id: string;
  status: string;
  mode: string;
  matched_template: string | null;
  created_at?: string;
}

interface Plan {
  id: string;
  mission_id: string;
  status: string;
  summary?: string;
  steps?: { id: string; description?: string; action?: string; status?: string }[];
  [key: string]: unknown;
}

interface Decision {
  id: string;
  kind?: string;
  summary?: string;
  rationale?: string;
  created_at?: string;
  [key: string]: unknown;
}

interface ModelsStatus {
  mode: string;
  providers: Record<string, { available: boolean; detail: string; models: string[] }>;
  configured_profiles: unknown[];
  planner_default: string;
}

/**
 * §7 Master Intelligence interface. Instructions become missions on the
 * real P-02 engine. There is NO streaming in the backend, so none is
 * simulated: responses are the engine's actual records (missions, plans,
 * explanations, decisions). A plan is shown as a proposal — never as
 * proof that an operation occurred (§7.3).
 */
export function IntelligenceView(): React.ReactElement {
  const missions = useApi<Mission[]>("/missions?limit=50", 20000);
  const models = useApi<ModelsStatus>("/models/status", 60000);
  const decisions = useApi<Decision[]>("/decisions?limit=25", 30000);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedMission, setSelectedMission] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);

  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api<Mission>("/missions", { method: "POST", body: { text: text.trim() } });
      setNotice(
        `Mission created: ${result.data.id} (status ${result.data.status}, mode ${result.data.mode}). ` +
          "Planning and execution happen on the engine; watch Missions and Execution for real progress.",
      );
      setText("");
      missions.reload();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  const makePlan = async (missionId: string) => {
    setError(null);
    setExplanation(null);
    try {
      const result = await api<Plan>(`/missions/${missionId}/plan`, { method: "POST" });
      setPlan(result.data);
      setSelectedMission(missionId);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    }
  };

  const explain = async (planId: string) => {
    try {
      const result = await api<{ explanation?: string } | string>(`/plans/${planId}/explanation`);
      setExplanation(typeof result.data === "string" ? result.data : (result.data.explanation ?? JSON.stringify(result.data)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  return (
    <div className="view">
      <PageHeader
        title="Master Intelligence"
        subtitle="Give instructions, inspect plans and decisions — the engine's records, not a chat illusion"
      />
      {models.data ? (
        <Panel title="AI provider status" meta="P-02 model router">
          <dl className="stat-row">
            <div><dt>Mode</dt><dd>{models.data.mode}</dd></div>
            {Object.entries(models.data.providers).map(([name, p]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>
                  <StatusBadge value={p.available ? "available" : "unavailable"} />{" "}
                  <span className="muted">{p.detail}</span>
                </dd>
              </div>
            ))}
          </dl>
          <p className="muted">{models.data.planner_default}</p>
          <p className="muted">
            Streaming responses are NOT supported by the backend — this interface therefore
            shows engine records (missions, plans, decisions) instead of simulating a stream.
          </p>
        </Panel>
      ) : null}

      <Panel title="New instruction">
        <label className="field">
          <span>Instruction to the Master Intelligence Engine</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={8000}
            placeholder="e.g. Research the market for AI-generated short-form video services"
            aria-label="Instruction"
          />
        </label>
        {error ? <p className="error-text" role="alert">{error}</p> : null}
        {notice ? <p className="ok-text" role="status">{notice}</p> : null}
        <button type="button" className="btn btn-primary" onClick={() => void submit()} disabled={busy || !text.trim()}>
          {busy ? "Submitting…" : "Create mission"}
        </button>
        <p className="muted">
          Submitting creates a mission (a task record). Sensitive follow-on actions still
          require P-10 approvals — an instruction here never bypasses them.
        </p>
      </Panel>

      <div className="two-col">
        <Panel title="Missions">
          {missions.loading && !missions.data ? <LoadingState /> : null}
          {missions.error ? <ErrorState error={missions.error} onRetry={missions.reload} /> : null}
          {missions.data && missions.data.length === 0 ? (
            <EmptyState title="No missions yet" detail="No instructions have been submitted to the Master Intelligence Engine." />
          ) : null}
          <ul className="plain-list">
            {(missions.data ?? []).map((m) => (
              <li key={m.id} className="plain-item">
                <StatusBadge value={m.status} />
                <div className="plain-body">
                  <strong>{m.text}</strong>
                  <p className="muted">
                    {m.id} · mode {m.mode} · by {m.creator_type}:{m.creator_id}
                    {m.matched_template ? ` · template ${m.matched_template}` : ""} ·{" "}
                    {formatDateTime(m.created_at)}
                  </p>
                  <span className="card-actions">
                    <button type="button" className="btn btn-small" onClick={() => void makePlan(m.id)}>
                      Create plan
                    </button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Plan & decisions">
          {plan ? (
            <div>
              <h3 className="subhead">
                Plan for mission {selectedMission} — <StatusBadge value={plan.status} />
              </h3>
              <p className="muted">
                A plan is a proposal recorded by the engine. It is not proof that any
                operation occurred (§7.3); execution records live in Execution.
              </p>
              {plan.summary ? <p>{plan.summary}</p> : null}
              {plan.steps && plan.steps.length > 0 ? (
                <ol className="plain-list">
                  {plan.steps.map((s) => (
                    <li key={s.id} className="plain-item">
                      <StatusBadge value={s.status ?? "pending"} />
                      <div className="plain-body">
                        <span>{s.description ?? s.action ?? s.id}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : null}
              <button type="button" className="btn btn-small" onClick={() => void explain(plan.id)}>
                View explanation
              </button>
              {explanation ? <p className="explanation">{explanation}</p> : null}
            </div>
          ) : (
            <p className="muted">Select “Create plan” on a mission to inspect its plan here.</p>
          )}
          <h3 className="subhead">Recent decisions</h3>
          {decisions.data && decisions.data.length === 0 ? (
            <p className="muted">No decisions recorded yet.</p>
          ) : null}
          <ul className="plain-list">
            {(decisions.data ?? []).slice(0, 10).map((d) => (
              <li key={d.id} className="plain-item">
                <div className="plain-body">
                  <strong>{String(d.kind ?? "decision")}</strong>
                  <p className="muted">{String(d.summary ?? d.rationale ?? "")}</p>
                  <p className="muted">{formatDateTime(d.created_at)}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
