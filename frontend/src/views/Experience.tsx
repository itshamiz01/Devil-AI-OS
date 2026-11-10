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
import { formatNumber } from "../lib/format";
import { useApi } from "../lib/hooks";

// P-18: the Customer Experience, Service Delivery & Customer
// Success Center. Every figure comes from the /experience/*
// endpoints. Customers are P-17 records (referenced, never
// copied); money is P-07's (refunds and goodwill exist only as
// P-07 records — this view shows references, never amounts the
// engine decided); no support channel is connected, so
// communications are shown as queued / dispatch-blocked, never
// sent. Health is a service-health classification from recorded
// signals — not a churn prediction and not sentiment.

interface Status {
  engine: string;
  autonomy_level: number;
  communications_stopped: boolean;
  counts: {
    onboardings: number;
    fulfillments: number;
    open_tickets: number;
    open_incidents: number;
    knowledge_articles: number;
    queued_communications: number;
  };
  customer_authority: string;
  financial_authority: string;
  workflow_authority: string;
  execution_capability: string;
}

interface PortfolioBusiness {
  business_id: string;
  business_name: string | null;
  counts: {
    onboardings_open: number;
    fulfillments_open: number;
    tickets_open: number;
    incidents_open: number;
    communications_queued: number;
    resolutions_recommended: number;
  };
  health_distribution: Record<string, number>;
  csat: { status: string; value: number | null; sample_size: number };
}

interface Portfolio {
  businesses: PortfolioBusiness[];
  note: string;
}

interface OnboardingDashboard {
  total: number;
  completed: number;
  incomplete: number;
  delayed: number;
  requiring_assistance: string[];
  average_completion_hours: number | null;
  success_rate_percent: number | null;
  note: string;
}

interface Onboarding {
  id: string;
  customer_id: string;
  status: string;
  steps_completed: number;
  steps_total: number;
  progress_percent: number;
  template_source: string;
  is_fixture: boolean;
}

interface Fulfillment {
  id: string;
  kind: string;
  title: string;
  status: string;
  status_source: string;
  acceptance: string;
  is_fixture: boolean;
}

interface Incident {
  id: string;
  kind: string;
  severity: string;
  status: string;
  detail: string;
}

interface Ticket {
  id: string;
  category: string;
  subject: string;
  priority: string;
  status: string;
  reopened_count: number;
  sla: { status: string };
}

interface SlaCompliance {
  status: string;
  reason?: string;
  compliance_percent?: number | null;
  tickets_total?: number;
  tickets_measured?: number;
  breached?: number;
}

interface Metric {
  status: string;
  value: number | null;
  sample_size?: number;
}

interface Metrics {
  csat: Metric;
  nps: Metric;
  customer_effort: Metric;
  basis: string;
  tickets_total: number;
  feedback_total: number;
}

interface HealthOverview {
  customers_with_snapshots: number;
  distribution: Record<string, number>;
  note: string;
}

interface Article {
  id: string;
  title: string;
  category: string;
  version: number;
  approval_status: string;
  review_status: string;
}

interface KbHealth {
  total: number;
  approved: number;
  draft: number;
  stale: string[];
  grounding_available: boolean;
  note: string;
}

interface QualitySummary {
  status: string;
  reason?: string;
  reviews?: number;
  average_score?: number | null;
  basis?: string;
}

interface Feedback {
  id: string;
  kind: string;
  score: number | null;
  source: string;
  comment: string;
  is_fixture: boolean;
}

interface Resolution {
  id: string;
  problem_class: string;
  action_kind: string;
  status: string;
  p07_refund_id: string | null;
  p07_spending_request_id: string | null;
  financial_authority: string;
}

const TABS = [
  "Overview",
  "Onboarding",
  "Fulfillment",
  "Support",
  "Customers & Health",
  "Knowledge",
  "Quality & Feedback",
] as const;
type Tab = (typeof TABS)[number];

function metricText(m: Metric | undefined): string {
  if (!m) return "—";
  if (m.status !== "computed" || m.value === null)
    return "insufficient data";
  return `${m.value} (n=${m.sample_size ?? 0})`;
}

function OverviewTab(): React.ReactElement {
  const status = useApi<Status>("/experience/status");
  const overview = useApi<Portfolio>("/experience/overview");
  const s = status.data;
  const d = overview.data;
  return (
    <>
      {overview.loading && !d ? (
        <LoadingState label="Loading experience overview…" />
      ) : null}
      {overview.error ? (
        <ErrorState error={overview.error} onRetry={overview.reload} />
      ) : null}
      {s ? (
        <Panel title="Engine posture">
          <p>
            Autonomy level {s.autonomy_level}. Communications{" "}
            {s.communications_stopped ? "STOPPED" : "not stopped"}.{" "}
            {s.execution_capability}
          </p>
          <p>
            Customers: <strong>{s.customer_authority}</strong> · Money:{" "}
            <strong>{s.financial_authority}</strong> · Workflows:{" "}
            <strong>{s.workflow_authority}</strong>. Refunds and goodwill
            exist only as P-07 records; this engine holds no money columns
            and sends nothing — no support channel is connected.
          </p>
        </Panel>
      ) : null}
      {d ? (
        <Panel title="Experience by business">
          <DataTable
            columns={[
              { key: "business", label: "Business" },
              { key: "onboarding", label: "Onboarding open" },
              { key: "fulfilment", label: "Fulfilment open" },
              { key: "tickets", label: "Tickets open" },
              { key: "incidents", label: "Incidents open" },
              { key: "queued", label: "Communications queued (never sent)" },
              { key: "csat", label: "CSAT (recorded)" },
            ]}
            rows={d.businesses.map((b) => ({
              business: b.business_name || b.business_id,
              onboarding: formatNumber(b.counts.onboardings_open),
              fulfilment: formatNumber(b.counts.fulfillments_open),
              tickets: formatNumber(b.counts.tickets_open),
              incidents: formatNumber(b.counts.incidents_open),
              queued: formatNumber(b.counts.communications_queued),
              csat: metricText(b.csat),
            }))}
            emptyTitle="No businesses"
            emptyDetail="No businesses exist yet."
          />
          <p>{d.note}</p>
        </Panel>
      ) : null}
    </>
  );
}

function OnboardingTab({ businessId }: { businessId: string | null }) {
  const path = businessId
    ? `/experience/businesses/${businessId}/onboarding-dashboard`
    : null;
  const listPath = businessId
    ? `/experience/businesses/${businessId}/onboardings`
    : null;
  const dashboard = useApi<OnboardingDashboard>(path);
  const list = useApi<{ items: Onboarding[] }>(listPath);
  const d = dashboard.data;
  const l = list.data;
  if (!businessId)
    return <Panel title="Onboarding"><p>Create a business first.</p></Panel>;
  return (
    <>
      {dashboard.loading && !d ? (
        <LoadingState label="Loading onboarding…" />
      ) : null}
      {dashboard.error ? (
        <ErrorState error={dashboard.error} onRetry={dashboard.reload} />
      ) : null}
      {d ? (
        <Panel title="Onboarding dashboard (§4)">
          <DataTable
            columns={[
              { key: "measure", label: "Measure" },
              { key: "value", label: "Value" },
            ]}
            rows={[
              { measure: "Total onboardings", value: formatNumber(d.total) },
              { measure: "Completed", value: formatNumber(d.completed) },
              { measure: "Incomplete", value: formatNumber(d.incomplete) },
              { measure: "Stalled / delayed", value: formatNumber(d.delayed) },
              {
                measure: "Requiring assistance",
                value: formatNumber(d.requiring_assistance.length),
              },
              {
                measure: "Average completion hours",
                value:
                  d.average_completion_hours === null
                    ? "not available"
                    : String(d.average_completion_hours),
              },
              {
                measure: "Success rate",
                value:
                  d.success_rate_percent === null
                    ? "not available"
                    : `${d.success_rate_percent}%`,
              },
            ]}
            emptyTitle="No onboardings"
            emptyDetail="Onboardings start from the governed API."
          />
          <p>{d.note}</p>
        </Panel>
      ) : null}
      {l ? (
        <Panel title="Onboardings">
          <DataTable
            columns={[
              { key: "customer", label: "Customer (P-17 record)" },
              { key: "status", label: "Status" },
              { key: "progress", label: "Progress" },
              { key: "template", label: "Template source" },
            ]}
            rows={l.items.map((o) => ({
              customer: o.customer_id,
              status: o.status,
              progress: `${o.steps_completed}/${o.steps_total} steps (${o.progress_percent}%)`,
              template: o.template_source,
            }))}
            emptyTitle="No onboardings"
            emptyDetail="No onboarding workflows exist for this business."
          />
        </Panel>
      ) : null}
    </>
  );
}

function FulfillmentTab({ businessId }: { businessId: string | null }) {
  const list = useApi<{ items: Fulfillment[] }>(
    businessId ? `/experience/businesses/${businessId}/fulfillments` : null,
  );
  const incidents = useApi<{ items: Incident[] }>(
    businessId ? `/experience/businesses/${businessId}/incidents` : null,
  );
  const l = list.data;
  const i = incidents.data;
  if (!businessId)
    return <Panel title="Fulfillment"><p>Create a business first.</p></Panel>;
  return (
    <>
      {l ? (
        <Panel title="Fulfilment records (§5)">
          <DataTable
            columns={[
              { key: "title", label: "Fulfilment" },
              { key: "kind", label: "Kind" },
              { key: "status", label: "Status" },
              { key: "source", label: "Status source" },
              { key: "acceptance", label: "Customer acceptance" },
            ]}
            rows={l.items.map((f) => ({
              title: f.title,
              kind: f.kind,
              status: f.status,
              source: f.status_source,
              acceptance: f.acceptance,
            }))}
            emptyTitle="No fulfilments"
            emptyDetail="Fulfilment states are recorded by operators; unverified stays labelled."
          />
          <p>
            No logistics or delivery integration is connected — a status is
            only ever as trustworthy as its recorded source label.
          </p>
        </Panel>
      ) : null}
      {i ? (
        <Panel title="Service incidents (evaluation pass)">
          <DataTable
            columns={[
              { key: "kind", label: "Incident" },
              { key: "severity", label: "Severity" },
              { key: "status", label: "Status" },
              { key: "detail", label: "Detail" },
            ]}
            rows={i.items.map((x) => ({
              kind: x.kind,
              severity: x.severity,
              status: x.status,
              detail: x.detail,
            }))}
            emptyTitle="No incidents"
            emptyDetail="The deterministic evaluation pass raises incidents from recorded state."
          />
        </Panel>
      ) : null}
    </>
  );
}

function SupportTab({ businessId }: { businessId: string | null }) {
  const tickets = useApi<{ items: Ticket[] }>(
    businessId ? `/experience/businesses/${businessId}/tickets` : null,
  );
  const sla = useApi<SlaCompliance>(
    businessId ? `/experience/businesses/${businessId}/sla-compliance` : null,
  );
  const t = tickets.data;
  const s = sla.data;
  if (!businessId)
    return <Panel title="Support"><p>Create a business first.</p></Panel>;
  return (
    <>
      {s ? (
        <Panel title="SLA compliance (§7)">
          {s.status === "NOT_AVAILABLE" ? (
            <p>
              <StatusBadge value="blocked" /> NOT AVAILABLE — {s.reason}
            </p>
          ) : (
            <p>
              Compliance {s.compliance_percent ?? "—"}% over{" "}
              {s.tickets_measured ?? 0} measured tickets (
              {s.breached ?? 0} breached). Targets exist only where the
              owner configured them; no SLA is invented.
            </p>
          )}
        </Panel>
      ) : null}
      {t ? (
        <Panel title="Support cases">
          <DataTable
            columns={[
              { key: "subject", label: "Case" },
              { key: "category", label: "Category" },
              { key: "priority", label: "Priority (explainable)" },
              { key: "status", label: "Status" },
              { key: "sla", label: "SLA" },
              { key: "reopened", label: "Reopened" },
            ]}
            rows={t.items.map((x) => ({
              subject: x.subject,
              category: x.category,
              priority: x.priority,
              status: x.status,
              sla: x.sla.status,
              reopened: formatNumber(x.reopened_count),
            }))}
            emptyTitle="No support cases"
            emptyDetail="Tickets are recorded by operators — no inbox or chat is connected."
          />
          <p>
            Escalations are P-12 workflows. The support assistant answers
            only from approved knowledge articles and escalates what it
            cannot verify.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function HealthTab({ businessId }: { businessId: string | null }) {
  const metrics = useApi<Metrics>(
    businessId ? `/experience/businesses/${businessId}/metrics` : null,
  );
  const health = useApi<HealthOverview>(
    businessId ? `/experience/businesses/${businessId}/health` : null,
  );
  const m = metrics.data;
  const h = health.data;
  if (!businessId)
    return (
      <Panel title="Customers & Health"><p>Create a business first.</p></Panel>
    );
  return (
    <>
      {m ? (
        <Panel title="Experience metrics (§16 — recorded data only)">
          <DataTable
            columns={[
              { key: "metric", label: "Metric" },
              { key: "value", label: "Value (with sample size)" },
            ]}
            rows={[
              { metric: "CSAT (1–5)", value: metricText(m.csat) },
              { metric: "NPS (0–10)", value: metricText(m.nps) },
              { metric: "Customer effort (1–5)", value: metricText(m.customer_effort) },
              { metric: "Tickets total", value: formatNumber(m.tickets_total) },
              { metric: "Feedback records", value: formatNumber(m.feedback_total) },
            ]}
            emptyTitle="No metrics"
            emptyDetail="Metrics appear when feedback and cases are recorded."
          />
          <p>{m.basis}</p>
        </Panel>
      ) : null}
      {h ? (
        <Panel title="Customer health (§12)">
          <DataTable
            columns={[
              { key: "classification", label: "Classification" },
              { key: "customers", label: "Customers" },
            ]}
            rows={Object.entries(h.distribution).map(([k, v]) => ({
              classification: k,
              customers: formatNumber(v),
            }))}
            emptyTitle="No health snapshots"
            emptyDetail="Health is computed per customer from recorded signals."
          />
          <p>
            {h.note} A classification is a service-health signal from
            recorded evidence — never a churn prediction and never a
            reading of customer sentiment.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function KnowledgeTab({ businessId }: { businessId: string | null }) {
  const articles = useApi<{ items: Article[] }>(
    businessId ? `/experience/businesses/${businessId}/articles` : null,
  );
  const kb = useApi<KbHealth>(
    businessId ? `/experience/businesses/${businessId}/kb-health` : null,
  );
  const a = articles.data;
  const k = kb.data;
  if (!businessId)
    return <Panel title="Knowledge"><p>Create a business first.</p></Panel>;
  return (
    <>
      {k ? (
        <Panel title="Knowledge base health (§13)">
          <p>
            {k.approved} approved of {k.total} articles; {k.draft} in draft;{" "}
            {k.stale.length} flagged stale. Grounding{" "}
            {k.grounding_available ? "available" : "NOT available"}.
          </p>
          <p>{k.note}</p>
        </Panel>
      ) : null}
      {a ? (
        <Panel title="Articles">
          <DataTable
            columns={[
              { key: "title", label: "Article" },
              { key: "category", label: "Category" },
              { key: "version", label: "Version" },
              { key: "approval", label: "Approval" },
              { key: "review", label: "Review" },
            ]}
            rows={a.items.map((x) => ({
              title: x.title,
              category: x.category,
              version: `v${x.version}`,
              approval: x.approval_status,
              review: x.review_status,
            }))}
            emptyTitle="No articles"
            emptyDetail="Only approved, current articles ground support answers."
          />
          <p>
            The assistant quotes approved articles with pinned citations and
            answers “insufficient information” — escalating to a human —
            rather than inventing a policy.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

function QualityTab({ businessId }: { businessId: string | null }) {
  const quality = useApi<QualitySummary>(
    businessId ? `/experience/businesses/${businessId}/quality-summary` : null,
  );
  const feedback = useApi<{ items: Feedback[] }>(
    businessId ? `/experience/businesses/${businessId}/feedback` : null,
  );
  const resolutions = useApi<{ items: Resolution[] }>(
    businessId ? `/experience/businesses/${businessId}/resolutions` : null,
  );
  const q = quality.data;
  const f = feedback.data;
  const r = resolutions.data;
  if (!businessId)
    return (
      <Panel title="Quality & Feedback"><p>Create a business first.</p></Panel>
    );
  return (
    <>
      {q ? (
        <Panel title="Support quality (§9 — sampled QA reviews)">
          {q.status === "INSUFFICIENT_DATA" ? (
            <p>INSUFFICIENT DATA — {q.reason}</p>
          ) : (
            <p>
              Average review score {q.average_score ?? "—"} across{" "}
              {q.reviews ?? 0} sampled reviews. {q.basis}
            </p>
          )}
        </Panel>
      ) : null}
      {f ? (
        <Panel title="Recorded feedback (§10)">
          <DataTable
            columns={[
              { key: "kind", label: "Kind" },
              { key: "score", label: "Score" },
              { key: "source", label: "Source" },
              { key: "comment", label: "Comment" },
            ]}
            rows={f.items.map((x) => ({
              kind: x.kind,
              score: x.score === null ? "—" : String(x.score),
              source: x.source,
              comment: x.comment || "—",
            }))}
            emptyTitle="No feedback recorded"
            emptyDetail="Feedback is recorded from real responses — never estimated."
          />
        </Panel>
      ) : null}
      {r ? (
        <Panel title="Resolutions & service recovery (§11)">
          <DataTable
            columns={[
              { key: "problem", label: "Problem class" },
              { key: "action", label: "Action" },
              { key: "status", label: "Status" },
              { key: "p07", label: "P-07 record" },
            ]}
            rows={r.items.map((x) => ({
              problem: x.problem_class,
              action: x.action_kind,
              status: x.status,
              p07: x.p07_refund_id
                ? `refund ${x.p07_refund_id}`
                : x.p07_spending_request_id
                  ? `spend request ${x.p07_spending_request_id}`
                  : "—",
            }))}
            emptyTitle="No resolutions"
            emptyDetail="Financial remedies execute only as P-07 records after owner approval."
          />
          <p>
            Financial authority: P-07. A recommendation moves no money; an
            approved refund executes as a P-07 refund against verified
            revenue, and goodwill as a P-07 spending request.
          </p>
        </Panel>
      ) : null}
    </>
  );
}

export function ExperienceView(): React.ReactElement {
  const [tab, setTab] = useState<Tab>("Overview");
  const [selected, setSelected] = useState<string | null>(null);
  const status = useApi<Status>("/experience/status");
  const overview = useApi<Portfolio>("/experience/overview");
  const businesses = overview.data?.businesses ?? [];
  const businessId =
    selected ?? (businesses.length > 0 ? businesses[0].business_id : null);
  return (
    <div className="view">
      <PageHeader
        title="Customer Experience & Success"
        subtitle="P-18 — post-purchase service delivery, support, and customer success over P-17's customers and P-07's money. Nothing is sent, shipped or refunded from here."
        actions={<FreshnessBar updatedAt={status.updatedAt} />}
      />
      {businesses.length > 1 ? (
        <label className="business-picker">
          Business{" "}
          <select
            aria-label="Business"
            value={businessId ?? ""}
            onChange={(e) => setSelected(e.target.value)}
          >
            {businesses.map((b) => (
              <option key={b.business_id} value={b.business_id}>
                {b.business_name || b.business_id}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <div className="tab-bar" role="tablist" aria-label="Experience sections">
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
      {tab === "Onboarding" && <OnboardingTab businessId={businessId} />}
      {tab === "Fulfillment" && <FulfillmentTab businessId={businessId} />}
      {tab === "Support" && <SupportTab businessId={businessId} />}
      {tab === "Customers & Health" && <HealthTab businessId={businessId} />}
      {tab === "Knowledge" && <KnowledgeTab businessId={businessId} />}
      {tab === "Quality & Feedback" && <QualityTab businessId={businessId} />}
    </div>
  );
}
