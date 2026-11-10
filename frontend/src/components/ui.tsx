import React, { useEffect, useRef } from "react";
import { ApiError } from "../lib/api";
import { formatMoney, humanize, timeAgo, toneFor, type Tone } from "../lib/format";
import { useConnection, usePrefs } from "../lib/store";
import type { Metric } from "../lib/types";

// ------------------------------------------------------------ StatusBadge
export function StatusBadge({ value }: { value: string | null | undefined }): React.ReactElement {
  const tone = toneFor(value);
  return (
    <span className={`badge tone-${tone}`} data-tone={tone}>
      <span className="badge-dot" aria-hidden="true" />
      {humanize(value)}
    </span>
  );
}

// ------------------------------------------------------------- PageHeader
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}): React.ReactElement {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

// ------------------------------------------------------------- MetricCard
export function MetricCard({ metric }: { metric: Metric }): React.ReactElement {
  const isMoney = metric.unit !== null && metric.unit !== undefined;
  const display =
    metric.state === "unavailable" || metric.value === null
      ? "Unavailable"
      : isMoney
        ? formatMoney(metric.value, metric.unit ?? "INR")
        : String(metric.value);
  return (
    <article className="metric-card" aria-label={metric.label}>
      <div className="metric-label">{metric.label}</div>
      <div className={`metric-value num ${metric.state === "unavailable" ? "metric-unavailable" : ""}`}>
        {display}
      </div>
      <div className="metric-meta">
        <span>{metric.period}</span>
        <span className="metric-source" title={metric.source}>
          {metric.source}
        </span>
      </div>
      {metric.note ? <p className="metric-note">{metric.note}</p> : null}
    </article>
  );
}

// -------------------------------------------------------------- states
export function LoadingState({ label = "Loading…" }: { label?: string }): React.ReactElement {
  return (
    <div className="state state-loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="state state-empty">
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: ApiError | Error;
  onRetry?: () => void;
}): React.ReactElement {
  const apiErr = error instanceof ApiError ? error : null;
  const title = apiErr?.isConnectionFailure
    ? "Backend unavailable"
    : apiErr?.isUnauthorized
      ? "Session expired"
      : apiErr?.isForbidden
        ? "Access denied"
        : "Could not load this view";
  return (
    <div className="state state-error" role="alert">
      <h3>{title}</h3>
      <p>{error.message}</p>
      {apiErr ? <p className="state-code">code: {apiErr.code}</p> : null}
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

// ----------------------------------------------------------- FreshnessBar
/** §22.4: last-updated, connection status, stale warning — always honest. */
export function FreshnessBar({ updatedAt }: { updatedAt: number | null }): React.ReactElement {
  const { online, lastOkAt } = useConnection();
  const now = Date.now();
  const stale = !online || (updatedAt !== null && lastOkAt !== null && lastOkAt < updatedAt);
  return (
    <div className={`freshness ${online ? "" : "freshness-down"}`} role="status">
      <span className={`conn-dot ${online ? "conn-ok" : "conn-bad"}`} aria-hidden="true" />
      {online ? (
        <span>
          Connected · updated {updatedAt ? timeAgo(new Date(updatedAt).toISOString(), now) : "—"}
        </span>
      ) : (
        <span>
          <strong>Connection lost.</strong> Showing last known data — it may be stale.
          {stale ? "" : ""}
        </span>
      )}
    </div>
  );
}

// -------------------------------------------------------- ProgressIndicator
export function ProgressIndicator({
  value,
  label,
}: {
  value: number; // 0..1
  label?: string;
}): React.ReactElement {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
      <span className="progress-label">{pct}%</span>
    </div>
  );
}

// ------------------------------------------------------ ConfirmationDialog
export function ConfirmationDialog({
  open,
  title,
  body,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}): React.ReactElement | null {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    if (open && !dlg.open) dlg.showModal();
    if (!open && dlg.open) dlg.close();
  }, [open ]);
  if (!open) return null;
  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
    >
      <h2>{title}</h2>
      <div className="confirm-body">{body}</div>
      <div className="confirm-actions">
        <button type="button" className="btn" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
          onClick={onConfirm}
          disabled={busy}
          autoFocus
        >
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

// -------------------------------------------------------------- DataTable
export function DataTable({
  columns,
  rows,
  emptyTitle,
  emptyDetail,
}: {
  columns: { key: string; label: string; numeric?: boolean }[];
  rows: Record<string, React.ReactNode>[];
  emptyTitle: string;
  emptyDetail: string;
}): React.ReactElement {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} detail={emptyDetail} />;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.numeric ? "num" : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? "num" : undefined}>
                  {row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --------------------------------------------------------------- Timeline
export function Timeline({
  items,
}: {
  items: { id: string; title: string; detail?: string; at: string | null; tone?: Tone }[];
}): React.ReactElement {
  const { prefs } = usePrefs();
  if (items.length === 0) {
    return <EmptyState title="No activity recorded" detail="Events will appear here as the system works. Nothing is fabricated — an empty feed means nothing has happened yet." />;
  }
  return (
    <ol className="timeline">
      {items.map((item) => (
        <li key={item.id} className="timeline-item">
          <span className={`timeline-dot tone-bg-${item.tone ?? toneFor(item.title)}`} aria-hidden="true" />
          <div className="timeline-body">
            <div className="timeline-title">{item.title}</div>
            {item.detail ? <div className="timeline-detail">{item.detail}</div> : null}
            <div className="timeline-at">
              {item.at ? timeAgo(item.at) : "—"}
              {item.at ? <span className="timeline-abs"> · {new Date(item.at).toLocaleString("en-GB", { timeZone: prefs.timezone })}</span> : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ----------------------------------------------------------------- charts
/** Hand-rolled SVG line chart fed by real API series only. */
export function LineChart({
  points,
  label,
  height = 120,
}: {
  points: { x: string; y: number }[];
  label: string;
  height?: number;
}): React.ReactElement {
  if (points.length === 0) {
    return <EmptyState title="No series data" detail="The backend returned no data points for this period." />;
  }
  const width = 640;
  const max = Math.max(...points.map((p) => p.y), 1);
  const min = Math.min(...points.map((p) => p.y), 0);
  const range = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : width;
  const coords = points.map((p, i) => {
    const x = i * stepX;
    const y = height - 8 - ((p.y - min) / range) * (height - 16);
    return `${x},${y}`;
  });
  return (
    <figure className="chart" aria-label={label}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
        <polyline points={coords.join(" ")} className="chart-line" fill="none" />
      </svg>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export function BarChart({
  bars,
  label,
  format,
}: {
  bars: { label: string; value: number; tone?: Tone }[];
  label: string;
  format?: (v: number) => string;
}): React.ReactElement {
  if (bars.length === 0) {
    return <EmptyState title="No data" detail="Nothing to chart for this period." />;
  }
  const max = Math.max(...bars.map((b) => Math.abs(b.value)), 1);
  return (
    <figure className="chart" aria-label={label}>
      <div className="bar-chart">
        {bars.map((b) => (
          <div className="bar-row" key={b.label}>
            <span className="bar-label">{b.label}</span>
            <span className="bar-track">
              <span
                className={`bar-fill tone-bg-${b.tone ?? "info"}`}
                style={{ width: `${Math.max(2, (Math.abs(b.value) / max) * 100)}%` }}
              />
            </span>
            <span className="bar-value num">{format ? format(b.value) : b.value}</span>
          </div>
        ))}
      </div>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export function ChartPanel({
  title,
  meta,
  children,
}: {
  title: string;
  meta: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <section className="panel chart-panel">
      <header className="panel-header">
        <h2>{title}</h2>
        <span className="panel-meta">{meta}</span>
      </header>
      {children}
    </section>
  );
}

export function Panel({
  title,
  meta,
  children,
  actions,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}): React.ReactElement {
  return (
    <section className="panel">
      <header className="panel-header">
        <h2>{title}</h2>
        {meta ? <span className="panel-meta">{meta}</span> : null}
        {actions}
      </header>
      {children}
    </section>
  );
}
