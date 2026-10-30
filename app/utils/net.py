"""Outbound URL validation.

Tenant admins can point an instance's AI config at any URL, and the server
then makes the request. Without a check that turns the app into an SSRF
proxy for cloud metadata (`169.254.169.254`), internal admin panels and
anything else reachable from the worker.
"""

import ipaddress
import socket
from urllib.parse import urlparse

# Ranges that must never be reachable from a tenant-supplied endpoint.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",  # carrier-grade NAT
        "127.0.0.0/8",
        "169.254.0.0/16",  # link-local, incl. cloud metadata
        "172.16.0.0/12",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


class UnsafeEndpoint(ValueError):
    """The endpoint would reach a private or non-HTTP destination."""


def _is_blocked(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in _BLOCKED_NETWORKS)


def _resolved_addresses(host: str) -> set[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        # Unresolvable hosts cannot be used to reach anything internal.
        return set()
    return {info[4][0] for info in infos}


def validate_llm_endpoint(url: str, allow_hosts: set[str] | None = None) -> str:
    """Return `url` if it is safe to call, else raise UnsafeEndpoint.

    `allow_hosts` is the set of trusted hosts (the server's own Ollama, for
    example) that may sit on a private address.
    """
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeEndpoint("endpoint must use http or https")
    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeEndpoint("endpoint has no host")

    trusted = {
        (urlparse(h).netloc.lower() if "://" in h else h.strip().lower())
        for h in (allow_hosts or set())
    }
    netloc = parsed.netloc.lower()
    if netloc in trusted or host in trusted:
        return url

    addresses = _resolved_addresses(host)
    for address in addresses:
        if _is_blocked(address):
            raise UnsafeEndpoint(
                f"endpoint host {host!r} resolves to a private address"
            )
    return url
