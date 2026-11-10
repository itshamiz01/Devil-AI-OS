import React from "react";
import {
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { formatBps, formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import { navigate } from "../lib/router";

interface SurvivalOverview {
  decisions_by_status: Record<string, number>;
  latest_health_by_business: {
    business_id: string;
    classification: string;
    score_bps: number | null;
    overlay_state: string;
    confidence: string;
    explanation: string;
    created_at: string | null;
  }[];
  source: string;
  note: string;
}

interface SurvivalDecision {
  id: string;
  business_id: string;
  decision_type: string;
  status: string;
  trigger: string;
  risk_assessment: string;
  expected_benefit: string;
  created_at: string;
}

/**
 * §12 Survival & Scaling. Recommendations and decisions are DISPLAYED
 * with their evidence; high-impact decisions are never executed from a
 * dashboard recommendation (§12.4) — P-08 policy + owner approval govern.
 */
export function SurvivalView(): React.ReactElement {
  const overview = useApi<SurvivalOverview>("/dashboard/survival/overview", 30000);
  const decisions = useApi<SurvivalDecision[]>("/survival/decisions?limit=50", 30000);

  return (
    <div className="view">
      <PageHeader
        title="Survival & Scaling"
        subtitle="Business health from P-08 — decisions explained, never auto-executed"
        actions={<FreshnessBar updatedAt={overview.updatedAt} />}
      />
      {overview.loading && !overview.data ? <LoadingState label="Loading survival data…" /> : null}
      {overview.error ? <ErrorState error={overview.error} onRetry={overview.reload} /> : null}
      {overview.data ? (
        <>
          <Panel title="Survival overview" meta={overview.data.source}>
            <dl className="stat-row num">
              {Object.entries(overview.data.decisions_by_status).map(([s, c]) => (
                <div key={s}><dt>Decisions: {s}</dt><dd>{c}</dd></div>
              ))}
              <div>
                <dt>Businesses with health snapshots</dt>
                <dd>{overview.data.latest_health_by_business.length}</dd>
              </div>
            </dl>
            <p className="muted">{overview.data.note}</p>
          </Panel>
          <Panel title="Business health (latest snapshot per business)">
            {overview.data.latest_health_by_business.length === 0 ? (
              <EmptyState
                title="No health snapshots yet"
                detail="P-08 has not produced health snapshots. On a business without verified collected revenue, the honest P-08 reading is INSUFFICIENT_DATA — this console shows that rather than inventing a health score."
              />
            ) : (
              <DataTable
                columns={[
                  { key: "business", label: "Business" },
                  { key: "classification", label: "Classification" },
                  { key: "score", label: "Score", numeric: true },
                  { key: "overlay", label: "Lifecycle overlay" },
                  { key: "confidence", label: "Confidence" },
                  { key: "at", label: "Snapshot" },
                ]}
                rows={overview.data.latest_health_by_business.map((s) => ({
                  business: (
                    <button type="button" className="link-button" onClick={() => navigate("businesses", s.business_id)}>
                      <span className="mono">{s.business_id}</span>
                    </button>
                  ),
                  classification: <StatusBadge value={s.classification} />,
                  score: formatBps(s.score_bps),
                  overlay: s.overlay_state,
                  confidence: s.confidence,
                  at: formatDateTime(s.created_at),
                }))}
                emptyTitle="No snapshots"
                emptyDetail="No health snapshots exist."
              />
            )}
            {overview.data.latest_health_by_business.map((s) =>
              s.explanation ? (
                <p key={s.business_id} className="muted">
                  <span className="mono">{s.business_id.slice(0, 8)}</span>: {s.explanation}
                </p>
              ) : null,
            )}
          </Panel>
        </>
      ) : null}

      <Panel title="Survival decisions" meta="P-08 records — owner approval governs execution">
        {decisions.data && decisions.data.length === 0 ? (
          <EmptyState title="No survival decisions" detail="No CONTINUE / OPTIMIZE / PAUSE / PIVOT / SCALE / CLOSE decisions have been recorded by P-08." />
        ) : null}
        <ul className="plain-list">
          {(decisions.data ?? []).map((d) => (
            <li key={d.id} className="plain-item">
              <StatusBadge value={d.status} />
              <div className="plain-body">
                <strong>{d.decision_type}</strong>
                <p className="muted">
                  business <span className="mono">{d.business_id}</span> · trigger: {d.trigger} ·{" "}
                  {formatDateTime(d.created_at)}
                </p>
                <p>Risk: {d.risk_assessment}</p>
                <p>Expected benefit: {d.expected_benefit}</p>
              </div>
            </li>
          ))}
        </ul>
        <p className="muted">
          Agent-originated CLOSE decisions are impossible by construction (Level 4,
          owner-only) — nothing on this page can execute a closure.
        </p>
      </Panel>
    </div>
  );
}
