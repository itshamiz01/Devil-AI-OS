import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { GrowthView } from "./Growth";

// Stubbed API values — the view must render exactly these (P-17
// §23: the Growth Center displays P-07's recorded spend and
// ATTRIBUTED verified revenue, with the P-16 gate state; nothing
// is invented client-side and nothing is presented as sent).

const GATE = {
  state: "closed",
  reason: "no verified collected revenue in any business (fixture figures)",
  businesses_profiled: 1,
  total_collected_minor: 0,
  total_net_profit_minor: null,
};

const STATUS = {
  engine: "P-17 Customer Acquisition, Marketing & Revenue Growth Engine",
  autonomy_level: 2,
  all_campaigns_paused: false,
  communications_stopped: false,
  outreach_suspended: false,
  marketing_spend_frozen: false,
  profitability_gate: GATE,
  counts: { campaigns: 1, leads: 3, customers: 1, content_items: 2, partnerships: 0 },
  execution_capability:
    "none — research, preparation, governed approvals and measurement only",
  generated_at: "2026-11-10T08:00:00+00:00",
};

const OVERVIEW = {
  profitability_gate: GATE,
  totals: {
    campaigns_active: 1,
    leads: 3,
    customers: 1,
    spend_minor: 120000,
    attributed_revenue_minor: 549900,
  },
  businesses: [
    {
      business_id: "biz-1",
      campaigns_total: 1,
      active_campaigns: 1,
      leads_total: 3,
      leads_by_stage: { new: 2, converted: 1 },
      customers_total: 1,
      converted_customers: 1,
      spend: { actual_spend_minor: 120000, source: "P-07" },
      attributed_revenue_minor: 549900,
      attributed_revenue_label: "ATTRIBUTED (channel-tagged verified collected revenue, P-07)",
      cac: { status: "computed", cac_minor: 120000 },
      note: "growth health is judged against P-07 verified profit",
    },
  ],
  labels: {
    spend: "P-07 marketing/advertising expenses (recorded, approved)",
    attributed_revenue:
      "ATTRIBUTED verified collected revenue (P-07, by channel tag); attribution is not causation",
  },
};

const ROLES = {
  items: [
    {
      name: "Marketing Analytics Agent",
      role: "p17_marketing_analytics_agent",
      capabilities: ["internal_reasoning"],
      permission_summary: "Produce labelled growth analytics.",
      template_status: "published",
      external_send_capability: "none — no external-send capability exists in the P-04 catalogue",
    },
  ],
  count: 17,
  note: "roles are P-04 Agent Factory templates (seeded by P-17)",
};

const INTEGRATIONS = {
  items: [
    {
      key: "email_transport",
      label: "Email transport (SMTP/provider)",
      needed_for: "sending any customer communication",
      state: "not_configured",
      state_label: "REQUIRES OWNER CONFIGURATION",
    },
  ],
  note: "no external marketing platform, transport or data feed is connected",
};

function stubAll() {
  return installFetchStub({
    "/growth/status": () => STATUS,
    "/growth/overview": () => OVERVIEW,
    "/growth/agent-roles": () => ROLES,
    "/growth/integrations": () => INTEGRATIONS,
  });
}

describe("GrowthView (P-17 §23)", () => {
  beforeEach(() => {
    signIn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("renders the profitability gate closed, first, with its reason", async () => {
    stubAll();
    render(
      <AppProviders>
        <GrowthView />
      </AppProviders>,
    );
    expect(
      await screen.findByText("Owner's profitability gate (P-16, consumed live)"),
    ).toBeInTheDocument();
    expect(screen.getByText(/CLOSED/)).toBeInTheDocument();
    expect(
      screen.getByText(/no verified collected revenue in any business/),
    ).toBeInTheDocument();
  });

  it("renders P-07 spend and ATTRIBUTED revenue, never as collected", async () => {
    stubAll();
    render(
      <AppProviders>
        <GrowthView />
      </AppProviders>,
    );
    // spend appears in the totals and the per-business table (and
    // as the CAC); attributed revenue in totals and per-business
    expect(
      (await screen.findAllByText("₹1,200.00")).length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("₹5,499.00").length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText(/attribution is not causation/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Autonomy level 2/)).toBeInTheDocument();
  });

  it("agents & integrations tab shows honest not-configured states", async () => {
    stubAll();
    render(
      <AppProviders>
        <GrowthView />
      </AppProviders>,
    );
    await screen.findByText("Owner's profitability gate (P-16, consumed live)");
    fireEvent.click(screen.getByRole("tab", { name: "Agents & Integrations" }));
    expect(
      await screen.findByText("Marketing Analytics Agent"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("REQUIRES OWNER CONFIGURATION"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no external marketing platform, transport or data feed is connected/),
    ).toBeInTheDocument();
  });
});
