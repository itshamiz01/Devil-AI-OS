import React, { useState } from "react";
import { ApiError, api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import {
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";

/**
 * Expansion Feature 2 (Universal Integration Framework): the
 * connector registry console. Everything renders the framework's
 * real endpoints — this view holds no connector state of its own.
 * States use the framework's ONE vocabulary (configured /
 * not_configured / requires_owner_configuration / error); a
 * connector with no implemented adapter is shown exactly as that,
 * never as connected. Configuration carries a P-10 secret registry
 * NAME only — no secret value is ever typed, sent or displayed
 * here.
 */

export interface ConnectorRow {
  key: string;
  name: string;
  provider: string;
  kind: string;
  source: string;
  has_adapter: boolean;
  requires_credential: boolean;
  credential_configured: boolean;
  credential_secret_name?: string | null;
  lifecycle_status: string;
  state: string;
  error_count: number;
  last_health_at?: string | null;
  last_sync_at?: string | null;
  last_invoked_at?: string | null;
  last_error?: string | null;
  capabilities: { name: string; permission: string; risk_action: string }[];
}

interface FrameworkStatus {
  api_version: string;
  connector_count: number;
  with_adapter: number;
  by_state: Record<string, number>;
  state_vocabulary: string[];
}

interface InvocationRow {
  id: string;
  capability: string;
  principal: string;
  outcome: string;
  error_detail?: string | null;
  created_at?: string | null;
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
}

export function IntegrationsView(): React.ReactElement {
  const status = useApi<FrameworkStatus>("/integrations/framework/status", 30000);
  const connectors = useApi<ConnectorRow[]>("/integrations", 30000);
  const [selected, setSelected] = useState<string>("local_echo");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [secretName, setSecretName] = useState("");
  const [echoMessage, setEchoMessage] = useState("");
  const [echoResult, setEchoResult] = useState<string | null>(null);

  const invocations = useApi<InvocationRow[]>(
    selected ? `/integrations/${selected}/invocations` : null, 30000);

  const rows: ConnectorRow[] = Array.isArray(connectors.data) ? connectors.data : [];
  const selectedRow = rows.find((r) => r.key === selected) ?? null;

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(label);
      connectors.reload();
      invocations.reload();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const configure = (row: ConnectorRow) =>
    act(`Configuration saved for ${row.key}.`, () =>
      api(`/integrations/${row.key}/configure`, {
        method: "POST",
        body: { credential_secret_name: secretName || null },
      }));

  const invokeEcho = () =>
    act("Echo invocation completed.", async () => {
      const result = await api<{ result: { echo: string; responded_at: string } }>(
        "/integrations/local_echo/invoke",
        { method: "POST", body: { capability: "echo", payload: { message: echoMessage } } },
      );
      setEchoResult(`${result.data.result.echo} — ${result.data.result.responded_at}`);
    });

  return (
    <div className="page">
      <PageHeader
        title="Integrations"
        subtitle="Universal Integration Framework — one registry, one capability contract, one honest state vocabulary. Credentials live in P-10; this console carries secret names only, never values."
      />
      {status.loading ? <LoadingState label="Loading framework status…" /> : null}
      {status.error ? <ErrorState error={status.error} /> : null}
      {status.data ? (
        <Panel title="Framework" meta={`API version ${status.data.api_version}`}>
          <p>
            {status.data.connector_count} connectors registered ·{" "}
            {status.data.with_adapter} with an implemented adapter ·{" "}
            {Object.entries(status.data.by_state)
              .map(([state, count]) => `${count} ${state.replace(/_/g, " ")}`)
              .join(" · ")}
          </p>
        </Panel>
      ) : null}

      <Panel title="Connector registry" meta="P-07 / P-17 / P-18 surfaces register here">
        {connectors.loading ? <LoadingState label="Loading connectors…" /> : null}
        {connectors.error ? <ErrorState error={connectors.error} /> : null}
        {!connectors.loading && !connectors.error ? (
          <DataTable
            columns={[
              { key: "name", label: "Connector" },
              { key: "provider", label: "Provider" },
              { key: "kind", label: "Kind" },
              { key: "lifecycle", label: "Lifecycle" },
              { key: "state", label: "State" },
              { key: "adapter", label: "Adapter" },
              { key: "errors", label: "Errors", numeric: true },
              { key: "actions", label: "Actions" },
            ]}
            rows={rows.map((row) => ({
              name: (
                <button type="button" className="btn btn-small" onClick={() => setSelected(row.key)}>
                  {row.name}
                </button>
              ),
              provider: row.provider,
              kind: row.kind,
              lifecycle: <StatusBadge value={row.lifecycle_status} />,
              state: <StatusBadge value={row.state} />,
              adapter: row.has_adapter ? "Implemented" : "None — not a working connector",
              errors: row.error_count,
              actions: (
                <span>
                  <button
                    type="button" className="btn btn-small" disabled={busy}
                    onClick={() => act(`Health checked for ${row.key}.`, () =>
                      api(`/integrations/${row.key}/health`, { method: "POST" }))}
                  >
                    Health
                  </button>{" "}
                  {row.lifecycle_status === "enabled" ? (
                    <button
                      type="button" className="btn btn-small" disabled={busy}
                      onClick={() => act(`${row.key} disabled.`, () =>
                        api(`/integrations/${row.key}/disable`, { method: "POST" }))}
                    >
                      Disable
                    </button>
                  ) : (
                    <button
                      type="button" className="btn btn-small" disabled={busy}
                      onClick={() => act(`${row.key} enabled.`, () =>
                        api(`/integrations/${row.key}/enable`, { method: "POST" }))}
                    >
                      Enable
                    </button>
                  )}
                </span>
              ),
            }))}
            emptyTitle="No connectors registered"
            emptyDetail="The framework seeds its catalogue at startup; an empty registry means seeding did not run."
          />
        ) : null}
        {notice ? <p className="notice">{notice}</p> : null}
        {actionError ? <p className="error-text">{actionError}</p> : null}
      </Panel>

      {selectedRow ? (
        <Panel title={`Configure — ${selectedRow.name}`} meta={selectedRow.key}>
          <p>
            {selectedRow.has_adapter
              ? "Adapter implemented."
              : "No adapter is implemented for this connector: it cannot be enabled or invoked until a real connector is built and tested."}{" "}
            {selectedRow.requires_credential
              ? selectedRow.credential_configured
                ? `Credential reference attached: ${selectedRow.credential_secret_name} (P-10 registry name only).`
                : "Requires a credential: attach the NAME of a P-10 secrets-registry entry."
              : "No credential required."}
          </p>
          <label>
            P-10 secret name{" "}
            <input
              value={secretName}
              onChange={(e) => setSecretName(e.target.value)}
              placeholder="e.g. stripe_api_key"
            />
          </label>{" "}
          <button
            type="button" className="btn btn-small" disabled={busy}
            onClick={() => configure(selectedRow)}
          >
            Save configuration
          </button>
        </Panel>
      ) : null}

      <Panel title="Reference connector — end-to-end invoke" meta="local_echo">
        <p>
          The local echo connector is genuinely implemented (no network, no
          credential). Invoking it exercises registration, the capability
          contract, P-10 broker authorization and the invocation ledger.
        </p>
        <label>
          Message{" "}
          <input value={echoMessage} onChange={(e) => setEchoMessage(e.target.value)} />
        </label>{" "}
        <button type="button" className="btn btn-small" disabled={busy || !echoMessage} onClick={invokeEcho}>
          Invoke echo
        </button>
        {echoResult ? <p className="notice">{echoResult}</p> : null}
      </Panel>

      <Panel title="Invocation history" meta={selected ?? undefined}>
        {invocations.loading ? <LoadingState label="Loading invocations…" /> : null}
        {!invocations.loading && !invocations.error ? (
          <DataTable
            columns={[
              { key: "capability", label: "Capability" },
              { key: "outcome", label: "Outcome" },
              { key: "principal", label: "Principal" },
              { key: "when", label: "When" },
              { key: "detail", label: "Detail" },
            ]}
            rows={(Array.isArray(invocations.data) ? invocations.data : []).map((row) => ({
              capability: row.capability,
              outcome: <StatusBadge value={row.outcome} />,
              principal: row.principal,
              when: formatDateTime(row.created_at),
              detail: row.error_detail ?? "",
            }))}
            emptyTitle="No invocations recorded"
            emptyDetail="Invocations of the selected connector will appear here, including refusals and failures."
          />
        ) : null}
        {invocations.error ? <ErrorState error={invocations.error} /> : null}
        {!selected ? <EmptyState title="No connector selected" detail="Select a connector in the registry." /> : null}
      </Panel>
    </div>
  );
}
