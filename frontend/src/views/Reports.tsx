import React, { useState } from "react";
import { PageHeader, Panel } from "../components/ui";
import { api } from "../lib/api";
import { usePrefs } from "../lib/store";

/**
 * §19 Reporting Center. Reports are assembled from live API responses at
 * click time and carry an integrity header (§19.4): generation timestamp,
 * reporting period, data sources, definitions, actual-vs-forecast labels
 * and known limitations. CSV/JSON export is real; PDF export is honestly
 * NOT IMPLEMENTED (no PDF capability exists in the backend or this
 * bundle) and is not offered as a dead button.
 */

const REPORT_KINDS = [
  {
    key: "financial",
    label: "Financial performance (actuals)",
    sources: ["GET /dashboard/finance/summary (P-07 consolidated, verbatim)"],
    fetch: async (currency: string) =>
      api(`/dashboard/finance/summary?currency=${currency}`).then((r) => r.data),
    definitions:
      "Collected = verified net collected revenue (minor units). Expenses = paid P&L expenses. " +
      "Net profit = collected − expenses. Forecasts are NOT included in this report.",
  },
  {
    key: "portfolio",
    label: "Business portfolio",
    sources: ["GET /dashboard/businesses/summary (P-06 registry)", "GET /dashboard/survival/overview (P-08)"],
    fetch: async () => {
      const [b, s] = await Promise.all([
        api("/dashboard/businesses/summary").then((r) => r.data),
        api("/dashboard/survival/overview").then((r) => r.data),
      ]);
      return { businesses: b, survival: s };
    },
    definitions: "Lifecycle statuses are P-06 state-machine values; health classifications are P-08's latest snapshots.",
  },
  {
    key: "agents",
    label: "Agent performance (registry)",
    sources: ["GET /dashboard/agents/summary (P-04)", "GET /agents"],
    fetch: async () => {
      const [s, list] = await Promise.all([
        api("/dashboard/agents/summary").then((r) => r.data),
        api("/agents?limit=200").then((r) => r.data),
      ]);
      return { summary: s, agents: list };
    },
    definitions: "Agent statuses are P-04 lifecycle values. Per-agent success rates are shown only where the backend records them.",
  },
  {
    key: "security",
    label: "Security events (summary)",
    sources: ["GET /dashboard/security/summary (P-10)"],
    fetch: async () => api("/dashboard/security/summary").then((r) => r.data),
    definitions: "Security mode, alert and incident counts from P-10's monitor and tables. Audit chain is tamper-evident, not tamper-proof.",
  },
] as const;

function toCsv(data: unknown): string {
  // Flatten one level: arrays of objects become rows; scalars become a
  // two-column key/value sheet. Good enough for the summary payloads this
  // console exports, and always derived from the real response.
  const rows: string[][] = [];
  const walk = (value: unknown, path: string) => {
    if (Array.isArray(value)) {
      value.forEach((item, i) => walk(item, `${path}[${i}]`));
    } else if (value !== null && typeof value === "object") {
      Object.entries(value as Record<string, unknown>).forEach(([k, v]) => walk(v, path ? `${path}.${k}` : k));
    } else {
      rows.push([path, String(value ?? "")]);
    }
  };
  walk(data, "");
  const esc = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  return ["key,value", ...rows.map((r) => r.map(esc).join(","))].join("\n");
}

function download(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportsView(): React.ReactElement {
  const { prefs } = usePrefs();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ kind: string; data: unknown; generatedAt: string } | null>(null);

  const generate = async (kind: (typeof REPORT_KINDS)[number], format: "json" | "csv" | "preview") => {
    setBusy(`${kind.key}-${format}`);
    setError(null);
    setMessage(null);
    try {
      const data = await kind.fetch(prefs.currency);
      const generatedAt = new Date().toISOString();
      const header = {
        report: kind.label,
        generated_at: generatedAt,
        reporting_period: "current state at generation time (live system snapshot)",
        data_sources: kind.sources,
        metric_definitions: kind.definitions,
        actual_vs_forecast: "actuals only unless a section is explicitly labelled FORECAST",
        known_limitations:
          "Snapshot semantics: values are read live from the owning engines at generation time and are not a signed export. Cross-currency amounts are never summed (P-07 §14).",
      };
      if (format === "preview") {
        setPreview({ kind: kind.key, data: { header, data }, generatedAt });
      } else if (format === "json") {
        download(`autonomus-${kind.key}-report.json`, JSON.stringify({ header, data }, null, 2), "application/json");
        setMessage(`${kind.label}: JSON exported with integrity header.`);
      } else {
        download(
          `autonomus-${kind.key}-report.csv`,
          `# ${kind.label}\n# generated_at: ${generatedAt}\n# sources: ${kind.sources.join("; ")}\n# definitions: ${kind.definitions}\n${toCsv(data)}`,
          "text/csv",
        );
        setMessage(`${kind.label}: CSV exported with integrity header.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="view">
      <PageHeader
        title="Reporting & Analytics"
        subtitle="Reports built from live backend data, with an integrity header on every export"
      />
      {message ? <p className="ok-text" role="status">{message}</p> : null}
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <Panel title="Report categories" meta="filters: live data only — a report reflects the moment it is generated">
        <ul className="plain-list">
          {REPORT_KINDS.map((kind) => (
            <li key={kind.key} className="plain-item">
              <div className="plain-body">
                <strong>{kind.label}</strong>
                <p className="muted">Sources: {kind.sources.join(" · ")}</p>
                <p className="muted">{kind.definitions}</p>
                <span className="card-actions">
                  <button type="button" className="btn btn-small" disabled={busy !== null} onClick={() => void generate(kind, "preview")}>
                    Preview
                  </button>
                  <button type="button" className="btn btn-small" disabled={busy !== null} onClick={() => void generate(kind, "json")}>
                    Export JSON
                  </button>
                  <button type="button" className="btn btn-small" disabled={busy !== null} onClick={() => void generate(kind, "csv")}>
                    Export CSV
                  </button>
                </span>
              </div>
            </li>
          ))}
        </ul>
        <p className="muted">
          PDF export: NOT IMPLEMENTED — no PDF generation capability exists in the backend or
          this bundle, so no button is offered for it. Period comparison: reports are live
          snapshots; historical comparison requires stored snapshots, which P-07/P-08 keep
          per business (see Survival) — a combined comparison report is not implemented.
        </p>
      </Panel>
      {preview ? (
        <Panel title={`Preview — generated ${preview.generatedAt}`}>
          <pre className="params-json preview-json">{JSON.stringify(preview.data, null, 2)}</pre>
        </Panel>
      ) : null}
    </div>
  );
}
