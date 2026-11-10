# Expansion Feature 3 — Voice Assistant: Architecture

Status: built under the owner's Gate 2 go-ahead (2026-11-10), as
feature 3 of 11 in the Post-Completion Expansion Pack's dependency
order (the pack's roadmap table lists it as Extra Feature 1; the
dependency order in the Gate 2 readiness review §7 governs). This
document records the architecture decisions taken inside the build
(the pack's internal approval steps are handled P-14-style:
architecture first, conservative minimal options, reported in the
gate summary).

## 1. What exists already (the starting map)

From the Gate 2 readiness review (§7.3, rated CONDITIONAL) and a
fresh inspection:

- **No audio code exists anywhere** — no speech, microphone,
  wake-word, STT or TTS code in the backend (verified by search).
  Everything downstream of transcription exists: the text command
  path (P-02 Intelligence: mission → plan → hash-bound approval →
  broker/permission-gated execution → verified results),
  conversation context in the shared mission store, approvals for
  consequential actions, and the P-01 task system the planner
  executes through.
- **The provider seam is P-02's `ModelProvider`**: an
  `IntegrationAdapter` subclass with an honest `probe()` contract —
  `OllamaProvider` reports unavailable when no server/models exist
  and fabricates nothing; `FakeProvider` is its clearly labelled
  test double; `CloudProviderStub` refuses honestly. F02's
  connector registry governs JSON-payload connectors; the media/
  model providers follow the P-02 seam instead (the seeded F02
  catalogue contains no model provider, by the same logic).
- **P-10 owns authorization** (the `PermissionBroker` over the
  P-01 deny-by-default engine; risk classification in
  `ACTION_RISK`, unclassified = CRITICAL fail-closed), **P-01 owns
  identity, sessions, tasks and the audit trail**, **P-09 owns
  memory** (ingestion via `memory.ingestion.ingest`, fed
  best-effort with verified findings only — the P-14/P-18
  posture), **P-07 owns money** (untouched; this feature has no
  money surface).
- **§4.2 inheritance contract** (review §4.2) binds every new
  route: principal from `get_principal`, enum permission gates,
  broker for governed execution, `ApprovalService` for Level 3,
  shared audit facade, secrets as metadata references only,
  additive tables, money in P-07.

## 2. The condition, stated plainly (DEF-A2)

No real LLM or speech model has ever been exercised in this
system, and none can be in this staging VM: it has no microphone
and no speech-model runtime, and the owner's target hardware is
CPU-only (i7-4712HQ, 16 GB RAM, GPU below Ollama's minimum; the
P-04 feasibility verdict caps interactive models at 1–3B Q4).
Therefore this feature builds the **complete voice pipeline
against the provider interfaces**, and real-model acceptance is
explicitly deferred to a pass on the owner's machine. Nothing in
this feature fakes transcription, understanding or speech: with
no available provider, every voice capability reports the honest
states of the F02 vocabulary (`not_configured` /
`requires_owner_configuration`) and refuses with the reason.

## 3. Decisions (conservative minimal options)

1. **A new `app/voice/` package, grown beside the existing
   seams** — `constants.py` (vocabulary), `providers.py` (the
   speech-provider seam), `testing.py` (the labelled test double),
   `service.py` (pipeline + governance). Models in
   `app/database/models/voice.py`, repositories in
   `app/database/repositories/voice.py`, routes in
   `app/api/routes/voice.py`, wired on the `Application` object
   as `application.voice` after F02 (it consumes P-02
   intelligence, P-09 memory, P-10 broker, all built earlier).
   No second task system, memory store, permission system, audit
   log or scheduler.

2. **The speech-provider seam mirrors `ModelProvider`.**
   `SpeechProvider(IntegrationAdapter)` declares `supports_stt` /
   `supports_tts`, an honest async `probe()`, `transcribe(...)`
   and `synthesize(...)` returning result dataclasses that carry
   provenance (provider name, model label, `is_fixture` flag).
   Providers raise `ProviderUnavailable` rather than fabricating
   output. Exactly one real provider ships:
   `LocalWhisperProvider` — a genuine faster-whisper adapter
   (local-first, per the pack) whose probe honestly reports the
   two facts that are true in staging: the library is not
   installed and no model is configured (`AUTONOMUS_WHISPER_MODEL`).
   Its transcription path is real code against the library API,
   unexercised here — the same posture `OllamaProvider` held in
   P-02. Speech *synthesis* has no local candidate implemented:
   no provider claims TTS, so the TTS state is
   `requires_owner_configuration`, never a fabricated voice.

3. **The test double is a fixture, and is labelled as one
   everywhere.** `FixtureSpeechProvider`
   (`app/voice/testing.py`, name `fixture_speech_double`) is
   deterministic: transcription returns a preset text with
   `confidence=None` (a double must not invent a confidence
   figure) and every result's model label reads
   `FIXTURE:test-double (not a real speech model)`; synthesis
   returns a generated silent WAV. It is **never** attached at
   startup, never seeded, and has **no HTTP route** — it is
   attached only in-process through the owner-only, audited
   service hook `attach_provider` (the F02 `attach_adapter`
   precedent), which tests use. Transcripts it produces are
   stored with `is_fixture=true` and its model label, so fixture
   provenance survives into every record and screen.

4. **Voice is an input channel, never an authority.** A
   transcript becomes a command only through the existing text
   machinery: `IntelligenceService.create_mission` →
   `create_plan` → (approval) → `execute_plan`. The voice service
   adds exactly three things around that path:
   - an **intake broker decision**: every interpretation is
     authorized through the P-10 broker (`submit_tasks` /
     `draft.create`, parameters bound to the transcript id and
     the SHA-256 of its text), so a voice-originated request
     enters the same decision ledger as every other governed
     action;
   - a **deterministic classification** of the interpreted
     request (below); and
   - a **confirmation gate** (below). Execution authority itself
     — per-step permission checks, the hash-bound plan approval
     inside `approve_plan`, mode gates inside `execute_plan` —
     remains the plan pipeline's, untouched.
   A voice-originated action carries the authenticated principal's
   permissions and nothing more; in practice the voice channel is
   the **owner's** channel: the service refuses every non-owner
   principal at the service layer (routes additionally gate on
   the `Permission` enum — the two-depth pattern).

5. **Classification is a screen, not an NLU claim.** The
   interpreted text is classified deterministically: word-boundary
   screens for financial terms (`transfer`, `payment`, `refund`,
   `purchase`, `wallet`, …) → `financial_operation`, and for
   destructive/irreversible terms (`delete`, `erase`, `install`,
   `publish`, `send`, `approve`, …) → `high_risk`; otherwise from
   the produced plan (all-read-only tool set →
   `information_request`; executable steps → `system_operation`);
   no plan → `question` for interrogative text, else `unresolved`.
   A command is **consequential** when its category is financial
   or high-risk, or any plan step's tool requires approval
   (L2+ in the P-02 tool registry), or a step's permission is one
   of P-01's approval-required permissions. The classifier
   classifies the *request*; it never claims to understand it.

6. **Confirmation is on-screen, exact, and never vocal.**
   Consequential commands stop at `awaiting_confirmation` with
   the interpreted text, category, risk and the plan's steps
   recorded on the command row, plus the SHA-256 of the plan's
   canonical steps. Confirmation is a separate authenticated
   owner API call (`POST /voice/commands/{id}/confirm`, gated on
   `approve_actions`): it recomputes the plan hash and refuses on
   any drift ("the interpreted command changed; re-interpret
   first"), then runs the existing `approve_plan` +
   `execute_plan`. **No voice input can confirm anything**: a
   transcript that says "yes, approve it" is interpreted as a new
   (unplannable) command and changes nothing — this is tested.
   A spoken **stop** is the one voice-native control: a stop
   phrase as a transcript cancels the session's own pending
   (awaiting-confirmation) commands and nothing else — it grants
   nothing, executes nothing, and is audited.

7. **Uncertain input never executes.** When no planner can
   produce a plan (no baseline template matches and no LLM is
   usable — the staging reality), interpretation ends at
   `needs_clarification` with the mission recorded and no
   execution. This is the pack's "do not execute an uncertain
   command; ask the user to clarify", implemented by the honest
   failure of the existing planner rather than by invented
   understanding.

8. **Privacy: audio and transcripts are owner data, retained
   under owner control, sent nowhere.** Audio bytes are stored
   under the application data dir (`<data_dir>/voice-audio/`,
   content-addressed by SHA-256, 10 MiB cap, audio content types
   only) with a metadata row; there is **no outbound network code
   in this feature** — providers are local interfaces and the one
   real provider is a local library. Deletion is real: deleting
   a session/audio/transcript removes stored files and clears
   transcript text (rows remain as tombstones with `deleted_at`
   so the audit trail stays coherent). Transcripts are **not**
   fed to P-09 memory; only a completed command's verified
   outcome summary is fed, best-effort, through P-09's existing
   ingestion with `voice-command:<id>` provenance (the P-18
   posture: memory is data, never authority).

9. **Configuration is data, honestly labelled.** A session
   carries language, STT/TTS provider selection, voice name,
   rate and volume (the pack's configurables), a `continuous_mode`
   flag (explicit owner control, default off) and a wake-word
   string. These configure a future real provider; the status
   surface states plainly which behaviours are **not
   implemented** in staging: wake-word detection (no audio DSP
   exists), voice-activity detection, noise handling, barge-in,
   and microphone capture (the Command Center records through
   the browser's `MediaRecorder` where the browser supports it
   and otherwise accepts file upload — capture is a client
   concern; the pipeline begins at uploaded audio).

10. **No money surface, no governance change.** The voice tables
    hold no money column (schema-asserted) and no secret value.
    A voice request that touches finance classifies as
    `financial_operation`, requires on-screen confirmation, and
    still executes only as a plan through the existing machinery
    — in staging no financial tool exists in the registry, so
    such requests end at `needs_clarification`, never at a money
    movement. Article 0 holds: no governance, safety or
    financial-authority code is modified. The API version advances
    to **1.3.0** under the F02 rule (minor per expansion feature).

## 4. Data model (additive migration, down_revision `3f7a1c9e52b4`)

- `voice_sessions`: id, owner_id, title, state (`active` /
  `closed`), language, stt_provider, tts_provider, voice_name,
  rate, volume, continuous_mode, wake_word, last_mission_id,
  created_by, timestamps, closed_at, deleted_at.
- `voice_audio`: id, session_id, command_id (nullable; set for
  synthesized responses), kind (`input` / `response`), filename,
  content_type, size_bytes, sha256, storage_path (relative),
  duration_seconds (nullable — recorded only when a provider
  reports it; never invented), created_by, timestamps,
  deleted_at.
- `voice_transcripts`: id, session_id, audio_id (nullable),
  source (`audio` / `manual_entry`), provider_name, model_label,
  is_fixture, language, text, confidence (nullable), status
  (`completed` / `failed` / `not_configured`), error_detail,
  created_by, timestamps, deleted_at.
- `voice_commands`: id, session_id, transcript_id, mission_id,
  plan_id, interpreted_text, category, risk_level (`low` /
  `consequential`), requires_confirmation, status (`interpreted`
  / `awaiting_confirmation` / `needs_clarification` / `denied` /
  `executing` / `completed` / `failed` / `rejected` /
  `cancelled`), plan_hash, broker_decision_id,
  confirmed_by / confirmed_at, result_summary, response_audio_id,
  speech_state (the honest TTS state at completion), error_detail,
  created_by, timestamps.

Physical tables: 228 → 232; metadata 227 → 231. Exact head/count/
version pins in earlier suites advance with F03 disclosure
comments, strictness preserved (the F01/F02 precedent).

## 5. Command Center

A new **Voice** view (Command section): the capability status
panel (STT/TTS states in the framework vocabulary, provider probe
details, the DEF-A2 note, and the not-implemented list, all read
from the status endpoint — the view fabricates nothing); session
list and creation; per-session settings (language, voice, rate,
volume, continuous mode, wake word — labelled as configuration
for a future real provider); audio upload and in-browser
recording where `MediaRecorder` exists; the manual-entry fallback
(labelled as the fallback it is); transcripts with full
provenance (source, provider, model label, fixture badge);
interpretation producing a command card that shows exactly what
was understood — interpreted text, category, risk, plan steps —
with Confirm / Reject for consequential commands; execution
status and the spoken-response playback (`<audio>` on the
response content endpoint) when a synthesized response exists.
All on real endpoints; the view holds no voice state of its own.
