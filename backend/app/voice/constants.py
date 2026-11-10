"""Voice Assistant vocabulary (Expansion Feature 3).

The reported capability states are the F02 framework's ONE honest
vocabulary — ``configured`` / ``not_configured`` /
``requires_owner_configuration`` / ``error`` — reused verbatim so
every surface in the system describes an unavailable capability
the same way. Everything else here is the voice pipeline's own
record vocabulary: transcript sources and statuses, command
categories (the pack Phase 3 distinctions, produced by a
deterministic screen — never an NLU claim), command statuses and
risk levels.
"""
from __future__ import annotations

# ------------------------------------------- reported states (F02)
STATE_CONFIGURED = "configured"
STATE_NOT_CONFIGURED = "not_configured"
STATE_REQUIRES_OWNER_CONFIGURATION = "requires_owner_configuration"
STATE_ERROR = "error"
STATES = (STATE_CONFIGURED, STATE_NOT_CONFIGURED,
          STATE_REQUIRES_OWNER_CONFIGURATION, STATE_ERROR)

# ------------------------------------------------------ sessions
SESSION_ACTIVE = "active"
SESSION_CLOSED = "closed"
SESSION_STATES = (SESSION_ACTIVE, SESSION_CLOSED)

# ---------------------------------------------------------- audio
AUDIO_INPUT = "input"
AUDIO_RESPONSE = "response"
AUDIO_KINDS = (AUDIO_INPUT, AUDIO_RESPONSE)

# ---------------------------------------------------- transcripts
SOURCE_AUDIO = "audio"
SOURCE_MANUAL_ENTRY = "manual_entry"
TRANSCRIPT_SOURCES = (SOURCE_AUDIO, SOURCE_MANUAL_ENTRY)

TRANSCRIPT_COMPLETED = "completed"
TRANSCRIPT_FAILED = "failed"
TRANSCRIPT_NOT_CONFIGURED = "not_configured"
TRANSCRIPT_STATUSES = (TRANSCRIPT_COMPLETED, TRANSCRIPT_FAILED,
                       TRANSCRIPT_NOT_CONFIGURED)

# Provenance label for the manual-entry fallback. It is real owner
# input, but it is NOT speech recognition and is never labelled as
# such anywhere.
MANUAL_ENTRY_MODEL_LABEL = (
    "manual entry — owner-typed text (fallback input, "
    "not speech recognition)")

# ------------------------------------------------------ commands
# The pack Phase 3 distinctions. Produced by the deterministic
# classifier in app/voice/classifier.py: word-boundary screens for
# the financial and destructive/irreversible vocabularies, then the
# produced plan's shape; interrogative text with no plan is a
# question; anything else unplannable is unresolved.
CAT_QUESTION = "question"
CAT_INFORMATION = "information_request"
CAT_APPLICATION_CONTROL = "application_control"
CAT_FILE_OPERATION = "file_operation"
CAT_SYSTEM_OPERATION = "system_operation"
CAT_BUSINESS_WORKFLOW = "business_workflow"
CAT_FINANCIAL = "financial_operation"
CAT_HIGH_RISK = "high_risk"
CAT_UNRESOLVED = "unresolved"
CATEGORIES = (CAT_QUESTION, CAT_INFORMATION, CAT_APPLICATION_CONTROL,
              CAT_FILE_OPERATION, CAT_SYSTEM_OPERATION,
              CAT_BUSINESS_WORKFLOW, CAT_FINANCIAL, CAT_HIGH_RISK,
              CAT_UNRESOLVED)

RISK_LOW = "low"
RISK_CONSEQUENTIAL = "consequential"
RISK_LEVELS = (RISK_LOW, RISK_CONSEQUENTIAL)

CMD_INTERPRETED = "interpreted"
CMD_AWAITING_CONFIRMATION = "awaiting_confirmation"
CMD_NEEDS_CLARIFICATION = "needs_clarification"
CMD_DENIED = "denied"
CMD_EXECUTING = "executing"
CMD_COMPLETED = "completed"
CMD_FAILED = "failed"
CMD_REJECTED = "rejected"
CMD_CANCELLED = "cancelled"
COMMAND_STATUSES = (CMD_INTERPRETED, CMD_AWAITING_CONFIRMATION,
                    CMD_NEEDS_CLARIFICATION, CMD_DENIED, CMD_EXECUTING,
                    CMD_COMPLETED, CMD_FAILED, CMD_REJECTED,
                    CMD_CANCELLED)

# The one voice-native control (pack Phase 4/5): a stop phrase, as
# a transcript, cancels the session's OWN pending commands. It
# grants nothing and executes nothing. Matched on the normalised
# transcript (lowercase, trimmed, trailing punctuation stripped).
STOP_PHRASES = (
    "stop",
    "stop everything",
    "cancel",
    "cancel that",
    "cancel everything",
    "emergency stop",
    "stop now",
    "halt",
)

# ---------------------------------------------------------- audio
# Intake bounds: an upload cap and an extension/content-type
# allowlist. Duration is never computed (no audio DSP exists in
# staging) — it is recorded only when a provider reports it.
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MiB
AUDIO_EXTENSIONS = (
    ".wav", ".mp3", ".ogg", ".opus", ".webm", ".m4a", ".flac", ".aac",
)

# Behaviours this feature does NOT implement in staging, reported
# verbatim on the status surface rather than implied. Each needs a
# real audio runtime / microphone on the owner's machine.
NOT_IMPLEMENTED = (
    "wake-word detection (configuration is stored; no audio DSP "
    "exists in staging)",
    "voice activity detection and background-noise handling",
    "interruption / barge-in during speech output",
    "microphone capture in the backend (the Command Center "
    "records in the browser where MediaRecorder is supported)",
    "real speech recognition (no speech model has been exercised "
    "— DEF-A2; acceptance is deferred to the owner's machine)",
    "real speech synthesis (no local TTS provider is implemented "
    "or configured)",
)
