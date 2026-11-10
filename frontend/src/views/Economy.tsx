import React, { useState } from "react";
import {
  DataTable,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";
import { formatMoney, formatNumber } from "../lib/format";
import { useApi } from "../lib/hooks";

// P-16 §15: the AI Economy & Expansion Center. Every figure comes
// from the /economy/* endpoints, which read P-07 live; proposals
// are labelled PROPOSED and stress results SIMULATION. The view
// renders no number of its own and offers no action the backend
// has not exposed — approvals are decided by the owner through the
// governed API and appear here as state.

interface Gate {
  state: string;
  reason: string;
  businesses_profiled: number;
  total_collected_minor: number;
  total_net_profit_minor: number | null;
}

interface Status {
  autonomy_level: number;
  expansion_paused: boolean;
  capital_commitments_frozen: boolean;
  profitability_gate: Gate;
}

interface Overview {
  generated_at: string;
  businesses: { total: number; with_financial_profile: number };
  global_economic_overview: {
    total_verified_collected_revenue_minor: number;
    total_net_profit_minor: number | null;
    total_actual_expenses_minor: number | null;
    combined_available_cash: number | null;
    combined_cash_note: string;
  };
  kpis: {
    recurring_share_of_collected: number | null;
    revenue_concentration: { hhi: number | null; top_share: number | null; overconcentrated: boolean };
  };
  profitability_gate: Gate;
}

interface ClassificationItem {
  business_id: string;
  name: string;
  is_fixture: boolean;
  lifecycle_label: string;
  classification: { industry: string; revenue_model: string; market: string } | null;
  profitability: { verified_collected_revenue_minor: number; net_profit_minor: number | null };
  revenue_share: number | null;
}

interface Opportunity {
  id: string;
  title: string;
  kind: string;
  stage: string;
  total_score: number | null;
  classification_band: string | null;
  confidence: number;
}

interface Diversification {
  per_business: { business_id: string; name: string; is_fixture: boolean; net_collected_minor: number | null; diversification_score: number | null; diversification_status: string }[];
  totals: { net_collected_minor: number; projected_minor: number; recurring_arr_minor: number };
}

interface Capital {
  businesses: { business_id: string; name: string; available_capital_minor: number | null; open_p16_commitments_minor: number; runway_months: number | null }[];
  capital_commitments_frozen: boolean;
}

interface Experiment {
  id: string;
  title: string;
  status: string;
  budget_ceiling_minor: number;
  p08_experiment_id: string | null;
}

interface Country {
  country: string;
  total_score: number | null;
  status: string;
}

interface Risk {
  status?: string;
  detectors?: { kind: string; detail: string }[];
  scenarios?: { key: string; title: string; portfolio_net_profit_after_minor: number; businesses_loss_making_after: number }[];
  scenarios_label?: string;
}

interface Recommendation {
  priority: number;
  kind: string;
  title: string;
  rationale: string;
  gate_blocked: boolean;
}

const TABS = [
  "Overview",
  "Portfolio",
  "Opportunities",
  "Diversification",
  "Capital",
  "Experiments",
  "Global",
  "Risk",
  "Recommendations",
  "Approvals",
] as const;
type Tab = (typeof TABS)[number];

function GatePanel({ gate }: { gate: Gate }): React.ReactElement {
  return (
    <Panel title="Owner's profitability gate">
      <p>
        <StatusBadge value={gate.state === "open" ? "approved" : "blocked"} />{" "}
        <strong>{gate.state.toUpperCase()}</strong> — {gate.reason}
      </p>
      <p>
        While the gate is closed, new-business and market-entry work cannot be
        approved and the growth allocation scenario is refused. Profitability
        of the existing portfolio comes first; diversification second; capital
        efficiency third.
      </p>
    </Panel>
  );
}

function OverviewTab(): React.ReactElement {
  const status = useApi<Status>("/economy/status");
  const overview = useApi<Overview>("/economy/overview");
  const d = overview.data;
  const s = status.data;
  return (
    <>
      {overview.loading && !d ? <LoadingState label="Loading economy overview…" /> : null}
      {overview.error ? <ErrorState error={overview.error} onRetry={overview.reload} /> : null}
      {d && s ? (
        <>
          <GatePanel gate={d.profitability_gate} />
          <Panel title="Global economic overview (P-07, live)">
            <DataTable
              columns={[
                { key: "measure", label: "Measure" },
                { key: "value", label: "Value" },
              ]}
              rows={[
                { measure: "Businesses", value: formatNumber(d.businesses.total) },
                { measure: "With a P-07 financial profile", value: formatNumber(d.businesses.with_financial_profile) },
                { measure: "Verified collected revenue", value: formatMoney(d.global_economic_overview.total_verified_collected_revenue_minor) },
                { measure: "Net profit (verified)", value: d.global_economic_overview.total_net_profit_minor === null ? "insufficient data" : formatMoney(d.global_economic_overview.total_net_profit_minor) },
                { measure: "Actual expenses", value: d.global_economic_overview.total_actual_expenses_minor === null ? "insufficient data" : formatMoney(d.global_economic_overview.total_actual_expenses_minor) },
                { measure: "Combined available cash", value: "never summed — see Capital tab per business" },
                { measure: "Recurring share of collected", value: d.kpis.recurring_share_of_collected === null ? "n/a" : `${Math.round(d.kpis.recurring_share_of_collected * 100)}%` },
                { measure: "Revenue concentration (HHI)", value: d.kpis.revenue_concentration.hhi === null ? "n/a" : String(d.kpis.revenue_concentration.hhi) },
              ]}
              emptyTitle="No economic data"
              emptyDetail="No P-07 figures are available yet."
            />
            <p>
              Autonomy level {s.autonomy_level} (§18). Expansion{" "}
              {s.expansion_paused ? "PAUSED" : "not paused"}; capital commitments{" "}
              {s.capital_commitments_frozen ? "FROZEN" : "not frozen"}.
            </p>
          </Panel>
        </>
      ) : null}
    </>
  );
}

function PortfolioTab(): React.ReactElement {
  const data = useApi<{ items: ClassificationItem[]; overconcentration_flags: { business_id: string; revenue_share: number }[] }>(
    "/economy/classifications",
  );
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading portfolio…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Business portfolio (§5.1)">
          <DataTable
            columns={[
              { key: "name", label: "Business" },
              { key: "lifecycle", label: "Lifecycle" },
              { key: "industry", label: "Industry" },
              { key: "collected", label: "Collected" },
              { key: "profit", label: "Net profit" },
              { key: "share", label: "Revenue share" },
            ]}
            rows={d.items.map((i) => ({
              name: `${i.name}${i.is_fixture ? " (fixture)" : ""}`,
              lifecycle: i.lifecycle_label,
              industry: i.classification?.industry || "unclassified",
              collected: formatMoney(i.profitability.verified_collected_revenue_minor),
              profit: i.profitability.net_profit_minor === null ? "n/a" : formatMoney(i.profitability.net_profit_minor),
              share: i.revenue_share === null ? "n/a" : `${Math.round(i.revenue_share * 100)}%`,
            }))}
            emptyTitle="No businesses"
            emptyDetail="No businesses exist yet."
          />
          {d.overconcentration_flags.length > 0 ? (
            <p>
              Overconcentration: {d.overconcentration_flags.length} business(es) above
              the owner's revenue-share threshold.
            </p>
          ) : null}
        </Panel>
      ) : null}
    </>
  );
}

function OpportunitiesTab(): React.ReactElement {
  const data = useApi<{ items: Opportunity[] }>("/economy/opportunities");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading opportunities…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Opportunity discovery (§4.2/§4.3)">
          <DataTable
            columns={[
              { key: "title", label: "Opportunity" },
              { key: "kind", label: "Kind" },
              { key: "stage", label: "Stage" },
              { key: "score", label: "Score" },
              { key: "band", label: "Band" },
              { key: "confidence", label: "Confidence" },
            ]}
            rows={d.items.map((o) => ({
              title: o.title,
              kind: o.kind,
              stage: o.stage,
              score: o.total_score === null ? "unscored" : String(o.total_score),
              band: o.classification_band || "—",
              confidence: `${o.confidence}%`,
            }))}
            emptyTitle="No expansion opportunities"
            emptyDetail="Run discovery or record an opportunity to begin."
          />
          <p>
            Scores are prioritisation, never success probabilities. Approval requires
            the evidence gate: sufficient source-backed evidence, whatever the score.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function DiversificationTab(): React.ReactElement {
  const data = useApi<Diversification>("/economy/diversification");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading diversification…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Revenue diversification (§6)">
          <DataTable
            columns={[
              { key: "name", label: "Business" },
              { key: "collected", label: "Collected" },
              { key: "index", label: "Diversification index" },
            ]}
            rows={d.per_business.map((b) => ({
              name: `${b.name}${b.is_fixture ? " (fixture)" : ""}`,
              collected: b.net_collected_minor === null ? "n/a" : formatMoney(b.net_collected_minor),
              index: b.diversification_score === null ? b.diversification_status : String(b.diversification_score),
            }))}
            emptyTitle="No businesses"
            emptyDetail="No businesses exist yet."
          />
          <p>
            Collected {formatMoney(d.totals.net_collected_minor)} · Projected{" "}
            {formatMoney(d.totals.projected_minor)} (kept separate, never blended) ·
            Recurring ARR {formatMoney(d.totals.recurring_arr_minor)}.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function CapitalTab(): React.ReactElement {
  const data = useApi<Capital>("/economy/capital");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading capital view…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Capital allocation (§9/§10)">
          <DataTable
            columns={[
              { key: "name", label: "Business" },
              { key: "capital", label: "Available capital (P-07)" },
              { key: "open", label: "Open P-16 proposals" },
              { key: "runway", label: "Runway (months)" },
            ]}
            rows={d.businesses.map((b) => ({
              name: b.name,
              capital: b.available_capital_minor === null ? "no profile" : formatMoney(b.available_capital_minor),
              open: formatMoney(b.open_p16_commitments_minor),
              runway: b.runway_months === null ? "n/a" : String(b.runway_months),
            }))}
            emptyTitle="No businesses"
            emptyDetail="No businesses exist yet."
          />
          <p>
            Combined cash is never summed across businesses. P-16 recommendations are
            PROPOSED only — approval moves no money; execution stays with P-07.
            Capital commitments are {d.capital_commitments_frozen ? "FROZEN" : "not frozen"}.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function ExperimentsTab(): React.ReactElement {
  const data = useApi<{ items: Experiment[] }>("/economy/experiments");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading experiments…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Economic experiments (§11)">
          <DataTable
            columns={[
              { key: "title", label: "Experiment" },
              { key: "status", label: "Status" },
              { key: "ceiling", label: "Budget ceiling (PROPOSED)" },
              { key: "p08", label: "P-08 experiment" },
            ]}
            rows={d.items.map((e) => ({
              title: e.title,
              status: e.status,
              ceiling: formatMoney(e.budget_ceiling_minor),
              p08: e.p08_experiment_id || "not handed off",
            }))}
            emptyTitle="No experiment proposals"
            emptyDetail="Propose an experiment to begin governed testing."
          />
          <p>
            Every experiment is pre-declared (hypothesis, budget ceiling, stop
            conditions) and, once handed off, runs in P-08 against a real P-07 budget
            with a mechanical stop-loss.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function GlobalTab(): React.ReactElement {
  const data = useApi<{ items: Country[]; methodology: string }>("/economy/countries/ranking");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading global expansion…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Global expansion (§14)">
          <DataTable
            columns={[
              { key: "country", label: "Country" },
              { key: "score", label: "Entry score" },
              { key: "status", label: "Status" },
            ]}
            rows={d.items.map((c) => ({
              country: c.country,
              score: c.total_score === null ? "unscored" : String(c.total_score),
              status: c.status,
            }))}
            emptyTitle="No country assessments"
            emptyDetail="Assess a country to begin international evaluation."
          />
          <p>{d.methodology}</p>
        </Panel>
      ) : null}
    </>
  );
}

function RiskTab(): React.ReactElement {
  const data = useApi<Risk>("/economy/risk/latest");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading risk view…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d && d.status === "none_computed" ? (
        <Panel title="Risk intelligence (§12)">
          <p>No risk assessment has been computed yet.</p>
        </Panel>
      ) : null}
      {d && d.status !== "none_computed" ? (
        <>
          <Panel title="Detector findings (§12)">
            <DataTable
              columns={[
                { key: "kind", label: "Kind" },
                { key: "detail", label: "Finding" },
              ]}
              rows={(d.detectors || []).map((x) => ({ kind: x.kind, detail: x.detail }))}
              emptyTitle="No detector findings"
              emptyDetail="No concentration or dependency risk detected."
            />
          </Panel>
          <Panel title="Stress scenarios">
            <DataTable
              columns={[
                { key: "title", label: "Scenario" },
                { key: "after", label: "Portfolio net profit after" },
                { key: "loss", label: "Businesses loss-making" },
              ]}
              rows={(d.scenarios || []).map((s) => ({
                title: s.title,
                after: formatMoney(s.portfolio_net_profit_after_minor),
                loss: String(s.businesses_loss_making_after),
              }))}
              emptyTitle="No scenarios"
              emptyDetail="Scenarios are quantitatively inapplicable."
            />
            <p>{d.scenarios_label}</p>
          </Panel>
        </>
      ) : null}
    </>
  );
}

function RecommendationsTab(): React.ReactElement {
  const data = useApi<{ items: Recommendation[]; ordering: string }>("/economy/recommendations");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading recommendations…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Strategic recommendations (§15I)">
          <DataTable
            columns={[
              { key: "priority", label: "Priority" },
              { key: "kind", label: "Kind" },
              { key: "title", label: "Recommendation" },
              { key: "why", label: "Why" },
            ]}
            rows={d.items.map((r) => ({
              priority: String(r.priority),
              kind: r.kind,
              title: `${r.title}${r.gate_blocked ? " (gate-blocked)" : ""}`,
              why: r.rationale,
            }))}
            emptyTitle="No recommendations"
            emptyDetail="Recommendations appear when portfolio evidence supports them."
          />
          <p>{d.ordering}</p>
        </Panel>
      ) : null}
    </>
  );
}

function ApprovalsTab(): React.ReactElement {
  const allocations = useApi<{ items: { id: string; scenario: string; status: string }[] }>(
    "/economy/allocations?status=proposed",
  );
  const strategies = useApi<{ items: { id: string; title: string; kind: string; blocked_by_profitability_gate: boolean }[] }>(
    "/economy/strategies?status=proposed",
  );
  return (
    <>
      <Panel title="Pending capital recommendations (§9)">
        <DataTable
          columns={[
            { key: "scenario", label: "Scenario" },
            { key: "status", label: "Status" },
          ]}
          rows={(allocations.data?.items || []).map((a) => ({ scenario: a.scenario, status: a.status }))}
          emptyTitle="Nothing pending"
          emptyDetail="No capital recommendations await a decision."
        />
      </Panel>
      <Panel title="Pending strategies (§4.4)">
        <DataTable
          columns={[
            { key: "title", label: "Strategy" },
            { key: "kind", label: "Kind" },
            { key: "gate", label: "Gate" },
          ]}
          rows={(strategies.data?.items || []).map((s) => ({
            title: s.title,
            kind: s.kind,
            gate: s.blocked_by_profitability_gate ? "blocked by profitability gate" : "approvable",
          }))}
          emptyTitle="Nothing pending"
          emptyDetail="No strategies await a decision."
        />
      </Panel>
      <p>
        Decisions are owner actions through the governed API under hash-bound P-01
        approvals; this center lists what awaits them.
      </p>
    </>
  );
}

export function EconomyView(): React.ReactElement {
  const [tab, setTab] = useState<Tab>("Overview");
  const status = useApi<Status>("/economy/status");
  return (
    <div className="view">
      <PageHeader
        title="AI Economy & Expansion"
        subtitle="P-16 — portfolio economics over P-07's verified figures. Profitability first, diversification second, capital efficiency third."
        actions={<FreshnessBar updatedAt={status.updatedAt} />}
      />
      <div className="tab-bar" role="tablist" aria-label="Economy sections">
        {TABS.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? "tab active" : "tab"}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>
      {tab === "Overview" && <OverviewTab />}
      {tab === "Portfolio" && <PortfolioTab />}
      {tab === "Opportunities" && <OpportunitiesTab />}
      {tab === "Diversification" && <DiversificationTab />}
      {tab === "Capital" && <CapitalTab />}
      {tab === "Experiments" && <ExperimentsTab />}
      {tab === "Global" && <GlobalTab />}
      {tab === "Risk" && <RiskTab />}
      {tab === "Recommendations" && <RecommendationsTab />}
      {tab === "Approvals" && <ApprovalsTab />}
    </div>
  );
}
