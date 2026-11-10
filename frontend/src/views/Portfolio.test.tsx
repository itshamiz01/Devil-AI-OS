import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { PortfolioView } from "./Portfolio";

// Stubbed API values — the view must render exactly these (§21
// Scenario 17, UI half: the Command Center displays the portfolio
// information the API returns, nothing invented).

const PORTFOLIO = {
  id: "pf-1",
  name: "Owner Portfolio",
  mission: "",
  status: "ACTIVE",
  survival_mode: false,
};

const MEMBERS = [
  {
    business_id: "biz-a",
    status: "ACTIVE",
    strategic_priority: 60,
    group_labels: ["core"],
    business: {
      business_id: "biz-a",
      name: "Alpha Ebook",
      category: "digital_products",
      portfolio_stage: "OPERATIONAL",
      p06_state: "OPERATIONAL",
      p08_overlay_state: "STABLE",
      is_fixture: true,
    },
  },
  {
    business_id: "biz-b",
    status: "ACTIVE",
    strategic_priority: 40,
    group_labels: [],
    business: {
      business_id: "biz-b",
      name: "Beta Course",
      category: "online_courses",
      portfolio_stage: "BUILDING",
      p06_state: "IN_DEVELOPMENT",
      p08_overlay_state: null,
      is_fixture: true,
    },
  },
];

const OVERVIEW = {
  portfolio: PORTFOLIO,
  total_businesses: 2,
  active_businesses: 2,
  businesses_at_risk: 0,
  stage_counts: { OPERATIONAL: 1, BUILDING: 1 },
  members: MEMBERS,
  survival_mode: false,
};

const FINANCE = {
  businesses: [
    {
      business_id: "biz-a",
      name: "Alpha Ebook",
      net_collected_minor: 500000,
      collected_minor: 500000,
      projected_minor: 900000,
    },
    {
      business_id: "biz-b",
      name: "Beta Course",
      net_collected_minor: 150000,
      collected_minor: 150000,
      projected_minor: 300000,
    },
  ],
  totals: {
    net_collected_minor: 650000,
    collected_minor: 650000,
    projected_minor: 1200000,
    basis: "sums of the per-business P-07 flow figures above",
  },
  combined_available_cash: null,
  combined_cash_note:
    "cash balances of separate businesses are never summed and presented as freely available portfolio cash (§11)",
  internal_allocations: [
    {
      id: "alloc-1",
      business_id: "biz-a",
      amount_minor: 7500,
      kind: "INTERNAL_ALLOCATION",
      is_external_payment: false,
      presentation:
        "internal management allocation — not an external cash payment",
      method: "usage_based",
      status: "APPROVED",
    },
  ],
};

const OPPORTUNITIES = {
  items: [
    {
      id: "opp-1",
      category: "SHARED_SERVICE",
      title: "Adopt shared service: Shared Analytics",
      evidence_status: "VERIFIED",
      confidence: "moderate",
      status: "PROPOSED",
      involved_business_ids: ["biz-a", "biz-b"],
    },
    {
      id: "opp-2",
      category: "SHARED_AUDIENCE",
      title: "Maybe synergy",
      evidence_status: "SPECULATIVE",
      confidence: "low",
      status: "PROPOSED",
      involved_business_ids: ["biz-a", "biz-b"],
    },
  ],
  total: 2,
};

function stubAll() {
  return installFetchStub({
    "/portfolio/portfolios/pf-1/overview": () => OVERVIEW,
    "/portfolio/portfolios/pf-1/finance": () => FINANCE,
    "/portfolio/portfolios/pf-1/opportunities": () => OPPORTUNITIES,
    "/portfolio/portfolios/pf-1/recommendations": () => ({ items: [], total: 0 }),
    "/portfolio/portfolios": () => ({ items: [PORTFOLIO], total: 1 }),
    "/portfolio/relationships": () => ({ items: [], total: 0 }),
    "/portfolio/compare": () => ({
      businesses: [
        {
          business_id: "biz-a",
          name: "Alpha Ebook",
          portfolio_stage: "OPERATIONAL",
          net_collected_minor: 500000,
          projected_minor: 900000,
        },
        {
          business_id: "biz-b",
          name: "Beta Course",
          portfolio_stage: "BUILDING",
          net_collected_minor: 150000,
          projected_minor: 300000,
        },
      ],
    }),
  });
}

describe("PortfolioView (P-13 §18)", () => {
  beforeEach(() => {
    signIn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("renders the overview with exactly the API's values (Scenario 17)", async () => {
    stubAll();
    render(
      <AppProviders>
        <PortfolioView />
      </AppProviders>,
    );
    expect(await screen.findByText("Alpha Ebook")).toBeInTheDocument();
    expect(screen.getByText("Beta Course")).toBeInTheDocument();
    // StatusBadge humanizes values; stages appear in both the stage
    // table and the member rows — all from API values.
    expect(screen.getAllByText("Operational").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Building").length).toBeGreaterThan(0);
    // The two businesses are counted, not merged.
    expect(screen.getByText("2", { selector: ".metric-value" })).toBeInTheDocument();
  });

  it("finance tab keeps collected/projected separate and never combines cash", async () => {
    stubAll();
    render(
      <AppProviders>
        <PortfolioView />
      </AppProviders>,
    );
    await screen.findByText("Alpha Ebook");
    fireEvent.click(screen.getByRole("tab", { name: "Finance" }));
    // ₹6,500.00 verified collected total from the API payload.
    expect(await screen.findByText("₹6,500.00")).toBeInTheDocument();
    expect(screen.getByText("Not combined")).toBeInTheDocument();
    expect(
      screen.getByText(/never summed and presented as freely available/),
    ).toBeInTheDocument();
    // Internal allocation is labelled as internal, never a payment.
    expect(screen.getByText("INTERNAL_ALLOCATION")).toBeInTheDocument();
    expect(screen.getByText("₹75.00")).toBeInTheDocument();
  });

  it("intelligence tab labels speculative opportunities as speculative", async () => {
    stubAll();
    render(
      <AppProviders>
        <PortfolioView />
      </AppProviders>,
    );
    await screen.findByText("Alpha Ebook");
    fireEvent.click(screen.getByRole("tab", { name: "Intelligence" }));
    expect(
      await screen.findByText("Adopt shared service: Shared Analytics"),
    ).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Speculative")).toBeInTheDocument();
  });

  it("comparison tab shows each business's own figures side by side", async () => {
    stubAll();
    render(
      <AppProviders>
        <PortfolioView />
      </AppProviders>,
    );
    await screen.findByText("Alpha Ebook");
    fireEvent.click(screen.getByRole("tab", { name: "Comparison" }));
    expect(await screen.findByText("₹5,000.00")).toBeInTheDocument();
    expect(screen.getByText("₹1,500.00")).toBeInTheDocument();
  });

  it("shows an honest empty state when no portfolio exists", async () => {
    installFetchStub({
      "/portfolio/portfolios": () => ({ items: [], total: 0 }),
    });
    render(
      <AppProviders>
        <PortfolioView />
      </AppProviders>,
    );
    expect(await screen.findByText("No portfolios yet")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("Alpha Ebook")).not.toBeInTheDocument(),
    );
  });
});
