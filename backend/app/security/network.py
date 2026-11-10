"""Network egress policy and SSRF protection (§13), plus browser
domain validation (§12.2).

Deterministic throughout: the validator parses the URL, applies
scheme and credential rules, resolves the host through an injectable
resolver, and range-checks EVERY resolved address — the hostname
alone is never trusted (§13.2: DNS rebinding and redirect bypasses
are defeated by validating resolution, and by re-validating every
redirect hop). No model participates.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}  # cloud metadata (link-local / CGNAT Alibaba)


def default_resolver(host: str) -> list[str]:
    """Real DNS resolution. Tests inject a fake resolver so no test
    depends on the network."""
    infos = socket.getaddrinfo(host, None)
    return sorted({info[4][0] for info in infos})


def ip_block_reason(ip_text: str) -> str | None:
    """Why this resolved IP must not be reached, or None if it is a
    public address. Fails closed: an unparseable address is blocked."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return f"resolved address '{ip_text}' is not a valid IP (fail closed)"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if str(ip) in _METADATA_IPS:
        return "cloud metadata endpoint"
    if ip.is_loopback:
        return "loopback address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_private:
        return "private network address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_unspecified:
        return "unspecified address"
    return None


class EgressValidator:
    """§13.1/§13.2 outbound request validation."""

    def __init__(self, get_settings, resolver=default_resolver):
        self._get_settings = get_settings
        self._resolver = resolver

    def validate_url(self, url: str) -> dict:
        checks: list[dict] = []

        def record(name: str, passed: bool, reason: str) -> bool:
            checks.append({"check": name, "passed": passed, "reason": reason})
            return passed

        def deny(reason: str) -> dict:
            return {"allowed": False, "url": url, "reason": reason, "checks": checks}

        parsed = urlparse(url or "")
        settings = self._get_settings()
        if parsed.scheme not in ("https", "http"):
            record("scheme", False, f"scheme '{parsed.scheme or '(none)'}' is not http(s)")
            return deny(checks[-1]["reason"])
        if parsed.scheme == "http" and not settings.get("allow_http_egress", False):
            record("scheme", False, "plain HTTP egress is disabled by policy (§13.1)")
            return deny(checks[-1]["reason"])
        record("scheme", True, f"scheme '{parsed.scheme}' permitted")

        if parsed.username or parsed.password:
            record("url_credentials", False,
                   "credentials embedded in URLs are refused (§13.2)")
            return deny(checks[-1]["reason"])
        record("url_credentials", True, "no embedded credentials")

        host = (parsed.hostname or "").lower()
        if not host:
            record("host", False, "URL has no host")
            return deny(checks[-1]["reason"])

        denylist = [d.lower() for d in settings.get("egress_denylist", [])]
        allowlist = [d.lower() for d in settings.get("egress_allowlist", [])]
        if any(host == d or host.endswith("." + d) for d in denylist):
            record("domain_policy", False, f"host '{host}' is on the egress denylist")
            return deny(checks[-1]["reason"])
        if allowlist and not any(host == d or host.endswith("." + d) for d in allowlist):
            record("domain_policy", False,
                   f"host '{host}' is not on the egress allowlist (§13.1)")
            return deny(checks[-1]["reason"])
        record("domain_policy", True, "host passes domain policy")

        # A literal IP host is checked directly; a name is resolved
        # and EVERY resulting address is checked (§13.2).
        try:
            ipaddress.ip_address(host)
            addresses = [host]
        except ValueError:
            try:
                addresses = self._resolver(host)
            except Exception as exc:
                record("resolution", False,
                       f"host '{host}' could not be resolved ({type(exc).__name__}); fail closed")
                return deny(checks[-1]["reason"])
            if not addresses:
                record("resolution", False, f"host '{host}' resolved to no addresses; fail closed")
                return deny(checks[-1]["reason"])
        for address in addresses:
            reason = ip_block_reason(address)
            if reason is not None:
                record("ssrf_range_check", False,
                       f"host '{host}' resolves to {address}: {reason} (§13.2)")
                return deny(checks[-1]["reason"])
        record("ssrf_range_check", True,
               f"all resolved addresses for '{host}' are public: {addresses}")
        return {"allowed": True, "url": url, "host": host,
                "resolved": addresses,
                "reason": "egress permitted by policy", "checks": checks}

    def validate_redirect_chain(self, urls: list[str]) -> dict:
        """Every hop of a redirect chain is validated with the same
        rules (§13.2 redirect-based bypass)."""
        for hop, url in enumerate(urls):
            result = self.validate_url(url)
            if not result["allowed"]:
                return {"allowed": False, "failed_hop": hop, "url": url,
                        "reason": f"redirect hop {hop} blocked: {result['reason']}",
                        "checks": result["checks"]}
        return {"allowed": True, "hops": len(urls),
                "reason": "every redirect hop validated"}


def validate_browser_domain(url: str, allowed_domains: list[str]) -> dict:
    """§12.2 website trust for browser actions: the intended domain
    must match the session's allowlist exactly or by subdomain, over
    HTTPS, with no embedded credentials and no lookalike tricks
    (userinfo deception is rejected by construction)."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return {"allowed": False, "host": host,
                "reason": "browser actions require HTTPS (§12.2)"}
    if parsed.username or parsed.password:
        return {"allowed": False, "host": host,
                "reason": "credentials embedded in the URL (possible lookalike deception)"}
    if not host:
        return {"allowed": False, "host": host, "reason": "URL has no host"}
    for domain in allowed_domains:
        domain = domain.lower()
        if host == domain or host.endswith("." + domain):
            return {"allowed": True, "host": host, "matched_domain": domain,
                    "reason": f"host matches the session allowlist ('{domain}')"}
    return {"allowed": False, "host": host,
            "reason": f"host '{host}' is not in this browser session's allowed domains"}
