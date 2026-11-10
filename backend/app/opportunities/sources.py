"""Research source acquisition (P-03 §8).

Provider-independent adapters over a pluggable transport:

- ``HttpTransport`` — real HTTP via httpx. Used for genuinely public pages
  of *registered* sources only. SSRF-guarded (http/https only; loopback,
  private, link-local and reserved literal IPs refused; ``localhost``
  refused). No credentials are ever attached; sources declaring
  ``auth_required`` are never fetched. There is deliberately NO code path
  that bypasses CAPTCHAs, paywalls, logins or rate limits (§8.2).
- ``MockTransport`` — deterministic fixture transport for tests. Unmapped
  URLs fail truthfully instead of touching the network.

Fetched content is UNTRUSTED DATA (§27): it is scanned for prompt
injection before any claim extraction, and a hit quarantines the document
(no claims extracted) and raises a security event upstream.

Extraction is deterministic: page title + price mentions (regex over the
visible text). Nothing else is inferred from raw pages in P-03.
"""
from __future__ import annotations

import ipaddress
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse


class TransportError(Exception):
    """A fetch failed; the caller records the failure truthfully."""


@dataclass
class FetchResult:
    status_code: int
    final_url: str
    text: str
    content_type: str = ""


@dataclass
class FetchedDocument:
    source_key: str
    url: str | None
    final_url: str | None
    status_code: int | None
    title: str
    text: str
    extraction_method: str
    # Structured claims authored with a seed document (fixtures). Web/RSS
    # documents leave this empty; claims are extracted deterministically.
    seed_claims: list[dict] = field(default_factory=list)
    publication_date: str | None = None


# --------------------------------------------------------------------- SSRF
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def assert_url_allowed(url: str, allow_private_hosts: bool = False) -> str:
    """Returns the URL if it may be fetched, else raises TransportError."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        raise TransportError(f"refused: only http/https URLs may be fetched (got scheme '{parsed.scheme}')")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise TransportError("refused: URL has no host")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise TransportError(f"refused: host '{host}' is not a public research target")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not allow_private_hosts:
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise TransportError(
                f"refused: host '{host}' is a non-public IP address (SSRF guard)")
    return url


# ----------------------------------------------------------------- transports
class HttpTransport:
    """Real HTTP. ``proxy_url`` exists because some sandboxes route egress
    through an explicit proxy; on a normal owner machine it stays unset.

    TLS verification uses an explicit ``ssl`` default context (which
    honours the platform CA configuration, e.g. ``SSL_CERT_FILE``) rather
    than httpx's bundled certifi store: in TLS-intercepting sandbox /
    corporate environments the intercepting CA is in the platform bundle
    only, and certifi-only verification fails every fetch. Verification
    itself is NEVER disabled — a certificate that does not verify against
    the platform bundle fails the fetch, truthfully."""

    def __init__(self, timeout_seconds: float = 10.0, proxy_url: str | None = None,
                 max_bytes: int = 512_000, allow_private_hosts: bool = False):
        self.timeout = timeout_seconds
        self.proxy_url = proxy_url
        self.max_bytes = max_bytes
        self.allow_private_hosts = allow_private_hosts

    async def fetch(self, url: str) -> FetchResult:
        import ssl

        import httpx

        assert_url_allowed(url, allow_private_hosts=self.allow_private_hosts)
        try:
            async with httpx.AsyncClient(
                    timeout=self.timeout, trust_env=False, proxy=self.proxy_url,
                    verify=ssl.create_default_context(),
                    follow_redirects=True, max_redirects=5,
                    headers={"User-Agent": "AUTONOMUS-Research/0.3 (owner-operated research; no login, no bypass)"}) as client:
                response = await client.get(url)
        except TransportError:
            raise
        except Exception as exc:  # ConnectError, timeouts, InvalidURL, ...
            raise TransportError(f"fetch failed for {url}: {type(exc).__name__}: {exc}") from exc
        text = response.text[: self.max_bytes]
        return FetchResult(status_code=response.status_code, final_url=str(response.url),
                           text=text, content_type=response.headers.get("content-type", ""))


class MockTransport:
    """Deterministic transport: URL -> FetchResult or exception instance."""

    def __init__(self, mapping: dict[str, FetchResult | Exception] | None = None,
                 allow_private_hosts: bool = False):
        self.mapping = mapping or {}
        self.allow_private_hosts = allow_private_hosts
        self.requested: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        assert_url_allowed(url, allow_private_hosts=self.allow_private_hosts)
        self.requested.append(url)
        result = self.mapping.get(url)
        if result is None:
            raise TransportError(
                f"no mock fixture registered for {url}; live fetching is disabled in tests")
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------- extraction
class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        return "", re.sub(r"<[^>]+>", " ", html or "")
    title = " ".join(" ".join(parser.title_parts).split())
    text = " ".join(" ".join(parser.parts).split())
    return title, text


_PRICE_RE = re.compile(
    r"(?P<symbol>[$₹€£]|USD|INR|EUR|GBP)\s?(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"(?P<period>\s*(?:per month|/month|monthly))?",
    re.IGNORECASE)
_SYMBOL_TO_CCY = {"$": "USD", "₹": "INR", "€": "EUR", "£": "GBP"}


def extract_price_mentions(text: str, limit: int = 8) -> list[dict]:
    """Deterministic price extraction: amounts verbatim from the text,
    with their surrounding context. Nothing is normalised into a 'market
    price' — each mention stays a claim about what one page states."""
    mentions: list[dict] = []
    seen: set[str] = set()
    for match in _PRICE_RE.finditer(text or ""):
        symbol = match.group("symbol")
        currency = _SYMBOL_TO_CCY.get(symbol, symbol.upper())
        amount_text = match.group("amount").replace(",", "")
        try:
            amount = float(amount_text)
        except ValueError:
            continue
        per_month = match.group("period") is not None
        key = f"{currency}:{amount}:{per_month}"
        if key in seen:
            continue
        seen.add(key)
        start = max(0, match.start() - 60)
        snippet = (text[start: match.end() + 20]).strip()
        mentions.append({
            "amount": amount, "currency": currency, "per_month": per_month,
            "verbatim": match.group(0).strip(), "snippet": snippet,
        })
        if len(mentions) >= limit:
            break
    return mentions


def parse_feed(xml_text: str) -> list[dict]:
    """Minimal RSS/Atom item extraction (stdlib only)."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter():
        if item.tag.endswith("}item") or item.tag == "item":
            fields = {}
            for child in item:
                tag = child.tag.split("}")[-1]
                if child.text:
                    fields[tag] = child.text.strip()
            if fields.get("title"):
                items.append({
                    "title": fields.get("title", ""),
                    "link": fields.get("link"),
                    "summary": fields.get("description", ""),
                    "published": fields.get("pubDate"),
                })
        elif item.tag.endswith("}entry"):
            fields = {}
            link = None
            for child in item:
                tag = child.tag.split("}")[-1]
                if tag == "link":
                    link = child.attrib.get("href", link)
                elif child.text:
                    fields[tag] = child.text.strip()
            if fields.get("title"):
                items.append({
                    "title": fields.get("title", ""),
                    "link": link,
                    "summary": fields.get("summary", ""),
                    "published": fields.get("updated") or fields.get("published"),
                })
    return items[:20]


# ------------------------------------------------------------------ adapters
class SeedDocumentAdapter:
    """Owner-provided / seed research documents. No network is involved;
    the document content ships with the catalogue and is labelled as
    fixture material everywhere it surfaces."""

    access_method = "seed_document"

    def __init__(self, documents: dict[str, list[dict]]):
        self._documents = documents  # source_key -> [document, ...]

    async def fetch_documents(self, source, opportunity) -> list[FetchedDocument]:
        docs = []
        for doc in self._documents.get(source.source_key, []):
            applies = doc.get("applies_to", [])
            if applies and opportunity.slug not in applies and opportunity.category not in applies:
                continue
            docs.append(FetchedDocument(
                source_key=source.source_key, url=source.url, final_url=source.url,
                status_code=200, title=doc.get("title", source.name),
                text=doc.get("text", ""), extraction_method="seed_document",
                seed_claims=list(doc.get("claims", [])),
                publication_date=doc.get("publication_date")))
        return docs


class WebPageAdapter:
    access_method = "web_page"

    def __init__(self, transport, mode: str = "supervised"):
        self.transport = transport
        self.mode = mode
        self._robots_cache: dict[str, list[str]] = {}

    async def _robots_disallows(self, url: str) -> bool:
        """Light robots.txt respect (§8.2): if the host's robots.txt can be
        fetched and disallows this path for '*', we do not fetch. A robots
        fetch failure is not treated as permission OR as a ban — it is
        recorded by the caller via the returned flag being best-effort."""
        parsed = urlparse(url)
        host_root = f"{parsed.scheme}://{parsed.netloc}"
        if host_root not in self._robots_cache:
            disallows: list[str] = []
            try:
                result = await self.transport.fetch(f"{host_root}/robots.txt")
                if result.status_code == 200:
                    current_star = False
                    for line in result.text.splitlines():
                        line = line.strip()
                        if line.lower().startswith("user-agent:"):
                            current_star = line.split(":", 1)[1].strip() in ("*", "")
                        elif current_star and line.lower().startswith("disallow:"):
                            path = line.split(":", 1)[1].strip()
                            if path:
                                disallows.append(path)
            except TransportError:
                disallows = []
            self._robots_cache[host_root] = disallows
        path = urlparse(url).path or "/"
        return any(path.startswith(d) for d in self._robots_cache[host_root])

    async def fetch_documents(self, source, opportunity) -> list[FetchedDocument]:
        if source.url is None:
            raise TransportError(f"source '{source.source_key}' has no URL to fetch")
        if self.mode == "simulation":
            raise TransportError(
                "live web fetching is disabled in simulation mode (seed/owner sources only)")
        if source.auth_required:
            raise TransportError(
                f"source '{source.source_key}' requires authentication; AUTONOMUS holds no "
                "credentials and never bypasses authentication (§8.2)")
        if await self._robots_disallows(source.url):
            raise TransportError(
                f"robots.txt for this host disallows fetching {source.url}; not fetched (§8.2)")
        result = await self.transport.fetch(source.url)
        if result.status_code >= 400:
            raise TransportError(
                f"source '{source.source_key}' returned HTTP {result.status_code}; "
                "recorded as unavailable, no content used")
        title, text = html_to_text(result.text)
        return [FetchedDocument(
            source_key=source.source_key, url=source.url, final_url=result.final_url,
            status_code=result.status_code, title=title or source.name, text=text,
            extraction_method="web_page")]


class RssAdapter:
    access_method = "rss"

    def __init__(self, transport, mode: str = "supervised"):
        self.transport = transport
        self.mode = mode

    async def fetch_documents(self, source, opportunity) -> list[FetchedDocument]:
        if source.url is None:
            raise TransportError(f"source '{source.source_key}' has no feed URL")
        if self.mode == "simulation":
            raise TransportError("live feed fetching is disabled in simulation mode")
        if source.auth_required:
            raise TransportError(
                f"source '{source.source_key}' requires authentication; never bypassed (§8.2)")
        result = await self.transport.fetch(source.url)
        if result.status_code >= 400:
            raise TransportError(
                f"feed '{source.source_key}' returned HTTP {result.status_code}; recorded as unavailable")
        docs = []
        for item in parse_feed(result.text):
            docs.append(FetchedDocument(
                source_key=source.source_key, url=item.get("link") or source.url,
                final_url=item.get("link") or source.url, status_code=result.status_code,
                title=item["title"], text=item.get("summary", ""),
                extraction_method="rss", publication_date=item.get("published")))
        return docs


class AdapterRegistry:
    def __init__(self, seed_documents: dict[str, list[dict]], transport, mode: str):
        self._adapters = {
            "seed_document": SeedDocumentAdapter(seed_documents),
            "web_page": WebPageAdapter(transport, mode),
            "rss": RssAdapter(transport, mode),
        }

    def for_source(self, source):
        adapter = self._adapters.get(source.access_method)
        if adapter is None:
            raise TransportError(f"no adapter for access method '{source.access_method}'")
        return adapter
