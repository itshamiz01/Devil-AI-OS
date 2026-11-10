import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { IntegrationsView } from "./Integrations";

// Expansion Feature 2: the registry console renders the framework's
// real endpoints and its ONE state vocabulary. A connector with no
// adapter must read as exactly that — never as connected.

const ECHO = {
  key: "local_echo",
  name: "Local Echo (reference connector)",
  provider: "AUTONOMUS (local)",
  kind: "custom",
  source: "framework",
  has_adapter: true,
  requires_credential: false,
  credential_configured: false,
  credential_secret_name: null,
  lifecycle_status: "enabled",
  state: "configured",
  error_count: 0,
  capabilities: [{ name: "echo", permission: "read_system_data", risk_action: "read" }],
};

const STRIPE = {
  ...ECHO,
  key: "stripe",
  name: "Stripe payments",
  provider: "Stripe",
  kind: "payment",
  source: "p07",
  has_adapter: false,
  requires_credential: true,
  lifecycle_status: "registered",
  state: "requires_owner_configuration",
  capabilities: [],
};

const STATUS = {
  api_version: "1.2.0",
  connector_count: 2,
  with_adapter: 1,
  by_state: { configured: 1, requires_owner_configuration: 1 },
  state_vocabulary: ["configured", "not_configured", "requires_owner_configuration", "error"],
};

function stubFramework(extra: Record<string, (url: string, init: RequestInit) => unknown> = {}) {
  // NB: the stub matches by first prefix — specific paths must be
  // declared before the generic "/integrations" list handler.
  return installFetchStub({
    "/integrations/framework/status": () => STATUS,
    "/integrations/local_echo/invocations": () => [],
    ...extra,
    "/integrations": () => [ECHO, STRIPE],
  });
}

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("IntegrationsView (Expansion F-02)", () => {
  it("renders the registry with honest states for adapter-less connectors", async () => {
    stubFramework();
    render(
      <AppProviders>
        <IntegrationsView />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getByText("Local Echo (reference connector)")).toBeInTheDocument());
    expect(screen.getByText("Stripe payments")).toBeInTheDocument();
    expect(screen.getByText("Requires Owner Configuration")).toBeInTheDocument();
    expect(screen.getByText("None — not a working connector")).toBeInTheDocument();
    expect(screen.getByText(/API version 1\.2\.0/)).toBeInTheDocument();
  });

  it("invoking the reference connector posts to the framework and shows the result", async () => {
    const { calls } = stubFramework({
      "/integrations/local_echo/invoke": () => ({
        outcome: "success",
        result: { echo: "hello ui", responded_at: "2026-11-10T12:00:00Z" },
      }),
    });
    render(
      <AppProviders>
        <IntegrationsView />
      </AppProviders>,
    );
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText("Local Echo (reference connector)")).toBeInTheDocument());
    await user.type(screen.getByLabelText(/Message/), "hello ui");
    await user.click(screen.getByRole("button", { name: "Invoke echo" }));
    await waitFor(() => expect(screen.getByText(/hello ui — 2026-11-10/)).toBeInTheDocument());
    expect(calls.some((c) => c.url.includes("/integrations/local_echo/invoke")
      && c.init.method === "POST")).toBe(true);
  });

  it("disabling a connector posts to the framework lifecycle endpoint", async () => {
    const { calls } = stubFramework();
    render(
      <AppProviders>
        <IntegrationsView />
      </AppProviders>,
    );
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText("Local Echo (reference connector)")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Disable" }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/integrations/local_echo/disable"))).toBe(true));
  });
});
