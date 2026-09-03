"""Security Hardening: SSRF Prevention, Header Sanitization, and Resource Limits."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from llm_circuit_breaker.errors import CircuitBreakerGatewayError

# Forbidden internal IP / metadata hosts (SSRF defense)
BLOCKED_HOST_PATTERNS = re.compile(
    r"^(169\.254\.\d+\.\d+|127\.\d+\.\d+\.\d+|localhost|0\.0\.0\.0|::1|metadata\.google\.internal)$",
    re.IGNORECASE,
)

# Header injection pattern (CRLF)
CRLF_PATTERN = re.compile(r"[\r\n]")


def validate_upstream_url(
    url: str,
    allowed_schemes: Tuple[str, ...] = ("https", "http", "mock"),
    allow_localhost: bool = True,  # Allowed for local testing / proxies
) -> bool:
    """
    Validates upstream endpoint URL against SSRF vulnerabilities:
    - Enforces allowed schemes.
    - Prohibits cloud metadata addresses (e.g. 169.254.169.254).
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme.lower() not in allowed_schemes:
            raise CircuitBreakerGatewayError(
                f"Security violation: Upstream URL scheme '{parsed.scheme}' is disallowed."
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise CircuitBreakerGatewayError("Security violation: Upstream URL lacks a valid hostname.")

        # Block metadata IP endpoints
        if not allow_localhost and BLOCKED_HOST_PATTERNS.match(hostname):
            raise CircuitBreakerGatewayError(
                f"Security violation: Upstream URL host '{hostname}' is blocked (SSRF defense)."
            )

        if hostname == "169.254.169.254" or hostname == "metadata.google.internal":
            raise CircuitBreakerGatewayError(
                f"Security violation: Access to cloud metadata service is prohibited."
            )

        return True
    except CircuitBreakerGatewayError:
        raise
    except Exception as e:
        raise CircuitBreakerGatewayError(f"Security violation: Malformed upstream URL '{url}': {e}")


def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Sanitize HTTP headers to prevent header injection and HTTP response splitting.
    Strips carriage return and newline characters from header names and values.
    """
    clean = {}
    for k, v in headers.items():
        clean_k = CRLF_PATTERN.sub("", str(k)).strip()
        clean_v = CRLF_PATTERN.sub("", str(v)).strip()
        if clean_k:
            clean[clean_k] = clean_v
    return clean


def enforce_payload_limit(size_bytes: int, max_allowed_bytes: int = 25_000_000) -> None:
    """Enforce maximum payload byte limit to defend against memory exhaustion attacks."""
    if size_bytes > max_allowed_bytes:
        raise CircuitBreakerGatewayError(
            f"Security violation: Request/Response size ({size_bytes} bytes) exceeds limit ({max_allowed_bytes} bytes)."
        )
