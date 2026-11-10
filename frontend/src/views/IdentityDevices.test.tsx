import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { DevicesPanel, RecoveryCodesPanel } from "./IdentityDevices";

// Expansion Feature 1: the panels render P-10's real device and
// recovery-code endpoints. Secrets/codes appear ONLY from the one
// minting response — the stubs below mirror that contract.

const DEVICE = {
  id: "dev-1234567890",
  principal: "owner:owner",
  label: "Owner laptop",
  platform: "windows",
  device_name: "host-1",
  trust_status: "untrusted",
  last_seen_at: null,
  created_at: "2026-11-10T10:00:00Z",
};

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("DevicesPanel (Expansion F-01)", () => {
  it("lists devices with trust state, and trusting posts to P-10 and re-reads", async () => {
    const state = { trust: "untrusted" };
    const { calls } = installFetchStub({
      "/security/devices": (_url, init) => {
        if (init.method === "POST" && _url.includes("/trust")) {
          state.trust = "trusted";
          return { ...DEVICE, trust_status: "trusted" };
        }
        return [{ ...DEVICE, trust_status: state.trust }];
      },
    });
    render(
      <AppProviders>
        <DevicesPanel />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText("Owner laptop")).toBeInTheDocument());
    expect(screen.getByText("Untrusted")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Trust" }));
    await waitFor(() => expect(screen.getByText("Trusted")).toBeInTheDocument());
    expect(
      calls.some((c) => c.url.includes("/security/devices/dev-1234567890/trust")),
    ).toBe(true);
  });

  it("enrolment shows the device secret exactly once, from the minting response", async () => {
    installFetchStub({
      "/security/devices": (_url, init) => {
        if (init.method === "POST" && !_url.includes("/trust")) {
          return {
            ...DEVICE,
            id: "dev-new999",
            label: "Kitchen tablet",
            device_secret: "one-time-secret-value",
            secret_shown_once: true,
          };
        }
        return [];
      },
    });
    render(
      <AppProviders>
        <DevicesPanel />
      </AppProviders>,
    );
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("e.g. Owner laptop"), "Kitchen tablet");
    await user.click(screen.getByRole("button", { name: "Enrol device" }));
    await waitFor(() =>
      expect(screen.getByText("one-time-secret-value")).toBeInTheDocument(),
    );
    expect(screen.getByText(/shown exactly once/)).toBeInTheDocument();
    // Dismissing removes it from the page — there is no re-display path.
    await user.click(screen.getByRole("button", { name: /I have stored it/ }));
    expect(screen.queryByText("one-time-secret-value")).not.toBeInTheDocument();
  });
});

describe("RecoveryCodesPanel (Expansion F-01)", () => {
  it("shows counts, generates a batch shown once, and verifies a code", async () => {
    const state = { generated: false, used: 0 };
    installFetchStub({
      "/security/auth/recovery-codes/generate": () => {
        state.generated = true;
        return {
          batch_id: "batch-1",
          codes: ["AB3D-EF5G-HJ7K", "MN9P-QR4S-TU6V"],
          count: 2,
          invalidated_previous: 0,
          shown_once: true,
        };
      },
      "/security/auth/recovery-codes/verify": () => ({ verified: true }),
      "/security/auth/recovery-codes": () => ({
        configured: state.generated,
        total_generated: state.generated ? 2 : 0,
        unused: state.generated ? 2 - state.used : 0,
        used: state.used,
        invalidated: 0,
        batches: state.generated ? 1 : 0,
        last_generated_at: state.generated ? "2026-11-10T10:00:00Z" : null,
      }),
    });
    render(
      <AppProviders>
        <RecoveryCodesPanel />
      </AppProviders>,
    );
    await waitFor(() => expect(screen.getByText("No codes generated yet")).toBeInTheDocument());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Generate new codes" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate codes" }));
    await waitFor(() => expect(screen.getByText("AB3D-EF5G-HJ7K")).toBeInTheDocument());
    expect(screen.getByText(/shown exactly once/)).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("XXXX-XXXX-XXXX"), "AB3D-EF5G-HJ7K");
    await user.click(screen.getByRole("button", { name: "Verify code" }));
    await waitFor(() =>
      expect(screen.getByText(/Verified — the code has been consumed/)).toBeInTheDocument(),
    );
  });
});
