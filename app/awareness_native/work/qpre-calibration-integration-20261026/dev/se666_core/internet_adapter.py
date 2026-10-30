"""Bounded, read-only HTTPS adapter for approved public research."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass


class InternetAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class InternetResponse:
    url: str
    status: int
    content_type: str
    text: str
    bytes_read: int
    redirect_count: int = 0


_ALLOWED_CONTENT_TYPES = {
    "text/plain", "text/html", "text/markdown",
    "application/json", "application/xml", "text/xml",
}


def _public_addresses(host: str) -> set[str]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise InternetAdapterError(f"DNS resolution failed for {host}") from exc
    addresses: set[str] = {str(record[4][0]) for record in records}
    if not addresses:
        raise InternetAdapterError(f"DNS returned no addresses for {host}")
    for value in addresses:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise InternetAdapterError(f"non-public address rejected for {host}")
    return addresses


def validate_public_https_url(
    url: str,
    *,
    allowed_domains: Iterable[str],
    resolver: Callable[[str], set[str]] = _public_addresses,
) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise InternetAdapterError("only HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise InternetAdapterError("URL credentials are forbidden")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise InternetAdapterError("URL host is required")
    domains = {d.strip().rstrip(".").lower() for d in allowed_domains if d.strip()}
    if not any(host == domain or host.endswith("." + domain) for domain in domains):
        raise InternetAdapterError(f"domain is outside the approved allowlist: {host}")
    if parsed.port not in (None, 443):
        raise InternetAdapterError("only HTTPS port 443 is allowed")
    addresses = resolver(host)
    if not addresses:
        raise InternetAdapterError(f"DNS returned no addresses for {host}")
    for value in addresses:
        if not ipaddress.ip_address(value).is_global:
            raise InternetAdapterError(f"non-public address rejected for {host}")
    return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains: set[str], max_redirects: int = 3):
        self.domains = domains
        self.max_redirects = max_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        count = int(req.headers.get("X-SE6-Redirect-Count", "0")) + 1
        if count > self.max_redirects:
            raise InternetAdapterError("redirect limit exceeded")
        safe = validate_public_https_url(newurl, allowed_domains=self.domains)
        redirected = super().redirect_request(req, fp, code, msg, headers, safe)
        if redirected is not None:
            redirected.add_header("X-SE6-Redirect-Count", str(count))
        return redirected


def fetch_public_text(
    url: str,
    *,
    allowed_domains: Iterable[str],
    timeout_seconds: float = 10.0,
    max_bytes: int = 512_000,
    user_agent: str = "SE6Triad-Research/0.1",
) -> InternetResponse:
    """Perform one bounded GET. No cookies, authentication, or form writes."""
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise InternetAdapterError("timeout must be between 0 and 30 seconds")
    if max_bytes <= 0 or max_bytes > 2_000_000:
        raise InternetAdapterError("max_bytes must be between 1 and 2000000")
    domains = {d.strip().lower() for d in allowed_domains if d.strip()}
    safe_url = validate_public_https_url(url, allowed_domains=domains)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(None),
        _BoundedRedirectHandler(domains),
    )
    request = urllib.request.Request(
        safe_url,
        method="GET",
        headers={"User-Agent": user_agent, "Accept": "text/html,text/plain,application/json;q=0.9"},
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type not in _ALLOWED_CONTENT_TYPES:
                raise InternetAdapterError(f"content type rejected: {content_type}")
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise InternetAdapterError("response size limit exceeded")
            charset = response.headers.get_content_charset() or "utf-8"
            return InternetResponse(
                url=response.geturl(),
                status=int(getattr(response, "status", 200)),
                content_type=content_type,
                text=raw.decode(charset, errors="replace"),
                bytes_read=len(raw),
            )
    except InternetAdapterError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise InternetAdapterError(f"HTTPS fetch failed: {exc}") from exc


__all__ = ["InternetAdapterError", "InternetResponse", "fetch_public_text", "validate_public_https_url"]
