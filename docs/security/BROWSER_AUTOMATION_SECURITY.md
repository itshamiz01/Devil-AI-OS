# Browser Automation Security (P-05, §11)

## Environment truth first

No live browser engine runs in this staging sandbox (Playwright's
Chromium binary is not downloadable from this network — audit §7,
evidence-based). What is built and tested here is the **session/policy
layer plus a fetch-backed read path**. Interactive automation
(click/type/submit/download) returns ADAPTER_UNAVAILABLE. Nothing in
this document should be read as claiming a working interactive browser
in staging.

## Controls

- **Domain allowlists, two layers:** the owner-governed global
  `browser_allowlist` (settings; session creation validates against it)
  and each session's own `allowed_domains`. Navigation outside the
  session scope is rejected at policy; the transport re-validates the
  host on every redirect hop (§25.3 #7/#8, tested).
- **SSRF discipline:** the read path rides the same redirect-following,
  per-hop-validating transport as the API adapter, with the P-03 guard.
- **Authentication is a human's job (§11.5, absolute):** password fields,
  CAPTCHA markers (reCAPTCHA/hCaptcha/Turnstile), MFA/OTP markers, and
  401/403 responses move the session to `requires_human` and the request
  to REQUIRES_HUMAN_ACTION. The system never solves CAPTCHAs, never
  requests the owner's credentials through an agent, and never bypasses
  an authentication wall. A session resumes only when a human has
  authenticated outside the automation (owner-side, on their machine).
- **Prompt injection (§11.8):** page content is data. Extraction returns
  text and links only; known instruction-like markers are detected and
  recorded on the run output (`injection_markers`) and in evidence.
  Tested: an injection page changes no capability and triggers no
  additional execution (§25.3 #9).
- **Evidence honesty:** `screenshot` on the fetch backend stores an HTML
  snapshot in the agent's workspace and labels it
  `html_snapshot_not_rendered_image` — never presented as a rendered
  screenshot.
- **Session bounds:** per-agent session ceiling (`max_browser_sessions`,
  default 2); sessions belong to exactly one agent (cross-agent session
  use returns NOT_FOUND); the emergency stop pauses open sessions.
- **No credential handling:** the browser layer has no credential store,
  no cookie persistence, and no form-filling capability in this build.

## On the owner's Windows machine

Attaching a real backend (Playwright/Chromium) happens behind this same
session/policy layer, after installation and testing there
(`docs/operations/WINDOWS_SETUP.md`). The §11.5 rule does not relax with
a real engine: authentication walls remain human-only.
