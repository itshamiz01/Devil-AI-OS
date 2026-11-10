"""HTTP API execution adapter (§13), built on the P-03 SSRF-guarded
transport pattern (§13.1: the same discipline — scheme allowlist, DNS
resolution with private/loopback/link-local rejection, redirect
re-validation — reused via ``app.opportunities.sources.assert_url_allowed``
plus this module's own redirect-following client).

Rules enforced here as well as in policy (defense in depth): host
allowlist per call, every redirect target re-validated, response-size
cap, timeout, retries ONLY for idempotent methods with backoff (never a
blind POST retry, §13.2), credentials resolved from a reference by the
broker at execution time and never logged or persisted (§13.3).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from ...opportunities.sources import TransportError, assert_url_allowed
from ..credentials import CredentialBroker
from ..policy import host_matches
from .base import AdapterContext, AdapterResult
from .filesystem import sha256_bytes

IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}
MAX_REDIRECTS = 3


@dataclass
class TransportResponse:
    url: str
    status: int
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    redirects: list[str] = field(default_factory=list)
    truncated: bool = False


class HttpTransport:
    """Redirect-following client that re-validates EVERY hop.

    ``trust_env=False``: proxy configuration is an explicit engine
    setting (``proxy_url``, wired from the P-03 research proxy setting),
    never ambient process environment — an execution engine must not
    silently reroute governed traffic through whatever proxy variables
    happen to be present."""

    def __init__(self, timeout_seconds: float = 20.0, max_bytes: int = 1_000_000,
                 allow_private_hosts: bool = False, proxy_url: str | None = None):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.allow_private_hosts = allow_private_hosts
        self.proxy_url = proxy_url

    async def request(self, method: str, url: str, headers: dict | None = None,
                      body: bytes | None = None, *,
                      allowed_hosts: list[str] | None = None) -> TransportResponse:
        current = url
        redirects: list[str] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds,
                                     follow_redirects=False, trust_env=False,
                                     proxy=self.proxy_url) as client:
            for _ in range(MAX_REDIRECTS + 1):
                assert_url_allowed(current, allow_private_hosts=self.allow_private_hosts)
                if allowed_hosts is not None:
                    from urllib.parse import urlsplit
                    host = (urlsplit(current).hostname or "").lower()
                    if not host_matches(host, allowed_hosts):
                        raise TransportError(
                            f"host '{host}' is not in the API allowlist")
                try:
                    response = await client.request(
                        method, current, headers=headers or {}, content=body)
                except httpx.HTTPError as exc:
                    raise TransportError(f"{type(exc).__name__}: {exc}") from exc
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        break
                    from urllib.parse import urljoin
                    current = urljoin(current, location)
                    redirects.append(current)
                    if method in ("POST",) and response.status_code in (301, 302, 303):
                        method = "GET"
                        body = None
                    continue
                data = bytearray()
                truncated = False
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self.max_bytes:
                        data = data[: self.max_bytes]
                        truncated = True
                        break
                return TransportResponse(
                    url=current, status=response.status_code,
                    headers={k: v for k, v in response.headers.items()
                             if k.lower() != "set-cookie"},
                    body=bytes(data), redirects=redirects, truncated=truncated)
        raise TransportError("too many redirects")


class MockTransport:
    """Deterministic transport for tests: maps (method, url) or url to a
    TransportResponse or an Exception; records every call."""

    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.calls: list[dict] = []

    async def request(self, method: str, url: str, headers: dict | None = None,
                      body: bytes | None = None, *,
                      allowed_hosts: list[str] | None = None) -> TransportResponse:
        # Guards run BEFORE the call is recorded: a blocked target was
        # never "called" (mirrors the real transport's behaviour).
        assert_url_allowed(url, allow_private_hosts=False)
        if allowed_hosts is not None:
            from urllib.parse import urlsplit
            host = (urlsplit(url).hostname or "").lower()
            if not host_matches(host, allowed_hosts):
                raise TransportError(f"host '{host}' is not in the API allowlist")
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}), "body": body})
        outcome = self.mapping.get((method, url), self.mapping.get(url))
        if outcome is None:
            raise TransportError(f"no mock response registered for {method} {url}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ApiAdapter:
    adapter_type = "api"

    def __init__(self, transport=None, broker: CredentialBroker | None = None):
        self._transport = transport or HttpTransport()
        self._broker = broker

    def health(self) -> dict:
        return {"status": "available", "health_status": "healthy",
                "details": {"transport": type(self._transport).__name__,
                            "ssrf_guard": "P-03 assert_url_allowed + per-hop re-validation",
                            "redirect_policy": f"max {MAX_REDIRECTS}, every hop re-validated",
                            "retry_policy": "idempotent methods only, bounded backoff"}}

    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        # Tool actions are the HTTP methods themselves (§7 seed: get/post/
        # put/patch/delete); "request" with an explicit method parameter
        # is also accepted for internal callers.
        if action not in ("get", "post", "put", "patch", "delete", "request"):
            return AdapterResult(False, error_category="ACTION_UNKNOWN",
                                 summary=f"api adapter has no action '{action}'")
        method = (str(parameters.get("method")).upper() if action == "request"
                  and parameters.get("method") else action.upper())
        url = str(parameters.get("url") or "")
        if not url:
            return AdapterResult(False, error_category="VALIDATION", summary="url is required")
        headers = {str(k): str(v) for k, v in dict(parameters.get("headers") or {}).items()}
        credential_ref = parameters.get("credential_ref")
        if credential_ref:
            if self._broker is None:
                return AdapterResult(False, error_category="ADAPTER_UNAVAILABLE",
                                     summary="no credential broker is configured")
            try:
                value = self._broker.resolve(str(credential_ref))
            except Exception as exc:
                return AdapterResult(False, error_category="CREDENTIAL_UNRESOLVED",
                                     summary=str(exc))
            if value is None:
                return AdapterResult(
                    False, error_category="CREDENTIAL_UNRESOLVED",
                    summary=f"credential reference {credential_ref} is not configured "
                            "on the server; the request was not sent")
            header_name = str(parameters.get("credential_header") or "Authorization")
            scheme = str(parameters.get("credential_scheme")
                         or ("Bearer" if header_name.lower() == "authorization" else ""))
            if header_name.lower() == "authorization" and scheme and not value.startswith(scheme):
                value = f"{scheme} {value}"
            headers[header_name] = value  # value never leaves this local scope
        body_param = parameters.get("body")
        body = body_param.encode("utf-8") if isinstance(body_param, str) else None
        allowed_hosts = list(context.settings.get("_allowed_hosts") or []) or None
        max_retries = int(parameters.get("max_retries", 2)) if method in IDEMPOTENT_METHODS else 0

        attempts = 0
        started = time.monotonic()
        last_error: Exception | None = None
        while attempts <= max_retries:
            attempts += 1
            try:
                response = await self._transport.request(
                    method, url, headers=headers, body=body, allowed_hosts=allowed_hosts)
            except (TransportError, Exception) as exc:  # noqa: BLE001 - normalized below
                last_error = exc if isinstance(exc, TransportError) else TransportError(str(exc))
                if attempts <= max_retries:
                    await asyncio.sleep(min(0.25 * (2 ** (attempts - 1)), 2.0))
                    continue
                break
            if response.status >= 500 and attempts <= max_retries:
                await asyncio.sleep(min(0.25 * (2 ** (attempts - 1)), 2.0))
                continue
            duration_ms = (time.monotonic() - started) * 1000.0
            cap = int(context.settings.get("max_output_bytes", 1_000_000))
            shown = response.body[:cap]
            success = response.status < 400
            return AdapterResult(
                success,
                output={"status": response.status, "final_url": response.url,
                        "headers": response.headers,
                        "body": shown.decode("utf-8", errors="replace"),
                        "body_truncated": response.truncated or len(response.body) > cap,
                        "redirects": response.redirects, "attempts": attempts},
                error_category=None if success else f"HTTP_{response.status}",
                summary=f"{method} {url} -> {response.status} "
                        f"({attempts} attempt(s), {len(response.body)} bytes)",
                evidence=[{"type": "api_response", "reference": response.url,
                           "content_hash": sha256_bytes(response.body),
                           "details": {"method": method, "status": response.status,
                                       "attempts": attempts,
                                       "redirects": response.redirects}}],
                resource_usage={"duration_ms": round(duration_ms, 2),
                                "response_bytes": len(response.body)})
        return AdapterResult(
            False, error_category="TRANSPORT_ERROR",
            summary=f"{method} {url} failed after {attempts} attempt(s): {last_error}",
            resource_usage={"duration_ms": round((time.monotonic() - started) * 1000.0, 2)})
