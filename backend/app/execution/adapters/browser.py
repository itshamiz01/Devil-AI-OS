"""Browser adapter (§11) — session/policy layer + fetch-backed reads.

ENVIRONMENT FINDING (audit §7, evidence-based): no real browser engine
can run in this staging sandbox — Playwright's Python package installs,
but the Chromium binary download from cdn.playwright.dev delivers no
bytes from this network, so no engine can launch. Per §32/§30 this
adapter therefore implements:

- the full session model (domain allowlists, lifecycle, persistence),
- read-only navigation/inspection/extraction and evidence snapshots over
  the SSRF-guarded, redirect-re-validating HTTP transport (P-03
  heritage), with authentication/CAPTCHA/MFA detection that stops at
  REQUIRES_HUMAN_AUTHENTICATION (§11.5 — never bypassed, never solved,
  credentials never requested from the owner through an agent),
- interactive actions (click/type/submit/…) honestly reporting
  ADAPTER_UNAVAILABLE: there is no live browser to perform them here.

On the owner's Windows machine a Playwright/Chromium backend can be
attached behind this same session/policy layer; until it is installed
AND tested there, live interaction stays disabled (§12 of the audit).
Page content is untrusted data (§11.8): extraction returns text and
links only, and instruction-like page content is flagged for the
caller's audit trail — it is never executed by this layer.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Protocol

from ...opportunities.sources import html_to_text
from ..workspaces import WorkspaceManager
from .api import HttpTransport
from .base import AdapterContext, AdapterResult
from .filesystem import atomic_write, sha256_bytes

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_STRONG_AUTH_MARKERS = (
    'type="password"', "type='password'", "recaptcha", "hcaptcha",
    "g-recaptcha", "cf-turnstile", "two-factor", "two factor",
    "verification code", "one-time passcode", "authenticator app",
)
_WEAK_AUTH_MARKERS = ("sign in", "log in", "login", "sign-in")
_INJECTION_MARKERS = (
    "ignore previous instructions", "ignore all previous", "you are now",
    "system prompt", "disregard your instructions", "new instructions:",
)


class BrowserSessionStore(Protocol):
    def create(self, *, agent_id: str, start_url: str,
               allowed_domains: list[str]) -> object: ...
    def get(self, session_id: str) -> object | None: ...
    def update(self, session_id: str, **fields) -> object: ...
    def count_open(self, agent_id: str) -> int: ...


class BrowserAdapter:
    adapter_type = "browser"
    backend = "fetch"  # no live browser engine in this environment

    def __init__(self, store: BrowserSessionStore, workspaces: WorkspaceManager,
                 transport=None):
        self._store = store
        self._workspaces = workspaces
        self._transport = transport or HttpTransport()

    def health(self) -> dict:
        return {"status": "degraded", "health_status": "degraded",
                "details": {
                    "backend": self.backend,
                    "live_browser_engine": "unavailable (Chromium binary not "
                                           "downloadable in this sandbox; audit §7)",
                    "read_actions": "available via SSRF-guarded fetch transport",
                    "interactive_actions": "disabled — no live browser engine here",
                    "auth_policy": "REQUIRES_HUMAN_AUTHENTICATION; never bypassed (§11.5)",
                }}

    # ---------------------------------------------------------------- actions
    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            return AdapterResult(False, error_category="ACTION_UNKNOWN",
                                 summary=f"browser adapter has no action '{action}'")
        try:
            return await handler(parameters, context)
        except Exception as exc:
            category = getattr(exc, "code", None) or type(exc).__name__
            return AdapterResult(False, error_category=str(category),
                                 summary=f"{type(exc).__name__}: {exc}")

    async def _do_open_session(self, params, context):
        cap = int(context.settings.get("max_browser_sessions", 2))
        if self._store.count_open(context.agent_id) >= cap:
            return AdapterResult(False, error_category="RESOURCE_LIMIT",
                                 summary=f"browser session ceiling reached ({cap})")
        session = self._store.create(
            agent_id=context.agent_id, start_url=str(params.get("start_url") or ""),
            allowed_domains=[str(d).lower() for d in (params.get("allowed_domains") or [])])
        return AdapterResult(
            True, output={"session_id": session.id, "status": session.status,
                          "allowed_domains": session.allowed_domains or [],
                          "backend": self.backend},
            summary=f"browser session {session.id} opened on the fetch backend "
                    f"(domains: {', '.join(session.allowed_domains or []) or 'none'})")

    async def _fetch(self, session, url: str):
        return await self._transport.request(
            "GET", url, headers={"User-Agent": "AUTONOMUS-Browser/1.0 (read-only)"},
            allowed_hosts=list(session.allowed_domains or []))

    async def _do_navigate(self, params, context):
        session = self._store.get(str(params.get("session_id") or ""))
        if session is None or session.agent_id != context.agent_id:
            return AdapterResult(False, error_category="NOT_FOUND", summary="browser session not found")
        if session.status != "active":
            return AdapterResult(False, error_category="SESSION_NOT_OPEN",
                                 summary=f"session is {session.status}")
        url = str(params.get("url") or "")
        response = await self._fetch(session, url)
        html = response.body.decode("utf-8", errors="replace")
        extracted_title, text = html_to_text(html)  # P-03 helper: (title, text)
        title = extracted_title or _title(html)
        lowered = html.lower()
        strong = [m for m in _STRONG_AUTH_MARKERS if m in lowered]
        if response.status in (401, 403) or strong:
            self._store.update(session.id, status="requires_human",
                               current_url=response.url)
            return AdapterResult(
                False, error_category="REQUIRES_HUMAN_AUTHENTICATION",
                output={"final_url": response.url, "status": response.status,
                        "auth_markers": strong, "session_status": "requires_human"},
                summary="authentication/CAPTCHA/MFA wall detected — a human must "
                        "authenticate; the system never bypasses it (§11.5)")
        warnings = []
        if any(m in lowered for m in _WEAK_AUTH_MARKERS):
            warnings.append("page mentions sign-in; content may be limited")
        injection_hits = [m for m in _INJECTION_MARKERS if m in text.lower()]
        if injection_hits:
            warnings.append("page content contains instruction-like text; treated as "
                            "untrusted data, never as instructions (§11.8)")
        self._store.update(session.id, current_url=response.url, last_activity=_now())
        cap = int(context.settings.get("max_output_bytes", 1_000_000))
        return AdapterResult(
            True, output={"final_url": response.url, "status": response.status,
                          "title": title, "text": text[:cap],
                          "links": _links(html, response.url),
                          "redirects": response.redirects,
                          "injection_markers": injection_hits},
            summary=f"navigated to {response.url} ({response.status})",
            warnings=warnings,
            evidence=[{"type": "browser_page", "reference": response.url,
                       "content_hash": sha256_bytes(response.body),
                       "details": {"session_id": session.id, "status": response.status,
                                   "injection_markers": injection_hits}}])

    async def _do_inspect(self, params, context):
        session = self._store.get(str(params.get("session_id") or ""))
        if session is None or session.agent_id != context.agent_id:
            return AdapterResult(False, error_category="NOT_FOUND", summary="browser session not found")
        return AdapterResult(True, output={
            "session_id": session.id, "status": session.status,
            "current_url": session.current_url,
            "allowed_domains": session.allowed_domains or [],
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        }, summary=f"session {session.id} is {session.status} at {session.current_url}")

    async def _do_extract(self, params, context):
        return await self._do_navigate(params, context)

    async def _do_screenshot(self, params, context):
        """No renderer exists here: capture an HTML evidence snapshot into
        the agent's workspace and reference it — labelled as a snapshot,
        never as a rendered screenshot (§11.4 honesty)."""
        session = self._store.get(str(params.get("session_id") or ""))
        if session is None or session.agent_id != context.agent_id:
            return AdapterResult(False, error_category="NOT_FOUND", summary="browser session not found")
        url = str(params.get("url") or session.current_url or "")
        if not url:
            return AdapterResult(False, error_category="VALIDATION",
                                 summary="no URL to snapshot (navigate first or pass url)")
        response = await self._fetch(session, url)
        workspace = self._workspaces.ensure_agent_workspace(context.agent_id)
        stamp = time.strftime("%Y%m%d%H%M%S")
        relative = f"browser_evidence/{session.id}-{stamp}.html"
        target = Path(workspace.root_path) / relative
        atomic_write(target, response.body)
        digest = sha256_bytes(response.body)
        return AdapterResult(
            True, output={"snapshot_reference": f"{workspace.name}:{relative}",
                          "sha256": digest, "kind": "html_snapshot_not_rendered_image"},
            summary=f"HTML evidence snapshot saved at {workspace.name}:{relative} "
                    "(not a rendered screenshot — no browser engine here)",
            evidence=[{"type": "browser_snapshot", "reference": f"{workspace.name}:{relative}",
                       "content_hash": digest, "details": {"session_id": session.id}}])

    async def _do_interact(self, params, context):
        return _interactive_unavailable(str(params.get("interaction") or "interact"))

    async def _do_close_session(self, params, context):
        session = self._store.get(str(params.get("session_id") or ""))
        if session is None or session.agent_id != context.agent_id:
            return AdapterResult(False, error_category="NOT_FOUND", summary="browser session not found")
        self._store.update(session.id, status="closed", last_activity=_now())
        return AdapterResult(True, output={"session_id": session.id, "status": "closed"},
                             summary=f"browser session {session.id} closed")


def _interactive_unavailable(action: str) -> AdapterResult:
    return AdapterResult(
        False, error_category="ADAPTER_UNAVAILABLE",
        summary=f"browser '{action}' is unavailable: no live browser engine can run "
                "in this environment (audit §7). The action was NOT performed and is "
                "not simulated.")


def _title(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    return match.group(1).strip()[:300] if match else None


def _links(html: str, base_url: str) -> list[str]:
    from urllib.parse import urljoin
    seen: list[str] = []
    for href in _LINK_RE.findall(html):
        absolute = urljoin(base_url, href)
        if absolute.startswith(("http://", "https://")) and absolute not in seen:
            seen.append(absolute)
        if len(seen) >= 100:
            break
    return seen


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
