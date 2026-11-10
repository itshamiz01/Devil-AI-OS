import React, { useEffect, useRef, useState } from "react";
import { ApiError, api, apiBlob, apiUpload } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/hooks";
import {
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/ui";

/**
 * Expansion Feature 3 (Voice Assistant): the voice console.
 * Everything renders the pipeline's real endpoints — this view
 * holds no voice state of its own. Capability states use the
 * framework's ONE vocabulary (configured / not_configured /
 * requires_owner_configuration / error): with no real speech
 * model configured, speech-to-text and text-to-speech read
 * exactly as that. Transcripts show their full provenance
 * (source, provider, model label, fixture badge) — a fixture
 * transcript is never dressed up as real recognition.
 *
 * Confirmation of a consequential command happens HERE, on
 * screen, through the confirm endpoint. Speaking "approve" into
 * a transcript confirms nothing, by design.
 */

export interface VoiceStatus {
  api_version: string;
  providers: {
    name: string;
    is_fixture: boolean;
    supports_stt: boolean;
    supports_tts: boolean;
    available: boolean;
    detail: string;
  }[];
  stt: { state: string; detail: string };
  tts: { state: string; detail: string };
  counts: Record<string, number>;
  awaiting_confirmation: number;
  not_implemented: string[];
  def_a2: string;
}

export interface VoiceSessionRow {
  id: string;
  title: string;
  state: string;
  language: string;
  stt_provider?: string | null;
  tts_provider?: string | null;
  voice_name?: string | null;
  rate: number;
  volume: number;
  continuous_mode: boolean;
  wake_word?: string | null;
  last_mission_id?: string | null;
  created_at?: string | null;
}

export interface VoiceAudioRow {
  id: string;
  kind: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at?: string | null;
}

export interface VoiceTranscriptRow {
  id: string;
  audio_id?: string | null;
  source: string;
  provider_name?: string | null;
  model_label?: string | null;
  is_fixture: boolean;
  language?: string | null;
  text: string;
  confidence?: number | null;
  status: string;
  error_detail?: string | null;
  created_at?: string | null;
}

export interface VoiceCommandRow {
  id: string;
  transcript_id: string;
  mission_id?: string | null;
  plan_id?: string | null;
  interpreted_text: string;
  category: string;
  risk_level: string;
  requires_confirmation: boolean;
  status: string;
  plan_hash?: string | null;
  result_summary?: string | null;
  response_audio_id?: string | null;
  speech_state?: string | null;
  error_detail?: string | null;
  detail: {
    steps?: { name: string; tool_name: string; permission: string }[];
    speech?: { provider: string; model_label: string; is_fixture: boolean };
  };
  created_at?: string | null;
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
}

const recorderSupported =
  typeof navigator !== "undefined" &&
  "mediaDevices" in navigator &&
  typeof MediaRecorder !== "undefined";

export function VoiceView(): React.ReactElement {
  const status = useApi<VoiceStatus>("/voice/status", 30000);
  const sessions = useApi<VoiceSessionRow[]>("/voice/sessions", 30000);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [manualText, setManualText] = useState("");
  const [recording, setRecording] = useState(false);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const rows: VoiceSessionRow[] = Array.isArray(sessions.data) ? sessions.data : [];
  useEffect(() => {
    if (selected === null && rows.length > 0) setSelected(rows[0].id);
  }, [rows, selected]);
  const session = rows.find((r) => r.id === selected) ?? null;

  const transcripts = useApi<VoiceTranscriptRow[]>(
    selected ? `/voice/sessions/${selected}/transcripts` : null, 30000);
  const commands = useApi<VoiceCommandRow[]>(
    selected ? `/voice/sessions/${selected}/commands` : null, 30000);
  const audioRows = useApi<VoiceAudioRow[]>(
    selected ? `/voice/sessions/${selected}/audio` : null, 30000);

  const reloadWork = () => {
    transcripts.reload();
    commands.reload();
    audioRows.reload();
    status.reload();
  };

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(label);
      reloadWork();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const createSession = () =>
    act("Voice session created.", async () => {
      const created = await api<VoiceSessionRow>("/voice/sessions", {
        method: "POST",
        body: { title: newTitle, language: "en" },
      });
      setNewTitle("");
      sessions.reload();
      setSelected(created.data.id);
    });

  const uploadFile = (file: File) => {
    if (!selected) return;
    void act(`Audio uploaded (${file.name}).`, () =>
      apiUpload(
        `/voice/sessions/${selected}/audio?filename=${encodeURIComponent(file.name)}`,
        file,
      ));
  };

  const startRecording = async () => {
    if (!selected || !recorderSupported) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        void act("Recording uploaded.", () =>
          apiUpload(
            `/voice/sessions/${selected}/audio?filename=recording.webm`,
            blob,
          ));
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setActionError(errorText(err));
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  const playResponse = (audioId: string) =>
    void (async () => {
      try {
        const blob = await apiBlob(`/voice/audio/${audioId}/content`);
        setPlaybackUrl(URL.createObjectURL(blob));
      } catch (err) {
        setActionError(errorText(err));
      }
    })();

  const transcriptRows: VoiceTranscriptRow[] = Array.isArray(transcripts.data)
    ? transcripts.data
    : [];
  const commandRows: VoiceCommandRow[] = Array.isArray(commands.data)
    ? commands.data
    : [];
  const audioList: VoiceAudioRow[] = Array.isArray(audioRows.data)
    ? audioRows.data
    : [];

  return (
    <div className="page">
      <PageHeader
        title="Voice"
        subtitle="Voice Assistant — an input channel into the governed OS, never an authority. Commands execute only through the existing mission → plan → approval pipeline, and consequential commands stop for on-screen confirmation."
      />
      {status.loading ? <LoadingState label="Loading voice status…" /> : null}
      {status.error ? <ErrorState error={status.error} /> : null}
      {status.data ? (
        <Panel title="Speech capabilities" meta={`API version ${status.data.api_version}`}>
          <p>
            Speech-to-text: <StatusBadge value={status.data.stt.state} />{" "}
            Text-to-speech: <StatusBadge value={status.data.tts.state} />
          </p>
          <p>{status.data.stt.detail}</p>
          <p>{status.data.tts.detail}</p>
          <p>
            {status.data.counts.sessions ?? 0} sessions ·{" "}
            {status.data.counts.transcripts ?? 0} transcripts ·{" "}
            {status.data.counts.commands ?? 0} commands ·{" "}
            {status.data.awaiting_confirmation} awaiting confirmation
          </p>
          <p className="error-text">{status.data.def_a2}</p>
          <DataTable
            columns={[
              { key: "name", label: "Provider" },
              { key: "kind", label: "Kind" },
              { key: "caps", label: "Capabilities" },
              { key: "available", label: "Available" },
              { key: "detail", label: "Detail" },
            ]}
            rows={status.data.providers.map((p) => ({
              name: p.name,
              kind: p.is_fixture ? "Test fixture (not a speech model)" : "Real provider",
              caps: [p.supports_stt ? "speech-to-text" : null, p.supports_tts ? "text-to-speech" : null]
                .filter(Boolean)
                .join(", ") || "none",
              available: p.available ? "Yes" : "No",
              detail: p.detail,
            }))}
            emptyTitle="No speech providers attached"
            emptyDetail="No provider seam is populated; speech capabilities report requires owner configuration."
          />
          <p>Not implemented in this environment:</p>
          <ul>
            {status.data.not_implemented.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel title="Sessions" meta="Owner-only · voice and text share the mission store">
        {sessions.loading ? <LoadingState label="Loading sessions…" /> : null}
        {sessions.error ? <ErrorState error={sessions.error} /> : null}
        {!sessions.loading && !sessions.error ? (
          <DataTable
            columns={[
              { key: "title", label: "Session" },
              { key: "state", label: "State" },
              { key: "language", label: "Language" },
              { key: "created", label: "Created" },
              { key: "actions", label: "Actions" },
            ]}
            rows={rows.map((row) => ({
              title: (
                <button type="button" className="btn btn-small" onClick={() => setSelected(row.id)}>
                  {row.title || "(untitled)"}
                </button>
              ),
              state: <StatusBadge value={row.state} />,
              language: row.language,
              created: row.created_at ? formatDateTime(row.created_at) : "—",
              actions: (
                <span>
                  <button
                    type="button" className="btn btn-small" disabled={busy}
                    onClick={() => act("Session closed.", () =>
                      api(`/voice/sessions/${row.id}/close`, { method: "POST" }))}
                  >
                    Close
                  </button>{" "}
                  <button
                    type="button" className="btn btn-small" disabled={busy}
                    onClick={() => act("Session deleted — recordings removed and texts cleared.", () =>
                      api(`/voice/sessions/${row.id}`, { method: "DELETE" }))}
                  >
                    Delete
                  </button>
                </span>
              ),
            }))}
            emptyTitle="No voice sessions"
            emptyDetail="Create a session to begin a voice conversation."
          />
        ) : null}
        <label>
          New session title{" "}
          <input
            aria-label="New session title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
        </label>{" "}
        <button type="button" className="btn" disabled={busy} onClick={createSession}>
          Create session
        </button>
        {notice ? <p className="notice">{notice}</p> : null}
        {actionError ? <p className="error-text">{actionError}</p> : null}
      </Panel>

      {session ? (
        <Panel
          title={`Session: ${session.title || "(untitled)"}`}
          meta="Settings are configuration for a future real provider"
        >
          <SessionSettings session={session} busy={busy} act={act} />
          <h4>Audio input</h4>
          <p>
            <label>
              Upload audio{" "}
              <input
                aria-label="Upload audio"
                type="file"
                accept="audio/*"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadFile(file);
                  e.target.value = "";
                }}
              />
            </label>{" "}
            {recorderSupported ? (
              recording ? (
                <button type="button" className="btn" disabled={busy} onClick={stopRecording}>
                  Stop recording
                </button>
              ) : (
                <button type="button" className="btn" disabled={busy} onClick={startRecording}>
                  Record (push-to-talk)
                </button>
              )
            ) : (
              <span>
                In-browser recording is not supported in this browser — upload an
                audio file instead.
              </span>
            )}
          </p>
          <DataTable
            columns={[
              { key: "filename", label: "File" },
              { key: "kind", label: "Kind" },
              { key: "size", label: "Bytes", numeric: true },
              { key: "actions", label: "Actions" },
            ]}
            rows={audioList.map((row) => ({
              filename: row.filename,
              kind: row.kind,
              size: row.size_bytes,
              actions:
                row.kind === "input" ? (
                  <span>
                    <button
                      type="button" className="btn btn-small" disabled={busy}
                      onClick={() => act("Transcription recorded.", () =>
                        api(`/voice/audio/${row.id}/transcribe`, { method: "POST" }))}
                    >
                      Transcribe
                    </button>{" "}
                    <button
                      type="button" className="btn btn-small" disabled={busy}
                      onClick={() => act("Audio deleted.", () =>
                        api(`/voice/audio/${row.id}`, { method: "DELETE" }))}
                    >
                      Delete
                    </button>
                  </span>
                ) : (
                  <button
                    type="button" className="btn btn-small"
                    onClick={() => playResponse(row.id)}
                  >
                    Play
                  </button>
                ),
            }))}
            emptyTitle="No audio in this session"
            emptyDetail="Upload or record audio, or use the manual-entry fallback below."
          />

          <h4>Manual entry (fallback)</h4>
          <p>
            Typed text enters the same pipeline with manual-entry provenance —
            it is a fallback input, never presented as speech recognition.
          </p>
          <label>
            Manual transcript{" "}
            <input
              aria-label="Manual transcript"
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
            />
          </label>{" "}
          <button
            type="button" className="btn" disabled={busy || !manualText.trim()}
            onClick={() =>
              act("Manual transcript recorded.", async () => {
                await api(`/voice/sessions/${session.id}/transcripts/manual`, {
                  method: "POST",
                  body: { text: manualText },
                });
                setManualText("");
              })}
          >
            Add transcript
          </button>

          <h4>Transcripts</h4>
          <DataTable
            columns={[
              { key: "text", label: "Text" },
              { key: "source", label: "Source" },
              { key: "provenance", label: "Provenance" },
              { key: "status", label: "Status" },
              { key: "actions", label: "Actions" },
            ]}
            rows={transcriptRows.map((row) => ({
              text: row.text || row.error_detail || "",
              source: row.source,
              provenance: row.is_fixture
                ? `FIXTURE — ${row.model_label ?? row.provider_name ?? ""}`
                : (row.model_label ?? row.provider_name ?? "—"),
              status: <StatusBadge value={row.status} />,
              actions: (
                <span>
                  <button
                    type="button" className="btn btn-small"
                    disabled={busy || row.status !== "completed"}
                    onClick={() => act("Command interpreted.", () =>
                      api(`/voice/transcripts/${row.id}/interpret`, { method: "POST" }))}
                  >
                    Interpret
                  </button>{" "}
                  <button
                    type="button" className="btn btn-small" disabled={busy}
                    onClick={() => act("Transcript deleted — text cleared.", () =>
                      api(`/voice/transcripts/${row.id}`, { method: "DELETE" }))}
                  >
                    Delete
                  </button>
                </span>
              ),
            }))}
            emptyTitle="No transcripts yet"
            emptyDetail="Transcribe uploaded audio or add a manual-entry transcript."
          />

          <h4>Commands</h4>
          {commandRows.length === 0 ? (
            <EmptyState
              title="No commands yet"
              detail="Interpret a transcript to create a governed command."
            />
          ) : (
            commandRows.map((row) => (
              <div key={row.id} className="panel" style={{ marginBottom: "0.75rem" }}>
                <p>
                  <strong>{row.interpreted_text}</strong>
                </p>
                <p>
                  <StatusBadge value={row.status} />{" "}
                  <StatusBadge value={row.category} />{" "}
                  risk: {row.risk_level}
                  {row.requires_confirmation ? " · requires confirmation" : ""}
                </p>
                {row.detail.steps && row.detail.steps.length > 0 ? (
                  <ul>
                    {row.detail.steps.map((step, i) => (
                      <li key={i}>
                        {step.name} — {step.tool_name} ({step.permission})
                      </li>
                    ))}
                  </ul>
                ) : null}
                {row.plan_hash ? <p>Plan hash: {row.plan_hash.slice(0, 16)}…</p> : null}
                {row.result_summary ? <p>{row.result_summary}</p> : null}
                {row.error_detail ? <p className="error-text">{row.error_detail}</p> : null}
                {row.speech_state ? (
                  <p>
                    Spoken response: <StatusBadge value={row.speech_state} />
                    {row.detail.speech?.is_fixture
                      ? " (fixture synthesis — not a real voice)"
                      : ""}
                  </p>
                ) : null}
                {row.status === "awaiting_confirmation" ? (
                  <p>
                    <button
                      type="button" className="btn" disabled={busy}
                      onClick={() => act("Command confirmed and executed.", () =>
                        api(`/voice/commands/${row.id}/confirm`, { method: "POST" }))}
                    >
                      Confirm &amp; execute
                    </button>{" "}
                    <button
                      type="button" className="btn" disabled={busy}
                      onClick={() => act("Command rejected — not executed.", () =>
                        api(`/voice/commands/${row.id}/reject`, { method: "POST" }))}
                    >
                      Reject
                    </button>
                  </p>
                ) : null}
                {row.status === "completed" && !row.response_audio_id ? (
                  <button
                    type="button" className="btn btn-small" disabled={busy}
                    onClick={() => act("Spoken response synthesized.", () =>
                      api(`/voice/commands/${row.id}/synthesize`, { method: "POST" }))}
                  >
                    Speak result
                  </button>
                ) : null}
                {row.response_audio_id ? (
                  <button
                    type="button" className="btn btn-small"
                    onClick={() => playResponse(row.response_audio_id as string)}
                  >
                    Play response
                  </button>
                ) : null}
              </div>
            ))
          )}
          {playbackUrl ? (
            <p>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio controls src={playbackUrl} aria-label="Spoken response playback" />
            </p>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}

function SessionSettings({
  session,
  busy,
  act,
}: {
  session: VoiceSessionRow;
  busy: boolean;
  act: (label: string, fn: () => Promise<unknown>) => Promise<void>;
}): React.ReactElement {
  const [language, setLanguage] = useState(session.language);
  const [voiceName, setVoiceName] = useState(session.voice_name ?? "");
  const [rate, setRate] = useState(String(session.rate));
  const [volume, setVolume] = useState(String(session.volume));
  const [wakeWord, setWakeWord] = useState(session.wake_word ?? "");
  const [continuous, setContinuous] = useState(session.continuous_mode);

  useEffect(() => {
    setLanguage(session.language);
    setVoiceName(session.voice_name ?? "");
    setRate(String(session.rate));
    setVolume(String(session.volume));
    setWakeWord(session.wake_word ?? "");
    setContinuous(session.continuous_mode);
  }, [session]);

  return (
    <div>
      <label>
        Language{" "}
        <input aria-label="Language" value={language} onChange={(e) => setLanguage(e.target.value)} />
      </label>{" "}
      <label>
        Voice{" "}
        <input aria-label="Voice name" value={voiceName} onChange={(e) => setVoiceName(e.target.value)} />
      </label>{" "}
      <label>
        Rate{" "}
        <input aria-label="Rate" value={rate} onChange={(e) => setRate(e.target.value)} />
      </label>{" "}
      <label>
        Volume{" "}
        <input aria-label="Volume" value={volume} onChange={(e) => setVolume(e.target.value)} />
      </label>{" "}
      <label>
        Wake word{" "}
        <input aria-label="Wake word" value={wakeWord} onChange={(e) => setWakeWord(e.target.value)} />
      </label>{" "}
      <label>
        Continuous mode{" "}
        <input
          aria-label="Continuous mode"
          type="checkbox"
          checked={continuous}
          onChange={(e) => setContinuous(e.target.checked)}
        />
      </label>{" "}
      <button
        type="button" className="btn" disabled={busy}
        onClick={() =>
          act("Session settings saved.", () =>
            api(`/voice/sessions/${session.id}`, {
              method: "PATCH",
              body: {
                language,
                voice_name: voiceName || null,
                rate: Number(rate),
                volume: Number(volume),
                wake_word: wakeWord || null,
                continuous_mode: continuous,
              },
            }))}
      >
        Save settings
      </button>
      <p>
        Wake-word and continuous-mode values are stored configuration for a
        future real provider — wake-word detection itself is not implemented
        in this environment.
      </p>
    </div>
  );
}
