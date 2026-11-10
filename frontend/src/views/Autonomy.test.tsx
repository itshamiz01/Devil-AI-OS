import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { AutonomyView } from "./Autonomy";

const OVERVIEW = {
  workflows: { COMPLETED: 2, RUNNING: 1, WAITING_FOR_APPROVAL: 1 },
  tasks: { COMPLETED: 5, WAITING_FOR_APPROVAL: 1 },
  pending_approvals: 1,
  open_dead_letters: 0,
  engine: { running: true, tick_interval_seconds: 30 },
  generated_at: "2026-11-09T18:00:00Z",
};

const WORKFLOW = {
  id: "wf-1",
  name: "Hourly monitoring",
  business_id: null,
  origin: "schedule",
  status: "COMPLETED",
  verified_outcome: "verified",
  autonomy_level: 2,
  current_step: null,
  progress_percent: 100,
  created_at: "2026-11-09T17:00:00Z",
  tasks: [
    {
      id: "t-1", step_key: "collect", name: "Collect signals",
      kind: "task_handler", action_class: "business.read",
      status: "COMPLETED", verification_status: "verified",
      assigned_agent_id: "owner", attempts: 1,
    },
  ],
  checkpoints: [{ completed_steps: [{ step_key: "collect" }] }],
  history: [],
  learning_record_id: "lr-1",
};

const READY_WORKFLOW = {
  ...WORKFLOW,
  id: "wf-2",
  name: "Ready workflow",
  status: "READY",
  verified_outcome: null,
  progress_percent: 0,
  tasks: [],
  learning_record_id: null,
};

function stubAll(extra: Record<string, (url: string, init: RequestInit) => unknown> = {}) {
  return installFetchStub({
    "/operations/workflows/wf-2": () => READY_WORKFLOW,
    "/operations/workflows/wf-1": () => WORKFLOW,
    "/operations/workflows": () => ({ items: [WORKFLOW, READY_WORKFLOW], total: 2 }),
    "/operations/templates": () => ({
      items: [{ name: "monitoring_report", description: "monitor" }],
    }),
    "/operations/overview": () => OVERVIEW,
    "/operations/agents": () => ({ items: [], total: 0 }),
    "/operations/approvals": () => ({ items: [], total: 0 }),
    "/operations/triggers": () => ({ items: [], total: 0 }),
    "/operations/recovery": () => ({
      dead_letters: [], dead_letter_total: 0, recovery_records: [],
      circuit_breakers: [], checkpoints: 3,
    }),
    "/operations/safety": () => ({
      security_mode: "normal", constitution_mode: "controlled",
      financial_suspended: false, paused_businesses: [],
      active_workflows: 1, autonomy_policies: [],
    }),
    "/operations/reports": () => ({ items: [], total: 0 }),
    ...extra,
  });
}

function renderView() {
  return render(
    <AppProviders>
      <AutonomyView />
    </AppProviders>,
  );
}

describe("AutonomyView", () => {
  beforeEach(() => {
    signIn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("renders overview metrics from the API, not placeholders", async () => {
    stubAll();
    renderView();
    expect(await screen.findByText("Workflows total")).toBeTruthy();
    expect(screen.getByText("Scheduler engine")).toBeTruthy();
    expect(screen.getByText("running")).toBeTruthy();
    // Honest framing is part of the surface.
    expect(screen.getByText(/not revenue/)).toBeTruthy();
  });

  it("lists workflows and opens a verified detail", async () => {
    stubAll();
    renderView();
    fireEvent.click(await screen.findByRole("tab", { name: "Workflows" }));
    const link = await screen.findByText("Hourly monitoring");
    fireEvent.click(link);
    expect(await screen.findByText("Collect signals")).toBeTruthy();
    expect(screen.getByText("lr-1")).toBeTruthy();
  });

  it("starts a READY workflow only through the backend endpoint", async () => {
    const { calls } = stubAll({
      "/operations/workflows/wf-2/start": () => ({ ...READY_WORKFLOW, status: "RUNNING" }),
    });
    renderView();
    fireEvent.click(await screen.findByRole("tab", { name: "Workflows" }));
    fireEvent.click(await screen.findByText("Ready workflow"));
    const start = await screen.findByRole("button", { name: "Start" });
    fireEvent.click(start);
    await waitFor(() => {
      expect(
        calls.some(
          (c) => c.url.includes("/operations/workflows/wf-2/start")
            && (c.init.method ?? "GET") === "POST",
        ),
      ).toBe(true);
    });
  });

  it("safety tab reflects backend modes and offers the emergency stop", async () => {
    stubAll();
    renderView();
    fireEvent.click(await screen.findByRole("tab", { name: "Safety" }));
    expect(await screen.findByText("Security mode (P-10)")).toBeTruthy();
    expect(screen.getByText("normal")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Global emergency stop" }),
    ).toBeTruthy();
  });

  it("recovery tab shows the empty dead-letter state honestly", async () => {
    stubAll();
    renderView();
    fireEvent.click(await screen.findByRole("tab", { name: "Recovery" }));
    expect(await screen.findByText("Dead-letter queue is empty")).toBeTruthy();
  });
});
