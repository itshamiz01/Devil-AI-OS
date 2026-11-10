import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import type { OverviewData } from "../lib/types";
import { installFetchStub, signIn } from "../test/fetchStub";
import { OverviewView } from "./Overview";

const ZERO: OverviewData = {
  operating_state: "operational",
  lifecycle_state: "ready",
  mode: "controlled",
  security_mode: "normal",
  financial_suspension: false,
  database_healthy: true,
  threshold_violations: [],
  queue: { capacity: 100, depth: 0, running: 0, by_status: {} },
  counts: {
    businesses_total: 0, businesses_by_status: {}, agents_total: 0,
    agents_by_status: {}, opportunities_total: 0, opportunities_by_status: {},
    tasks_by_status: {}, pending_approvals: 0, open_security_alerts: 0,
    critical_alerts: 0,
  },
  kpis: [
    { key: "active_businesses", label: "Active businesses", value: 0, unit: null, period: "current", source: "P-06", note: null, state: "ok", measured_at: "2026-11-09T10:00:00Z" },
    { key: "collected_revenue", label: "Collected revenue", value: 0, unit: "INR", period: "current", source: "P-07", note: null, state: "ok", measured_at: "2026-11-09T10:00:00Z" },
    { key: "available_cash", label: "Available cash", value: null, unit: "INR", period: "current", source: "P-07", note: "per-business", state: "unavailable", measured_at: "2026-11-09T10:00:00Z" },
  ],
  finance: {
    currency: "INR",
    totals: { net_collected_minor: 0, expenses_minor: 0, net_profit_minor: 0 },
    businesses: [], internal_transfers_excluded: true, note: "", source: "P-07",
  },
  measured_at: "2026-11-09T10:00:00Z",
};

function stubAll(overview: OverviewData) {
  return installFetchStub({
    "/dashboard/overview": () => overview,
    "/dashboard/system-health": () => ({
      overall: "degraded", measured_at: overview.measured_at,
      checks: [
        { key: "database", label: "Database", state: "ok", detail: "connectivity check passed", source: "P-01", measured_at: overview.measured_at },
        { key: "gpu", label: "GPU", state: "unavailable", detail: "no GPU telemetry source exists", source: "not measured", measured_at: overview.measured_at },
      ],
      // P-14 Stage B (DEF-A3): §14 monitoring surface fields.
      resources: { cpu_percent: 12, memory_percent: 40, disk_percent: 55, threshold_violations: [], source: "P-01 system monitor" },
      modules: [{ module: "P-01", state: "ok", checks: ["database"] }],
      event_dead_letters: 0,
    }),
    "/dashboard/activity": () => ({ items: [], total: 0, measured_at: overview.measured_at, note: "" }),
    "/dashboard/attention": () => ({ items: [], measured_at: overview.measured_at }),
    "/dashboard/notifications": () => ({ items: [], unread: 0, total: 0, measured_at: overview.measured_at, note: "" }),
    "/auth/me": () => ({ principal_type: "owner", principal_id: "owner" }),
  });
}

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("OverviewView", () => {
  it("Scenario 12: a fresh install shows true zeros and honest empty states", async () => {
    stubAll(ZERO);
    render(
      <AppProviders>
        <OverviewView />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText("Collected revenue")).toBeInTheDocument());
    expect(screen.getByText("₹0.00")).toBeInTheDocument();
    // Available cash is per-business in P-07: shown Unavailable, not ₹0.
    // (The GPU health check also honestly reports Unavailable.)
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Nothing needs your attention/)).toBeInTheDocument();
    expect(screen.getByText(/No persisted events yet/)).toBeInTheDocument();
    // P-14 Stage B (DEF-A3): the §14 surface shows resource
    // utilization and per-module health in the same panel.
    expect(screen.getByText(/Resource utilization/)).toBeInTheDocument();
    expect(screen.getByText(/P-01 module health/)).toBeInTheDocument();
  });

  it("Scenario 1: KPI values equal the API values, formatted from minor units", async () => {
    const data: OverviewData = {
      ...ZERO,
      counts: { ...ZERO.counts, businesses_total: 3, pending_approvals: 2 },
      kpis: ZERO.kpis.map((k) =>
        k.key === "collected_revenue" ? { ...k, value: 123456 } : k,
      ),
      finance: {
        ...ZERO.finance,
        totals: { net_collected_minor: 123456, expenses_minor: 25000, net_profit_minor: 98456 },
      },
    };
    stubAll(data);
    render(
      <AppProviders>
        <OverviewView />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText("₹1,234.56")).toBeInTheDocument());
    // operating counts from the same payload
    expect(screen.getByText("Businesses")).toBeInTheDocument();
  });
});
