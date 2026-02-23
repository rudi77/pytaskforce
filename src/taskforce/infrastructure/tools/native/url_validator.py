"""URL validation utilities to prevent SSRF attacks.

Validates URLs before making HTTP requests to ensure they don't target
private/internal network addresses (RFC 1918, link-local, loopback,
cloud metadata endpoints, etc.).

This module is intended for use by tools that accept user-controlled URLs
(e.g., web_fetch, browser navigate).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Well-known cloud metadata endpoints that should always be blocked
_BLOCKED_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
    }
)


def validate_url_for_ssrf(url: str) -> tuple[bool, str | None]:
    """Validate a URL is safe to fetch (not targeting internal/private networks).

    Args:
        url: The URL to validate.

    Returns:
        Tuple of (is_safe, error_message). If is_safe is True, error_message is None.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, f"Invalid URL: {url}"

    if not parsed.scheme:
        return False, "URL must include a scheme (http:// or https://)"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported URL scheme: {parsed.scheme}. Only http and https are allowed."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a hostname"

    # Block well-known metadata hostnames
    if hostname.lower() in _BLOCKED_HOSTS:
        return False, f"Blocked host: {hostname} (cloud metadata endpoint)"

    # Resolve hostname to IP and check
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        # DNS resolution failed — let the actual HTTP client handle this
        return True, None

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, (
                f"URL resolves to private/reserved address {ip_str}. "
                f"Requests to internal networks are blocked for security."
            )

    return True, None
