import React, { useState } from "react";
import { ApiError, api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import { DevicesPanel, RecoveryCodesPanel } from "./IdentityDevices";
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

interface SecuritySummary {
  mode: string;
  financial_suspension: boolean;
  active_sessions: number;
  active_agents: number;
  pending_approvals: number;
  open_alerts: number;
  audit_chain: { ok: boolean; chain_length: number; unsealed_events: number };
  incidents_by_status: Record<string, number>;
  alerts_by_status: Record<string, number>;
  source: string;
}

interface SecAlert {
  id: string;
  rule: string;
  severity: string;
  subject: string;
  detail: string;
  status: string;
  created_at: string;
}

interface SecIncident {
  id: string;
  title: string;
  category: string;
  severity: string;
  status: string;
  created_at: string;
}

interface SessionRow {
  id?: string;
  session_id?: string;
  principal?: string;
  principal_id?: string;
  device_id?: string | null;
  created_at?: string;
  last_seen_at?: string;
  status?: string;
  [key: string]: unknown;
}

/**
 * §15 Security & Governance Center. Emergency controls (§15.5) POST to
 * P-10 and the displayed state is ALWAYS re-read from the backend —
 * the UI never claims an emergency action succeeded from local state.
 */
export function SecurityView(): React.ReactElement {
  const summary = useApi<SecuritySummary>("/dashboard/security/summary", 20000);
  const alerts = useApi<SecAlert[]>("/security/alerts?limit=100", 30000);
  const incidents = useApi<SecIncident[]>("/security/incidents?limit=100", 30000);
  const sessions = useApi<SessionRow[]>("/security/auth/sessions", 30000);
  const [confirmMode, setConfirmMode] = useState<string | null>(null);
  const [confirmSuspension, setConfirmSuspension] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<string | null>(null);

  const applyMode = async (mode: string) => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await api<{ mode: string }>("/security/emergency/mode", {
        method: "POST",
        body: { mode, reason: reason || `set from Command Center` },
      });
      // The mode shown comes from P-10's response, then the summary is
      // re-read so the panel reflects the backend's own status endpoint.
      setNotice(`Backend confirmed security mode: ${result.data.mode}`);
      setConfirmMode(null);
      setReason("");
      summary.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      setConfirmMode(null);
    } finally {
      setBusy(false);
    }
  };

  const applySuspension = async (suspended: boolean) => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await api<{ financial_suspension: boolean }>(
        "/security/emergency/financial-suspension",
        { method: "POST", body: { suspended, reason: reason || "set from Command Center" } },
      );
      setNotice(
        `Backend confirmed financial suspension: ${result.data.financial_suspension ? "ACTIVE" : "lifted"}`,
      );
      setConfirmSuspension(null);
      setReason("");
      summary.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      setConfirmSuspension(null);
    } finally {
      setBusy(false);
    }
  };

  const setAlertStatus = async (id: string, status: string) => {
    setActionError(null);
    try {
      await api(`/security/alerts/${id}/status`, { method: "POST", body: { status } });
      alerts.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const revokeSession = async (id: string) => {
    setActionError(null);
    try {
      await api(`/security/auth/sessions/${id}/revoke`, { method: "POST" });
      sessions.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const verifyAudit = async () => {
    setAuditResult(null);
    try {
      const result = await api<{ ok: boolean; checked: number; chain_length: number }>(
        "/security/audit/verify",
      );
      setAuditResult(
        `Audit hash chain verification: ${result.data.ok ? "OK" : "MISMATCH"} — ` +
          `${result.data.checked} events checked, chain length ${result.data.chain_length}. ` +
          "The chain is tamper-EVIDENT, not tamper-proof (P-10).",
      );
    } catch (err) {
      setAuditResult(err instanceof ApiError ? err.message : String(err));
    }
  };

  const data = summary.data;
  return (
    <div className="view">
      <PageHeader
        title="Security & Governance"
        subtitle="P-10 posture — the frontend displays and requests; P-10 decides and enforces"
        actions={<FreshnessBar updatedAt={summary.updatedAt} />}
      />
      {summary.loading && !data ? <LoadingState label="Loading security posture…" /> : null}
      {summary.error ? <ErrorState error={summary.error} onRetry={summary.reload} /> : null}
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}

      {data ? (
        <Panel title="Security overview" meta={data.source}>
          <dl className="stat-row">
            <div><dt>Security mode</dt><dd><StatusBadge value={data.mode} /></dd></div>
            <div>
              <dt>Financial suspension</dt>
              <dd>{data.financial_suspension ? "ACTIVE" : "Not suspended"}</dd>
            </div>
            <div><dt>Active sessions</dt><dd className="num">{data.active_sessions}</dd></div>
            <div><dt>Active agents</dt><dd className="num">{data.active_agents}</dd></div>
            <div><dt>Pending approvals</dt><dd className="num">{data.pending_approvals}</dd></div>
            <div><dt>Open alerts</dt><dd className="num">{data.open_alerts}</dd></div>
            <div>
              <dt>Audit chain</dt>
              <dd>
                {data.audit_chain.ok ? "Verified OK" : "CHECK FAILED"} · length{" "}
                {data.audit_chain.chain_length} · {data.audit_chain.unsealed_events} unsealed
              </dd>
            </div>
          </dl>
          <button type="button" className="btn" onClick={() => void verifyAudit()}>
            Verify audit chain now
          </button>
          {auditResult ? <p className="muted" role="status">{auditResult}</p> : null}
        </Panel>
      ) : null}

      <Panel
        title="Emergency controls"
        meta="P-10 governed — state shown only after backend confirmation"
      >
        <p className="muted">
          These controls are deliberately separated from ordinary navigation. Each one asks
          for confirmation, sends the request to P-10, and this page then re-reads the
          confirmed state. If the backend refuses or is unreachable, nothing here pretends
          the action happened.
        </p>
        <label className="field">
          <span>Reason (recorded by P-10)</span>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this control being used?"
          />
        </label>
        <div className="card-actions emergency-actions">
          <button type="button" className="btn" onClick={() => setConfirmMode("safe_mode")} disabled={busy}>
            Enter safe mode
          </button>
          <button type="button" className="btn btn-danger" onClick={() => setConfirmMode("emergency_stop")} disabled={busy}>
            Emergency stop
          </button>
          <button type="button" className="btn" onClick={() => setConfirmMode("normal")} disabled={busy}>
            Resume normal mode (after verification)
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => setConfirmSuspension(true)}
            disabled={busy}
          >
            Suspend financial execution
          </button>
          <button type="button" className="btn" onClick={() => setConfirmSuspension(false)} disabled={busy}>
            Lift financial suspension
          </button>
        </div>
        <p className="muted">
          Current confirmed mode: <strong>{data ? data.mode : "unknown"}</strong> · financial
          suspension: <strong>{data ? (data.financial_suspension ? "ACTIVE" : "not suspended") : "unknown"}</strong>
        </p>
      </Panel>

      <div className="two-col">
        <Panel title="Security alerts" meta="deterministic rules over the audit trail (P-10)">
          {alerts.loading && !alerts.data ? <LoadingState /> : null}
          {alerts.error ? <p className="error-text">{alerts.error.message}</p> : null}
          {alerts.data && alerts.data.length === 0 ? (
            <EmptyState title="No security alerts" detail="No alert rules have fired. Alerts are generated deterministically by P-10 from the audit trail — never by a model." />
          ) : null}
          <ul className="plain-list">
            {(alerts.data ?? []).map((a) => (
              <li key={a.id} className="plain-item">
                <StatusBadge value={a.severity} />
                <div className="plain-body">
                  <strong>{a.subject}</strong>
                  <p className="muted">{a.detail}</p>
                  <p className="muted">rule: {a.rule} · {formatDateTime(a.created_at)} · status: {a.status}</p>
                  {a.status === "open" ? (
                    <span className="card-actions">
                      <button type="button" className="btn btn-small" onClick={() => void setAlertStatus(a.id, "acknowledged")}>
                        Acknowledge
                      </button>
                      <button type="button" className="btn btn-small" onClick={() => void setAlertStatus(a.id, "closed")}>
                        Close
                      </button>
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Incidents & sessions">
          <h3 className="subhead">Incidents</h3>
          {incidents.data && incidents.data.length === 0 ? (
            <p className="muted">No incidents recorded.</p>
          ) : null}
          <ul className="plain-list">
            {(incidents.data ?? []).map((inc) => (
              <li key={inc.id} className="plain-item">
                <StatusBadge value={inc.severity} />
                <div className="plain-body">
                  <strong>{inc.title}</strong>
                  <p className="muted">{inc.category} · {inc.status} · {formatDateTime(inc.created_at)}</p>
                </div>
              </li>
            ))}
          </ul>
          <h3 className="subhead">Active sessions</h3>
          {sessions.data && sessions.data.length === 0 ? (
            <p className="muted">No active sessions reported by P-10.</p>
          ) : null}
          <DataTable
            columns={[
              { key: "id", label: "Session" },
              { key: "principal", label: "Principal" },
              { key: "device", label: "Device" },
              { key: "created", label: "Created" },
              { key: "action", label: "" },
            ]}
            rows={(sessions.data ?? []).map((s) => {
              const id = String(s.id ?? s.session_id ?? "");
              return {
                id: <span className="mono">{id.slice(0, 12)}…</span>,
                principal: String(s.principal ?? s.principal_id ?? "—"),
                device: s.device_id ? (
                  <span className="mono">{String(s.device_id).slice(0, 8)}…</span>
                ) : (
                  <span className="muted">unbound</span>
                ),
                created: formatDateTime(typeof s.created_at === "string" ? s.created_at : null),
                action: id ? (
                  <button type="button" className="btn btn-small" onClick={() => void revokeSession(id)}>
                    Revoke
                  </button>
                ) : null,
              };
            })}
            emptyTitle="No sessions"
            emptyDetail="P-10 reported no active sessions."
          />
        </Panel>
      </div>

      <DevicesPanel />

      <RecoveryCodesPanel />

      <Panel title="Permission management" meta="inspection via P-10">
        <p className="muted">
          Identities, roles and per-agent permissions are inspected in the Agents view
          (per-agent permissions) and via P-10's identity endpoints. All changes execute
          through P-10 — this console holds no permission state of its own. Secret vault
          status (metadata only, values never leave P-10's broker) is reported on the
          Operations view.
        </p>
      </Panel>

      <ConfirmationDialog
        open={confirmMode !== null}
        title={`Set security mode to ${confirmMode ?? ""}?`}
        body={
          <p>
            This sends a mode change to P-10's emergency control. The page will display the
            new mode only after P-10 confirms it. Mode requested:{" "}
            <strong>{confirmMode}</strong>.
          </p>
        }
        confirmLabel="Send to P-10"
        danger={confirmMode === "emergency_stop"}
        busy={busy}
        onConfirm={() => confirmMode && void applyMode(confirmMode)}
        onCancel={() => setConfirmMode(null)}
      />
      <ConfirmationDialog
        open={confirmSuspension !== null}
        title={confirmSuspension ? "Suspend financial execution?" : "Lift financial suspension?"}
        body={
          <p>
            This changes P-07 financial execution availability through P-10's emergency
            control. Confirmation comes from the backend response — never from this dialog.
          </p>
        }
        confirmLabel={confirmSuspension ? "Suspend execution" : "Lift suspension"}
        danger={confirmSuspension === true}
        busy={busy}
        onConfirm={() => confirmSuspension !== null && void applySuspension(confirmSuspension)}
        onCancel={() => setConfirmSuspension(null)}
      />
    </div>
  );
}
