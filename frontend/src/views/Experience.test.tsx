import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { ExperienceView } from "./Experience";

// Stubbed API values — the view must render exactly these (P-18:
// customers are P-17 records, money is P-07's, communications are
// never presented as sent, health is a recorded-signal
// classification, and metrics carry their sample sizes).

const STATUS = {
  engine: "P-18 Customer Experience, Service Delivery & Customer Success Engine",
  autonomy_level: 1,
  communications_stopped: false,
  counts: {
    onboardings: 2,
    fulfillments: 1,
    open_tickets: 1,
    open_incidents: 0,
    knowledge_articles: 3,
    queued_communications: 1,
  },
  customer_authority: "P-17 (crm_customers)",
  financial_authority: "P-07",
  workflow_authority: "P-12",
  execution_capability:
    "none — records, coordinates and measures service delivery; sends nothing",
};

const OVERVIEW = {
  businesses: [
    {
      business_id: "biz-1",
      business_name: "Fixture Shop",
      counts: {
        onboardings_open: 1,
        fulfillments_open: 1,
        tickets_open: 1,
        incidents_open: 0,
        communications_queued: 1,
        resolutions_recommended: 0,
      },
      health_distribution: { healthy: 1 },
      csat: { status: "computed", value: 4.5, sample_size: 2 },
    },
  ],
  note: "aggregates are computed live per business; no customer data crosses businesses",
};

const SLA = {
  status: "NOT_AVAILABLE",
  reason:
    "no SLA policy is configured for this business; compliance is not computed against invented targets",
  tickets_total: 1,
};

const TICKETS = {
  items: [
    {
      id: "t-1",
      category: "account_access",
      subject: "Locked out of account",
      priority: "high",
      status: "in_progress",
      reopened_count: 0,
      sla: { status: "not_configured" },
    },
  ],
  count: 1,
};

const METRICS = {
  csat: { status: "computed", value: 4.5, sample_size: 2 },
  nps: { status: "INSUFFICIENT_DATA", value: null, sample_size: 0 },
  customer_effort: { status: "computed", value: 2.0, sample_size: 1 },
  basis:
    "recorded P-18 data only; every figure carries its sample size",
  tickets_total: 1,
  feedback_total: 3,
};

const HEALTH = {
  customers_with_snapshots: 1,
  distribution: { healthy: 1 },
  note: "classifications come from recorded signals only",
};

function stubAll() {
  return installFetchStub({
    "/experience/status": () => STATUS,
    "/experience/overview": () => OVERVIEW,
    "/experience/businesses/biz-1/sla-compliance": () => SLA,
    "/experience/businesses/biz-1/tickets": () => TICKETS,
    "/experience/businesses/biz-1/metrics": () => METRICS,
    "/experience/businesses/biz-1/health": () => HEALTH,
  });
}

describe("ExperienceView (P-18)", () => {
  beforeEach(() => {
    signIn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("renders the authorities and never-sent posture", async () => {
    stubAll();
    render(
      <AppProviders>
        <ExperienceView />
      </AppProviders>,
    );
    expect(await screen.findByText("Engine posture")).toBeInTheDocument();
    expect(screen.getByText(/P-17 \(crm_customers\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/Communications queued \(never sent\)/),
    ).toBeInTheDocument();
    expect(screen.getByText("4.5 (n=2)")).toBeInTheDocument();
    expect(screen.getByText("Fixture Shop")).toBeInTheDocument();
  });

  it("support tab shows SLA NOT AVAILABLE honestly, with the case", async () => {
    stubAll();
    render(
      <AppProviders>
        <ExperienceView />
      </AppProviders>,
    );
    await screen.findByText("Engine posture");
    fireEvent.click(screen.getByRole("tab", { name: "Support" }));
    expect(
      await screen.findByText(/NOT AVAILABLE — no SLA policy is configured/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Locked out of account"),
    ).toBeInTheDocument();
    expect(screen.getByText("not_configured")).toBeInTheDocument();
  });

  it("health tab labels metrics with samples and refuses sentiment claims", async () => {
    stubAll();
    render(
      <AppProviders>
        <ExperienceView />
      </AppProviders>,
    );
    await screen.findByText("Engine posture");
    fireEvent.click(screen.getByRole("tab", { name: "Customers & Health" }));
    expect(
      await screen.findByText("Experience metrics (§16 — recorded data only)"),
    ).toBeInTheDocument();
    expect(screen.getByText("insufficient data")).toBeInTheDocument();
    expect(
      screen.getByText(/never a churn prediction/),
    ).toBeInTheDocument();
  });
});
