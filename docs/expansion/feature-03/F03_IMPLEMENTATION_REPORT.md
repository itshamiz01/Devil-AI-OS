# Expansion Feature 3 — Voice Assistant: Implementation Report

Design: `docs/expansion/feature-03/F03_ARCHITECTURE.md` (written
before code, per the pack's build order).

## What was built

A complete voice pipeline as an **input channel** into the
governed OS — `backend/app/voice/` (`VoiceService` over a small
provider seam), four additive tables, 18 owner-only routes, and
a Voice view in the Command Center. Voice holds no authority:
every command executes only through the existing P-01 →
P-09/P-02 → P-10 broker → plan approval/execution machinery,
carrying the authenticated owner's permissions and nothing
more.

- **Provider seam** (`app/voice/providers.py`): `SpeechProvider`
  mirrors P-02's `ModelProvider` contract (honest `probe()`,
  `ProviderUnavailable`, provenance on every result) and
  implements the F02 `IntegrationAdapter` interface. One real
  candidate ships — `LocalWhisperProvider`, a genuine
  faster-whisper adapter (STT only) that probes honestly:
  library absent / no model → unavailable with the DEF-A2
  reason. Attaching it as a framework connector was
  dispositioned against (registry rows persist in the database;
  provider instances cannot — architecture §2.1). No TTS
  provider is implemented, so TTS reports
  `requires_owner_configuration`.
- **The labelled test double** (`app/voice/testing.py`,
  `FixtureSpeechProvider`): deterministic preset transcript and
  silent-WAV synthesis; every output carries `is_fixture=True`,
  the model label `FIXTURE:test-double (not a real speech
  model)` and **no confidence** (a double must not invent one).
  It attaches only in-process via the owner-only, audited
  `VoiceService.attach_provider`; never at startup, never
  seeded, and there is **no HTTP route** that can attach it
  (test-asserted 404).
- **Pipeline**: raw-body audio upload (no new dependency —
  `python-multipart` is absent; bytes stored content-addressed
  under `<data_dir>/voice-audio/`, SHA-256 recorded, 10 MiB
  cap, audio types only) → transcription with full provenance
  (source, provider, model label, fixture flag, confidence only
  when a provider reports it) → interpretation → execution.
  With no provider, transcription records the attempt as
  `not_configured` with empty text — the refusal is the record.
  Manual text entry is a first-class fallback with manual-entry
  provenance, labelled "not speech recognition" everywhere.
- **Interpretation** (`app/voice/classifier.py`): deterministic,
  rule-based, word-boundary screens — financial terms →
  `financial_operation`, destructive terms → `high_risk`, else
  the P-02 plan shape decides (all-information tools →
  `information_request`, otherwise `system_operation`; no plan
  + interrogative → `question`; else `unresolved`). Voice
  commands intake through the P-10 broker (`submit_tasks` /
  `draft.create`, parameters bound to the transcript id and the
  SHA-256 of its text), then plan through
  `IntelligenceService`. Intake is per-command inside the
  mission-first flow: plan creation is broker-exempt by the
  system's own design, so voice adds its own check for the one
  act the broker would have gated (architecture §5 records
  this reasoning).
- **Confirmation discipline**: a command is *consequential*
  when its category is financial/high-risk, any step's tool is
  Level 2+, or any step needs the `approve_actions` permission.
  Consequential commands stop at `awaiting_confirmation` with
  the plan and its SHA-256 stored. `confirm` (a separate
  authenticated owner call, `APPROVE_ACTIONS`-gated) recomputes
  the plan hash — drift is refused — and only then approves and
  executes. A spoken "approve" is just another transcript: it
  confirms nothing (tested). Stop phrases (exact normalised
  match against the configured set) cancel only the session's
  own awaiting commands and never reach the planner.
- **Responses**: on completion the result summary is
  synthesized when a TTS-capable provider exists (the response
  audio is stored as a voice_audio row, fixture-labelled in the
  command detail when applicable); with none, the command
  records `speech_state=requires_owner_configuration` — display
  is the honest fallback.
- **Privacy**: audio and transcripts are owner data. Deletion
  is real (files removed, texts cleared, rows tombstoned).
  Completed commands — never transcripts — feed P-09 memory
  through its existing ingestion with verified-outcome
  labelling and `voice-command:<id>` provenance, best-effort.
  The feature contains no outbound network code.

## Data and migration

Four additive tables — `voice_sessions`, `voice_audio`,
`voice_transcripts`, `voice_commands` — via migration
`c41f7a9d03e6` (revises `3f7a1c9e52b4`), cycle-verified
228 ⇄ 232 physical tables (231 metadata). **No money columns
and no secret-value columns** (schema-asserted by test). P-07
untouched; no `financial_*` table referenced. API version
1.2.0 → **1.3.0** per the recorded rule (minor per expansion
feature).

## Permission and audit discipline (measured)

Service layer owner-only on every data path (non-owner, agent,
service and external principals refused — tested); routes bind
from the `Permission` enum per §4.2 (reads `READ_SYSTEM_DATA`,
writes `WRITE_SYSTEM_DATA`, transcribe/synthesize
`EXECUTE_TOOLS`, interpret `SUBMIT_TASKS`, confirm/reject
`APPROVE_ACTIONS`). Every act lands in the existing P-01 audit
trail as `voice.*` actions (17 of them). Article 0 held:
`app/voice` contains no approval decision, no financial
machinery, no governance import — structurally test-guarded.
Sessions follow the P-11 chat-session pattern (per-owner rows
over the shared mission store, `last_mission_id`).

## Results

Backend **1057 passed / 0 failed** (1017 baseline + 40 new
F03); frontend **62/62** with clean strict TypeScript build;
live smoke **28/28** over real uvicorn (see
`F03_TEST_REPORT.md` and `REGRESSION_EVIDENCE.txt`).

## Honest limitations

- **Real-model acceptance is outstanding (DEF-A2) — the top
  limitation.** No real speech or language model has been
  exercised: staging has no microphone and no model runtime,
  and the owner's target hardware is CPU-only (P-04 verdict:
  1–3B Q4 interactive). In staging, STT and TTS both report
  `requires_owner_configuration`; the pipeline is proven over
  the clearly labelled test double and through the honest
  refusal paths. Acceptance requires an owner-machine pass:
  install faster-whisper + a small model, set
  `AUTONOMUS_WHISPER_MODEL`, and re-run the acceptance path
  with real audio.
- Interpretation is deterministic and rule-based, not an LLM:
  commands it cannot plan end at `needs_clarification` —
  honestly, with nothing executed.
- The real provider candidate covers STT only; no TTS provider
  is implemented at all (a future owner-configured provider
  fills the seam).
- Wake-word detection and continuous listening are **not
  implemented** — the settings are stored configuration for a
  future real provider and are labelled as such in the UI and
  the status surface. Push-to-talk/upload are the working
  intake modes.
- In-browser recording depends on the browser's MediaRecorder
  and microphone permission; the view falls back to upload
  where unsupported.
- A voice request that touches finance classifies as
  `financial_operation` and, in staging, ends at clarification
  (no financial tool exists in the catalogue) — voice never
  moves money, and any future financial voice flow inherits
  the normal P-07 approval path.
- DEF-A1 stands: nothing Windows-specific is claimed.

## Rollback

Feature-additive. Downgrade migration `c41f7a9d03e6` →
`3f7a1c9e52b4` drops exactly the four voice tables (stored
audio files under `<data_dir>/voice-audio/` become orphaned
files, removable by hand). Removing the voice router from
`app/main.py`, the `VoiceService` wiring in
`app/core/application.py`, the Voice view/nav entry and
`APP_VERSION` back to 1.2.0 restores the F02 surface; no other
engine's data or behaviour is touched.
