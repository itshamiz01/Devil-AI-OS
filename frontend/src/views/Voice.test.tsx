import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { installFetchStub, signIn } from "../test/fetchStub";
import { VoiceView } from "./Voice";

// Expansion Feature 3: the voice console renders the pipeline's
// real endpoints and the framework's ONE state vocabulary. With
// no real speech model configured, both capabilities must read
// requires_owner_configuration — never as working speech. A
// consequential command shows its interpreted plan and waits for
// the on-screen Confirm; nothing in the view confirms by voice.

const STATUS = {
  // Expansion F06 disclosure: the fixture mirrors the live API
  // version, advanced to 1.4.0 by the F06 minor bump.
  api_version: "1.4.0",
  providers: [
    {
      name: "local_whisper",
      is_fixture: false,
      supports_stt: true,
      supports_tts: false,
      available: false,
      detail: "faster-whisper is not installed in this environment (DEF-A2)",
    },
  ],
  stt: {
    state: "requires_owner_configuration",
    detail: "faster-whisper is not installed in this environment (DEF-A2)",
  },
  tts: {
    state: "requires_owner_configuration",
    detail: "no tts provider is implemented or configured",
  },
  counts: { sessions: 1, transcripts: 1, commands: 1, audio: 0 },
  awaiting_confirmation: 1,
  not_implemented: ["wake-word detection (configuration is stored)"],
  def_a2: "no real speech or language model has been exercised in this system",
};

const SESSION = {
  id: "sess-1",
  title: "Morning briefing",
  state: "active",
  language: "en",
  stt_provider: null,
  tts_provider: null,
  voice_name: null,
  rate: 1.0,
  volume: 1.0,
  continuous_mode: false,
  wake_word: null,
  last_mission_id: null,
  created_at: "2026-11-10T12:00:00Z",
};

const TRANSCRIPT = {
  id: "tr-1",
  audio_id: null,
  source: "manual_entry",
  provider_name: null,
  model_label: "manual entry — owner-typed text (fallback input, not speech recognition)",
  is_fixture: false,
  language: "en",
  text: "echo delete the old backups",
  confidence: null,
  status: "completed",
  error_detail: null,
  created_at: "2026-11-10T12:01:00Z",
};

const COMMAND = {
  id: "cmd-1",
  transcript_id: "tr-1",
  mission_id: "m-1",
  plan_id: "p-1",
  interpreted_text: "echo delete the old backups",
  category: "high_risk",
  risk_level: "consequential",
  requires_confirmation: true,
  status: "awaiting_confirmation",
  plan_hash: "abcdef0123456789",
  result_summary: null,
  response_audio_id: null,
  speech_state: null,
  error_detail: null,
  detail: {
    steps: [
      { name: "echo mission message", tool_name: "core.echo_check", permission: "execute_tools" },
    ],
  },
  created_at: "2026-11-10T12:02:00Z",
};

function stubVoice(extra: Record<string, (url: string, init: RequestInit) => unknown> = {}) {
  // NB: the stub matches by first prefix — specific paths must be
  // declared before the generic "/voice/sessions" list handler.
  return installFetchStub({
    "/voice/status": () => STATUS,
    "/voice/sessions/sess-1/transcripts": () => [TRANSCRIPT],
    "/voice/sessions/sess-1/commands": () => [COMMAND],
    "/voice/sessions/sess-1/audio": () => [],
    ...extra,
    "/voice/sessions": () => [SESSION],
  });
}

beforeEach(() => signIn());
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("VoiceView (Expansion F-03)", () => {
  it("renders honest capability states and the not-implemented list", async () => {
    stubVoice();
    render(
      <AppProviders>
        <VoiceView />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getAllByText("Requires Owner Configuration").length).toBeGreaterThan(0));
    expect(screen.getAllByText(/faster-whisper is not installed/).length).toBeGreaterThan(0);
    expect(screen.getByText(/no real speech or language model has been exercised/)).toBeInTheDocument();
    expect(screen.getByText(/wake-word detection \(configuration is stored\)/)).toBeInTheDocument();
    expect(screen.getByText(/API version 1\.4\.0/)).toBeInTheDocument();
  });

  it("shows transcript provenance and the interpreted command awaiting confirmation", async () => {
    stubVoice();
    render(
      <AppProviders>
        <VoiceView />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getAllByText("echo delete the old backups").length).toBeGreaterThan(0));
    // Manual-entry provenance is shown as the fallback it is.
    expect(
      screen.getByText(/manual entry — owner-typed text/),
    ).toBeInTheDocument();
    // The interpreted plan is shown before any execution.
    expect(screen.getByText(/core\.echo_check/)).toBeInTheDocument();
    expect(screen.getByText("Awaiting Confirmation")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm & execute" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("confirming posts to the confirm endpoint (the only confirmation path)", async () => {
    const { calls } = stubVoice({
      "/voice/commands/cmd-1/confirm": () => ({ ...COMMAND, status: "completed" }),
    });
    render(
      <AppProviders>
        <VoiceView />
      </AppProviders>,
    );
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Confirm & execute" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Confirm & execute" }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.url.includes("/voice/commands/cmd-1/confirm") && c.init.method === "POST",
        ),
      ).toBe(true));
  });

  it("manual entry posts typed text as a transcript", async () => {
    const { calls } = stubVoice();
    render(
      <AppProviders>
        <VoiceView />
      </AppProviders>,
    );
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByLabelText("Manual transcript")).toBeInTheDocument());
    await user.type(screen.getByLabelText("Manual transcript"), "echo hello");
    await user.click(screen.getByRole("button", { name: "Add transcript" }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url.includes("/voice/sessions/sess-1/transcripts/manual") &&
            c.init.method === "POST",
        ),
      ).toBe(true));
  });
});
