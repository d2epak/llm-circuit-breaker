"""API Error Classifier for LLM Provider Calls.

Maps HTTP status codes, exception payloads, and WAF error bodies into
structured failover actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class FailoverReason(str, Enum):
    rate_limit = "rate_limit"
    upstream_rate_limit = "upstream_rate_limit"
    billing = "billing"
    auth = "auth"
    model_not_found = "model_not_found"
    overloaded = "overloaded"
    server_error = "server_error"
    timeout = "timeout"
    ssl_cert_verification = "ssl_cert_verification"
    payload_too_large = "payload_too_large"
    waf_blocked = "waf_blocked"
    connection_refused = "connection_refused"
    unknown = "unknown"


@dataclass
class ClassifiedError:
    reason: FailoverReason
    should_fallback: bool
    retryable: bool
    status_code: Optional[int] = None
    message: str = ""


_BILLING_PATTERNS = [
    "insufficient credits",
    "credit balance",
    "billing",
    "payment required",
    "out of credits",
    "usage limit reached",
    "monthly spending cap",
]

_DEPRECATION_PATTERNS = [
    "deprecated",
    "decommissioned",
    "model does not exist",
    "not found",
    "model_not_found",
    "has been removed",
    "is no longer available",
    "is not found for api version",
]

_UPSTREAM_429_PATTERNS = [
    "temporarily rate-limited upstream",
    "upstream_provider_shared_pool",
    "provider returned error",
    "rate limit exceeded: free-models-per-day",
    "daily",
    "quota exceeded",
]

_WAF_PATTERNS = [
    "cloudflare",
    "security challenge",
    "attention required",
    "error 1010",
    "error 1015",
    "error 1020",
]

_SSL_PATTERNS = [
    "certificate verify failed",
    "self signed certificate",
    "sslcertverificationerror",
    "ssLError",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context_length_exceeded",
    "payload too large",
    "maximum context length",
    "token count exceeds limit",
    "request size exceeds",
]


def classify_api_error(error: Any, status_code: Optional[int] = None) -> ClassifiedError:
    """Classify an exception or response into a structured recovery instruction."""
    code = status_code
    if code is None and hasattr(error, "status_code"):
        code = getattr(error, "status_code")
    if code is None and hasattr(error, "code"):
        code = getattr(error, "code")
    if code is None and hasattr(error, "response") and hasattr(error.response, "status_code"):
        code = error.response.status_code

    msg = str(error).lower()
    if hasattr(error, "body") and isinstance(error.body, dict):
        msg += " " + str(error.body).lower()

    # 1. SSL / TLS Verification Failures
    if any(p in msg for p in _SSL_PATTERNS) or "ssLError" in type(error).__name__:
        return ClassifiedError(FailoverReason.ssl_cert_verification, should_fallback=True, retryable=False, status_code=code, message=msg)

    # 2. Connection Refused (e.g. Local Ollama Daemon Offline)
    if "connection refused" in msg or "errno 61" in msg or "errno 111" in msg:
        return ClassifiedError(FailoverReason.connection_refused, should_fallback=True, retryable=False, status_code=599, message=msg)

    # 3. Context Length / Payload Overflow
    if code == 413 or any(p in msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return ClassifiedError(FailoverReason.payload_too_large, should_fallback=True, retryable=False, status_code=413, message=msg)

    # 4. HTTP 402 Billing / Credits Exhaustion
    if code == 402 or any(p in msg for p in _BILLING_PATTERNS):
        return ClassifiedError(FailoverReason.billing, should_fallback=True, retryable=False, status_code=402, message=msg)

    # 5. HTTP 429 Rate Limits
    if code == 429 or "ratelimit" in type(error).__name__.lower():
        if any(p in msg for p in _UPSTREAM_429_PATTERNS):
            return ClassifiedError(FailoverReason.upstream_rate_limit, should_fallback=True, retryable=True, status_code=429, message=msg)
        return ClassifiedError(FailoverReason.rate_limit, should_fallback=True, retryable=True, status_code=429, message=msg)

    # 6. HTTP 404 / 400 Model Deprecation & Sunset
    if code in (404, 400) and any(p in msg for p in _DEPRECATION_PATTERNS):
        return ClassifiedError(FailoverReason.model_not_found, should_fallback=True, retryable=False, status_code=code, message=msg)
    if code == 404:
        return ClassifiedError(FailoverReason.model_not_found, should_fallback=True, retryable=False, status_code=404, message=msg)

    # 7. HTTP 401 / 403 Auth / Permissions / Access Denied
    if code in (401, 403) or "access denied" in msg or "forbidden" in msg or "unauthorized" in msg:
        return ClassifiedError(FailoverReason.auth, should_fallback=True, retryable=False, status_code=code or 403, message=msg)

    # 8. WAF / Cloudflare Challenge
    if any(p in msg for p in _WAF_PATTERNS):
        return ClassifiedError(FailoverReason.waf_blocked, should_fallback=True, retryable=False, status_code=code or 403, message=msg)

    # 9. HTTP 5xx Server Outage & Overload
    if code in (500, 502, 503, 504, 529) or "overloaded" in msg or "bad gateway" in msg or "gateway timeout" in msg:
        return ClassifiedError(
            FailoverReason.overloaded if code in (503, 529) or "overloaded" in msg else FailoverReason.server_error,
            should_fallback=True,
            retryable=True,
            status_code=code,
            message=msg,
        )

    # 10. Network Timeouts
    if "timeout" in msg or "timed out" in msg or "connecttimeout" in type(error).__name__.lower():
        return ClassifiedError(FailoverReason.timeout, should_fallback=True, retryable=True, status_code=code or 504, message=msg)

    return ClassifiedError(FailoverReason.unknown, should_fallback=False, retryable=True, status_code=code, message=msg)
