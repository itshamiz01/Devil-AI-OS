import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { installFetchStub, signIn } from "./test/fetchStub";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  window.location.hash = "";
});

describe("App gate (§28.3: unauthenticated visitors are blocked)", () => {
  it("shows only the login form without a token — no protected content", () => {
    installFetchStub({});
    render(<App />);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    expect(screen.queryByText("Approval Inbox")).not.toBeInTheDocument();
  });

  it("renders the shell for a signed-in owner", async () => {
    signIn();
    installFetchStub({
      "/auth/me": () => ({ principal_type: "owner", principal_id: "owner" }),
      "/dashboard/preferences": () => ({
        principal: "owner:owner",
        preferences: {
          sidebar_collapsed: false, default_view: "overview", timezone: "UTC",
          currency: "INR", density: "comfortable", reduce_motion: false,
        },
        is_default: false,
      }),
      "/dashboard/overview": () => ({
        operating_state: "operational", mode: "controlled", security_mode: "normal",
        counts: { pending_approvals: 0, critical_alerts: 0, businesses_total: 0 },
        kpis: [], finance: { currency: "INR", totals: { net_collected_minor: 0, expenses_minor: 0, net_profit_minor: 0 }, businesses: [] },
        queue: { capacity: 100, depth: 0, running: 0, by_status: {} },
        threshold_violations: [], measured_at: "2026-11-09T10:00:00Z",
      }),
      "/dashboard/notifications": () => ({ items: [], unread: 0, total: 0, measured_at: "2026-11-09T10:00:00Z", note: "" }),
      "/dashboard/system-health": () => ({ overall: "ok", checks: [], measured_at: "2026-11-09T10:00:00Z" }),
      "/dashboard/activity": () => ({ items: [], total: 0, measured_at: "2026-11-09T10:00:00Z", note: "" }),
      "/dashboard/attention": () => ({ items: [], measured_at: "2026-11-09T10:00:00Z" }),
      "/models/status": () => ({ providers: {} }),
    });
    render(<App />);
    await waitFor(() => expect(screen.getByText("AUTONOMUS")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Approvals/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });
});
