import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { HttpError, installFetchStub, signIn } from "../test/fetchStub";
import { SecurityView } from "./Security";

const SUMMARY_BASE = {
  financial_suspension: false,
  active_sessions: 1,
  active_agents: 0,
  pending_approvals: 0,
  open_alerts: 0,
  audit_chain: { ok: true, chain_length: 12, unsealed_events: 0 },
  incidents_by_status: {},
  alerts_by_status: {},
  source: "P-10 security monitor",
  measured_at: "2026-11-09T10:00:00Z",
};

function stubSecurity(modeRef: { mode: string }, failModePost = false) {
  return installFetchStub({
    "/dashboard/security/summary": () => ({ ...SUMMARY_BASE, mode: modeRef.mode }),
    "/security/alerts": () => [],
    "/security/incidents": () => [],
    "/security/auth/sessions": () => [],
    "/security/emergency/mode": (_url, init) => {
      if (failModePost) {
        throw new HttpError(403, "permission_denied", "owner session required");
      }
      const body = JSON.parse(String(init.body)) as { mode: string };
      modeRef.mode = body.mode;
      return { mode: body.mode };
    },
    "/dashboard/overview": () => ({ counts: { pending_approvals: 0, critical_alerts: 0 }, measured_at: SUMMARY_BASE.measured_at }),
    "/dashboard/notifications": () => ({ items: [], unread: 0, total: 0, measured_at: SUMMARY_BASE.measured_at, note: "" }),
    "/auth/me": () => ({ principal_type: "owner", principal_id: "owner" }),
  });
}

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("SecurityView emergency controls (§15.5, Scenario 10)", () => {
  it("shows the new mode ONLY after P-10 confirms it", async () => {
    const modeRef = { mode: "normal" };
    stubSecurity(modeRef);
    render(
      <AppProviders>
        <SecurityView />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText(/Current confirmed mode:/)).toBeInTheDocument());
    expect(screen.getByText(/Current confirmed mode:/)).toHaveTextContent("normal");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Enter safe mode" }));
    const dialog = await screen.findByRole("dialog");
    // Nothing has been sent yet: no confirmation notice exists.
    expect(screen.queryByText(/Backend confirmed security mode/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Send to P-10" }));
    await waitFor(() =>
      expect(screen.getByText("Backend confirmed security mode: safe_mode")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText(/Current confirmed mode:/)).toHaveTextContent("safe_mode"),
    );
  });

  it("never claims success when the backend refuses", async () => {
    const modeRef = { mode: "normal" };
    stubSecurity(modeRef, true);
    render(
      <AppProviders>
        <SecurityView />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText(/Current confirmed mode:/)).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Emergency stop" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Send to P-10" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/permission_denied/));
    expect(screen.queryByText(/Backend confirmed/)).not.toBeInTheDocument();
    expect(screen.getByText(/Current confirmed mode:/)).toHaveTextContent("normal");
  });
});
