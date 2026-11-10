import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { EconomyView } from "./Economy";

// Stubbed API values — the view must render exactly these (P-16
// §15: the Expansion Center displays P-07's verified economics and
// the profitability gate; nothing is invented client-side).

const GATE = {
  state: "closed",
  reason: "aggregate verified net profit is not positive (fixture figures)",
  businesses_profiled: 1,
  total_collected_minor: 350000,
  total_net_profit_minor: -300000,
};

const STATUS = {
  generated_at: "2026-11-10T08:00:00+00:00",
  module: "p16-economy",
  autonomy_level: 2,
  expansion_paused: false,
  capital_commitments_frozen: false,
  profitability_gate: GATE,
  settings: {},
};

const OVERVIEW = {
  generated_at: "2026-11-10T08:00:00+00:00",
  businesses: { total: 1, with_financial_profile: 1 },
  global_economic_overview: {
    total_verified_collected_revenue_minor: 350000,
    total_net_profit_minor: -300000,
    total_actual_expenses_minor: 650000,
    combined_available_cash: null,
    combined_cash_note: "combined cash is never summed across businesses",
  },
  profitability_gate: GATE,
  kpis: {
    recurring_share_of_collected: null,
    revenue_concentration: { hhi: 10000, top_share: 1.0, overconcentrated: true },
  },
};

const CLASSIFICATIONS = {
  items: [
    {
      business_id: "biz-1",
      name: "Fixture Books",
      is_fixture: true,
      p06_status: "OPERATIONAL",
      lifecycle_label: "Established",
      classification: { industry: "publishing", revenue_model: "one_off", market: "global" },
      profitability: { verified_collected_revenue_minor: 350000, net_profit_minor: -300000 },
      revenue_share: 1.0,
    },
  ],
  thresholds: { concentration_threshold_bps: 6000 },
  overconcentration_flags: [{ business_id: "biz-1", revenue_share: 1.0 }],
};

function stubAll() {
  return installFetchStub({
    "/economy/status": () => STATUS,
    "/economy/overview": () => OVERVIEW,
    "/economy/classifications": () => CLASSIFICATIONS,
  });
}

describe("EconomyView (P-16 §15)", () => {
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
        <EconomyView />
      </AppProviders>,
    );
    expect(await screen.findByText("Owner's profitability gate")).toBeInTheDocument();
    expect(screen.getByText(/CLOSED/)).toBeInTheDocument();
    expect(screen.getByText(/aggregate verified net profit is not positive/)).toBeInTheDocument();
    expect(screen.getByText(/Profitability of the existing portfolio comes first/)).toBeInTheDocument();
  });

  it("renders P-07's verified figures and never a summed combined cash", async () => {
    stubAll();
    render(
      <AppProviders>
        <EconomyView />
      </AppProviders>,
    );
    expect(await screen.findByText("₹3,500.00")).toBeInTheDocument();
    expect(screen.getByText("never summed — see Capital tab per business")).toBeInTheDocument();
    expect(screen.getByText(/Autonomy level 2/)).toBeInTheDocument();
  });

  it("portfolio tab marks fixtures and the overconcentration flag", async () => {
    stubAll();
    render(
      <AppProviders>
        <EconomyView />
      </AppProviders>,
    );
    await screen.findByText("Owner's profitability gate");
    fireEvent.click(screen.getByRole("tab", { name: "Portfolio" }));
    expect(await screen.findByText("Fixture Books (fixture)")).toBeInTheDocument();
    expect(screen.getByText("Established")).toBeInTheDocument();
    expect(screen.getByText(/Overconcentration: 1 business\(es\)/)).toBeInTheDocument();
  });
});
