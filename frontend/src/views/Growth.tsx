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

// P-17 §23: the Customer Acquisition & Revenue Growth Center.
// Every figure comes from the /growth/* endpoints, which read
// P-07 live: spend is P-07 recorded marketing expense, attributed
// revenue is P-07 verified collected revenue grouped by channel
// tag and is ALWAYS labelled ATTRIBUTED (attribution is not
// causation and never accounting revenue). The view renders no
// number of its own and offers no action the backend has not
// exposed; no platform is connected, no message is sent from here.

interface Gate {
  state: string;
  reason: string;
}

interface Status {
  autonomy_level: number;
  all_campaigns_paused: boolean;
  communications_stopped: boolean;
  outreach_suspended: boolean;
  marketing_spend_frozen: boolean;
  profitability_gate: Gate;
  counts: {
    campaigns: number;
    leads: number;
    customers: number;
    content_items: number;
    partnerships: number;
  };
  execution_capability: string;
}

interface BusinessGrowth {
  business_id: string;
  campaigns_total: number;
  active_campaigns: number;
  leads_total: number;
  customers_total: number;
  converted_customers: number;
  spend: { actual_spend_minor: number };
  attributed_revenue_minor: number;
  cac: { status: string; cac_minor: number | null };
}

interface Overview {
  totals: {
    campaigns_active: number;
    leads: number;
    customers: number;
    spend_minor: number;
    attributed_revenue_minor: number;
  };
  businesses: BusinessGrowth[];
  labels: { spend: string; attributed_revenue: string };
}

interface Campaign {
  id: string;
  name: string;
  code: string;
  purpose: string;
  status: string;
  channel_key: string;
  budget_ceiling_minor: number | null;
  attribution_channel: string;
}

interface Experiment {
  id: string;
  title: string;
  status: string;
  primary_metric: string;
  budget_ceiling_minor: number;
  p08_experiment_id: string | null;
}

interface Recommendation {
  kind: string;
  rank: number;
  business_id: string | null;
  title: string;
  detail: string;
  gate_blocked: boolean;
}

interface Portfolio {
  ranked_by_attributed_contribution: {
    business_id: string;
    attributed_contribution_minor: number;
  }[];
  cross_promotion: { status: string; rule: string };
  label: string;
}

const TABS = [
  "Overview",
  "Campaigns",
  "Portfolio",
  "Experiments",
  "Recommendations",
  "Agents & Integrations",
] as const;
type Tab = (typeof TABS)[number];

function GatePanel({ gate }: { gate: Gate }): React.ReactElement {
  return (
    <Panel title="Owner's profitability gate (P-16, consumed live)">
      <p>
        <StatusBadge value={gate.state === "open" ? "approved" : "blocked"} />{" "}
        <strong>{gate.state.toUpperCase()}</strong> — {gate.reason}
      </p>
      <p>
        While the gate is closed, expansion-purpose campaigns and strategies
        cannot be approved in this engine. The only bypass is a per-item owner
        override with a recorded reason; there is no global off-switch.
      </p>
    </Panel>
  );
}

function OverviewTab(): React.ReactElement {
  const status = useApi<Status>("/growth/status");
  const overview = useApi<Overview>("/growth/overview");
  const d = overview.data;
  const s = status.data;
  return (
    <>
      {overview.loading && !d ? <LoadingState label="Loading growth overview…" /> : null}
      {overview.error ? <ErrorState error={overview.error} onRetry={overview.reload} /> : null}
      {d && s ? (
        <>
          <GatePanel gate={s.profitability_gate} />
          <Panel title="Portfolio growth totals">
            <DataTable
              columns={[
                { key: "measure", label: "Measure" },
                { key: "value", label: "Value" },
              ]}
              rows={[
                { measure: "Active campaigns", value: formatNumber(d.totals.campaigns_active) },
                { measure: "Leads recorded", value: formatNumber(d.totals.leads) },
                { measure: "CRM customers", value: formatNumber(d.totals.customers) },
                { measure: "Marketing spend (P-07 recorded)", value: formatMoney(d.totals.spend_minor) },
                { measure: "Attributed revenue (P-07 verified, by channel tag)", value: formatMoney(d.totals.attributed_revenue_minor) },
              ]}
              emptyTitle="No growth data"
              emptyDetail="No growth records exist yet."
            />
            <p>{d.labels.attributed_revenue}</p>
            <p>
              Autonomy level {s.autonomy_level} (§24). Campaigns{" "}
              {s.all_campaigns_paused ? "PAUSED" : "not paused"}; communications{" "}
              {s.communications_stopped ? "STOPPED" : "not stopped"}; marketing
              spend {s.marketing_spend_frozen ? "FROZEN" : "not frozen"}.{" "}
              {s.execution_capability}
            </p>
          </Panel>
          <Panel title="Growth by business">
            <DataTable
              columns={[
                { key: "business", label: "Business" },
                { key: "leads", label: "Leads" },
                { key: "customers", label: "Customers" },
                { key: "spend", label: "Spend (P-07)" },
                { key: "attributed", label: "Attributed revenue" },
                { key: "cac", label: "CAC" },
              ]}
              rows={d.businesses.map((b) => ({
                business: b.business_id,
                leads: formatNumber(b.leads_total),
                customers: formatNumber(b.customers_total),
                spend: formatMoney(b.spend.actual_spend_minor),
                attributed: formatMoney(b.attributed_revenue_minor),
                cac: b.cac.cac_minor === null ? "insufficient data" : formatMoney(b.cac.cac_minor),
              }))}
              emptyTitle="No businesses"
              emptyDetail="No businesses exist yet."
            />
          </Panel>
        </>
      ) : null}
    </>
  );
}

function CampaignsTab(): React.ReactElement {
  const data = useApi<{ items: Campaign[] }>("/growth/campaigns");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading campaigns…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Campaigns (§7)">
          <DataTable
            columns={[
              { key: "name", label: "Campaign" },
              { key: "purpose", label: "Purpose" },
              { key: "status", label: "Status" },
              { key: "channel", label: "Channel" },
              { key: "ceiling", label: "Budget ceiling (proposal, not spend)" },
              { key: "tag", label: "Attribution tag" },
            ]}
            rows={d.items.map((c) => ({
              name: c.name,
              purpose: c.purpose,
              status: c.status,
              channel: c.channel_key || "—",
              ceiling: c.budget_ceiling_minor === null ? "none set" : formatMoney(c.budget_ceiling_minor),
              tag: c.attribution_channel,
            }))}
            emptyTitle="No campaigns"
            emptyDetail="Campaigns are created and approved through the governed API."
          />
          <p>
            Actual spend and attributed revenue are read live from P-07 per
            campaign; a ceiling is an approved proposal limit, never spend.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function PortfolioTab(): React.ReactElement {
  const data = useApi<Portfolio>("/growth/portfolio");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading portfolio growth…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Portfolio growth (§20)">
          <DataTable
            columns={[
              { key: "business", label: "Business" },
              { key: "contribution", label: "Attributed contribution (attributed revenue − spend)" },
            ]}
            rows={d.ranked_by_attributed_contribution.map((r) => ({
              business: r.business_id,
              contribution: formatMoney(r.attributed_contribution_minor),
            }))}
            emptyTitle="No businesses"
            emptyDetail="No businesses exist yet."
          />
          <p>
            Cross-promotion: {d.cross_promotion.status} — {d.cross_promotion.rule}
          </p>
          <p>{d.label}</p>
        </Panel>
      ) : null}
    </>
  );
}

function ExperimentsTab(): React.ReactElement {
  const data = useApi<{ items: Experiment[] }>("/growth/experiments");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading experiments…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Growth experiments (§14)">
          <DataTable
            columns={[
              { key: "title", label: "Experiment" },
              { key: "metric", label: "Primary metric" },
              { key: "status", label: "Status" },
              { key: "ceiling", label: "Budget ceiling (pre-declared)" },
              { key: "p08", label: "P-08 experiment" },
            ]}
            rows={d.items.map((e) => ({
              title: e.title,
              metric: e.primary_metric,
              status: e.status,
              ceiling: formatMoney(e.budget_ceiling_minor),
              p08: e.p08_experiment_id || "not handed off",
            }))}
            emptyTitle="No growth experiments"
            emptyDetail="Experiments are pre-declared in full before approval."
          />
          <p>
            Approved designs execute only in P-08, which binds a real P-07 budget
            and enforces the mechanical stop-loss. Below the declared minimum
            evaluation the verdict stays INSUFFICIENT_DATA.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function RecommendationsTab(): React.ReactElement {
  const data = useApi<{ items: Recommendation[]; ordering: string }>("/growth/recommendations");
  const d = data.data;
  return (
    <>
      {data.loading && !d ? <LoadingState label="Loading recommendations…" /> : null}
      {data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : null}
      {d ? (
        <Panel title="Growth recommendations (§19)">
          <DataTable
            columns={[
              { key: "kind", label: "Kind" },
              { key: "title", label: "Recommendation" },
              { key: "detail", label: "Detail" },
            ]}
            rows={d.items.map((r) => ({
              kind: r.kind,
              title: `${r.title}${r.gate_blocked ? " (gate-blocked)" : ""}`,
              detail: r.detail,
            }))}
            emptyTitle="No recommendations"
            emptyDetail="Recommendations appear when recorded evidence supports them."
          />
          <p>{d.ordering}</p>
        </Panel>
      ) : null}
    </>
  );
}

function AgentsTab(): React.ReactElement {
  const roles = useApi<{
    items: { name: string; role: string; template_status: string; external_send_capability: string }[];
    note: string;
  }>("/growth/agent-roles");
  const integrations = useApi<{
    items: { key: string; label: string; needed_for: string; state: string; state_label: string }[];
    note: string;
  }>("/growth/integrations");
  const r = roles.data;
  const i = integrations.data;
  return (
    <>
      {roles.loading && !r ? <LoadingState label="Loading agent roles…" /> : null}
      {roles.error ? <ErrorState error={roles.error} onRetry={roles.reload} /> : null}
      {r ? (
        <Panel title="Marketing agent roles (§12 — P-04 templates)">
          <DataTable
            columns={[
              { key: "name", label: "Role" },
              { key: "template", label: "Template" },
              { key: "send", label: "External send capability" },
            ]}
            rows={r.items.map((x) => ({
              name: x.name,
              template: x.template_status,
              send: x.external_send_capability,
            }))}
            emptyTitle="No roles seeded"
            emptyDetail="Agent role templates are seeded at startup."
          />
          <p>{r.note}</p>
        </Panel>
      ) : null}
      {i ? (
        <Panel title="External integrations">
          <DataTable
            columns={[
              { key: "label", label: "Surface" },
              { key: "needed", label: "Needed for" },
              { key: "state", label: "State" },
            ]}
            rows={i.items.map((x) => ({
              label: x.label,
              needed: x.needed_for,
              state: x.state_label,
            }))}
            emptyTitle="No integrations"
            emptyDetail="No integration surfaces are defined."
          />
          <p>{i.note}</p>
        </Panel>
      ) : null}
    </>
  );
}

export function GrowthView(): React.ReactElement {
  const [tab, setTab] = useState<Tab>("Overview");
  const status = useApi<Status>("/growth/status");
  return (
    <div className="view">
      <PageHeader
        title="Customer Acquisition & Growth"
        subtitle="P-17 — marketing and revenue growth over P-07's verified figures and the P-16 profitability gate. Attributed is labelled attributed; nothing here sends, posts or spends."
        actions={<FreshnessBar updatedAt={status.updatedAt} />}
      />
      <div className="tab-bar" role="tablist" aria-label="Growth sections">
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
      {tab === "Campaigns" && <CampaignsTab />}
      {tab === "Portfolio" && <PortfolioTab />}
      {tab === "Experiments" && <ExperimentsTab />}
      {tab === "Recommendations" && <RecommendationsTab />}
      {tab === "Agents & Integrations" && <AgentsTab />}
    </div>
  );
}
