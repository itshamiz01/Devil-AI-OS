import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import type { Approval } from "../lib/types";
import { HttpError, installFetchStub, signIn } from "../test/fetchStub";
import { ApprovalCard } from "./cards";

const APPROVAL: Approval = {
  id: "appr-1",
  requesting_principal_type: "service",
  requesting_principal_id: "service-api",
  action: "config.change",
  resource: "system:settings",
  risk_classification: "high",
  reason: "tune alerting",
  requested_permissions: ["modify_system_config"],
  parameters: { setting: "alert_threshold", value: 3 },
  parameters_hash: "abc123hash456",
  status: "pending",
  approver_id: null,
  decision_at: null,
  decision_notes: null,
  expires_at: null,
  created_at: "2026-11-09T10:00:00Z",
};

function renderCard(onDecided = vi.fn()) {
  return {
    onDecided,
    ...render(
      <AppProviders>
        <ApprovalCard approval={APPROVAL} onDecided={onDecided} />
      </AppProviders>,
    ),
  };
}

beforeEach(() => {
  signIn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("ApprovalCard (§18, Scenarios 5–6)", () => {
  it("shows the exact parameters and their hash", async () => {
    installFetchStub({});
    renderCard();
    expect(screen.getByText("config.change")).toBeInTheDocument();
    expect(screen.getByText("abc123hash456")).toBeInTheDocument();
    const pre = document.querySelector(".params-json");
    expect(pre?.textContent).toContain('"setting": "alert_threshold"');
    expect(pre?.textContent).toContain('"value": 3');
  });

  it("decides via the governed endpoint and confirms only from the backend response", async () => {
    const { calls } = installFetchStub({
      "/approvals/appr-1/decision": () => ({ ...APPROVAL, status: "approved" }),
    });
    const { onDecided } = renderCard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Approve once" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/parameters with hash/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Approve once" }));
    await waitFor(() =>
      expect(screen.getByText(/Backend confirmed: status is now Approved/)).toBeInTheDocument(),
    );
    const decisionCall = calls.find((c) => c.url.includes("/approvals/appr-1/decision"));
    expect(decisionCall).toBeDefined();
    expect(JSON.parse(String(decisionCall!.init.body))).toMatchObject({ approve: true });
    expect(onDecided).toHaveBeenCalled();
  });

  it("refuses to claim success when the backend response binds different parameters", async () => {
    installFetchStub({
      "/approvals/appr-1/decision": () => ({
        ...APPROVAL,
        status: "approved",
        parameters_hash: "totally-different-hash",
      }),
    });
    renderCard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Approve once" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve once" }));
    await waitFor(() =>
      expect(screen.getByText(/different parameters than shown/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Backend confirmed/)).not.toBeInTheDocument();
  });

  it("surfaces a backend refusal and never reports success", async () => {
    installFetchStub({
      "/approvals/appr-1/decision": () => {
        throw new HttpError(403, "self_approval_forbidden", "requester cannot decide");
      },
    });
    renderCard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/self_approval_forbidden/));
    expect(screen.queryByText(/Backend confirmed/)).not.toBeInTheDocument();
  });
});
