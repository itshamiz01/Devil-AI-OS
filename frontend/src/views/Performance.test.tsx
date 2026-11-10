import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { PerformanceView } from "./Performance";

// Stubbed API values — the view must render exactly these (P-15 §14:
// the Command Center displays measured operational health, incidents
// and readiness; nothing is invented client-side).

const OVERVIEW = {
  generated_at: "2026-11-10T07:00:00+00:00",
  health: {
    overall: "degraded",
    checks: [
      { key: "backend", label: "Backend", state: "ok", detail: "lifecycle state: ready", source: "P-01 lifecycle manager" },
      { key: "gpu", label: "GPU", state: "unavailable", detail: "no GPU telemetry source exists", source: "not measured" },
    ],
    resources: { cpu_percent: 12.5, memory_percent: 41.0, disk_percent: 55.0 },
    event_dead_letters: 0,
    modules: [],
  },
  history: [
    { sampled_at: "2026-11-10T06:59:00+00:00", cpu_percent: 10, memory_percent: 40, disk_percent: 55, queue_depth: 0, queue_running: 0, db_latency_ms: 0.4, database_healthy: true, metrics: {} },
    { sampled_at: "2026-11-10T07:00:00+00:00", cpu_percent: 12.5, memory_percent: 41, disk_percent: 55, queue_depth: 0, queue_running: 0, db_latency_ms: 0.5, database_healthy: true, metrics: {} },
  ],
  ai: {
    providers: {
      ollama: { available: false, detail: "connection refused", models: [] },
      cloud: { available: false, detail: "cloud AI disabled", models: [] },
    },
  },
  agents: { total: 3, by_status: { active: 3 } },
  businesses: { total: 1, by_status: { OPERATIONAL: 1 } },
  queue: {
    snapshot: { depth: 0, running: 0, capacity: 100, by_status: { completed: 4 } },
    operations_dead_letters_open: 0,
  },
  reliability: {
    incidents: {
      open_total: 1,
      resolved: 2,
      recovery_rate: 0.667,
      open_by_severity: { P0: 0, P1: 0, P2: 0, P3: 1 },
    },
    circuit_breakers: [],
    recent_incidents: [
      {
        id: "inc-1",
        severity: "P3",
        component: "backup",
        kind: "no_backups",
        title: "No backups recorded",
        status: "open",
        detected_at: "2026-11-10T06:00:00+00:00",
      },
    ],
  },
  data_protection: {
    backups: { count: 0, latest_verified: null, stale: false, latest: null },
    database: { healthy: true, latency_ms: 0.5 },
    migration: { database_revision: "d12e4d6cf5ef", head: "d12e4d6cf5ef", is_head: true },
  },
  readiness: {
    id: "snap-1",
    computed_at: "2026-11-10T07:00:00+00:00",
    overall_score: 71.5,
    band: "Controlled testing",
    classification: "Controlled testing",
    critical_gate_ok: true,
    categories: {
      performance: { weight: 15, score: 55.0, failed_checks: ["benchmarks_recorded"] },
      reliability: { weight: 20, score: 80.0, failed_checks: [] },
    },
    failed_checks: [],
    blockers: [
      { key: "windows_unverified", scope: "external", detail: "Windows 10/11 operation is UNVERIFIED from this Linux staging (P-14 DEF-A1) — an owner-machine item." },
    ],
    recommendations: ["Run a baseline benchmark from the Command Center."],
  },
  financial: {
    businesses_checked: 1,
    integrity_ok: true,
    financial_suspended: false,
    trading: "NOT APPLICABLE — no trading integration exists in the platform; nothing is monitored or invented",
  },
  controls: { security_mode: "normal", financial_suspended: false, source: "P-10 emergency service (P-15 delegates; it owns no parallel control)" },
  resources: {
    admission_block_reason: null,
    backpressure: "none",
    max_concurrency: 4,
    note: "admission control is the P-01 monitor guard + P-01 queue capacity; P-15 reports and classifies — it is not a second scheduler",
  },
  stability: {
    total_samples: 2,
    windows: [
      { target_hours: 24, status: "INCOMPLETE", sample_span_hours: 0.02 },
      { target_hours: 72, status: "INCOMPLETE", sample_span_hours: 0.02 },
      { target_hours: 168, status: "INCOMPLETE", sample_span_hours: 0.02 },
    ],
    stuck_tasks: [],
  },
};

function stubAll() {
  return installFetchStub({
    "/reliability/overview": () => OVERVIEW,
  });
}

describe("PerformanceView (P-15 §14)", () => {
  beforeEach(() => {
    signIn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("renders all nine §14 panels with the API's measured values", async () => {
    stubAll();
    render(
      <AppProviders>
        <PerformanceView />
      </AppProviders>,
    );
    expect(await screen.findByText("A · Live system health")).toBeInTheDocument();
    expect(screen.getByText("B · AI infrastructure")).toBeInTheDocument();
    expect(screen.getByText("C · Agent monitoring")).toBeInTheDocument();
    expect(screen.getByText("D · Business monitoring")).toBeInTheDocument();
    expect(screen.getByText("E · Queue monitoring")).toBeInTheDocument();
    expect(screen.getByText("F · Reliability dashboard")).toBeInTheDocument();
    expect(screen.getByText("G · Data protection")).toBeInTheDocument();
    expect(screen.getByText("H · Production readiness")).toBeInTheDocument();
    expect(screen.getByText("I · Emergency controls")).toBeInTheDocument();
    // Measured values come from the API, verbatim.
    expect(screen.getByText("12.5%")).toBeInTheDocument();
    expect(screen.getByText("No backups recorded")).toBeInTheDocument();
    expect(screen.getByText("71.5 / 100")).toBeInTheDocument();
    // Band and classification both render the API's band verbatim.
    expect(screen.getAllByText("Controlled testing").length).toBe(2);
  });

  it("shows long-duration windows as INCOMPLETE and providers as unavailable — never upgraded", async () => {
    stubAll();
    render(
      <AppProviders>
        <PerformanceView />
      </AppProviders>,
    );
    expect(await screen.findByText("A · Live system health")).toBeInTheDocument();
    // StatusBadge humanizes values; all three windows stay INCOMPLETE.
    expect(screen.getAllByText("Incomplete").length).toBe(3);
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/NOT APPLICABLE — no trading integration exists/)).toBeInTheDocument();
  });

  it("surfaces the external blockers on the readiness panel", async () => {
    stubAll();
    render(
      <AppProviders>
        <PerformanceView />
      </AppProviders>,
    );
    expect(await screen.findByText("H · Production readiness")).toBeInTheDocument();
    expect(screen.getByText(/Windows 10\/11 operation is UNVERIFIED/)).toBeInTheDocument();
    expect(screen.getByText("benchmarks_recorded")).toBeInTheDocument();
  });
});
