import React, { useState } from "react";
import { ApiError, api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import {
  ConfirmationDialog,
  DataTable,
  EmptyState,
  LoadingState,
  Panel,
  StatusBadge,
} from "../components/ui";

/**
 * Expansion Feature 1 (Identity & Device Security) panels for the
 * Security & Governance view. Everything renders P-10's real
 * device/recovery endpoints — this console holds no device or
 * credential state of its own. A device secret and a batch of
 * recovery codes are displayed EXACTLY ONCE, from the single
 * enrol/rotate/generate response that mints them; the backend
 * stores only hashes, so there is nothing to re-display.
 */

export interface DeviceRow {
  id: string;
  principal?: string;
  label: string;
  platform?: string | null;
  device_name?: string | null;
  trust_status: string;
  last_seen_at?: string | null;
  created_at?: string | null;
}

interface DeviceCreated extends DeviceRow {
  device_secret: string;
  secret_shown_once: boolean;
}

interface RecoveryStatus {
  configured?: boolean;
  total_generated?: number;
  unused?: number;
  used?: number;
  invalidated?: number;
  batches?: number;
  last_generated_at?: string | null;
}

interface RecoveryGenerated {
  batch_id: string;
  codes: string[];
  count: number;
  invalidated_previous: number;
  shown_once: boolean;
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
}

export function DevicesPanel(): React.ReactElement {
  const devices = useApi<DeviceRow[]>("/security/devices", 30000);
  const [label, setLabel] = useState("");
  const [platform, setPlatform] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [shownSecret, setShownSecret] = useState<{ forLabel: string; secret: string } | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<DeviceRow | null>(null);

  const rows: DeviceRow[] = Array.isArray(devices.data) ? devices.data : [];

  const enrol = async () => {
    setBusy(true);
    setActionError(null);
    setShownSecret(null);
    try {
      const result = await api<DeviceCreated>("/security/devices", {
        method: "POST",
        body: { label: label.trim(), platform: platform.trim() || null },
      });
      setShownSecret({ forLabel: result.data.label, secret: result.data.device_secret });
      setNotice(
        `Device "${result.data.label}" enrolled as UNTRUSTED. Trust it below before it can hold a session.`,
      );
      setLabel("");
      setPlatform("");
      devices.reload();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const act = async (device: DeviceRow, action: "trust" | "untrust" | "rotate-secret" | "revoke") => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await api<DeviceCreated>(`/security/devices/${device.id}/${action}`, {
        method: "POST",
      });
      if (action === "rotate-secret") {
        setShownSecret({ forLabel: device.label, secret: result.data.device_secret });
        setNotice(`Credential for "${device.label}" rotated. Its previous sessions were revoked.`);
      } else {
        setNotice(`Device "${device.label}" is now ${result.data.trust_status}.`);
      }
      setConfirmRevoke(null);
      devices.reload();
    } catch (err) {
      setActionError(errorText(err));
      setConfirmRevoke(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Devices"
      meta="Expansion F-01 — device registry in P-10; a device identity is its credential, never a hardware claim"
    >
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}
      {shownSecret ? (
        <div className="plain-item">
          <div className="plain-body">
            <strong>Device secret for “{shownSecret.forLabel}” — shown exactly once</strong>
            <p className="mono">{shownSecret.secret}</p>
            <p className="muted">
              Store it on the device now. P-10 keeps only a hash of this secret; it cannot be
              shown again. If it is lost, rotate the credential here (that revokes the
              device's sessions).
            </p>
            <button type="button" className="btn btn-small" onClick={() => setShownSecret(null)}>
              I have stored it — dismiss
            </button>
          </div>
        </div>
      ) : null}
      {devices.loading && !devices.data ? <LoadingState label="Loading devices…" /> : null}
      {devices.error ? <p className="error-text">{devices.error.message}</p> : null}
      {devices.data && rows.length === 0 ? (
        <EmptyState
          title="No devices registered"
          detail="Enrol a device below. New devices start untrusted and cannot hold a session until you trust them."
        />
      ) : null}
      <DataTable
        columns={[
          { key: "label", label: "Device" },
          { key: "platform", label: "Platform (self-declared)" },
          { key: "trust", label: "Trust" },
          { key: "seen", label: "Last seen" },
          { key: "action", label: "" },
        ]}
        rows={rows.map((d) => ({
          label: (
            <span>
              <strong>{d.label}</strong>{" "}
              <span className="mono muted">{d.id.slice(0, 8)}…</span>
            </span>
          ),
          platform: d.platform ?? "—",
          trust: <StatusBadge value={d.trust_status} />,
          seen: formatDateTime(d.last_seen_at ?? null),
          action: (
            <span className="card-actions">
              {d.trust_status === "untrusted" ? (
                <button type="button" className="btn btn-small" disabled={busy} onClick={() => void act(d, "trust")}>
                  Trust
                </button>
              ) : null}
              {d.trust_status === "trusted" ? (
                <button type="button" className="btn btn-small" disabled={busy} onClick={() => void act(d, "untrust")}>
                  Untrust
                </button>
              ) : null}
              {d.trust_status !== "revoked" ? (
                <>
                  <button type="button" className="btn btn-small" disabled={busy} onClick={() => void act(d, "rotate-secret")}>
                    Rotate secret
                  </button>
                  <button type="button" className="btn btn-small btn-danger" disabled={busy} onClick={() => setConfirmRevoke(d)}>
                    Revoke
                  </button>
                </>
              ) : null}
            </span>
          ),
        }))}
        emptyTitle="No devices"
        emptyDetail="P-10 reported no registered devices."
      />
      <div className="card-actions">
        <label className="field">
          <span>New device label</span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Owner laptop"
          />
        </label>
        <label className="field">
          <span>Platform (self-declared)</span>
          <input
            type="text"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            placeholder="e.g. windows"
          />
        </label>
        <button
          type="button"
          className="btn"
          disabled={busy || label.trim() === ""}
          onClick={() => void enrol()}
        >
          Enrol device
        </button>
      </div>
      <p className="muted">
        Revoking a device is permanent and immediately kills every session bound to it.
        Untrusting does the same to sessions but keeps the device registered.
      </p>
      <ConfirmationDialog
        open={confirmRevoke !== null}
        title={`Revoke device “${confirmRevoke?.label ?? ""}”?`}
        body={
          <p>
            P-10 will mark this device revoked — permanently. Every session bound to it is
            revoked immediately, and the device credential stops working. A revoked device
            cannot be trusted again; enrol a new device instead.
          </p>
        }
        confirmLabel="Revoke device"
        danger
        busy={busy}
        onConfirm={() => confirmRevoke && void act(confirmRevoke, "revoke")}
        onCancel={() => setConfirmRevoke(null)}
      />
    </Panel>
  );
}

export function RecoveryCodesPanel(): React.ReactElement {
  const status = useApi<RecoveryStatus>("/security/auth/recovery-codes", 30000);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<RecoveryGenerated | null>(null);
  const [code, setCode] = useState("");
  const [verifyResult, setVerifyResult] = useState<string | null>(null);
  const [confirmGenerate, setConfirmGenerate] = useState(false);

  const data: RecoveryStatus = status.data ?? {};

  const generate = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await api<RecoveryGenerated>("/security/auth/recovery-codes/generate", {
        method: "POST",
        body: { count: 10 },
      });
      setGenerated(result.data);
      setNotice(
        result.data.invalidated_previous > 0
          ? `New batch generated. ${result.data.invalidated_previous} unused code(s) from the previous batch were invalidated.`
          : "New recovery-code batch generated.",
      );
      setConfirmGenerate(false);
      status.reload();
    } catch (err) {
      setActionError(errorText(err));
      setConfirmGenerate(false);
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    setActionError(null);
    setVerifyResult(null);
    try {
      const result = await api<{ verified: boolean }>("/security/auth/recovery-codes/verify", {
        method: "POST",
        body: { code: code.trim() },
      });
      setVerifyResult(
        result.data.verified
          ? "Verified — the code has been consumed and cannot be used again."
          : "Not verified — the code did not match any unused recovery code.",
      );
      if (result.data.verified) setCode("");
      status.reload();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="MFA recovery codes"
      meta="Expansion F-01 — closes the P-10 gap: codes exist, are hash-stored and single-use"
    >
      {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}
      {status.loading && !status.data ? <LoadingState label="Loading recovery-code status…" /> : null}
      {status.error ? <p className="error-text">{status.error.message}</p> : null}
      <dl className="stat-row">
        <div><dt>Configured</dt><dd>{data.configured ? "Yes" : "No codes generated yet"}</dd></div>
        <div><dt>Unused</dt><dd className="num">{data.unused ?? 0}</dd></div>
        <div><dt>Used</dt><dd className="num">{data.used ?? 0}</dd></div>
        <div><dt>Invalidated</dt><dd className="num">{data.invalidated ?? 0}</dd></div>
        <div><dt>Last generated</dt><dd>{formatDateTime(data.last_generated_at ?? null)}</dd></div>
      </dl>
      {generated ? (
        <div className="plain-item">
          <div className="plain-body">
            <strong>Your recovery codes — shown exactly once</strong>
            <ul className="plain-list">
              {generated.codes.map((c) => (
                <li key={c} className="mono">{c}</li>
              ))}
            </ul>
            <p className="muted">
              Store these somewhere safe and offline. P-10 stores only hashes — these codes
              cannot be displayed again. Each code works once.
            </p>
            <button type="button" className="btn btn-small" onClick={() => setGenerated(null)}>
              I have stored them — dismiss
            </button>
          </div>
        </div>
      ) : null}
      <div className="card-actions">
        <button type="button" className="btn" disabled={busy} onClick={() => setConfirmGenerate(true)}>
          Generate new codes
        </button>
        <label className="field">
          <span>Verify a code (consumes it)</span>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="XXXX-XXXX-XXXX"
          />
        </label>
        <button
          type="button"
          className="btn"
          disabled={busy || code.trim() === ""}
          onClick={() => void verify()}
        >
          Verify code
        </button>
      </div>
      {verifyResult ? <p className="muted" role="status">{verifyResult}</p> : null}
      <p className="muted">
        Generating a new batch invalidates every unused code from earlier batches. Recovery
        codes are a fallback for MFA — they never replace your password.
      </p>
      <ConfirmationDialog
        open={confirmGenerate}
        title="Generate a new recovery-code batch?"
        body={
          <p>
            P-10 will mint 10 new codes and invalidate every unused code from earlier
            batches. The new codes are shown exactly once — have somewhere safe ready to
            store them.
          </p>
        }
        confirmLabel="Generate codes"
        busy={busy}
        onConfirm={() => void generate()}
        onCancel={() => setConfirmGenerate(false)}
      />
    </Panel>
  );
}
